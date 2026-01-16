"""Job executor for running ETL pipelines."""

import json
import os
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from .dry_run import DryRunConfig, DryRunResult

from .config import (
    AssetDefinition,
    JobConfig,
    MetricsConfig,
    NotificationConfig,
    SourceConfig,
    TargetConfig,
)
from .connectors.factory import ExtractorFactory
from .logging import get_logger, update_logging_settings
from .metrics import MetricsCollector
from .plugins import PluginLoader, extract_sandbox_config
from .run_summary import (
    CostInfo,
    IngestionInfo,
    ResourceInfo,
    RunAssetInfo,
    RunErrorInfo,
    RunInfo,
    RunSummary,
    SchemaInfo,
    StorageInfo,
    TimeInfo,
    VolumeInfo,
)
from .schema_validator import SchemaValidator
from .utils import expand_env_variable
from .validator import ConnectorValidator, IncrementalStateManager
from .wal_manager import WALManager


class JobExecutor:
    """Executes a single job configuration through the complete ETL pipeline."""

    # Constants for dry-run mode (kept for backward compatibility)
    DRY_RUN_SAMPLE_MIN = 10
    DRY_RUN_SAMPLE_MAX = 50

    def __init__(
        self,
        job_config: JobConfig,
        mode: str = "self_hosted",
        dry_run: bool = False,
        dry_run_config: Optional["DryRunConfig"] = None,
        notifications: Optional[NotificationConfig] = None,
        config_path: Optional[str] = None,
    ):
        """Initialize job executor.

        Args:
            job_config: Job configuration
            mode: Execution mode (default: self_hosted)
            dry_run: If True, perform discovery and sample extraction without writing
            dry_run_config: Optional configuration for dry-run mode (sample size, timeout)
            notifications: Optional notification configuration
            config_path: Path to the job configuration file
        """
        self.job_config = job_config
        self.mode = mode
        self.dry_run = dry_run
        self.dry_run_config = dry_run_config
        self.notifications = notifications
        self.config_path = config_path
        self.tenant_id = job_config.tenant_id
        self.logger = None
        self.source_config: Optional[SourceConfig] = None
        self.target_config: Optional[TargetConfig] = None
        self.asset_definition: Optional[AssetDefinition] = None
        self.extractor: Any = None
        self.validator: Optional[SchemaValidator] = None
        self.writer: Any = None
        self.committer: Any = None
        self.state_manager: Optional[IncrementalStateManager] = None
        self.wal_manager: Optional[WALManager] = None
        self.source_tags: Optional[Dict[str, Any]] = None
        self.metrics_collector: Optional[MetricsCollector] = None
        self.run_summary: Optional[RunSummary] = None

        # Dry-run result tracking (for structured output)
        self._dry_run_result: Optional["DryRunResult"] = None

    def _setup_logging(self) -> None:
        """Set up logging for the job.

        In dry-run mode with verbose flag, DEBUG level is forced for diagnostic output.
        """
        # Dry-run verbose mode forces DEBUG level
        if self.dry_run and self.dry_run_config and self.dry_run_config.verbose:
            log_level = "DEBUG"
        else:
            log_level = (
                self.job_config.logging.level if self.job_config.logging else None
            )

        redact = self.job_config.logging.redaction if self.job_config.logging else None

        self.logger = update_logging_settings(
            level=log_level,
            redact_secrets=redact,
            tenant_id=self.job_config.tenant_id,
        )

    def _initialize_metrics(
        self, runner_metrics: Optional[MetricsConfig] = None
    ) -> None:
        """Initialize metrics collector with resolved config.

        Config precedence: job > runner > disabled

        BEHAVIOR:
        - orchestrated: HTTP server started by orchestrated.py from runner config
        - oneshot: NO HTTP server, metrics logged only
        - OTEL: exports if configured, never crashes job

        NOT YET SUPPORTED:
        - Prometheus multiprocess cleanup
        - Per-API-call / per-retry instrumentation (partial only)
        """
        from .metrics import MetricsCollector
        from .metrics_config import log_resolved_metrics_config, resolve_metrics_config

        # Get connector type
        connector_type = "unknown"
        if self.source_config:
            connector_type = self.source_config.type

        # Determine execution mode
        metrics_mode = "orchestrated" if self.mode == "orchestrated" else "oneshot"

        # Resolve config: job > runner > disabled
        effective_metrics = resolve_metrics_config(
            job_metrics=self.job_config.metrics,
            runner_metrics=runner_metrics,
            mode=metrics_mode,
        )

        # Log resolved config
        log_resolved_metrics_config(effective_metrics, metrics_mode)

        # If disabled, skip initialization
        if not effective_metrics.enabled:
            return

        # Initialize metrics collector with resolved config
        self.metrics_collector = MetricsCollector(
            job_name=self.job_config.asset or "unknown",
            tenant_id=self.tenant_id,
            connector_type=connector_type,
            mode=metrics_mode,
            config=effective_metrics,
        )
        self.metrics_collector.start()

    def _finish_metrics(self, exit_code: int) -> None:
        """Finish metrics collection with status based on exit code.

        Ensures the Prometheus gauge is reset to 0 on all exit paths.

        Args:
            exit_code: Job exit code (0=success, 1=partial, 2=failure)
        """
        if self.metrics_collector:
            status_map = {0: "success", 1: "partial", 2: "failure"}
            self.metrics_collector.finish(status_map.get(exit_code, "failure"))

    def _validate_job(self) -> int:
        """Validate job configuration.

        Returns:
            Exit code (0=success, 2=failure)
        """
        self.logger.info(
            "Starting job execution",
            extra={
                "connector_type": self.source_config.type,
                "event_type": "job_started",
            },
        )

        # Validate schema presence
        try:
            self.job_config.validate_schema_presence()
            self.logger.info(
                "Schema validation passed",
                extra={
                    "connector_type": self.source_config.type,
                    "event_type": "job_validated",
                },
            )
        except SystemExit as e:
            self.logger.error(
                "Schema validation failed",
                extra={
                    "connector_type": self.source_config.type,
                    "event_type": "job_error",
                },
            )
            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True,
                    error_message="Schema validation failed",
                    error_type="JobValidationError",
                )
            return e.code if e.code else 2

        # Validate connector and mode restrictions
        try:
            validator = ConnectorValidator()
            validator.validate_job(self.job_config, mode=self.mode)
            self.logger.info(
                "Connector validation passed",
                extra={
                    "connector_type": self.source_config.type,
                    "event_type": "job_validated",
                },
            )
        except SystemExit as e:
            self.logger.error(
                "Connector validation failed",
                extra={
                    "connector_type": self.source_config.type,
                    "event_type": "job_error",
                },
            )
            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True,
                    error_message="Connector validation failed",
                    error_type="JobValidationError",
                )
            return e.code if e.code else 2

        return 0

    def _load_asset(self) -> int:
        """Load asset definition.

        Returns:
            Exit code (0=success, 2=failure)
        """
        try:
            self.asset_definition = self.job_config._resolve_asset()

            # Validate that source.object matches asset definition's object field
            # DESIGN DECISION: One job = one asset = one source object (see docs/design/one-asset-per-job.md)
            # This invariant ensures:
            # - Clear failure semantics (one job = one failure)
            # - Per-asset governance and FinOps metadata
            # - Simple debugging and testing
            # - Scalable configuration model
            # For grouping multiple assets, use orchestration layer (Dagster) rather than multi-asset jobs.
            if self.source_config.object:
                asset_object = self.asset_definition.object
                source_object = self.source_config.object

                if source_object != asset_object:
                    self.logger.error(
                        f"Source object '{source_object}' does not match asset definition object '{asset_object}'. "
                        f"source.object must contain the same object as specified in the asset definition.",
                        extra={
                            "asset_object": asset_object,
                            "source_object": source_object,
                            "event_type": "validation_error",
                        },
                    )
                    return 2
            else:
                # If object is not specified, warn but don't fail (may be handled by connector defaults)
                self.logger.warning(
                    f"source.object not specified. Asset definition expects object: '{self.asset_definition.object}'.",
                    extra={
                        "asset_object": self.asset_definition.object,
                        "event_type": "validation_warning",
                    },
                )

            self.logger.info(
                "Asset definition loaded",
                extra={
                    "asset_name": self.asset_definition.name,
                    "asset_object": self.asset_definition.object,
                    "event_type": "asset_loaded",
                },
            )
        except Exception as e:
            self.logger.error(
                f"Failed to load asset definition: {e}",
                extra={
                    "event_type": "asset_error",
                },
            )
            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True, error_message=str(e), error_type="AssetLoadError"
                )
            return 2
        return 0

    def _initialize_state_manager(self) -> None:
        """Initialize incremental state manager if needed."""
        if self.source_config.incremental:
            state_path_str = self.source_config.incremental.get("state_path", "")
            if state_path_str:
                self.state_manager = IncrementalStateManager()
                self.logger.info(
                    "Incremental state manager initialized",
                    extra={
                        "state_path": state_path_str,
                        "event_type": "state_initialized",
                    },
                )

    def _initialize_wal_manager(self) -> None:
        """Initialize WAL manager if WAL is enabled."""
        if not self.source_config.wal or not self.source_config.wal.get(
            "enabled", False
        ):
            return

        wal_config = self.source_config.wal
        wal_base_dir = wal_config.get("base_dir", "/app/wal")
        run_id = wal_config.get("run_id")  # Optional: allow override

        # Use asset name or job name for WAL file naming
        job_name = self.job_config.asset or "default_job"

        # If run_id not explicitly provided, check for existing WAL files to resume
        if run_id is None:
            latest_wal_file = WALManager.find_latest_wal(
                job_name=job_name,
                tenant_id=self.tenant_id,
                wal_base_dir=wal_base_dir,
            )
            if latest_wal_file:
                # Extract run_id from filename (e.g., "20240101_120000.wal.json" -> "20240101_120000")
                run_id = latest_wal_file.stem.replace(".wal", "")
                self.logger.info(
                    f"Found existing WAL file, will resume: {latest_wal_file}",
                    extra={
                        "wal_file": str(latest_wal_file),
                        "run_id": run_id,
                        "event_type": "wal_resume_detected",
                    },
                )

        self.wal_manager = WALManager(
            job_name=job_name,
            tenant_id=self.tenant_id,
            wal_base_dir=wal_base_dir,
            run_id=run_id,
        )

        # Create or load WAL
        metadata = {
            "extractor_type": (
                getattr(self.extractor, "__class__", {}).__name__
                if self.extractor
                else "unknown"
            ),
            "connector_type": self.source_config.type,
        }
        self.wal_manager.create_wal(metadata=metadata)

        if self.wal_manager.is_resuming():
            self.logger.info(
                "Resuming from WAL checkpoint",
                extra={
                    "wal_file": str(self.wal_manager.wal_file),
                    "event_type": "wal_resume",
                },
            )
        else:
            self.logger.info(
                "WAL manager initialized",
                extra={
                    "wal_file": str(self.wal_manager.wal_file),
                    "event_type": "wal_initialized",
                },
            )

    def _initialize_extractor(self) -> int:
        """Initialize extractor using ExtractorFactory.

        Returns:
            Exit code (0=success, 2=failure)
        """
        try:
            self.extractor, self.source_tags = ExtractorFactory.create(
                source_config=self.source_config,
                job_config=self.job_config,
                tenant_id=self.tenant_id,
                mode=self.mode,
                asset_definition=self.asset_definition,  # Pass asset_definition for mimesis connector
            )
        except ValueError as e:
            error_msg = f"Failed to initialize extractor: {e}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            self.logger.error(
                error_msg,
                extra={
                    "event_type": "extractor_error",
                },
                exc_info=True,
            )
            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True,
                    error_message=str(e),
                    error_type="ExtractorInitError",
                )
            return 2
        except Exception as e:
            error_msg = f"Failed to initialize extractor: {e}"
            print(f"ERROR: {error_msg}", file=sys.stderr)
            if hasattr(e, "__cause__") and e.__cause__:
                print(f"  Caused by: {e.__cause__}", file=sys.stderr)
            self.logger.error(
                error_msg,
                extra={
                    "event_type": "extractor_error",
                },
                exc_info=True,
            )
            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True,
                    error_message=str(e),
                    error_type="ExtractorInitError",
                )
            return 2
        return 0

    def _initialize_validator(self) -> int:
        """Initialize schema validator.

        Returns:
            Exit code (0=success, 2=failure)
        """
        try:
            validation_mode = self.job_config.schema_validation_mode or "strict"
            self.validator = SchemaValidator(
                self.asset_definition, validation_mode=validation_mode
            )
            self.logger.info(
                "Schema validator initialized",
                extra={
                    "validation_mode": validation_mode,
                    "event_type": "validator_initialized",
                },
            )
        except Exception as e:
            self.logger.error(
                f"Failed to initialize schema validator: {e}",
                extra={
                    "event_type": "validator_error",
                },
            )
            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True,
                    error_message=str(e),
                    error_type="ValidatorInitError",
                )
            return 2
        return 0

    def _build_output_path(self) -> str:
        """Build output path following industry standards.

        Returns:
            Output base path (S3 URI)
        """
        # Extract bucket from connection config
        connection = self.target_config.connection or {}
        s3_config = connection.get("s3") or connection.get("minio", {})
        bucket_raw = s3_config.get("bucket") or connection.get("bucket")
        bucket = (
            expand_env_variable(bucket_raw)
            or os.getenv("S3_BUCKET")
            or os.getenv("MINIO_BUCKET")
        )
        if not bucket:
            raise ValueError(
                "S3 bucket must be specified in target.connection.s3.bucket, "
                "target.connection.bucket, or S3_BUCKET/MINIO_BUCKET environment variable"
            )

        # Build path following industry standards
        domain = self.asset_definition.domain or self.tenant_id or "default"
        data_product = getattr(self.asset_definition, "dataProduct", None) or "default"

        # Special handling for markdown_kv connector: use markdown_kv/{object_name} path
        if self.target_config.type == "markdown_kv":
            object_name = (
                self.asset_definition.object.lower().replace("-", "_").replace(" ", "_")
                if self.asset_definition.object
                else "default"
            )
            output_base = f"s3://{bucket}/{domain}/markdown_kv/{object_name}"
        else:
            table_name = (
                self.asset_definition.name.lower().replace("-", "_").replace(" ", "_")
            )

            if domain == self.tenant_id and data_product == "default":
                output_base = f"s3://{bucket}/{domain}/{table_name}"
            else:
                output_base = f"s3://{bucket}/{domain}/{data_product}/{table_name}"

        return output_base

    def _initialize_writer(self) -> int:
        """Initialize writer (custom, Spark, or Parquet).

        Returns:
            Exit code (0=success, 2=failure)
        """
        try:
            output_base = self._build_output_path()

            if self.target_config.custom_writer:
                self.logger.info(
                    f"Loading custom writer from: {self.target_config.custom_writer}",
                    extra={
                        "custom_writer": self.target_config.custom_writer,
                        "event_type": "custom_writer_loading",
                    },
                )

                sandbox_config, plugin_config = extract_sandbox_config(self.job_config)

                writer_class = PluginLoader.load_writer(
                    self.target_config.custom_writer,
                    mode=self.mode,
                    sandbox_config=sandbox_config,
                    plugin_config=plugin_config,
                )
                self.writer = writer_class(
                    self.asset_definition, self.target_config, output_base
                )

                self.logger.info(
                    "Custom writer initialized",
                    extra={
                        "custom_writer": self.target_config.custom_writer,
                        "output_base": output_base,
                        "event_type": "custom_writer_initialized",
                    },
                )
            else:
                # Determine engine type from target connector recipe or target config
                engine_type = None
                if self.target_config.engine:
                    engine_type = self.target_config.engine.get("type")
                else:
                    # Try to get engine type from connector recipe
                    try:
                        target_recipe = self.job_config._resolve_target_recipe()
                        default_engine = target_recipe.default_engine
                        if isinstance(default_engine, dict):
                            engine_type = default_engine.get("type")
                        elif default_engine:
                            engine_type = str(default_engine)
                    except Exception as e:
                        self.logger.debug(
                            f"Could not load target connector recipe to determine engine type: {e}",
                            extra={"event_type": "engine_type_determination_skipped"},
                        )

                validation_mode = self.job_config.schema_validation_mode or "strict"

                # Branch based on engine type
                if engine_type == "spark":
                    from .spark_writer import SparkWriter

                    self.writer = SparkWriter(
                        self.asset_definition,
                        self.target_config,
                        output_base,
                        validation_mode=validation_mode,
                    )

                    self.logger.info(
                        "Spark writer initialized",
                        extra={
                            "output_base": output_base,
                            "validation_mode": validation_mode,
                            "engine_type": "spark",
                            "event_type": "writer_initialized",
                        },
                    )
                else:
                    # Default to native Parquet writer
                    from .parquet_writer import ParquetWriter

                    self.writer = ParquetWriter(
                        self.asset_definition,
                        self.target_config,
                        output_base,
                        validation_mode=validation_mode,
                    )

                    self.logger.info(
                        "Parquet writer initialized",
                        extra={
                            "output_base": output_base,
                            "validation_mode": validation_mode,
                            "engine_type": engine_type or "native",
                            "event_type": "writer_initialized",
                        },
                    )
        except Exception as e:
            self.logger.error(
                f"Failed to initialize writer: {e}",
                extra={
                    "event_type": "writer_error",
                },
                exc_info=True,
            )
            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True, error_message=str(e), error_type="WriterInitError"
                )
            return 2
        return 0

    def _initialize_committer(self) -> None:
        """Initialize Iceberg committer if catalog is configured."""
        if self.target_config.catalog:
            try:
                from .iceberg_committer import IcebergCommitter

                self.committer = IcebergCommitter(
                    asset_definition=self.asset_definition,
                    target_config=self.target_config,
                    classification_overrides=self.job_config.classification_overrides,
                    finops=self.job_config.finops,
                    governance_overrides=self.job_config.governance_overrides,
                    source_tags=self.source_tags,
                )
                self.logger.info(
                    "Iceberg committer initialized",
                    extra={
                        "branch": self.target_config.branch,
                        "catalog": self.target_config.catalog,
                        "event_type": "committer_initialized",
                    },
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to initialize Iceberg catalog (catalog: {self.target_config.catalog}): {e}. "
                    "Will write Parquet files to S3 without Iceberg metadata.",
                    extra={
                        "event_type": "catalog_init_failed",
                        "catalog": self.target_config.catalog,
                    },
                )
                self.committer = None
        else:
            self.logger.info(
                "No catalog configured - writing Parquet files directly to S3 without Iceberg metadata",
                extra={
                    "event_type": "no_catalog_mode",
                },
            )

    def _execute_etl_pipeline(self) -> int:
        """Execute the ETL pipeline (extract, validate, write, commit).

        Returns:
            Exit code (0=success, 1=partial, 2=failure)
        """
        total_records = 0
        total_valid_records = 0
        total_files_written = 0
        file_counter = 0
        all_file_metadata = []
        has_errors = False
        validation_mode = self.job_config.schema_validation_mode or "strict"

        try:
            # Ensure table exists (only if catalog is configured)
            if self.committer:
                self.committer.ensure_table_exists()
                self.logger.info(
                    "Iceberg table ensured",
                    extra={
                        "table_name": self.asset_definition.name,
                        "event_type": "table_ensured",
                    },
                )

            # Extract, validate, and write in batches
            batch_count = 0
            self.logger.info(
                "Starting data extraction",
                extra={
                    "event_type": "extraction_started",
                },
            )

            # Mark extraction start time (covers extract + validate + write)
            if self.metrics_collector:
                self.metrics_collector.start_extraction()

            # Prepare checkpoint context for extractor
            checkpoint_context = None
            if self.wal_manager:
                stream_name = self.source_config.object or "default"
                checkpoint = self.wal_manager.get_resume_point(stream_name)
                checkpoint_context = {
                    "checkpoint": checkpoint,
                    "wal_manager": self.wal_manager,
                    "stream_name": stream_name,
                }

            for batch_records in self.extractor.extract(
                state_manager=self.state_manager,
                checkpoint_context=checkpoint_context,
            ):
                batch_count += 1
                total_records += len(batch_records)

                # Transform to Markdown-KV format if configured
                batch_records = self._transform_markdown_kv(batch_records)

                self.logger.info(
                    f"Processing batch {batch_count}: {len(batch_records)} records extracted",
                    extra={
                        "batch_number": batch_count,
                        "records_in_batch": len(batch_records),
                        "event_type": "batch_extracted",
                    },
                )

                # Validate batch
                valid_records, validation_errors = self.validator.validate_batch(
                    batch_records
                )
                total_valid_records += len(valid_records)

                # Log validation results
                if len(valid_records) < len(batch_records):
                    self.logger.warning(
                        f"Validation filtered records: {len(valid_records)}/{len(batch_records)} passed validation",
                        extra={
                            "batch_number": batch_count,
                            "total_records": len(batch_records),
                            "valid_records": len(valid_records),
                            "filtered_records": len(batch_records) - len(valid_records),
                            "event_type": "validation_filtered",
                        },
                    )

                # Log validation errors if any
                if validation_errors:
                    has_errors = True
                    error_summary = self.validator.get_error_summary()
                    self.logger.warning(
                        f"Validation errors in batch: {error_summary['total_errors']} errors",
                        extra={
                            "error_summary": error_summary,
                            "event_type": "validation_errors",
                        },
                    )

                    # In strict mode, fail if there are errors
                    if validation_mode == "strict" and len(valid_records) < len(
                        batch_records
                    ):
                        self.logger.error(
                            f"Strict validation mode: failing due to validation errors for job '{self.job_config.asset}'",
                            extra={
                                "event_type": "validation_failed",
                                "job_name": self.job_config.asset,
                                "error_summary": error_summary,
                            },
                        )
                        return 2

                # Write valid records to Parquet
                if valid_records:
                    file_metadata = self.writer.write_batch(valid_records, file_counter)
                    all_file_metadata.extend(file_metadata)
                    total_files_written += len(file_metadata)
                    file_counter += len(file_metadata)

                    self.logger.info(
                        f"Wrote batch: {len(valid_records)} records, {len(file_metadata)} files",
                        extra={
                            "records": len(valid_records),
                            "files": len(file_metadata),
                            "event_type": "batch_written",
                        },
                    )

                    # Update WAL checkpoint after successful batch write
                    # Only update if extractor hasn't already updated with a specific checkpoint type
                    # Extractors update checkpoints with types like: chunk_based, offset_based,
                    # spreadsheet_based, state_based. We only use batch_based as a fallback for
                    # extractors that don't implement checkpoint updates.
                    if self.wal_manager and checkpoint_context:
                        stream_name = checkpoint_context["stream_name"]
                        current_checkpoint = self.wal_manager.get_checkpoint(
                            stream_name
                        )

                        # Only update if checkpoint doesn't exist or is already batch_based
                        # (meaning extractor hasn't updated it with a specific type)
                        should_update = (
                            current_checkpoint is None
                            or current_checkpoint.get("type") == "batch_based"
                        )

                        if should_update:
                            checkpoint_data = {
                                "type": "batch_based",
                                "last_batch": batch_count,
                                "records_processed": total_valid_records,
                            }
                            self.wal_manager.update_checkpoint(
                                stream_name, checkpoint_data
                            )
                        else:
                            # Extractor has already updated checkpoint with specific type
                            # Log for debugging but don't overwrite
                            self.logger.debug(
                                f"Skipping batch_based checkpoint update - extractor already updated with type: {current_checkpoint.get('type')}",
                                extra={
                                    "stream_name": stream_name,
                                    "extractor_checkpoint_type": current_checkpoint.get(
                                        "type"
                                    ),
                                    "event_type": "checkpoint_skipped_extractor_updated",
                                },
                            )
                else:
                    self.logger.warning(
                        f"Batch {batch_count} had no valid records to write",
                        extra={
                            "batch_number": batch_count,
                            "total_records_in_batch": len(batch_records),
                            "valid_records": len(valid_records),
                            "event_type": "batch_no_valid_records",
                        },
                    )

            # Mark extraction end time (after all batches processed)
            if self.metrics_collector:
                self.metrics_collector.end_extraction()

            # Log extraction summary
            if batch_count == 0:
                self.logger.warning(
                    "No batches extracted from source - check file paths, incremental state, or source configuration",
                    extra={
                        "event_type": "no_batches_extracted",
                        "total_records": total_records,
                    },
                )
            else:
                self.logger.info(
                    f"Extraction complete: {batch_count} batches, {total_records} total records extracted",
                    extra={
                        "total_batches": batch_count,
                        "total_records": total_records,
                        "total_valid_records": total_valid_records,
                        "event_type": "extraction_complete",
                    },
                )

            # Record extraction and validation metrics using new API
            if self.metrics_collector:
                self.metrics_collector.record_records(total_records, phase="extracted")
                self.metrics_collector.record_records(
                    total_valid_records, phase="written"
                )
                self.metrics_collector.record_records(
                    total_records - total_valid_records, phase="invalid"
                )

            # Mark load/commit start time
            if self.metrics_collector:
                self.metrics_collector.start_load()

            # Finalize WAL before committing (on successful extraction)
            if self.wal_manager:
                self.wal_manager.finalize_wal()
                self.logger.info(
                    "WAL finalized before commit",
                    extra={"event_type": "wal_finalized"},
                )

            # Commit all files
            exit_code = self._commit_files(
                all_file_metadata,
                total_records,
                total_valid_records,
                total_files_written,
                has_errors,
                validation_mode,
                batch_count,
            )

            # Mark load/commit end time
            if self.metrics_collector:
                self.metrics_collector.end_load()

            # Cleanup WAL after successful commit
            if exit_code == 0 and self.wal_manager:
                self.wal_manager.cleanup_wal()
                self.logger.info(
                    "WAL cleaned up after successful commit",
                    extra={"event_type": "wal_cleaned"},
                )

            return exit_code

        except Exception as e:
            self.logger.error(
                f"ETL pipeline execution failed: {e}",
                extra={
                    "event_type": "etl_error",
                },
                exc_info=True,
            )

            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True, error_message=str(e), error_type=type(e).__name__
                )

            # Record failure metrics
            if self.metrics_collector:
                self.metrics_collector.finish("failure")

            return 2

    def _transform_markdown_kv(
        self, batch_records: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Transform records to Markdown-KV format if configured.

        Args:
            batch_records: List of records to transform

        Returns:
            Transformed records
        """
        # Check if markdown_kv transformation should be applied
        if not self.target_config.markdown_kv_storage:
            # If target is markdown_kv but markdown_kv_storage is not configured, warn
            if self.target_config.type == "markdown_kv":
                self.logger.warning(
                    "markdown_kv target connector detected but markdown_kv_storage is not configured. "
                    "Transformation will be skipped. Please configure 'target.markdown_kv_storage.mode' "
                    "in your job configuration.",
                    extra={"event_type": "markdown_kv_config_missing"},
                )
            return batch_records

        from .markdown_kv import parse_markdown_kv, transform_to_markdown_kv

        mode = self.target_config.markdown_kv_storage.get("mode")
        if not mode:
            self.logger.warning(
                "markdown_kv_storage is configured but 'mode' is missing. "
                "Transformation will be skipped. Please set 'target.markdown_kv_storage.mode' "
                "to one of: 'string', 'raw_file', 'structured'.",
                extra={"event_type": "markdown_kv_mode_missing"},
            )
            return batch_records
        transformed_records = []

        for record in batch_records:
            if mode == "string":
                doc_id = str(
                    record.get("emp_id")
                    or record.get("businessentityid")
                    or record.get("productid")
                    or record.get("customerid")
                    or record.get("salesorderid")
                    or record.get("addressid")
                    or record.get("productcategoryid")
                    or record.get("id")
                    or record.get("doc_id")
                    or "unknown"
                )

                markdown_kv_content = transform_to_markdown_kv(
                    record, format="compact", doc_id=doc_id
                )

                transformed_records.append(
                    {
                        "doc_id": doc_id,
                        "markdown_kv_content": markdown_kv_content,
                    }
                )

            elif mode == "structured":
                doc_id = str(
                    record.get("emp_id")
                    or record.get("businessentityid")
                    or record.get("productid")
                    or record.get("customerid")
                    or record.get("salesorderid")
                    or record.get("addressid")
                    or record.get("productcategoryid")
                    or record.get("id")
                    or record.get("doc_id")
                    or "unknown"
                )

                markdown_kv_content = transform_to_markdown_kv(
                    record, format="compact", doc_id=doc_id
                )

                structured_pattern = self.target_config.markdown_kv_storage.get(
                    "structured_pattern", "row_per_kv"
                )
                structured_rows = parse_markdown_kv(
                    markdown_kv_content,
                    doc_id=doc_id,
                    pattern=structured_pattern,
                )

                if isinstance(structured_rows, list):
                    transformed_records.extend(structured_rows)
                else:
                    transformed_records.append(structured_rows)

            else:
                transformed_records.append(record)

        return transformed_records

    def _commit_files(
        self,
        all_file_metadata: List[Dict[str, Any]],
        total_records: int,
        total_valid_records: int,
        total_files_written: int,
        has_errors: bool,
        validation_mode: str,
        batch_count: int,
    ) -> int:
        """Commit files to catalog or upload to S3.

        Args:
            all_file_metadata: List of file metadata
            total_records: Total records extracted
            total_valid_records: Total valid records
            total_files_written: Total files written
            has_errors: Whether validation errors occurred
            validation_mode: Validation mode
            batch_count: Total number of batches processed

        Returns:
            Exit code (0=success, 1=partial, 2=failure)
        """
        if self.run_summary:
            self.run_summary.volume.records_extracted = total_records
            self.run_summary.volume.records_written = total_valid_records
            self.run_summary.volume.records_invalid = (
                total_records - total_valid_records
            )
            self.run_summary.volume.files_written = total_files_written

            if has_errors:
                self.run_summary.ingestion.error = RunErrorInfo(has_errors=True)
                if self.validator:
                    self.run_summary.ingestion.error.error_summary = (
                        self.validator.get_error_summary()
                    )

        if all_file_metadata:
            # Check if writer has custom commit_files method
            if self.target_config.custom_writer and hasattr(
                self.writer, "commit_files"
            ):
                try:
                    commit_result = self.writer.commit_files(all_file_metadata)
                    self.logger.info(
                        "Files committed using custom writer",
                        extra={
                            "files_added": commit_result.get(
                                "files_added", len(all_file_metadata)
                            ),
                            "status": commit_result.get("status"),
                            "event_type": "custom_writer_commit_success",
                        },
                    )
                    if self.run_summary:
                        self.run_summary.storage.files_added = commit_result.get(
                            "files_added", len(all_file_metadata)
                        )
                        self.run_summary.storage.partition_stats = commit_result.get(
                            "partition_stats"
                        )
                except Exception as e:
                    self.logger.error(
                        f"Failed to commit files using custom writer: {e}",
                        extra={
                            "event_type": "custom_writer_commit_failed",
                        },
                    )
                    if self.run_summary:
                        # Preserve existing error info (e.g., validation errors)
                        existing_error = self.run_summary.ingestion.error
                        existing_summary = (
                            existing_error.error_summary if existing_error else None
                        )
                        existing_message = (
                            existing_error.error_message if existing_error else None
                        )

                        # Merge error messages if both exist
                        if existing_message:
                            error_message = f"{existing_message}; CommitError: {str(e)}"
                        else:
                            error_message = str(e)

                        self.run_summary.ingestion.error = RunErrorInfo(
                            has_errors=True,
                            error_message=error_message,
                            error_type="CommitError",
                            error_summary=existing_summary,
                        )
                    return 2
            elif self.committer:
                try:
                    commit_result = self.committer.commit_files(all_file_metadata)
                    self.logger.info(
                        "Files committed to Iceberg catalog",
                        extra={
                            "commit_id": commit_result.get("commit_id"),
                            "files_added": commit_result.get("files_added"),
                            "table_name": commit_result.get("table_name"),
                            "branch": commit_result.get("branch"),
                            "event_type": "commit_success",
                        },
                    )
                    if self.run_summary:
                        self.run_summary.storage.commit_id = commit_result.get(
                            "commit_id"
                        )
                        self.run_summary.storage.files_added = commit_result.get(
                            "files_added"
                        )
                        self.run_summary.storage.branch = commit_result.get("branch")
                        self.run_summary.storage.partition_stats = commit_result.get(
                            "summary"
                        )
                except Exception as e:
                    self.logger.warning(
                        f"Failed to commit files to Iceberg catalog: {e}. "
                        "Files were uploaded to S3 but not registered in catalog.",
                        extra={
                            "event_type": "commit_failed",
                            "files_uploaded": len(all_file_metadata),
                        },
                    )
                    if self.run_summary:
                        # Preserve existing error info (e.g., validation errors)
                        existing_error = self.run_summary.ingestion.error
                        existing_summary = (
                            existing_error.error_summary if existing_error else None
                        )
                        existing_message = (
                            existing_error.error_message if existing_error else None
                        )

                        # Merge error messages if both exist
                        commit_error_msg = f"Iceberg commit failed: {str(e)}"
                        if existing_message:
                            error_message = f"{existing_message}; {commit_error_msg}"
                        else:
                            error_message = commit_error_msg

                        self.run_summary.ingestion.error = RunErrorInfo(
                            has_errors=True,
                            error_message=error_message,
                            error_type="IcebergCommitError",
                            error_summary=existing_summary,
                        )
            else:
                # No catalog and no custom writer - still need to upload files to S3/MinIO
                from .iceberg_committer import IcebergCommitter

                upload_committer = IcebergCommitter(
                    asset_definition=self.asset_definition,
                    target_config=self.target_config,
                    classification_overrides=self.job_config.classification_overrides,
                    finops=self.job_config.finops,
                    governance_overrides=self.job_config.governance_overrides,
                    source_tags=self.source_tags,
                )
                try:
                    upload_result = upload_committer.commit_files(all_file_metadata)
                    self.logger.info(
                        f"Files uploaded to S3 (no catalog configured): {upload_result.get('files_added', len(all_file_metadata))} file(s)",
                        extra={
                            "files_written": upload_result.get(
                                "files_added", len(all_file_metadata)
                            ),
                            "file_paths": upload_result.get("file_paths", []),
                            "event_type": "files_written_no_catalog",
                        },
                    )
                    if self.run_summary:
                        self.run_summary.storage.files_added = upload_result.get(
                            "files_added", len(all_file_metadata)
                        )
                except Exception as e:
                    self.logger.error(
                        f"Failed to upload files to S3: {e}",
                        extra={
                            "event_type": "upload_failed",
                        },
                    )
                    if self.run_summary:
                        # Preserve existing error info (e.g., validation errors)
                        existing_error = self.run_summary.ingestion.error
                        existing_summary = (
                            existing_error.error_summary if existing_error else None
                        )
                        existing_message = (
                            existing_error.error_message if existing_error else None
                        )

                        # Merge error messages if both exist
                        if existing_message:
                            error_message = f"{existing_message}; UploadError: {str(e)}"
                        else:
                            error_message = str(e)

                        self.run_summary.ingestion.error = RunErrorInfo(
                            has_errors=True,
                            error_message=error_message,
                            error_type="UploadError",
                            error_summary=existing_summary,
                        )
                    return 2
        else:
            self.logger.warning(
                "No files to commit",
                extra={
                    "event_type": "no_files",
                    "total_records_extracted": total_records,
                    "total_valid_records": total_valid_records,
                    "total_batches": batch_count,
                    "total_files_written": total_files_written,
                },
            )

        # Determine exit code
        # Check for commit failure first (files uploaded but catalog registration failed)
        commit_failed = (
            self.run_summary
            and self.run_summary.ingestion.error
            and self.run_summary.ingestion.error.has_errors
            and self.run_summary.ingestion.error.error_type == "IcebergCommitError"
        )

        if total_valid_records == 0:
            exit_code = 2  # Failure - no valid records
        elif commit_failed:
            exit_code = 1  # Partial failure - files uploaded but catalog commit failed
        elif has_errors and validation_mode == "warn":
            exit_code = 1  # Partial success
        else:
            exit_code = 0  # Success

        # Calculate total bytes written
        total_bytes = (
            sum(file_meta.get("size_bytes", 0) for file_meta in all_file_metadata)
            if all_file_metadata
            else 0
        )

        if self.run_summary:
            self.run_summary.volume.bytes_written = total_bytes

        # Record writing metrics using new API
        if self.metrics_collector:
            self.metrics_collector.record_bytes(
                total_bytes, phase="written"
            )  # bytes_total{phase=written}

        # Emit enhanced metadata
        self.logger.info(
            "Job execution completed",
            extra={
                "total_records": total_records,
                "valid_records": total_valid_records,
                "files_written": total_files_written,
                "total_bytes": total_bytes,
                "exit_code": exit_code,
                "event_type": "job_finished",
                "metadata": {
                    "records_extracted": total_records,
                    "records_valid": total_valid_records,
                    "records_invalid": total_records - total_valid_records,
                    "files_written": total_files_written,
                    "total_bytes": total_bytes,
                    "validation_mode": validation_mode,
                    "has_errors": has_errors,
                },
            },
        )

        return exit_code

    def _write_run_summary(self, exit_code: Optional[int] = None) -> Optional[Path]:
        """Write run summary to file.
        
        Returns:
            Path to the written summary file, or None if failed/skipped.
        """
        if not self.run_summary:
            return None

        try:
            # Finalize summary
            self.run_summary.run.end_time = datetime.now(timezone.utc)
            if self.run_summary.run.start_time:
                duration = (
                    self.run_summary.run.end_time - self.run_summary.run.start_time
                ).total_seconds()
                self.run_summary.ingestion.duration_seconds = duration

            self.run_summary.ingestion.exit_code = exit_code

            if exit_code == 0:
                self.run_summary.ingestion.status = "success"
            elif exit_code == 1:
                self.run_summary.ingestion.status = "partial"
            elif exit_code == 2:
                self.run_summary.ingestion.status = "failure"
            else:
                self.run_summary.ingestion.status = "unknown"

            # Capture watermark if state manager is available
            if self.state_manager and self.source_config.incremental:
                state_path_str = self.source_config.incremental.get("state_path", "")
                if state_path_str:
                    try:
                        # Use the static method directly since self.state_manager is an instance of IncrementalStateManager
                        # but the methods are static on the class
                        state = IncrementalStateManager.read_state(Path(state_path_str))
                        self.run_summary.time.watermark = state
                    except Exception as e:
                        self.logger.warning(
                            f"Failed to read state for summary: {e}",
                            extra={"event_type": "run_summary_state_read_error"},
                        )

            # Capture resource usage (placeholders for now)
            self.run_summary.resources = ResourceInfo(
                cpu_seconds=None,  # Requires OS-level metrics
                memory_mb=None,  # Requires OS-level metrics
                api_calls=None,  # Requires API instrumentation
            )

            # Determine path
            # state/<tenant>/<job>/runs/run-<timestamp>.json
            # Use local state dir if configured, otherwise default to .local/state
            state_dir = os.getenv("STATE_DIR", ".local/state")
            if not os.path.isabs(state_dir):
                state_dir = os.path.abspath(state_dir)

            job_name = self.job_config.asset or "unknown-job"
            # Use run.id directly to ensure filename matches the run_id in the JSON
            run_timestamp = self.run_summary.run.id

            # Sanitize names for path
            tenant_safe = self.tenant_id.replace("/", "_")
            job_safe = job_name.replace("/", "_")

            summary_dir = Path(state_dir) / tenant_safe / job_safe / "runs"
            summary_dir.mkdir(parents=True, exist_ok=True)

            summary_file = summary_dir / f"run-{run_timestamp}.json"

            # Write to file
            with open(summary_file, "w") as f:
                f.write(self.run_summary.model_dump_json(indent=2, by_alias=True))

            self.logger.info(
                f"Run summary written to {summary_file}",
                extra={
                    "summary_file": str(summary_file),
                    "event_type": "run_summary_written",
                },
            )
            return summary_file

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Failed to write run summary: {e}",
                    extra={"event_type": "run_summary_error"},
                    exc_info=True,
                )
            else:
                print(f"ERROR: Failed to write run summary: {e}", file=sys.stderr)
            return None

    def _execute_dry_run(self) -> int:
        """Execute dry-run mode: discovery, schema negotiation, and sample extraction.

        Performs:
        - Discovery and schema negotiation (inline phase tracking)
        - Fetches sample rows from source (inline phase tracking)
        - Validates data against schema (inline phase tracking)
        - Does NOT write to Iceberg or object storage

        Safety guarantees:
        - Never writes to storage
        - Never updates incremental state
        - Never commits transactions

        Returns:
            Exit code (0=success, 1=general failure, 2=usage/validation error)
        """
        from .dry_run import (
            PHASE_DISCOVERY,
            PHASE_SAMPLE_FETCH,
            PHASE_SAMPLE_VALIDATION,
            PHASE_SCHEMA_NEGOTIATION,
            DryRunConfig,
            DryRunResult,
            format_dry_run_output,
        )

        # Initialize configuration
        config = self.dry_run_config or DryRunConfig()
        sample_limit = config.sample_size
        verbose = config.verbose
        json_output = config.json_output
        timeout_seconds = config.timeout_seconds

        # Initialize result with flattened structure
        result = DryRunResult()
        result.source_connector = (
            self.source_config.type if self.source_config else None
        )
        result.target_connector = (
            self.target_config.type if self.target_config else None
        )
        result.asset_name = (
            self.asset_definition.name if self.asset_definition else None
        )

        # Add clamping warning if sample size was adjusted
        if config.was_sample_size_clamped:
            result.add_warning(config.clamping_warning)

        # Store result for potential external access
        self._dry_run_result = result

        sample_records = []
        valid_records_list = []
        dry_run_start_time = time.perf_counter()
        current_phase = None

        # Helper function to check timeout
        def check_timeout(phase_name: str) -> None:
            """Check if timeout has been exceeded and raise TimeoutError if so.

            Args:
                phase_name: Name of the current phase for error message

            Raises:
                TimeoutError: If elapsed time exceeds timeout_seconds
            """
            elapsed = time.perf_counter() - dry_run_start_time
            if elapsed >= timeout_seconds:
                raise TimeoutError(
                    f"Dry-run timeout exceeded ({timeout_seconds}s) during {phase_name}. "
                    f"Elapsed: {elapsed:.2f}s"
                )

        # Log dry-run start
        self.logger.debug(
            f"DRY-RUN MODE: Starting (sample_size={sample_limit}, timeout={timeout_seconds}s)",
            extra={
                "event_type": "dry_run_started",
                "sample_size": sample_limit,
                "timeout_seconds": timeout_seconds,
            },
        )

        try:
            # Phase 1: Discovery
            check_timeout("discovery")
            current_phase = PHASE_DISCOVERY
            phase_start = time.perf_counter()
            try:
                self.logger.debug(
                    f"Phase: {PHASE_DISCOVERY}",
                    extra={"event_type": "dry_run_phase", "phase": PHASE_DISCOVERY},
                )

                # Discovery: inspect asset schema
                if self.asset_definition:
                    schema_fields = self.asset_definition.schema
                    self.logger.debug(
                        f"Asset schema defines {len(schema_fields)} field(s)",
                        extra={
                            "event_type": "dry_run_schema_info",
                            "field_count": len(schema_fields),
                        },
                    )

                duration = time.perf_counter() - phase_start
                result.record_phase(PHASE_DISCOVERY, duration_seconds=duration)

            except Exception as e:
                result.record_phase(PHASE_DISCOVERY, error=str(e))
                result.add_error(f"Discovery failed: {e}")
                raise

            # Phase 2: Schema Negotiation
            check_timeout("schema_negotiation")
            current_phase = PHASE_SCHEMA_NEGOTIATION
            phase_start = time.perf_counter()
            try:
                self.logger.debug(
                    f"Phase: {PHASE_SCHEMA_NEGOTIATION}",
                    extra={
                        "event_type": "dry_run_phase",
                        "phase": PHASE_SCHEMA_NEGOTIATION,
                    },
                )

                # Schema negotiation is implicit when asset schema is present
                if not self.asset_definition:
                    result.add_warning(
                        "No asset definition loaded; schema validation skipped"
                    )

                duration = time.perf_counter() - phase_start
                result.record_phase(PHASE_SCHEMA_NEGOTIATION, duration_seconds=duration)

            except Exception as e:
                result.record_phase(PHASE_SCHEMA_NEGOTIATION, error=str(e))
                result.add_error(f"Schema negotiation failed: {e}")
                raise

            # Phase 3: Sample Fetch
            check_timeout("sample_fetch")
            current_phase = PHASE_SAMPLE_FETCH
            phase_start = time.perf_counter()
            try:
                self.logger.debug(
                    f"Phase: {PHASE_SAMPLE_FETCH} (limit={sample_limit})",
                    extra={
                        "event_type": "dry_run_phase",
                        "phase": PHASE_SAMPLE_FETCH,
                        "limit": sample_limit,
                    },
                )

                batch_count = 0
                total_fetched = 0

                # SAFETY: Explicitly pass None for state_manager and checkpoint_context
                # to prevent any state updates during dry-run
                for batch_records in self.extractor.extract(
                    state_manager=None,  # SAFETY: Don't use state manager in dry-run
                    checkpoint_context=None,  # SAFETY: Don't use checkpoints in dry-run
                ):
                    # Check timeout after each batch to prevent hanging on slow sources
                    check_timeout("sample_fetch")

                    batch_count += 1
                    sample_records.extend(batch_records)
                    total_fetched = len(sample_records)

                    self.logger.debug(
                        f"Batch {batch_count}: {len(batch_records)} records (total: {total_fetched})",
                        extra={
                            "event_type": "dry_run_batch",
                            "batch": batch_count,
                            "batch_size": len(batch_records),
                            "total": total_fetched,
                        },
                    )

                    # Stop after collecting enough samples
                    if total_fetched >= sample_limit:
                        sample_records = sample_records[:sample_limit]
                        break

                result.sample_size = len(sample_records)

                if not sample_records:
                    result.add_warning("No records extracted from source")

                duration = time.perf_counter() - phase_start
                result.record_phase(PHASE_SAMPLE_FETCH, duration_seconds=duration)

            except Exception as e:
                result.record_phase(PHASE_SAMPLE_FETCH, error=str(e))
                result.add_error(f"Sample fetch failed: {e}")
                raise

            # Phase 4: Sample Validation
            check_timeout("sample_validation")
            current_phase = PHASE_SAMPLE_VALIDATION
            phase_start = time.perf_counter()
            try:
                self.logger.debug(
                    f"Phase: {PHASE_SAMPLE_VALIDATION}",
                    extra={
                        "event_type": "dry_run_phase",
                        "phase": PHASE_SAMPLE_VALIDATION,
                    },
                )

                validation_passed = True

                if sample_records and self.validator:
                    valid_records_list, validation_errors = (
                        self.validator.validate_batch(sample_records)
                    )

                    result.valid_records = len(valid_records_list)
                    result.invalid_records = len(sample_records) - len(
                        valid_records_list
                    )

                    validation_passed = result.invalid_records == 0

                    self.logger.debug(
                        f"Validation: {result.valid_records}/{len(sample_records)} valid",
                        extra={
                            "event_type": "dry_run_validation",
                            "valid": result.valid_records,
                            "invalid": result.invalid_records,
                        },
                    )

                    if not validation_passed:
                        validation_mode = (
                            self.job_config.schema_validation_mode or "strict"
                        )
                        if validation_mode == "strict":
                            result.add_error(
                                f"Data contract validation failed: {result.invalid_records} invalid records"
                            )
                        else:
                            result.add_warning(
                                f"Validation warnings: {result.invalid_records} invalid records"
                            )
                else:
                    result.valid_records = len(sample_records)
                    result.invalid_records = 0

                duration = time.perf_counter() - phase_start
                result.record_phase(PHASE_SAMPLE_VALIDATION, duration_seconds=duration)

            except Exception as e:
                result.record_phase(PHASE_SAMPLE_VALIDATION, error=str(e))
                result.add_error(f"Sample validation failed: {e}")
                raise

            # Calculate total duration
            result.dry_run_duration_seconds = time.perf_counter() - dry_run_start_time

            # Determine exit code based on errors and warnings
            # 0 = success, 1 = general failure (e.g., validation in warn mode), 2 = validation/usage error
            validation_mode = self.job_config.schema_validation_mode or "strict"

            # Check for validation warnings in warn mode first
            # (warnings are added instead of errors in warn mode)
            if (
                validation_mode == "warn"
                and result.warnings
                and any("validation" in w.lower() for w in result.warnings)
            ):
                # Validation warnings in warn mode: exit 1 (general failure)
                result.valid = True
                result.exit_code = 1
            elif not result.errors:
                result.valid = True
                result.exit_code = 0
            elif validation_mode == "warn" and all(
                "validation" in e.lower() for e in result.errors
            ):
                # Validation errors in warn mode: exit 1 (general failure)
                result.valid = True
                result.exit_code = 1
            else:
                result.valid = False
                result.exit_code = 2

            # Output result (always valid JSON when --json)
            if json_output:
                print(result.to_json())
            else:
                output = format_dry_run_output(
                    result, json_output=False, verbose=verbose
                )
                print(output)

            return result.exit_code

        except Exception as e:
            # Catch-all: ensure we always output valid JSON when requested
            result.dry_run_duration_seconds = time.perf_counter() - dry_run_start_time

            if current_phase and current_phase not in [
                p["name"] for p in result.phases
            ]:
                # Record the failed phase if not already recorded
                result.record_phase(current_phase, error=str(e))

            if f"Unexpected error: {e}" not in result.errors:
                result.add_error(f"Unexpected error: {e}")

            result.valid = False
            result.exit_code = 2

            if json_output:
                # Always output valid JSON, even on error
                print(result.to_json())
            else:
                self.logger.error(
                    f"Dry-run failed: {e}",
                    extra={"event_type": "dry_run_error"},
                    exc_info=True,
                )
                output = format_dry_run_output(
                    result, json_output=False, verbose=verbose
                )
                print(output)

            return 2

    def _push_to_catalog(self) -> None:
        """Push lineage and metadata to catalog if configured."""
        if not self.job_config.catalog:
            return

        try:
            from .catalog import CatalogFactory

            catalog = CatalogFactory.create(
                self.job_config.catalog, self.asset_definition, self.job_config
            )

            # Ensure target entity exists
            target_entity = catalog._extract_target_entity()
            catalog.ensure_entity_exists(
                target_entity, schema=self.asset_definition.schema
            )

            # Push metadata if enabled
            if self.job_config.catalog.push_metadata:
                tags = catalog._extract_tags()
                owners = catalog._extract_owners()
                description = catalog._extract_description()

                metadata_result = catalog.push_metadata(
                    target_entity,
                    tags=tags,
                    owners=owners,
                    description=description,
                    custom_properties={
                        "source_type": self.asset_definition.source_type,
                        "asset_version": str(self.asset_definition.version),
                        "tenant_id": self.job_config.tenant_id,
                    },
                )
                self.logger.info(
                    "Catalog metadata pushed",
                    extra={
                        "catalog_type": self.job_config.catalog.type,
                        "status": metadata_result.get("status"),
                        "event_type": "catalog_metadata_pushed",
                    },
                )

            # Push lineage if enabled
            if self.job_config.catalog.push_lineage:
                source_entities = catalog._extract_source_entities()
                lineage_result = catalog.push_lineage(
                    source_entities, target_entity, operation="ingest"
                )
                self.logger.info(
                    "Catalog lineage pushed",
                    extra={
                        "catalog_type": self.job_config.catalog.type,
                        "status": lineage_result.get("status"),
                        "sources_count": len(source_entities),
                        "event_type": "catalog_lineage_pushed",
                    },
                )
        except Exception as e:
            self.logger.warning(
                f"Failed to push to catalog: {e}",
                extra={
                    "catalog_type": (
                        self.job_config.catalog.type
                        if self.job_config.catalog
                        else None
                    ),
                    "event_type": "catalog_push_failed",
                },
                exc_info=True,
            )
            # Don't fail the job if catalog push fails

    def _execute_notification_hook(self, summary_path: Path) -> None:
        """Execute notification hook if configured and job failed."""
        if not self.notifications or not self.notifications.on_failure:
            return

        command_template = self.notifications.on_failure.get("command")
        if not command_template:
            return

        env_config = self.notifications.on_failure.get("env", {})

        # Create a simplified summary file for the hook
        try:
            notification_summary_path = summary_path.parent / f"notification-{summary_path.name}"

            # Flatten summary for notification contract
            flat_summary = {
                "tenant_id": self.tenant_id,
                "job_name": self.job_config.asset or "unknown",
                "run_id": self.run_summary.run.id if self.run_summary else "unknown",
                "status": self.run_summary.ingestion.status if self.run_summary else "failure",
                "timestamp": (
                    self.run_summary.run.start_time.isoformat()
                    if self.run_summary and self.run_summary.run.start_time
                    else datetime.now(timezone.utc).isoformat()
                ),
                "config_path": self.config_path or "unknown",
                "error": (
                    {
                        "message": (
                            self.run_summary.ingestion.error.error_message
                            if self.run_summary.ingestion.error
                            else "Unknown error"
                        ),
                        "type": (
                            self.run_summary.ingestion.error.error_type
                            if self.run_summary.ingestion.error
                            else "UnknownError"
                        ),
                    }
                    if self.run_summary
                    and self.run_summary.ingestion.error
                    and self.run_summary.ingestion.error.has_errors
                    else None
                ),
            }

            with open(notification_summary_path, "w") as f:
                json.dump(flat_summary, f, indent=2)

            summary_path_to_use = notification_summary_path

        except Exception as e:
            self.logger.warning(
                f"Failed to create notification summary file: {e}. Using standard summary file.",
                extra={"event_type": "notification_summary_error"},
            )
            summary_path_to_use = summary_path

        self.logger.info(
            "Executing failure notification hook",
            extra={
                "command": command_template,
                "event_type": "notification_hook_started",
            },
        )

        try:
            # Prepare environment variables
            env = os.environ.copy()

            # User provided env vars (with expansion)
            for key, value in env_config.items():
                env[key] = expand_env_variable(str(value))

            # Required DATIVO_* vars (override user vars)
            env["DATIVO_TENANT_ID"] = self.tenant_id
            env["DATIVO_JOB_NAME"] = self.job_config.asset or "unknown"
            env["DATIVO_RUN_ID"] = (
                self.run_summary.run.id if self.run_summary else "unknown"
            )
            env["DATIVO_SUMMARY_PATH"] = str(summary_path_to_use)

            # Execute command
            result = subprocess.run(
                command_template,
                env=env,
                capture_output=True,
                text=True,
                timeout=20,  # 20s timeout
            )

            if result.returncode != 0:
                self.logger.warning(
                    f"Notification hook failed with exit code {result.returncode}",
                    extra={
                        "event_type": "notification_hook_failed",
                        "exit_code": result.returncode,
                        "stderr": result.stderr[:1000] if result.stderr else None,
                    },
                )
            else:
                self.logger.info(
                    "Notification hook executed successfully",
                    extra={
                        "event_type": "notification_hook_success",
                        "stdout": result.stdout[:1000] if result.stdout else None,
                    },
                )

        except subprocess.TimeoutExpired:
            self.logger.warning(
                "Notification hook timed out",
                extra={
                    "event_type": "notification_hook_timeout",
                    "timeout_seconds": 20,
                },
            )
        except Exception as e:
            self.logger.warning(
                f"Failed to execute notification hook: {e}",
                extra={"event_type": "notification_hook_error", "error": str(e)},
            )

    def execute(self) -> int:
        """Execute the complete job pipeline.

        Returns:
            Exit code (0=success, 1=partial, 2=failure)
        """
        try:
            # Resolve source and target configs
            try:
                self.source_config = self.job_config.get_source()
                self.target_config = self.job_config.get_target()
            except ValueError as e:
                error_msg = f"Failed to load connector configuration: {e}"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                # Set up logging to log the error
                self._setup_logging()
                self.logger.error(
                    error_msg,
                    extra={"event_type": "config_error"},
                    exc_info=True,
                )
                return 2
            except Exception as e:
                error_msg = f"Failed to resolve source/target configuration: {e}"
                print(f"ERROR: {error_msg}", file=sys.stderr)
                if hasattr(e, "__cause__") and e.__cause__:
                    print(f"  Caused by: {e.__cause__}", file=sys.stderr)
                # Set up logging to log the error
                self._setup_logging()
                self.logger.error(
                    error_msg,
                    extra={"event_type": "config_error"},
                    exc_info=True,
                )
                return 2

            # Set up logging
            self._setup_logging()

            # Initialize run summary
            is_incremental = bool(self.source_config and self.source_config.incremental)
            run_type = "incremental" if is_incremental else "full_refresh"

            # Capture a single timestamp to ensure run_id and start_time are synchronized
            run_start_time = datetime.now(timezone.utc)
            run_id = run_start_time.strftime("%Y%m%dT%H%M%SZ")

            self.run_summary = RunSummary(
                run=RunInfo(
                    id=run_id,
                    type=run_type,
                    start_time=run_start_time,
                    tenant_id=self.tenant_id,
                    job_name=self.job_config.asset or "unknown",
                    environment=self.job_config.environment
                    or os.getenv("DATIVO_ENV", "dev"),
                    triggered_by=self.mode,
                ),
                ingestion=IngestionInfo(status="running"),
                schema=SchemaInfo(
                    version="0.0.0",
                    enforcement_mode=self.job_config.schema_validation_mode or "strict",
                ),
                storage=StorageInfo(
                    target_type=(
                        self.target_config.type if self.target_config else "unknown"
                    ),
                    format=(
                        self.target_config.file_format if self.target_config else None
                    ),
                ),
                asset=RunAssetInfo(
                    name=self.job_config.asset or "unknown", version="0.0.0"
                ),
                time=TimeInfo(
                    event_time_field=(
                        self.source_config.incremental.get("cursor_field")
                        if is_incremental and self.source_config.incremental
                        else None
                    )
                ),
            )

            # Initialize metrics (after logging is set up)
            self._initialize_metrics()

            # Validate job
            exit_code = self._validate_job()
            if exit_code != 0:
                # Ensure metrics gauge is reset on early return
                self._finish_metrics(exit_code)
                self._write_run_summary(exit_code)
                return exit_code

            # Load asset
            exit_code = self._load_asset()
            if exit_code != 0:
                # Ensure metrics gauge is reset on early return
                self._finish_metrics(exit_code)
                self._write_run_summary(exit_code)
                return exit_code

            if self.run_summary and self.asset_definition:
                self.run_summary.asset = RunAssetInfo(
                    id=self.asset_definition.id,
                    name=self.asset_definition.name,
                    version=self.asset_definition.version,
                )
                self.run_summary.schema_info.version = self.asset_definition.version

            # Initialize state manager
            self._initialize_state_manager()

            # Initialize extractor
            exit_code = self._initialize_extractor()
            if exit_code != 0:
                # Ensure metrics gauge is reset on early return
                self._finish_metrics(exit_code)
                self._write_run_summary(exit_code)
                return exit_code

            # Initialize WAL manager (after extractor is initialized for metadata)
            self._initialize_wal_manager()

            # Initialize validator
            exit_code = self._initialize_validator()
            if exit_code != 0:
                # Ensure metrics gauge is reset on early return
                self._finish_metrics(exit_code)
                self._write_run_summary(exit_code)
                return exit_code

            # Dry-run mode: skip writer/committer initialization and use dry-run execution
            if self.dry_run:
                exit_code = self._execute_dry_run()
                self._finish_metrics(exit_code)
                self._write_run_summary(exit_code)
                return exit_code

            # Initialize writer
            exit_code = self._initialize_writer()
            if exit_code != 0:
                # Ensure metrics gauge is reset on early return
                self._finish_metrics(exit_code)
                self._write_run_summary(exit_code)
                return exit_code

            # Initialize committer
            self._initialize_committer()

            # Execute ETL pipeline
            exit_code = self._execute_etl_pipeline()
            # Only return early for actual failures (exit_code == 2)
            # Partial success (exit_code == 1) should still push to catalog
            if exit_code == 2:
                # Ensure metrics gauge is reset on early return
                self._finish_metrics(exit_code)
                self._write_run_summary(exit_code)
                return exit_code

            # Push to catalog (for both success and partial success)
            self._push_to_catalog()

            # Finalize metrics
            self._finish_metrics(exit_code)
            summary_path = self._write_run_summary(exit_code)

            # Execute notification hook on failure
            if exit_code == 2 and summary_path:
                self._execute_notification_hook(summary_path)

            return exit_code

        except Exception as e:
            if self.logger:
                self.logger.error(
                    f"Job execution failed: {e}",
                    extra={
                        "event_type": "job_error",
                    },
                    exc_info=True,
                )

            if self.run_summary:
                self.run_summary.ingestion.error = RunErrorInfo(
                    has_errors=True, error_message=str(e), error_type=type(e).__name__
                )

            # Record error in metrics (ensure finish is called even on exception)
            if self.metrics_collector:
                self.metrics_collector.finish("failure")

            summary_path = self._write_run_summary(2)
            if summary_path:
                self._execute_notification_hook(summary_path)
            return 2
