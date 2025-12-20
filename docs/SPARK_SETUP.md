# Spark Engine Setup for Iceberg Target

This guide explains how to set up and use the Spark engine for writing to Iceberg tables.

## Quick Reference

**Example Job Configuration:**
- [`examples/jobs/csv_to_iceberg_spark.yaml`](../../examples/jobs/csv_to_iceberg_spark.yaml) - Complete example job
- [`docs/examples/jobs/spark_iceberg_example.yaml`](examples/jobs/spark_iceberg_example.yaml) - Detailed example with comments

**Quick Start:**
```yaml
target:
  type: iceberg
  engine:
    type: spark
    options:
      spark:
        max_file_size_mb: 200
```

**Installation:**
```bash
pip install pyspark
```

## Overview

The Spark engine (`engine.type: spark`) uses Apache Spark to write Parquet files directly to Iceberg tables. This is an alternative to the native Parquet writer (`engine.type: native`) and provides better performance and scalability for large datasets.

## Prerequisites

### Required Dependencies

1. **PySpark**: Python API for Apache Spark
   ```bash
   pip install pyspark
   ```

2. **Iceberg Spark Runtime**: Spark runtime JARs for Iceberg support
   - The Spark writer automatically configures Iceberg extensions
   - For local development, Spark will download required JARs automatically
   - For production, you may need to specify JAR paths in connector configuration

3. **Hadoop AWS Libraries**: Required for S3/MinIO connectivity
   - Usually included with Spark distributions
   - May need to be added explicitly for S3A filesystem support

### Infrastructure Requirements

- **MinIO/S3**: Object storage for Parquet files (already included in `docker-compose.dev.yml`)
- **Nessie Catalog** (optional): For Iceberg catalog support (already included in `docker-compose.dev.yml`)

## Local Development Setup

### Option 1: Local Spark Installation

1. **Install Spark** (if not already installed):
   ```bash
   # macOS
   brew install apache-spark
   
   # Linux
   # Download from https://spark.apache.org/downloads.html
   # Extract and add to PATH
   ```

2. **Set Environment Variables**:
   ```bash
   export SPARK_HOME=/path/to/spark
   export PATH=$SPARK_HOME/bin:$PATH
   ```

3. **Install Python Dependencies**:
   ```bash
   pip install pyspark
   ```

### Option 2: Use Spark via Docker (Recommended for Testing)

For integration testing, you can use Spark in a Docker container:

```bash
# Run Spark in Docker (for testing)
docker run -it --rm \
  -v $(pwd):/workspace \
  -w /workspace \
  -e SPARK_HOME=/opt/spark \
  apache/spark:3.5.0 \
  /bin/bash
```

However, for local development, it's recommended to install Spark directly on your machine.

## Configuration

### Connector Configuration

The Iceberg connector supports Spark engine configuration:

```yaml
# connectors/examples/iceberg.yaml
default_engine:
  type: spark  # Use Spark engine instead of native
  options:
    spark:
      max_file_size_mb: 200
      config:
        # Additional Spark configuration
        spark.sql.adaptive.enabled: "true"
        spark.sql.adaptive.coalescePartitions.enabled: "true"
      # Optional: Specify JAR paths if not in Spark classpath
      # jars:
      #   - "s3a://path/to/iceberg-spark-runtime.jar"
```

### Job Configuration

In your job YAML, specify the Spark engine:

```yaml
target:
  type: iceberg
  engine:
    type: spark
    options:
      spark:
        max_file_size_mb: 200
        config:
          spark.sql.adaptive.enabled: "true"
  connection:
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: test-bucket
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      region: "${AWS_REGION}"
    nessie:
      uri: "${NESSIE_URI}"
  catalog: nessie
  branch: main
```

## Running Jobs with Spark Engine

### Start Infrastructure

```bash
# Start MinIO and Nessie
docker-compose -f docker-compose.dev.yml up -d minio nessie
```

### Set Environment Variables

```bash
export S3_ENDPOINT=http://localhost:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export AWS_REGION=us-east-1
export NESSIE_URI=http://localhost:19120/api/v1
```

### Run Job

```bash
dativo ingest --config path/to/job.yaml --mode self_hosted
```

## Spark Configuration Options

### Common Spark Settings

The Spark writer supports the following configuration options:

- **`max_file_size_mb`**: Target file size in MB (default: 200)
- **`config`**: Dictionary of Spark configuration properties
- **`jars`**: List of JAR file paths (optional, for custom Iceberg versions)

### S3/MinIO Configuration

Spark automatically configures S3A filesystem based on connection settings:

- **Endpoint**: MinIO endpoint URL
- **Access Key**: S3 access key
- **Secret Key**: S3 secret key
- **Path Style Access**: Enable for MinIO compatibility

### Nessie Catalog Configuration

If Nessie catalog is configured, Spark will use REST catalog:

- **Catalog Type**: REST (automatically set)
- **URI**: Nessie base URI (without `/api/v1`)
- **Warehouse**: S3 path for table data

## Troubleshooting

### Spark Not Found

**Error**: `ImportError: pyspark is required for Spark writer`

**Solution**:
```bash
pip install pyspark
```

### Iceberg JARs Not Found

**Error**: `ClassNotFoundException: org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions`

**Solution**: Add Iceberg JARs to Spark configuration:

```yaml
target:
  engine:
    type: spark
    options:
      spark:
        jars:
          - "https://repo1.maven.org/maven2/org/apache/iceberg/iceberg-spark-runtime-3.5_2.12/1.4.2/iceberg-spark-runtime-3.5_2.12-1.4.2.jar"
```

### S3 Connection Issues

**Error**: `org.apache.hadoop.fs.s3a.AWSException: Unable to load credentials`

**Solution**: Ensure S3 credentials are correctly configured in connection settings:

```yaml
target:
  connection:
    s3:
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      endpoint: "${S3_ENDPOINT}"
```

### Nessie Catalog Connection Issues

**Error**: `Failed to connect to Nessie catalog`

**Solution**: 
1. Verify Nessie is running: `curl http://localhost:19120/api/v1/config`
2. Check URI format (should not include `/api/v1` suffix in Spark config)
3. Ensure network connectivity between Spark and Nessie

## Integration Testing

Integration tests for Spark engine are located in:

```
tests/integration/test_spark_iceberg_integration.py
```

Run tests:

```bash
# Start infrastructure
docker-compose -f docker-compose.dev.yml up -d

# Run Spark integration tests
pytest tests/integration/test_spark_iceberg_integration.py -v
```

## Performance Considerations

### When to Use Spark Engine

- **Large datasets**: Spark provides better performance for datasets > 10GB
- **Complex transformations**: If you need Spark SQL transformations before writing
- **Distributed processing**: For multi-node Spark clusters
- **Existing Spark infrastructure**: If you already have Spark deployed

### When to Use Native Engine

- **Small to medium datasets**: Native writer is simpler and faster for < 10GB
- **Simple use cases**: No need for Spark's distributed processing
- **Resource constraints**: Native writer uses less memory

## Production Deployment

### Spark Cluster Setup

For production, deploy Spark on a cluster:

1. **Standalone Cluster**: Simple Spark cluster
2. **YARN**: Hadoop YARN integration
3. **Kubernetes**: Spark on Kubernetes
4. **Mesos**: Apache Mesos integration

### Configuration for Production

```yaml
target:
  engine:
    type: spark
    options:
      spark:
        config:
          spark.master: "spark://spark-master:7077"
          spark.executor.memory: "4g"
          spark.executor.cores: "2"
          spark.sql.adaptive.enabled: "true"
          spark.sql.adaptive.coalescePartitions.enabled: "true"
```

## Additional Resources

- [Apache Spark Documentation](https://spark.apache.org/docs/latest/)
- [Iceberg Spark Integration](https://iceberg.apache.org/docs/latest/spark-configuration/)
- [Nessie Catalog Documentation](https://projectnessie.org/docs/)
