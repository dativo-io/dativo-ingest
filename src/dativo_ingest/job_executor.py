"""Job executor for running ETL pipelines."""

import os
import sys
from typing import Any, Dict, List, Optional

from .config import AssetDefinition, JobConfig, SourceConfig, TargetConfig
from .connectors.factory import ExtractorFactory
from .logging import get_logger, update_logging_settings
from .plugins import PluginLoader, extract_sandbox_config
from .schema_validator import SchemaValidator
from .utils import expand_env_variable
from .validator import ConnectorValidator, IncrementalStateManager
from .wal_manager import WALManager


class JobExecutor:
    """Executes a single job configuration through the complete ETL pipeline."""

    def __init__(self, job_config: JobConfig, mode: str = "self_hosted"):
        """Initialize job executor.

        Args:
            job_config: Job configuration
            mode: Execution mode (default: self_hosted)
        """
        self.job_config = job_config
        self.mode = mode
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

    def _setup_logging(self) -> None:
        """Set up logging for the job."""
        log_level = self.job_config.logging.level if self.job_config.logging else None
        redact = self.job_config.logging.redaction if self.job_config.logging else None

        self.logger = update_logging_settings(
            level=log_level,
            redact_secrets=redact,
            tenant_id=self.job_config.tenant_id,
        )

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
            # DESIGN DECISION: One job = one asset = one source object (see docs/DESIGN_ONE_ASSET_PER_JOB.md)
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
        if not self.target_config.markdown_kv_storage:
            return batch_records

        from .markdown_kv import parse_markdown_kv, transform_to_markdown_kv

        mode = self.target_config.markdown_kv_storage.get("mode")
        transformed_records = []

        for record in batch_records:
            if mode == "string":
                doc_id = str(
                    record.get("businessentityid")
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
                    record.get("businessentityid")
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
                except Exception as e:
                    self.logger.error(
                        f"Failed to commit files using custom writer: {e}",
                        extra={
                            "event_type": "custom_writer_commit_failed",
                        },
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
                except Exception as e:
                    self.logger.warning(
                        f"Failed to commit files to Iceberg catalog: {e}. "
                        "Files were uploaded to S3 but not registered in catalog.",
                        extra={
                            "event_type": "commit_failed",
                            "files_uploaded": len(all_file_metadata),
                        },
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
                except Exception as e:
                    self.logger.error(
                        f"Failed to upload files to S3: {e}",
                        extra={
                            "event_type": "upload_failed",
                        },
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
        if has_errors and validation_mode == "warn":
            exit_code = 1  # Partial success
        elif total_valid_records == 0:
            exit_code = 2  # Failure - no valid records
        else:
            exit_code = 0  # Success

        # Calculate total bytes written
        total_bytes = (
            sum(file_meta.get("size_bytes", 0) for file_meta in all_file_metadata)
            if all_file_metadata
            else 0
        )

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

            # Validate job
            exit_code = self._validate_job()
            if exit_code != 0:
                return exit_code

            # Load asset
            exit_code = self._load_asset()
            if exit_code != 0:
                return exit_code

            # Initialize state manager
            self._initialize_state_manager()

            # Initialize extractor
            exit_code = self._initialize_extractor()
            if exit_code != 0:
                return exit_code

            # Initialize WAL manager (after extractor is initialized for metadata)
            self._initialize_wal_manager()

            # Initialize validator
            exit_code = self._initialize_validator()
            if exit_code != 0:
                return exit_code

            # Initialize writer
            exit_code = self._initialize_writer()
            if exit_code != 0:
                return exit_code

            # Initialize committer
            self._initialize_committer()

            # Execute ETL pipeline
            exit_code = self._execute_etl_pipeline()
            # Only return early for actual failures (exit_code == 2)
            # Partial success (exit_code == 1) should still push to catalog
            if exit_code == 2:
                return exit_code

            # Push to catalog (for both success and partial success)
            self._push_to_catalog()

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
            return 2
