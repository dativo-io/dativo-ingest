"""Command-line interface for Dativo ingestion runner."""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import JobConfig, RunnerConfig
from .infrastructure import validate_infrastructure, validate_infrastructure_config
from .logging import get_logger, setup_logging, update_logging_settings
from .secrets import load_secrets
from .validator import ConnectorValidator, IncrementalStateManager


def initialize_state_directory(job_config: JobConfig) -> None:
    """Initialize state directory for incremental sync tracking.

    Args:
        job_config: Job configuration
    """
    source_config = job_config.get_source()
    if source_config.incremental:
        state_path_str = source_config.incremental.get("state_path", "")
        if state_path_str:
            state_path = Path(state_path_str)
            # Create parent directories if they don't exist
            state_path.parent.mkdir(parents=True, exist_ok=True)
            # Validate directory is writable
            if not os.access(state_path.parent, os.W_OK):
                raise PermissionError(
                    f"State directory is not writable: {state_path.parent}"
                )


def _load_secret_manager_config_arg(
    config_arg: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Load secret manager configuration from path or inline JSON."""

    candidate = config_arg or os.getenv("DATIVO_SECRET_MANAGER_CONFIG")
    if not candidate:
        return None

    candidate_path = Path(candidate)
    if candidate_path.exists():
        with open(candidate_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        suffix = candidate_path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(content) or {}
        if suffix == ".json":
            return json.loads(content or "{}")
        # Fall back to JSON parsing for arbitrary extensions
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Secret manager config file '{candidate_path}' must be YAML or JSON."
            ) from exc

    # Treat argument as inline JSON
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Secret manager config must be a path to a YAML/JSON file or a JSON string."
        ) from exc


def startup_sequence(
    job_dir: Path,
    secrets_dir: Path,
    tenant_id: Optional[str] = None,
    mode: str = "self_hosted",
    secret_manager: str = "env",
    secret_manager_config: Optional[Dict[str, Any]] = None,
) -> List[JobConfig]:
    """Complete startup sequence for batch job execution.

    Loads and validates job configurations from a directory, sets up
    infrastructure, and prepares jobs for execution.

    Args:
        job_dir: Directory containing job YAML files
        secrets_dir: Directory containing secrets (filesystem manager only)
        tenant_id: Optional tenant identifier (if not provided, inferred from jobs)
        mode: Execution mode (default: self_hosted)
        secret_manager: Secret backend to use (env, filesystem, vault, aws, gcp)
        secret_manager_config: Optional manager-specific configuration dictionary

    Returns:
        List of validated job configurations

    Raises:
        ValueError: If startup sequence fails
    """
    # 1. Load jobs from directory first to infer tenant_id
    try:
        jobs = JobConfig.load_jobs_from_directory(job_dir)
        if not jobs:
            raise ValueError(f"No valid jobs found in {job_dir}")
    except ValueError as e:
        # Set up basic logging even if jobs fail to load
        logger = setup_logging(level="INFO", redact_secrets=True)
        logger.error(
            f"Failed to load jobs: {e}",
            extra={"event_type": "jobs_load_error"},
        )
        raise

    # 2. Infer tenant_id from jobs if not provided
    if tenant_id is None:
        # All jobs should have the same tenant_id
        tenant_ids = {job.tenant_id for job in jobs}
        if len(tenant_ids) > 1:
            raise ValueError(
                f"Jobs have conflicting tenant_ids: {tenant_ids}. "
                "All jobs in a directory must belong to the same tenant, or specify --tenant-id to override."
            )
        tenant_id = jobs[0].tenant_id
        tenant_source = "inferred from job configurations"
    else:
        # Validate that all jobs match the provided tenant_id
        mismatched = [job for job in jobs if job.tenant_id != tenant_id]
        if mismatched:
            raise ValueError(
                f"Tenant ID mismatch: {len(mismatched)} job(s) have tenant_id different from '{tenant_id}'. "
                f"Conflicting tenant_ids: {set(job.tenant_id for job in mismatched)}"
            )
        tenant_source = "command line"

    # Set up logging once after tenant_id is determined
    logger = setup_logging(level="INFO", redact_secrets=True, tenant_id=tenant_id)
    logger.info(
        f"Tenant ID '{tenant_id}' {tenant_source}",
        extra={
            "event_type": (
                "tenant_inferred"
                if tenant_source == "inferred from job configurations"
                else "tenant_override"
            )
        },
    )

    logger.info(
        f"Starting startup sequence for tenant '{tenant_id}'",
        extra={"event_type": "startup_begin", "job_count": len(jobs)},
    )

    # 3. Load secrets using inferred/validated tenant_id
    try:
        secrets = load_secrets(
            tenant_id,
            secrets_dir,
            manager_type=secret_manager,
            manager_config=secret_manager_config,
        )
        logger.info(
            f"Secrets loaded for tenant {tenant_id}",
            extra={"event_type": "secrets_loaded", "secret_count": len(secrets)},
        )
    except ValueError as e:
        logger.warning(
            f"Secrets loading failed (may be optional): {e}",
            extra={"event_type": "secrets_warning"},
        )

    # 4. Validate environment variables for all jobs
    for job in jobs:
        try:
            job.validate_environment_variables()
        except ValueError as e:
            logger.warning(
                f"Environment variable validation warning for job: {e}",
                extra={"event_type": "env_validation_warning"},
            )

    logger.info(
        "Environment variables validated",
        extra={"event_type": "env_validated"},
    )

    # 5. Validate infrastructure for all jobs
    for job in jobs:
        try:
            # Validate infrastructure dependencies (health checks)
            validate_infrastructure(job)
            # Validate infrastructure configuration (Terraform integration)
            if job.infrastructure:
                validate_infrastructure_config(job)
        except ValueError as e:
            logger.warning(
                f"Infrastructure validation warning for job: {e}",
                extra={"event_type": "infrastructure_warning"},
            )

    logger.info(
        "Infrastructure validated",
        extra={"event_type": "infra_validated"},
    )

    # 6. Initialize state management for all jobs
    for job in jobs:
        try:
            initialize_state_directory(job)
        except Exception as e:
            logger.warning(
                f"State directory initialization warning for job: {e}",
                extra={"event_type": "state_warning"},
            )

    logger.info(
        "State management initialized",
        extra={"event_type": "state_initialized"},
    )

    # 7. Validate all job configurations
    validator = ConnectorValidator()
    for job in jobs:
        try:
            job.validate_schema_presence()
            validator.validate_job(job, mode=mode)
        except (SystemExit, ValueError) as e:
            logger.error(
                f"Job validation failed: {e}",
                extra={"event_type": "job_validation_error"},
            )
            # Continue with other jobs

    logger.info(
        "Startup sequence completed",
        extra={"event_type": "startup_complete", "job_count": len(jobs)},
    )

    return jobs


def run_command(args: argparse.Namespace) -> int:
    """Execute oneshot job run.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 1=partial, 2=failure)
    """
    try:
        manager_config = _load_secret_manager_config_arg(args.secret_manager_config)
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    # Check if running from directory or single file
    if args.job_dir:
        # Run startup sequence and execute all jobs
        try:
            jobs = startup_sequence(
                job_dir=Path(args.job_dir),
                secrets_dir=Path(args.secrets_dir),
                tenant_id=args.tenant_id,
                mode=args.mode,
                secret_manager=args.secret_manager,
                secret_manager_config=manager_config,
            )
        except ValueError as e:
            print(f"ERROR: Startup sequence failed: {e}", file=sys.stderr)
            return 2

        # Execute all jobs sequentially
        results = []
        for job_config in jobs:
            result = _execute_single_job(job_config, args.mode)
            results.append(result)

        # Return 0 if all succeeded, 2 if any failed
        return 0 if all(r == 0 for r in results) else 2
    else:
        # Single job execution (original behavior)
        try:
            job_config = JobConfig.from_yaml(args.config)
        except SystemExit as e:
            return e.code if e.code else 2

        # Set up logging for single job execution (no startup_sequence was called)
        log_level = job_config.logging.level if job_config.logging else "INFO"
        redact = job_config.logging.redaction if job_config.logging else False
        setup_logging(
            level=log_level, redact_secrets=redact, tenant_id=job_config.tenant_id
        )

        return _execute_single_job(job_config, args.mode)


def _execute_single_job(job_config: JobConfig, mode: str) -> int:
    """Execute a single job configuration.

    Args:
        job_config: Job configuration
        mode: Execution mode

    Returns:
        Exit code (0=success, 1=partial, 2=failure)
    """

    # Resolve source and target configs
    source_config = job_config.get_source()
    target_config = job_config.get_target()

    # Store tenant_id for credential path resolution (will be passed to extractors)
    tenant_id = job_config.tenant_id

    # Update logging settings if job has specific requirements
    # Always update tenant_id to ensure correct tenant context for this job
    log_level = job_config.logging.level if job_config.logging else None
    redact = job_config.logging.redaction if job_config.logging else None

    # Update logging settings (tenant_id always updated, level/redact only if specified)
    logger = update_logging_settings(
        level=log_level,
        redact_secrets=redact,
        tenant_id=job_config.tenant_id,
    )

    logger.info(
        "Starting job execution",
        extra={
            "connector_type": source_config.type,
            "event_type": "job_started",
        },
    )

    # Validate schema presence
    try:
        job_config.validate_schema_presence()
        logger.info(
            "Schema validation passed",
            extra={
                "connector_type": source_config.type,
                "event_type": "job_validated",
            },
        )
    except SystemExit as e:
        logger.error(
            "Schema validation failed",
            extra={
                "connector_type": source_config.type,
                "event_type": "job_error",
            },
        )
        return e.code if e.code else 2

    # Validate connector and mode restrictions
    try:
        validator = ConnectorValidator()
        validator.validate_job(job_config, mode=mode)
        logger.info(
            "Connector validation passed",
            extra={
                "connector_type": source_config.type,
                "event_type": "job_validated",
            },
        )
    except SystemExit as e:
        logger.error(
            "Connector validation failed",
            extra={
                "connector_type": source_config.type,
                "event_type": "job_error",
            },
        )
        return e.code if e.code else 2

    # Load asset definition
    try:
        asset_definition = job_config._resolve_asset()
        logger.info(
            "Asset definition loaded",
            extra={
                "asset_name": asset_definition.name,
                "event_type": "asset_loaded",
            },
        )
    except Exception as e:
        logger.error(
            f"Failed to load asset definition: {e}",
            extra={
                "event_type": "asset_error",
            },
        )
        return 2

    # Initialize state manager for incremental syncs
    state_manager = None
    if source_config.incremental:
        state_path_str = source_config.incremental.get("state_path", "")
        if state_path_str:
            state_manager = IncrementalStateManager()
            logger.info(
                "Incremental state manager initialized",
                extra={
                    "state_path": state_path_str,
                    "event_type": "state_initialized",
                },
            )

    # Initialize extractor based on source type or custom reader
    # Initialize source_tags early to ensure it's always defined
    source_tags = None
    try:
        if source_config.custom_reader:
            # Use custom reader plugin
            from .plugins import PluginLoader

            logger.info(
                f"Loading custom reader from: {source_config.custom_reader}",
                extra={
                    "custom_reader": source_config.custom_reader,
                    "event_type": "custom_reader_loading",
                },
            )

            reader_class = PluginLoader.load_reader(source_config.custom_reader)
            extractor = reader_class(source_config)

            logger.info(
                "Custom reader initialized",
                extra={
                    "custom_reader": source_config.custom_reader,
                    "event_type": "custom_reader_initialized",
                },
            )
        else:
            # Load connector recipe to determine engine type
            connector_recipe = None
            # Get connector path from job_config (not source_config)
            if (
                hasattr(job_config, "source_connector_path")
                and job_config.source_connector_path
            ):
                from .config import ConnectorRecipe

                try:
                    connector_recipe = ConnectorRecipe.from_yaml(
                        job_config.source_connector_path
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to load connector recipe: {e}. Using default engine selection.",
                        extra={"event_type": "connector_recipe_warning"},
                    )

            # Check engine type if connector recipe is available
            engine_type = None
            if connector_recipe:
                default_engine = connector_recipe.default_engine
                if isinstance(default_engine, dict):
                    engine_type = default_engine.get("type")
                elif default_engine:
                    engine_type = str(default_engine)

            # Route to connector-specific extractors first (to preserve custom metadata),
            # then fall back to engine framework or native extractors
            if source_config.type == "stripe":
                # Stripe uses Airbyte but has custom extractor for metadata
                if connector_recipe:
                    from .connectors.stripe_extractor import StripeExtractor

                    extractor = StripeExtractor(
                        source_config, connector_recipe, tenant_id
                    )
                else:
                    logger.error(
                        "Stripe connector requires connector_recipe for Airbyte engine",
                        extra={"event_type": "extractor_error"},
                    )
                    return 2
            elif source_config.type == "hubspot":
                # HubSpot uses Airbyte but has custom extractor for metadata
                if connector_recipe:
                    from .connectors.hubspot_extractor import HubSpotExtractor

                    extractor = HubSpotExtractor(
                        source_config, connector_recipe, tenant_id
                    )
                else:
                    logger.error(
                        "HubSpot connector requires connector_recipe for Airbyte engine",
                        extra={"event_type": "extractor_error"},
                    )
                    return 2
            elif source_config.type == "csv":
                from .connectors.csv_extractor import CSVExtractor

                extractor = CSVExtractor(source_config)
            elif source_config.type == "postgres":
                from .connectors.postgres_extractor import PostgresExtractor

                extractor = PostgresExtractor(source_config)
            elif source_config.type == "mysql":
                from .connectors.mysql_extractor import MySQLExtractor

                extractor = MySQLExtractor(source_config)
            elif engine_type == "airbyte":
                from .connectors.engine_framework import AirbyteExtractor

                extractor = AirbyteExtractor(source_config, connector_recipe, tenant_id)
                logger.info(
                    f"Using Airbyte engine for {source_config.type}",
                    extra={
                        "connector_type": source_config.type,
                        "engine_type": "airbyte",
                        "event_type": "extractor_initialized",
                    },
                )
            elif engine_type == "meltano":
                from .connectors.engine_framework import MeltanoExtractor

                extractor = MeltanoExtractor(source_config, connector_recipe, tenant_id)
                logger.info(
                    f"Using Meltano engine for {source_config.type}",
                    extra={
                        "connector_type": source_config.type,
                        "engine_type": "meltano",
                        "event_type": "extractor_initialized",
                    },
                )
            elif engine_type == "singer":
                from .connectors.engine_framework import SingerExtractor

                extractor = SingerExtractor(source_config, connector_recipe, tenant_id)
                logger.info(
                    f"Using Singer engine for {source_config.type}",
                    extra={
                        "connector_type": source_config.type,
                        "engine_type": "singer",
                        "event_type": "extractor_initialized",
                    },
                )
            elif source_config.type == "gdrive_csv":
                from .connectors.gdrive_csv_extractor import GDriveCSVExtractor

                extractor = GDriveCSVExtractor(
                    source_config, connector_recipe, tenant_id
                )
            elif source_config.type == "google_sheets":
                from .connectors.google_sheets_extractor import GoogleSheetsExtractor

                extractor = GoogleSheetsExtractor(
                    source_config, connector_recipe, tenant_id
                )
            else:
                logger.error(
                    f"Unsupported source type: {source_config.type}. "
                    f"Either use a supported type or specify a custom_reader in the source configuration.",
                    extra={
                        "event_type": "extractor_error",
                    },
                )
                return 2

        # Extract source tags from extractor if available (for three-level tag hierarchy)
        if hasattr(extractor, "extract_metadata"):
            try:
                metadata = extractor.extract_metadata()
                if metadata and isinstance(metadata, dict):
                    source_tags = metadata.get("tags") or metadata.get("source_tags")
                    if source_tags:
                        logger.info(
                            "Source tags extracted from connector",
                            extra={
                                "source_tags_count": len(source_tags),
                                "event_type": "source_tags_extracted",
                            },
                        )
            except Exception as e:
                logger.debug(
                    f"Failed to extract source tags from connector (non-critical): {e}",
                    extra={"event_type": "source_tags_extraction_failed"},
                )
        elif hasattr(extractor, "get_source_tags"):
            try:
                source_tags = extractor.get_source_tags()
                if source_tags:
                    logger.info(
                        "Source tags extracted from connector",
                        extra={
                            "source_tags_count": len(source_tags),
                            "event_type": "source_tags_extracted",
                        },
                    )
            except Exception as e:
                logger.debug(
                    f"Failed to extract source tags from connector (non-critical): {e}",
                    extra={"event_type": "source_tags_extraction_failed"},
                )

        if not source_config.custom_reader:
            logger.info(
                "Extractor initialized",
                extra={
                    "source_type": source_config.type,
                    "event_type": "extractor_initialized",
                },
            )
    except Exception as e:
        logger.error(
            f"Failed to initialize extractor: {e}",
            extra={
                "event_type": "extractor_error",
            },
            exc_info=True,
        )
        return 2

    # Initialize schema validator
    try:
        from .schema_validator import SchemaValidator

        validation_mode = job_config.schema_validation_mode or "strict"
        validator = SchemaValidator(asset_definition, validation_mode=validation_mode)
        logger.info(
            "Schema validator initialized",
            extra={
                "validation_mode": validation_mode,
                "event_type": "validator_initialized",
            },
        )
    except Exception as e:
        logger.error(
            f"Failed to initialize schema validator: {e}",
            extra={
                "event_type": "validator_error",
            },
        )
        return 2

    # Initialize writer based on target config or custom writer
    try:
        # Get output base path from target config following industry standards
        # Standard path structure: s3://bucket/domain/data_product/table/
        # Always build standard path regardless of warehouse config to ensure consistency

        # Extract bucket from connection config
        connection = target_config.connection or {}
        s3_config = connection.get("s3") or connection.get("minio", {})
        bucket = s3_config.get("bucket") or os.getenv("S3_BUCKET")
        if not bucket:
            raise ValueError(
                "S3 bucket must be specified in target.connection.s3.bucket "
                "or S3_BUCKET environment variable"
            )

        # Build path following industry standards:
        # s3://bucket/domain/data_product/table/
        # - Use domain from asset definition (required for organization)
        # - Use dataProduct from asset definition (logical grouping)
        # - Use table name (asset name, normalized)
        domain = asset_definition.domain or "default"
        data_product = getattr(asset_definition, "dataProduct", None) or "default"
        table_name = asset_definition.name.lower().replace("-", "_").replace(" ", "_")

        # Always build standard path structure (industry best practice)
        # This ensures consistent organization and makes it easy to:
        # - Find data by domain
        # - Find data by data product
        # - Find data by table
        # - Apply access policies at domain/data_product level
        output_base = f"s3://{bucket}/{domain}/{data_product}/{table_name}"

        if target_config.custom_writer:
            # Use custom writer plugin
            from .plugins import PluginLoader

            logger.info(
                f"Loading custom writer from: {target_config.custom_writer}",
                extra={
                    "custom_writer": target_config.custom_writer,
                    "event_type": "custom_writer_loading",
                },
            )

            writer_class = PluginLoader.load_writer(target_config.custom_writer)
            writer = writer_class(asset_definition, target_config, output_base)

            logger.info(
                "Custom writer initialized",
                extra={
                    "custom_writer": target_config.custom_writer,
                    "output_base": output_base,
                    "event_type": "custom_writer_initialized",
                },
            )
        else:
            # Use default Parquet writer
            from .parquet_writer import ParquetWriter

            writer = ParquetWriter(
                asset_definition,
                target_config,
                output_base,
                validation_mode=validation_mode,
            )

            logger.info(
                "Parquet writer initialized",
                extra={
                    "output_base": output_base,
                    "validation_mode": validation_mode,
                    "event_type": "writer_initialized",
                },
            )
    except Exception as e:
        logger.error(
            f"Failed to initialize writer: {e}",
            extra={
                "event_type": "writer_error",
            },
            exc_info=True,
        )
        return 2

    # Initialize Iceberg committer (only if catalog is configured)
    committer = None
    if target_config.catalog:
        try:
            from .iceberg_committer import IcebergCommitter

            committer = IcebergCommitter(
                asset_definition=asset_definition,
                target_config=target_config,
                classification_overrides=job_config.classification_overrides,
                finops=job_config.finops,
                governance_overrides=job_config.governance_overrides,
                source_tags=source_tags,
            )
            logger.info(
                "Iceberg committer initialized",
                extra={
                    "branch": target_config.branch,
                    "catalog": target_config.catalog,
                    "event_type": "committer_initialized",
                },
            )
        except Exception as e:
            logger.warning(
                f"Failed to initialize Iceberg catalog (catalog: {target_config.catalog}): {e}. "
                "Will write Parquet files to S3 without Iceberg metadata.",
                extra={
                    "event_type": "catalog_init_failed",
                    "catalog": target_config.catalog,
                },
            )
            committer = None
    else:
        logger.info(
            "No catalog configured - writing Parquet files directly to S3 without Iceberg metadata",
            extra={
                "event_type": "no_catalog_mode",
            },
        )

    # Execute ETL pipeline
    total_records = 0
    total_valid_records = 0
    total_files_written = 0
    file_counter = 0
    all_file_metadata = []
    has_errors = False

    try:
        # Ensure table exists (only if catalog is configured)
        if committer:
            committer.ensure_table_exists()
            logger.info(
                "Iceberg table ensured",
                extra={
                    "table_name": asset_definition.name,
                    "event_type": "table_ensured",
                },
            )

        # Extract, validate, and write in batches
        for batch_records in extractor.extract(state_manager=state_manager):
            total_records += len(batch_records)

            # Transform to Markdown-KV format if configured
            if target_config.markdown_kv_storage:
                from .markdown_kv import parse_markdown_kv, transform_to_markdown_kv

                mode = target_config.markdown_kv_storage.get("mode")
                transformed_records = []

                for record in batch_records:
                    if mode == "string":
                        # Transform to Markdown-KV string format
                        # Get doc_id from record (try common ID fields)
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

                        # Transform record to Markdown-KV format
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
                        # Transform to Markdown-KV first, then parse to structured format
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

                        # Transform to Markdown-KV string
                        markdown_kv_content = transform_to_markdown_kv(
                            record, format="compact", doc_id=doc_id
                        )

                        # Parse to structured format
                        structured_pattern = target_config.markdown_kv_storage.get(
                            "structured_pattern", "row_per_kv"
                        )
                        structured_rows = parse_markdown_kv(
                            markdown_kv_content,
                            doc_id=doc_id,
                            pattern=structured_pattern,
                        )

                        # structured_rows is a list of rows (for row_per_kv) or a single dict (for document_level)
                        if isinstance(structured_rows, list):
                            transformed_records.extend(structured_rows)
                        else:
                            transformed_records.append(structured_rows)

                    else:
                        # raw_file mode - not handled here, would be in writer
                        transformed_records.append(record)

                batch_records = transformed_records

            # Validate batch
            valid_records, validation_errors = validator.validate_batch(batch_records)
            total_valid_records += len(valid_records)

            # Log validation errors if any
            if validation_errors:
                has_errors = True
                error_summary = validator.get_error_summary()
                logger.warning(
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
                    logger.error(
                        f"Strict validation mode: failing due to validation errors for job '{job_config.asset}'",
                        extra={
                            "event_type": "validation_failed",
                            "job_name": job_config.asset,
                            "error_summary": error_summary,
                        },
                    )
                    return 2

            # Write valid records to Parquet
            if valid_records:
                file_metadata = writer.write_batch(valid_records, file_counter)
                all_file_metadata.extend(file_metadata)
                total_files_written += len(file_metadata)
                file_counter += len(file_metadata)

                logger.info(
                    f"Wrote batch: {len(valid_records)} records, {len(file_metadata)} files",
                    extra={
                        "records": len(valid_records),
                        "files": len(file_metadata),
                        "event_type": "batch_written",
                    },
                )

        # Commit all files to Iceberg (if catalog is configured) or upload to S3 (if no catalog)
        if all_file_metadata:
            # Check if writer has custom commit_files method
            if target_config.custom_writer and hasattr(writer, "commit_files"):
                # Use custom writer's commit logic
                try:
                    commit_result = writer.commit_files(all_file_metadata)
                    logger.info(
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
                    logger.error(
                        f"Failed to commit files using custom writer: {e}",
                        extra={
                            "event_type": "custom_writer_commit_failed",
                        },
                    )
                    return 2
            elif committer:
                try:
                    commit_result = committer.commit_files(all_file_metadata)
                    logger.info(
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
                    logger.warning(
                        f"Failed to commit files to Iceberg catalog: {e}. "
                        "Files were uploaded to S3 but not registered in catalog.",
                        extra={
                            "event_type": "commit_failed",
                            "files_uploaded": len(all_file_metadata),
                        },
                    )
            else:
                # No catalog and no custom writer - still need to upload files to S3/MinIO
                # Create a minimal committer just for uploading (without catalog operations)
                from .iceberg_committer import IcebergCommitter

                upload_committer = IcebergCommitter(
                    asset_definition=asset_definition,
                    target_config=target_config,
                    classification_overrides=job_config.classification_overrides,
                    finops=job_config.finops,
                    governance_overrides=job_config.governance_overrides,
                    source_tags=source_tags,
                )
                try:
                    upload_result = upload_committer.commit_files(all_file_metadata)
                    logger.info(
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
                    logger.error(
                        f"Failed to upload files to S3: {e}",
                        extra={
                            "event_type": "upload_failed",
                        },
                    )
                    return 2
        else:
            logger.warning(
                "No files to commit",
                extra={
                    "event_type": "no_files",
                },
            )

        # Determine exit code
        if has_errors and validation_mode == "warn":
            exit_code = 1  # Partial success
        elif total_valid_records == 0:
            exit_code = 2  # Failure - no valid records
        else:
            exit_code = 0  # Success

        # Calculate total bytes written (estimate from file count if metadata available)
        total_bytes = (
            sum(file_meta.get("size_bytes", 0) for file_meta in all_file_metadata)
            if all_file_metadata
            else 0
        )

        # Emit enhanced metadata
        logger.info(
            "Job execution completed",
            extra={
                "total_records": total_records,
                "valid_records": total_valid_records,
                "files_written": total_files_written,
                "total_bytes": total_bytes,
                "exit_code": exit_code,
                "event_type": "job_finished",
                # Enhanced metadata for observability
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

    except Exception as e:
        logger.error(
            f"Job execution failed: {e}",
            extra={
                "event_type": "job_error",
            },
            exc_info=True,
        )
        return 2


def start_command(args: argparse.Namespace) -> int:
    """Start orchestrated mode with Dagster.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0=success, 2=failure)
    """
    # Import here to avoid dependency if not using orchestrated mode
    from .orchestrated import start_orchestrated

    # Load runner configuration
    try:
        runner_config = RunnerConfig.from_yaml(args.runner_config)
    except SystemExit as e:
        return e.code if e.code else 2

    # Set up logging
    logger = setup_logging(level="INFO", redact_secrets=False)
    logger.info(
        "Starting orchestrated mode",
        extra={"event_type": "orchestrator_starting"},
    )

    # Start orchestrated mode
    try:
        start_orchestrated(runner_config)
    except KeyboardInterrupt:
        logger.info("Orchestrator stopped by user")
        return 0
    except Exception as e:
        logger.error(
            f"Orchestrator failed: {e}",
            extra={"event_type": "orchestrator_error"},
        )
        return 2

    return 0


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Dativo ingestion runner - config-driven data ingestion engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run a single job
  dativo run --config /app/configs/jobs/stripe.yaml --mode self_hosted

  # Start orchestrated mode
  dativo start orchestrated --runner-config /app/configs/runner.yaml
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Run command
    run_parser = subparsers.add_parser(
        "run",
        help="Run a single job in oneshot mode",
        description="Execute a single ingestion job and exit. Validates configuration, "
        "schema presence, and connector restrictions before execution.",
    )
    config_group = run_parser.add_mutually_exclusive_group(required=True)
    config_group.add_argument(
        "--config",
        help="Path to job configuration YAML file",
    )
    config_group.add_argument(
        "--job-dir",
        help="Path to directory containing job YAML files (mutually exclusive with --config)",
    )
    run_parser.add_argument(
        "--secrets-dir",
        default="/secrets",
        help="Path to secrets directory (default: /secrets, used by filesystem secret manager)",
    )
    run_parser.add_argument(
        "--tenant-id",
        help="Tenant ID override (optional; if not provided, inferred from job configurations). "
        "If provided, validates all jobs belong to this tenant.",
    )
    run_parser.add_argument(
        "--secret-manager",
        choices=["env", "filesystem", "vault", "aws", "gcp"],
        default=os.getenv("DATIVO_SECRET_MANAGER", "env"),
        help="Secret backend to use (default: env or DATIVO_SECRET_MANAGER env var).",
    )
    run_parser.add_argument(
        "--secret-manager-config",
        help="Path to YAML/JSON file or inline JSON blob with secret manager configuration. "
        "Falls back to DATIVO_SECRET_MANAGER_CONFIG when omitted.",
    )
    run_parser.add_argument(
        "--mode",
        choices=["self_hosted", "cloud"],
        default="self_hosted",
        help="Execution mode (default: self_hosted). Database connectors are only "
        "allowed in self_hosted mode.",
    )

    # Start command
    start_parser = subparsers.add_parser(
        "start",
        help="Start orchestrated mode with Dagster",
        description="Start the Dagster orchestrator in long-running mode. Reads schedules "
        "from runner.yaml and executes jobs according to cron expressions. "
        "Ensures tenant-level serialization to avoid conflicts.",
    )
    start_parser.add_argument(
        "mode",
        choices=["orchestrated"],
        help="Orchestration mode (currently only 'orchestrated' is supported)",
    )
    start_parser.add_argument(
        "--runner-config",
        default="/app/configs/runner.yaml",
        help="Path to runner configuration YAML file (default: /app/configs/runner.yaml)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 2

    if args.command == "run":
        return run_command(args)
    elif args.command == "start":
        return start_command(args)
    else:
        parser.print_help()
        return 2


if __name__ == "__main__":
    sys.exit(main())
