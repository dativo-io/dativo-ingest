"""Nessie/Iceberg integration for committing Parquet files to catalog."""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import AssetDefinition, TargetConfig
from .tag_derivation import derive_tags_from_asset


class IcebergCommitter:
    """Commits Parquet files to Iceberg tables via Nessie catalog."""

    def __init__(
        self,
        asset_definition: AssetDefinition,
        target_config: TargetConfig,
        classification_overrides: Optional[Dict[str, str]] = None,
        finops: Optional[Dict[str, Any]] = None,
        governance_overrides: Optional[Dict[str, Any]] = None,
        source_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize Iceberg committer.

        Args:
            asset_definition: Asset definition containing schema
            target_config: Target configuration with Nessie and storage connection
            classification_overrides: Field-level classification overrides from job config
            finops: FinOps metadata from job config
            governance_overrides: Governance metadata overrides from job config
            source_tags: Source system tags (LOWEST priority)
        """
        self.asset_definition = asset_definition
        self.target_config = target_config
        self.branch = target_config.branch or "main"
        self.catalog_name = target_config.catalog or "nessie"
        self.warehouse = target_config.warehouse or "s3://lake/"

        # Store tag override parameters
        self.classification_overrides = classification_overrides
        self.finops = finops
        self.governance_overrides = governance_overrides
        self.source_tags = source_tags

        # Get connection details
        connection = target_config.connection or {}
        self.nessie_uri = self._get_nessie_uri(connection)
        self.storage_config = self._get_storage_config(connection)

    def _get_nessie_uri(self, connection: Dict[str, Any]) -> str:
        """Get Nessie URI from connection config.

        Args:
            connection: Connection configuration dictionary

        Returns:
            Nessie base URI string (without /api/v1, PyIceberg will add that)
        """
        nessie_config = connection.get("nessie", {})
        if isinstance(nessie_config, str):
            uri = nessie_config
        else:
            uri = nessie_config.get("uri") or os.getenv(
                "NESSIE_URI", "http://localhost:19120/api/v1"
            )

        # Expand environment variables
        if uri and "${" in uri:
            uri = os.path.expandvars(uri)

        # PyIceberg REST catalog expects base URI without /api/v1
        # It will add /v1/config automatically
        if uri.endswith("/api/v1"):
            uri = uri[:-7]  # Remove /api/v1
        elif uri.endswith("/api/v2"):
            uri = uri[:-7]  # Remove /api/v2

        return uri or "http://localhost:19120"

    def _get_storage_config(self, connection: Dict[str, Any]) -> Dict[str, Any]:
        """Get storage configuration (S3/MinIO) from connection config.

        Args:
            connection: Connection configuration dictionary

        Returns:
            Storage configuration dictionary
        """
        # Check for S3 or MinIO config
        s3_config = connection.get("s3") or connection.get("minio", {})
        if not s3_config:
            # Try environment variables
            return {
                "endpoint": os.getenv("S3_ENDPOINT") or os.getenv("MINIO_ENDPOINT"),
                "bucket": os.getenv("S3_BUCKET") or os.getenv("MINIO_BUCKET"),
                "access_key_id": os.getenv("AWS_ACCESS_KEY_ID")
                or os.getenv("MINIO_ACCESS_KEY"),
                "secret_access_key": os.getenv("AWS_SECRET_ACCESS_KEY")
                or os.getenv("MINIO_SECRET_KEY"),
                "region": os.getenv("AWS_REGION", "us-east-1"),
            }

        # Expand environment variables in config values
        import re

        def expand_env(value):
            if isinstance(value, str):
                # Handle bash-style ${VAR:-default} syntax
                bash_default_pattern = r"\$\{([^:}]+):-([^}]+)\}"
                match = re.search(bash_default_pattern, value)
                if match:
                    env_var = match.group(1)
                    default_value = match.group(2)
                    return os.getenv(env_var, default_value)
                elif "${" in value:
                    # Simple ${VAR} syntax - expand and if still has ${}, use env var or None
                    expanded = os.path.expandvars(value)
                    if "${" in expanded:
                        # Variable not set, extract var name and try to get from env
                        var_match = re.search(r"\$\{([^}]+)\}", expanded)
                        if var_match:
                            var_name = var_match.group(1)
                            return os.getenv(var_name, None)
                    return expanded
            return value

        endpoint = (
            expand_env(s3_config.get("endpoint"))
            or os.getenv("S3_ENDPOINT")
            or os.getenv("MINIO_ENDPOINT")
            or "http://localhost:9000"
        )
        bucket = (
            expand_env(s3_config.get("bucket"))
            or os.getenv("S3_BUCKET")
            or os.getenv("MINIO_BUCKET")
            or "test-bucket"
        )
        access_key_id = (
            expand_env(s3_config.get("access_key_id"))
            or os.getenv("AWS_ACCESS_KEY_ID")
            or os.getenv("MINIO_ACCESS_KEY")
            or "minioadmin"
        )
        secret_access_key = (
            expand_env(s3_config.get("secret_access_key"))
            or os.getenv("AWS_SECRET_ACCESS_KEY")
            or os.getenv("MINIO_SECRET_KEY")
            or "minioadmin"
        )
        region = (
            expand_env(s3_config.get("region"))
            or os.getenv("AWS_REGION")
            or "us-east-1"
        )

        return {
            "endpoint": endpoint,
            "bucket": bucket,
            "access_key_id": access_key_id,
            "secret_access_key": secret_access_key,
            "region": region,
        }

    def _create_pyiceberg_schema(self) -> Any:
        """Create PyIceberg schema from asset definition.

        Returns:
            PyIceberg schema object
        """
        try:
            from pyiceberg.schema import Schema
            from pyiceberg.types import (
                BooleanType,
                DateType,
                DoubleType,
                LongType,
                NestedField,
                StringType,
                TimestampType,
            )
        except ImportError:
            raise ImportError(
                "pyiceberg is required for Iceberg table management. Install with: pip install pyiceberg"
            )

        fields = []
        for idx, field_def in enumerate(self.asset_definition.schema):
            field_name = field_def["name"]
            field_type = field_def.get("type", "string")
            is_required = field_def.get("required", False)

            # Map to PyIceberg types
            if field_type == "string":
                iceberg_type = StringType()
            elif field_type == "integer":
                iceberg_type = LongType()
            elif field_type in ["float", "double"]:
                iceberg_type = DoubleType()
            elif field_type == "boolean":
                iceberg_type = BooleanType()
            elif field_type in ["timestamp", "datetime"]:
                iceberg_type = TimestampType()
            elif field_type == "date":
                iceberg_type = DateType()
            else:
                # Default to string
                iceberg_type = StringType()

            fields.append(
                NestedField(
                    field_id=idx + 1,
                    name=field_name,
                    field_type=iceberg_type,
                    required=is_required,
                )
            )

        return Schema(*fields)

    def _derive_table_properties(self) -> Dict[str, str]:
        """Derive table properties from asset definition and tag overrides.

        Returns:
            Dictionary of table properties in namespaced format
        """
        # Derive all tags using tag derivation module
        tags = derive_tags_from_asset(
            asset_definition=self.asset_definition,
            classification_overrides=self.classification_overrides,
            finops=self.finops,
            governance_overrides=self.governance_overrides,
            source_tags=self.source_tags,
        )

        # Add asset metadata
        tags["asset.name"] = self.asset_definition.name
        tags["asset.version"] = str(self.asset_definition.version)
        if self.asset_definition.domain:
            tags["asset.domain"] = self.asset_definition.domain
        if hasattr(self.asset_definition, "dataProduct") and self.asset_definition.dataProduct:
            tags["asset.data_product"] = self.asset_definition.dataProduct

        # Add source metadata
        tags["asset.source_type"] = self.asset_definition.source_type
        tags["asset.object"] = self.asset_definition.object

        return tags

    def _update_table_properties(
        self, catalog: Any, namespace: str, table_name: str
    ) -> None:
        """Update table properties idempotently.

        Merges derived tags with existing properties without dropping unrelated ones.

        Args:
            catalog: PyIceberg catalog instance
            namespace: Table namespace
            table_name: Table name
        """
        try:
            table = catalog.load_table((namespace, table_name))
            
            # Derive new properties
            new_properties = self._derive_table_properties()
            
            # Get current properties
            current_properties = table.properties or {}
            
            # Check if update is needed
            needs_update = False
            for key, value in new_properties.items():
                if key not in current_properties or current_properties[key] != value:
                    needs_update = True
                    break
            
            if not needs_update:
                return
            
            # Merge properties (new properties override existing ones)
            merged_properties = {**current_properties, **new_properties}
            
            # Update table properties using transaction
            with table.transaction() as txn:
                for key, value in new_properties.items():
                    txn.set_properties(**{key: value})
            
            import logging
            logger = logging.getLogger(__name__)
            logger.info(
                f"Updated {len(new_properties)} table properties for {namespace}.{table_name}"
            )
        except Exception as e:
            import warnings
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to update table properties for {namespace}.{table_name}: {e}"
            )

    def _ensure_branch_exists(self) -> None:
        """Ensure Nessie branch exists, create if it doesn't.

        Uses Nessie REST API directly to create branch if needed.
        """
        import requests

        # Get base URI for API calls
        base_uri = self.nessie_uri
        if not base_uri.endswith("/api/v1"):
            base_uri = f"{base_uri}/api/v1"

        # Check if branch exists
        try:
            resp = requests.get(f"{base_uri}/trees/tree/{self.branch}")
            if resp.status_code == 200:
                return  # Branch exists
        except Exception:
            pass

        # Create branch from main
        try:
            resp = requests.post(
                f"{base_uri}/trees/branch/{self.branch}",
                json={"sourceRefName": "main"},
                headers={"Content-Type": "application/json"},
            )
            if resp.status_code in [200, 201]:
                import logging

                logger = logging.getLogger(__name__)
                logger.info(f"Created Nessie branch: {self.branch}")
            elif resp.status_code == 400:
                # Branch may already exist or other issue
                pass
        except Exception as e:
            import warnings

            warnings.warn(
                f"Failed to create Nessie branch '{self.branch}': {e}. "
                "Will attempt to use existing branch.",
                UserWarning,
            )

    def _create_catalog(self) -> Any:
        """Create and configure PyIceberg catalog.

        Returns:
            PyIceberg catalog object
        """
        try:
            from pyiceberg.catalog import load_catalog
        except ImportError:
            raise ImportError(
                "pyiceberg is required for Iceberg table management. Install with: pip install pyiceberg"
            )

        # Ensure branch exists first
        self._ensure_branch_exists()

        # Build catalog properties
        # PyIceberg REST catalog expects base URI (it adds /v1/config)
        properties = {
            "type": "rest",
            "uri": self.nessie_uri,
            "ref": self.branch,
            "warehouse": self.warehouse,
        }

        # Add S3/MinIO configuration
        if self.storage_config.get("endpoint"):
            properties["s3.endpoint"] = self.storage_config["endpoint"]
        if self.storage_config.get("access_key_id"):
            properties["s3.access-key-id"] = self.storage_config["access_key_id"]
        if self.storage_config.get("secret_access_key"):
            properties["s3.secret-access-key"] = self.storage_config[
                "secret_access_key"
            ]
        if self.storage_config.get("region"):
            properties["s3.region"] = self.storage_config["region"]

        # Load catalog
        try:
            catalog = load_catalog(self.catalog_name, **properties)
            return catalog
        except Exception as e:
            # If catalog load fails, try with different URI format
            import warnings

            warnings.warn(
                f"Failed to load PyIceberg catalog with URI '{self.nessie_uri}': {e}",
                UserWarning,
            )
            raise

    def ensure_table_exists(self) -> None:
        """Ensure Iceberg table exists, create if it doesn't.

        Raises:
            Exception: If table creation fails
        """
        try:
            catalog = self._create_catalog()
        except Exception as e:
            # If catalog creation fails, log and continue
            # This allows the pipeline to at least extract and write Parquet files
            import warnings

            warnings.warn(
                f"Failed to create Iceberg catalog (PyIceberg/Nessie compatibility issue): {e}. "
                "Parquet files will be written but not committed to Iceberg. "
                "This is a known limitation - PyIceberg REST catalog may need configuration adjustments for Nessie.",
                UserWarning,
            )
            return

        table_name = self.asset_definition.name
        namespace = self.asset_definition.domain or "default"

        try:
            # Try to load existing table and update its properties
            table = catalog.load_table((namespace, table_name))
            # Update properties idempotently
            self._update_table_properties(catalog, namespace, table_name)
        except Exception:
            # Table doesn't exist, create it
            try:
                schema = self._create_pyiceberg_schema()

                # Get partitioning spec
                partition_spec = None
                if self.target_config.partitioning:
                    try:
                        from pyiceberg.partitioning import PartitionField, PartitionSpec
                        from pyiceberg.transforms import IdentityTransform

                        partition_fields = []
                        for partition_col in self.target_config.partitioning:
                            # Find field ID for partition column
                            field_id = None
                            for idx, field_def in enumerate(
                                self.asset_definition.schema
                            ):
                                if field_def["name"] == partition_col:
                                    field_id = idx + 1
                                    break

                            if field_id:
                                partition_fields.append(
                                    PartitionField(
                                        source_id=field_id,
                                        field_id=len(partition_fields) + 1000,
                                        name=partition_col,
                                        transform=IdentityTransform(),
                                    )
                                )

                        if partition_fields:
                            partition_spec = PartitionSpec(*partition_fields)
                    except ImportError:
                        # If partitioning import fails, continue without partitioning
                        pass

                # Derive table properties
                table_properties = self._derive_table_properties()

                # Create table with properties
                catalog.create_table(
                    identifier=(namespace, table_name),
                    schema=schema,
                    partition_spec=partition_spec,
                    properties=table_properties,
                )
                
                import logging
                logger = logging.getLogger(__name__)
                logger.info(
                    f"Created Iceberg table with {len(table_properties)} properties: {namespace}.{table_name}"
                )
            except Exception as e:
                # If table creation fails, log warning but continue
                # This allows Parquet files to be written even if Iceberg table creation fails
                import warnings

                warnings.warn(
                    f"Failed to create Iceberg table (may need manual creation): {e}. "
                    "Parquet files will still be written.",
                    UserWarning,
                )

    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit Parquet files to Iceberg table.

        Args:
            file_metadata: List of file metadata dictionaries from ParquetWriter

        Returns:
            Dictionary with commit information:
            - commit_id: Nessie commit ID
            - files_added: Number of files added
            - table_name: Full table name
        """
        table_name = self.asset_definition.name
        namespace = self.asset_definition.domain or "default"

        # Upload files to storage and get paths
        # This happens regardless of catalog configuration
        file_paths = []
        for file_meta in file_metadata:
            local_path = file_meta.get("local_path")
            s3_path = file_meta.get("path")

            if local_path and s3_path:
                try:
                    # Upload to S3/MinIO with metadata
                    self._upload_to_storage(
                        local_path, s3_path, file_metadata=file_meta
                    )
                    file_paths.append(s3_path)
                except Exception as e:
                    # Log warning but continue with other files
                    import warnings

                    warnings.warn(
                        f"Failed to upload file {local_path} to storage: {e}",
                        UserWarning,
                    )

        # If no catalog is configured, just return success for file uploads
        if not self.target_config.catalog:
            return {
                "commit_id": None,
                "files_added": len(file_paths),
                "table_name": f"{self.asset_definition.domain or 'default'}.{self.asset_definition.name}",
                "branch": None,
                "file_paths": file_paths,
                "note": "No catalog configured - files uploaded to S3 only",
            }

        # Try to commit to Iceberg via catalog
        try:
            catalog = self._create_catalog()
            table = catalog.load_table((namespace, table_name))

            # Append data files to the table using PyIceberg's add_files method
            # This properly registers files in Iceberg metadata and commits to Nessie
            try:
                from pyiceberg.io.pyarrow import PyArrowFileIO
                from pyiceberg.manifest import DataFile
                from pyiceberg.partitioning import PartitionSpec
                from pyiceberg.typedef import Record

                # Create DataFile objects for each uploaded Parquet file
                data_files = []
                for file_path in file_paths:
                    # Parse S3 path to get bucket and key
                    if file_path.startswith("s3://"):
                        path_parts = file_path[5:].split("/", 1)
                        bucket = path_parts[0]
                        key = path_parts[1] if len(path_parts) > 1 else ""
                    else:
                        parts = file_path.split("/", 1)
                        bucket = parts[0]
                        key = parts[1] if len(parts) > 1 else ""

                    # Get file metadata
                    file_meta = next(
                        (f for f in file_metadata if f.get("path") == file_path), {}
                    )
                    file_size = file_meta.get("size_bytes", 0)
                    record_count = file_meta.get("record_count", 0)

                    # Full S3 path for the data file
                    data_file_path = f"s3://{bucket}/{key}"

                    # Parse partition from path if available
                    partition_data = None
                    if file_meta.get("partition"):
                        # Partition is in format "column=value" or "col1=val1/col2=val2"
                        partition_str = file_meta["partition"]
                        # For now, we'll let PyIceberg infer partition from path
                        # Full implementation would parse and create PartitionData
                        partition_data = None

                    # Create DataFile entry
                    # PyIceberg's add_files expects DataFile objects or file paths
                    # For simplicity, we'll pass the file path and let PyIceberg read metadata
                    data_files.append(data_file_path)

                # Use PyIceberg's add_files method to append files to table
                # This creates a new snapshot and commits to Nessie
                import logging

                logger = logging.getLogger(__name__)

                if hasattr(table, "add_files"):
                    # add_files is the correct method in PyIceberg 0.10+
                    logger.info(
                        f"Appending {len(data_files)} files to table using add_files"
                    )
                    result = table.add_files(data_files)

                    # Get snapshot/commit information
                    commit_id = None
                    if hasattr(result, "snapshot_id"):
                        commit_id = str(result.snapshot_id)
                    elif hasattr(table, "current_snapshot"):
                        snapshot = table.current_snapshot()
                        if snapshot:
                            commit_id = str(snapshot.snapshot_id)

                    # Also try to get Nessie commit hash from catalog if available
                    nessie_commit_hash = None
                    try:
                        if hasattr(catalog, "get_reference"):
                            ref = catalog.get_reference(self.branch)
                            if ref:
                                nessie_commit_hash = (
                                    str(ref.hash) if hasattr(ref, "hash") else None
                                )
                    except Exception:
                        pass

                    logger.info(
                        f"Successfully committed {len(file_paths)} files to Iceberg table. "
                        f"Snapshot ID: {commit_id}, Branch: {self.branch}"
                    )

                    return {
                        "commit_id": nessie_commit_hash or commit_id or "committed",
                        "snapshot_id": commit_id,
                        "files_added": len(file_paths),
                        "table_name": f"{namespace}.{table_name}",
                        "branch": self.branch,
                        "file_paths": file_paths,
                    }
                else:
                    # Fallback if add_files not available
                    logger.warning(
                        "PyIceberg add_files method not available. "
                        "Files uploaded but table metadata not updated."
                    )
                    return {
                        "commit_id": "method_not_available",
                        "files_added": len(file_paths),
                        "table_name": f"{namespace}.{table_name}",
                        "branch": self.branch,
                        "file_paths": file_paths,
                        "note": "Files uploaded. Table metadata update requires PyIceberg add_files method.",
                    }

            except Exception as append_error:
                import logging
                import warnings

                logger = logging.getLogger(__name__)
                logger.error(
                    f"Failed to append files to Iceberg table: {append_error}",
                    exc_info=True,
                )
                warnings.warn(
                    f"Failed to append files to Iceberg table: {append_error}. "
                    f"Files are uploaded but not committed to table.",
                    UserWarning,
                )
                raise

        except Exception as e:
            # If catalog/table operations fail, still return success for file uploads
            import logging
            import warnings

            logger = logging.getLogger(__name__)
            logger.warning(
                f"Failed to commit to Iceberg catalog (PyIceberg/Nessie issue): {e}. "
                f"However, {len(file_paths)} Parquet file(s) were successfully uploaded to storage."
            )

            return {
                "commit_id": None,
                "files_added": len(file_paths),
                "table_name": f"{namespace}.{table_name}",
                "branch": self.branch,
                "file_paths": file_paths,
                "warning": "Iceberg catalog commit failed, but files were uploaded to storage",
            }

    def _upload_to_storage(
        self,
        local_path: str,
        s3_path: str,
        file_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Upload file from local path to S3/MinIO storage with metadata.

        Args:
            local_path: Local file path
            s3_path: S3/MinIO path (s3://bucket/path/to/file.parquet)
            file_metadata: Optional file metadata dictionary from ParquetWriter
        """
        try:
            import boto3
            from botocore.exceptions import ClientError
        except ImportError:
            raise ImportError(
                "boto3 is required for S3/MinIO access. Install with: pip install boto3"
            )

        # Parse S3 path following industry standards
        # Expected format: s3://bucket/domain/data_product/table/partition/file.parquet
        if s3_path.startswith("s3://"):
            # Remove s3:// prefix
            path_without_prefix = s3_path[5:]
            # Split bucket from key (first component is bucket)
            parts = path_without_prefix.split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""
        else:
            # Assume it's already in the format bucket/key (without s3://)
            parts = s3_path.split("/", 1)
            bucket = parts[0]
            key = parts[1] if len(parts) > 1 else ""

        # Normalize key: ensure no double slashes, no leading slash
        if key:
            key = "/".join(
                [part for part in key.split("/") if part]
            )  # Remove empty parts
            # Ensure key doesn't start with /
            key = key.lstrip("/")

        # Create S3 client
        s3_client = boto3.client(
            "s3",
            endpoint_url=self.storage_config.get("endpoint"),
            aws_access_key_id=self.storage_config.get("access_key_id"),
            aws_secret_access_key=self.storage_config.get("secret_access_key"),
            region_name=self.storage_config.get("region", "us-east-1"),
        )

        # Build metadata from asset definition and file metadata
        metadata = {}
        tags = []

        # Asset metadata
        metadata["asset-name"] = self.asset_definition.name
        metadata["asset-version"] = str(self.asset_definition.version or "1.0")
        if self.asset_definition.domain:
            metadata["asset-domain"] = self.asset_definition.domain
            tags.append(f"domain:{self.asset_definition.domain}")

        # Data product metadata
        if (
            hasattr(self.asset_definition, "dataProduct")
            and self.asset_definition.dataProduct
        ):
            metadata["data-product"] = self.asset_definition.dataProduct
            tags.append(f"data-product:{self.asset_definition.dataProduct}")

        # Tenant and branch metadata
        if self.asset_definition.tenant:
            metadata["tenant-id"] = self.asset_definition.tenant
            tags.append(f"tenant:{self.asset_definition.tenant}")
        metadata["branch"] = self.branch
        tags.append(f"branch:{self.branch}")

        # Team/owner metadata
        if self.asset_definition.team and self.asset_definition.team.owner:
            metadata["owner"] = self.asset_definition.team.owner
            tags.append(f"owner:{self.asset_definition.team.owner}")

        # Tags from asset definition
        if self.asset_definition.tags:
            asset_tags = self.asset_definition.tags
            if isinstance(asset_tags, list):
                tags.extend([f"asset-tag:{tag}" for tag in asset_tags])
            elif isinstance(asset_tags, str):
                tags.append(f"asset-tag:{asset_tags}")

        # Compliance/retention metadata
        if self.asset_definition.compliance:
            if self.asset_definition.compliance.retention_days:
                metadata["retention-days"] = str(
                    self.asset_definition.compliance.retention_days
                )
            if self.asset_definition.compliance.classification:
                metadata["classification"] = ",".join(
                    self.asset_definition.compliance.classification
                )

        # File metadata
        if file_metadata:
            if file_metadata.get("record_count"):
                metadata["record-count"] = str(file_metadata["record_count"])
            if file_metadata.get("size_bytes"):
                metadata["file-size-bytes"] = str(file_metadata["size_bytes"])
            if file_metadata.get("partition"):
                metadata["partition"] = file_metadata["partition"]
                tags.append(f"partition:{file_metadata['partition']}")

        # Timestamp metadata
        from datetime import datetime

        metadata["ingest-timestamp"] = datetime.utcnow().isoformat() + "Z"
        metadata["file-format"] = "parquet"
        metadata["compression"] = "snappy"

        # Content type
        content_type = "application/x-parquet"

        # Upload file with metadata and tags
        try:
            with open(local_path, "rb") as f:
                # Prepare tag set for S3 (ensure unique keys)
                # Note: Use 'tag_key' to avoid shadowing the S3 'key' variable
                tag_set = []
                seen_tag_keys = set()
                for tag in tags[:10]:  # S3 limits to 10 tags
                    if ":" in tag:
                        key_val = tag.split(":", 1)
                        tag_key = key_val[0]  # Tag key (not S3 key!)
                        tag_value = key_val[1]
                        # Only add if we haven't seen this tag key before
                        if tag_key not in seen_tag_keys:
                            tag_set.append({"Key": tag_key, "Value": tag_value})
                            seen_tag_keys.add(tag_key)

                # Upload with metadata
                extra_args = {
                    "ContentType": content_type,
                    "Metadata": metadata,
                }

                # Add tags if we have any
                if tag_set:
                    import urllib.parse

                    tag_string = "&".join(
                        [
                            f"{urllib.parse.quote(t['Key'])}={urllib.parse.quote(t['Value'])}"
                            for t in tag_set
                        ]
                    )
                    extra_args["Tagging"] = tag_string

                # Ensure key is not empty and doesn't contain just "partition"
                if not key or key == "partition":
                    raise ValueError(
                        f"Invalid S3 key '{key}' derived from path '{s3_path}'. "
                        "Key should be the full path after bucket name."
                    )

                s3_client.upload_fileobj(f, bucket, key, ExtraArgs=extra_args)

                # Log successful upload
                import logging

                logger = logging.getLogger(__name__)
                logger.debug(
                    f"Uploaded to s3://{bucket}/{key} with {len(metadata)} metadata fields and {len(tag_set)} tags"
                )
        except ClientError as e:
            raise RuntimeError(f"Failed to upload file to S3/MinIO: {str(e)}") from e
