"""Spark-based Parquet writer for Iceberg tables using PySpark."""

import datetime
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import AssetDefinition, TargetConfig


class SparkWriter:
    """Writes records to Iceberg tables using Apache Spark."""

    def __init__(
        self,
        asset_definition: AssetDefinition,
        target_config: TargetConfig,
        output_base_path: str,
        validation_mode: str = "strict",
    ):
        """Initialize Spark writer.

        Args:
            asset_definition: Asset definition containing schema
            target_config: Target configuration with partitioning and file size settings
            output_base_path: Base path for output files (S3/MinIO compatible)
            validation_mode: Validation mode - 'strict' or 'warn' (affects nullability of required fields)
        """
        self.asset_definition = asset_definition
        self.target_config = target_config
        self.output_base_path = output_base_path
        self.validation_mode = validation_mode

        # Get Spark configuration from engine options
        self.engine_options = target_config.engine or {}
        spark_options = self.engine_options.get("options", {}).get("spark", {})

        # Get target file size (default: 128-200 MB range, use 150 MB as default)
        self.target_size_mb = spark_options.get(
            "max_file_size_mb", target_config.parquet_target_size_mb or 150
        )

        # Get partitioning columns
        self.partitioning = target_config.partitioning or []

        # Initialize Spark session
        self.spark = self._create_spark_session()

    def _create_spark_session(self):
        """Create Spark session with Iceberg support.

        Returns:
            SparkSession configured for Iceberg
        """
        try:
            from pyspark.sql import SparkSession
        except ImportError:
            raise ImportError(
                "pyspark is required for Spark writer. Install with: pip install pyspark"
            )

        # Get Spark configuration from engine options
        spark_options = self.engine_options.get("options", {}).get("spark", {})

        # Build Spark configuration
        spark_config = {
            "spark.sql.extensions": "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
            "spark.sql.catalog.iceberg": "org.apache.iceberg.spark.SparkCatalog",
            "spark.sql.catalog.iceberg.type": "hadoop",
            "spark.sql.catalog.iceberg.warehouse": self.output_base_path,
            "spark.serializer": "org.apache.spark.serializer.KryoSerializer",
            "spark.sql.adaptive.enabled": "true",
            "spark.sql.adaptive.coalescePartitions.enabled": "true",
        }

        # Add S3/MinIO configuration if provided
        connection = self.target_config.connection or {}
        s3_config = connection.get("s3") or connection.get("minio", {})
        if s3_config:
            endpoint = s3_config.get("endpoint", os.getenv("S3_ENDPOINT", ""))
            access_key = s3_config.get(
                "access_key_id", os.getenv("AWS_ACCESS_KEY_ID", "")
            )
            secret_key = s3_config.get(
                "secret_access_key", os.getenv("AWS_SECRET_ACCESS_KEY", "")
            )
            region = s3_config.get("region", os.getenv("AWS_REGION", "us-east-1"))
            path_style = s3_config.get("path_style_access", False)

            if endpoint:
                spark_config.update(
                    {
                        "spark.hadoop.fs.s3a.endpoint": endpoint,
                        "spark.hadoop.fs.s3a.access.key": access_key,
                        "spark.hadoop.fs.s3a.secret.key": secret_key,
                        "spark.hadoop.fs.s3a.path.style.access": str(
                            path_style
                        ).lower(),
                        "spark.hadoop.fs.s3a.impl": "org.apache.hadoop.fs.s3a.S3AFileSystem",
                    }
                )

        # Add Nessie catalog configuration if provided
        nessie_config = connection.get("nessie", {})
        if isinstance(nessie_config, dict) and nessie_config.get("uri"):
            nessie_uri = nessie_config.get("uri")
            # Remove /api/v1 suffix if present (Spark catalog expects base URI)
            if nessie_uri.endswith("/api/v1"):
                nessie_uri = nessie_uri[:-7]
            elif nessie_uri.endswith("/api/v2"):
                nessie_uri = nessie_uri[:-7]

            catalog_name = self.target_config.catalog or "iceberg"
            spark_config.update(
                {
                    f"spark.sql.catalog.{catalog_name}": "org.apache.iceberg.spark.SparkCatalog",
                    f"spark.sql.catalog.{catalog_name}.type": "rest",
                    f"spark.sql.catalog.{catalog_name}.uri": nessie_uri,
                    f"spark.sql.catalog.{catalog_name}.warehouse": self.output_base_path,
                }
            )

        # Merge with user-provided Spark options
        user_spark_config = spark_options.get("config", {})
        spark_config.update(user_spark_config)

        # Create Spark session builder
        builder = SparkSession.builder.appName("dativo-ingest-spark")

        # Apply all configurations
        for key, value in spark_config.items():
            builder = builder.config(key, value)

        # Add Iceberg and S3A JARs if specified
        jars = spark_options.get("jars", [])
        if jars:
            builder = builder.config("spark.jars", ",".join(jars))

        # Create Spark session
        spark = builder.getOrCreate()

        return spark

    def _get_partition_value(self, record: Dict[str, Any], partition_col: str) -> str:
        """Get partition value from record.

        Args:
            record: Record dictionary
            partition_col: Partition column name

        Returns:
            Partition value as string
        """
        if partition_col == "ingest_date":
            # Use current date for ingest_date partition
            return datetime.date.today().isoformat()

        # Get value from record
        value = record.get(partition_col)
        if value is None:
            return "unknown"

        # Convert to string
        if isinstance(value, datetime.datetime):
            return value.date().isoformat()
        if isinstance(value, datetime.date):
            return value.isoformat()

        return str(value)

    def _create_spark_schema(self):
        """Create Spark DataFrame schema from asset definition.

        Returns:
            Spark StructType schema
        """
        try:
            from pyspark.sql.types import (
                BooleanType,
                DoubleType,
                IntegerType,
                LongType,
                StringType,
                StructField,
                StructType,
                TimestampType,
            )
        except ImportError:
            raise ImportError(
                "pyspark is required for Spark writer. Install with: pip install pyspark"
            )

        fields = []
        for field_def in self.asset_definition.schema:
            field_name = field_def["name"]
            field_type = field_def.get("type", "string")

            # Map to Spark types
            if field_type == "string":
                spark_type = StringType()
            elif field_type == "integer":
                spark_type = LongType()  # Use LongType for integers
            elif field_type in ["float", "double"]:
                spark_type = DoubleType()
            elif field_type == "boolean":
                spark_type = BooleanType()
            elif field_type in ["timestamp", "datetime", "date"]:
                spark_type = TimestampType()
            else:
                # Default to string for unknown types
                spark_type = StringType()

            # Check if nullable
            is_required = field_def.get("required", False)
            if self.validation_mode == "warn":
                # In warn mode, make all fields nullable
                nullable = True
            else:
                # In strict mode, required fields are non-nullable
                nullable = not is_required

            fields.append(StructField(field_name, spark_type, nullable=nullable))

        return StructType(fields)

    def _generate_create_table_sql(self, table_path: str, schema) -> str:
        """Generate CREATE TABLE SQL for Iceberg table.

        Args:
            table_path: Full table path (catalog.database.table)
            schema: Spark StructType schema

        Returns:
            SQL CREATE TABLE statement
        """
        # Extract table components
        parts = table_path.split(".")
        if len(parts) != 3:
            raise ValueError(
                f"Invalid table path format: {table_path}. Expected catalog.database.table"
            )

        catalog_name, database_name, table_name = parts

        # Build column definitions
        column_defs = []
        for field in schema.fields:
            field_name = field.name
            field_type = field.dataType.simpleString().upper()
            nullable = "NULL" if field.nullable else "NOT NULL"
            column_defs.append(f"  {field_name} {field_type} {nullable}")

        # Build partition clause if partitioning is specified
        partition_clause = ""
        if self.partitioning:
            partition_cols = [
                col_name.lower().replace(" ", "_").replace("-", "_")
                for col_name in self.partitioning
            ]
            partition_clause = f"PARTITIONED BY ({', '.join(partition_cols)})"

        # Generate SQL
        sql = f"""
        CREATE TABLE IF NOT EXISTS {table_path} (
        {', '.join(column_defs)}
        )
        USING ICEBERG
        {partition_clause}
        """

        return sql.strip()

    def write_batch(
        self,
        records: List[Dict[str, Any]],
        file_counter: int = 0,
    ) -> List[Dict[str, Any]]:
        """Write a batch of records to Iceberg table using Spark.

        Args:
            records: List of record dictionaries
            file_counter: Counter for generating unique file names (not used in Spark)

        Returns:
            List of file metadata dictionaries with:
            - path: Full file path (S3 URI)
            - record_count: Number of records in file
            - size_bytes: File size in bytes (estimated)
        """
        if not records:
            return []

        try:
            from pyspark.sql import Row
        except ImportError:
            raise ImportError(
                "pyspark is required for Spark writer. Install with: pip install pyspark"
            )

        # Create Spark DataFrame from records
        schema = self._create_spark_schema()

        # Convert records to Row objects
        rows = []
        for record in records:
            row_dict = {}
            for field_def in self.asset_definition.schema:
                field_name = field_def["name"]
                value = record.get(field_name)

                # Handle type conversions
                field_type = field_def.get("type", "string")
                if field_type in ["timestamp", "datetime", "date"]:
                    if isinstance(value, str):
                        try:
                            value = datetime.datetime.fromisoformat(
                                value.replace("Z", "+00:00")
                            )
                        except ValueError:
                            value = None
                    elif isinstance(value, datetime.date) and not isinstance(
                        value, datetime.datetime
                    ):
                        value = datetime.datetime.combine(value, datetime.time.min)

                row_dict[field_name] = value

            rows.append(Row(**row_dict))

        # Create DataFrame
        df = self.spark.createDataFrame(rows, schema=schema)

        # Build table path
        domain = self.asset_definition.domain or "default"
        table_name = (
            self.asset_definition.name.lower().replace("-", "_").replace(" ", "_")
        )
        catalog_name = self.target_config.catalog or "iceberg"
        table_path = f"{catalog_name}.{domain}.{table_name}"

        # Write to Iceberg table
        writer = df.write.format("iceberg").mode("append")

        # Add partitioning if specified
        if self.partitioning:
            partition_cols = [
                col_name.lower().replace(" ", "_").replace("-", "_")
                for col_name in self.partitioning
            ]
            writer = writer.partitionBy(*partition_cols)

        # Set target file size (Spark will coalesce partitions to approximate this)
        # Convert MB to bytes for Spark
        target_size_bytes = self.target_size_mb * 1024 * 1024
        writer = writer.option("write-target-file-size-bytes", str(target_size_bytes))

        # Write to table (create if not exists, append if exists)
        # Note: For Spark, the table will be created automatically on first write
        # if it doesn't exist. For Iceberg tables, we need to ensure the table
        # schema matches. The committer will handle table creation if catalog is configured.
        try:
            writer.saveAsTable(table_path)
        except Exception as e:
            # If table doesn't exist and we have a catalog, let committer create it first
            # Otherwise, try creating table with CREATE TABLE IF NOT EXISTS
            if (
                "Table or view not found" in str(e)
                or "does not exist" in str(e).lower()
            ):
                # Table doesn't exist - Spark will create it on first write
                # But we need to ensure schema matches. For now, let's try again
                # with explicit table creation via SQL
                try:
                    # Create table if it doesn't exist (Spark SQL)
                    create_table_sql = self._generate_create_table_sql(
                        table_path, schema
                    )
                    self.spark.sql(create_table_sql)
                    # Now try writing again
                    writer.saveAsTable(table_path)
                except Exception:
                    # If that fails, re-raise original error
                    raise e
            else:
                raise

        # Get written files metadata
        # Spark/Iceberg doesn't provide direct file paths, so we estimate
        # In a real implementation, you might query the Iceberg table metadata
        file_metadata = []

        # Estimate file count based on data size
        # This is approximate - in production you'd query Iceberg metadata
        num_partitions = len(self.partitioning) if self.partitioning else 1
        estimated_files = max(1, len(records) // 50000) * num_partitions

        # Build S3 path pattern
        if self.output_base_path.startswith("s3://"):
            base = self.output_base_path.rstrip("/")
            for i in range(estimated_files):
                # Generate partition path if partitioning is enabled
                partition_path = ""
                if self.partitioning:
                    # Use first record's partition values (approximation)
                    if records:
                        partition_parts = []
                        for part_col in self.partitioning:
                            part_value = self._get_partition_value(records[0], part_col)
                            normalized_col = (
                                part_col.lower().replace(" ", "_").replace("-", "_")
                            )
                            partition_parts.append(f"{normalized_col}={part_value}")
                        partition_path = "/".join(partition_parts) + "/"

                file_path = (
                    f"{base}/{domain}/{table_name}/{partition_path}data-{i:06d}.parquet"
                )
                file_metadata.append(
                    {
                        "path": file_path,
                        "record_count": (
                            len(records) // estimated_files
                            if estimated_files > 0
                            else len(records)
                        ),
                        "size_bytes": (len(records) * 1000)
                        // estimated_files,  # Rough estimate
                        "partition": (
                            partition_path.rstrip("/") if partition_path else None
                        ),
                    }
                )
        else:
            # Non-S3 path
            base = self.output_base_path.rstrip("/")
            file_path = f"{base}/{domain}/{table_name}/data-{file_counter:06d}.parquet"
            file_metadata.append(
                {
                    "path": file_path,
                    "record_count": len(records),
                    "size_bytes": len(records) * 1000,  # Rough estimate
                    "partition": None,
                }
            )

        return file_metadata

    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit files to Iceberg table (no-op for Spark as writes are already committed).

        Args:
            file_metadata: List of file metadata dictionaries

        Returns:
            Commit result dictionary
        """
        # Spark writes are already committed when saveAsTable is called
        # This method exists for compatibility with the writer interface
        return {
            "status": "success",
            "files_committed": len(file_metadata),
            "message": "Files already committed via Spark write",
        }
