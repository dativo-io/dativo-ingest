# Catalog Limitations and Workarounds

## Current Status

The `dativo-ingest` pipeline supports **optional catalog configuration**. If no catalog is configured, Parquet files are written directly to S3/MinIO without Iceberg metadata registration.

## PyIceberg and Nessie Compatibility

**Important**: PyIceberg's REST catalog type is **not compatible with Nessie**. PyIceberg's REST catalog is designed for Iceberg REST catalog servers, which have a different API structure than Nessie.

### The Problem

When using `catalog: nessie` with PyIceberg:
- PyIceberg tries to access `/v1/config` endpoint
- Nessie doesn't provide this endpoint (it uses `/api/v1/trees`, `/api/v2/branches`, etc.)
- Result: Catalog operations fail, but **files are still uploaded to S3**

### Current Behavior

1. **Files are successfully uploaded to S3/MinIO** with full metadata and tags
2. **Catalog operations fail gracefully** - pipeline continues
3. **No Iceberg table metadata** is registered in Nessie
4. **No commits appear in Nessie history**

## Solutions

### Option 1: No Catalog (Recommended for MVP)

Simply omit the `catalog` field in your target configuration:

```yaml
target:
  type: iceberg
  # catalog: nessie  # Omit this
  connection:
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: "data-lake"
```

**Benefits:**
- ✅ Simplest setup
- ✅ Files written to S3 with metadata
- ✅ No additional infrastructure required
- ✅ Works immediately

**Limitations:**
- ❌ No ACID transactions
- ❌ No time-travel queries
- ❌ No schema evolution tracking
- ❌ Query engines (Trino, Spark) won't see table metadata

### Option 2: Use Spark/Java for Nessie Registration

If you need Nessie integration, use Spark or Java Iceberg libraries to register tables:

```python
# After dativo-ingest writes files, use Spark to register:
from pyspark.sql import SparkSession

spark = SparkSession.builder \
    .config("spark.sql.catalog.nessie.type", "nessie") \
    .config("spark.sql.catalog.nessie.uri", "http://localhost:19120/api/v2") \
    .config("spark.sql.catalog.nessie.ref", "main") \
    .config("spark.sql.catalog.nessie.warehouse", "s3://bucket/warehouse/") \
    .getOrCreate()

# Register existing Parquet files as Iceberg table
spark.sql("""
    CREATE TABLE nessie.default.my_table
    USING ICEBERG
    LOCATION 's3://bucket/domain/data_product/table/'
""")
```

### Option 3: Wait for PyIceberg Nessie Support

PyIceberg may add native Nessie support in future versions. Monitor:
- [PyIceberg GitHub Issues](https://github.com/apache/iceberg-python/issues)
- [Nessie Python Client](https://github.com/projectnessie/nessie-python)

### Option 4: Use Alternative Catalogs

PyIceberg supports other catalog types that work out of the box:

#### AWS Glue Catalog
```yaml
target:
  type: iceberg
  catalog: glue
  connection:
    glue:
      catalog_id: "${AWS_ACCOUNT_ID}"
      region: "${AWS_REGION}"
```

#### Hive Metastore
```yaml
target:
  type: iceberg
  catalog: hive
  connection:
    hive:
      uri: "thrift://metastore:9083"
      warehouse: "s3://bucket/warehouse/"
```

## Future Roadmap

1. **Phase 1 (Current)**: Optional catalog - write to S3 only ✅
2. **Phase 2**: Add AWS Glue Catalog support
3. **Phase 3**: Add Hive Metastore support
4. **Phase 4**: Native Nessie support (when PyIceberg adds it)
5. **Phase 5**: Polaris catalog support

## Workaround: Manual Nessie Registration

If you need Nessie commits immediately, you can manually register tables using the Nessie API or Spark:

```bash
# Using Nessie CLI (if available)
nessie content put \
  --ref main \
  --key default.my_table \
  --type ICEBERG_TABLE \
  --iceberg-table-metadata-location s3://bucket/warehouse/default/my_table/metadata/00000-xxx.metadata.json
```

## Summary

- ✅ **Files are written successfully** to S3 with full metadata
- ⚠️ **Nessie catalog operations fail** due to PyIceberg limitation
- ✅ **Pipeline continues** - no blocking errors
- 📝 **Use Spark/Java** for Nessie table registration if needed
- 🚀 **No catalog mode** works great for MVP/prototyping

