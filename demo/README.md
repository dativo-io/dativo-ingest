# Dativo Demo Environment

One-command demo environment to get started with Dativo Ingestion Platform.

## Quick Start

### 1. Start Infrastructure

```bash
docker-compose -f docker-compose.demo.yml up -d
```

This starts:
- **Nessie Catalog** on port 19120
- **MinIO Object Storage** on ports 9000 (API) and 9001 (Console)
- Pre-configured Dativo runner

### 2. Set Environment Variables

```bash
export S3_ENDPOINT=http://localhost:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export AWS_REGION=us-east-1
export S3_BUCKET=test-bucket
export NESSIE_URI=http://localhost:19120/api/v1
```

Or source the example environment file:
```bash
source .env.example
```

### 3. Run Demo Job

```bash
dativo run --config demo/jobs/csv_to_iceberg.yaml --mode self_hosted
```

## What's Included

### Infrastructure

- **Nessie Catalog**: Git-like data catalog for Iceberg tables
- **MinIO**: S3-compatible object storage
- **Pre-configured Services**: All services ready to use

### Demo Data

- `demo/data/employees.csv` - Sample employee data

### Demo Jobs

- `demo/jobs/csv_to_iceberg.yaml` - Simple CSV to Iceberg ingestion job

## Verify Results

### Check MinIO Console

1. Open http://localhost:9001
2. Login with `minioadmin` / `minioadmin`
3. Navigate to `test-bucket` to see ingested Parquet files

### Check Nessie Catalog

```bash
curl http://localhost:19120/api/v1/config
```

### Query Data (if using catalog)

```sql
-- Using Trino or Spark with Nessie
SELECT * FROM demo.employees;
```

## Clean Up

```bash
docker-compose -f docker-compose.demo.yml down -v
```

## Next Steps

1. **Modify the Job**: Edit `demo/jobs/csv_to_iceberg.yaml`
2. **Add More Data**: Add CSV files to `demo/data/`
3. **Create Assets**: Define asset schemas in `assets/examples/`
4. **Explore Connectors**: See `connectors/examples/` for available connectors

## Troubleshooting

### Services Not Starting

```bash
docker-compose -f docker-compose.demo.yml ps
docker-compose -f docker-compose.demo.yml logs
```

### Port Conflicts

If ports 9000, 9001, or 19120 are already in use, modify `docker-compose.demo.yml` to use different ports.

### MinIO Bucket Not Found

The bucket will be created automatically on first write. If you see errors, ensure MinIO is running:

```bash
curl http://localhost:9000/minio/health/live
```

## Documentation

- [Quick Start Guide](../docs/quickstart.md)
- [Configuration Reference](../docs/CONFIG_REFERENCE.md)
- [Connector Reference](../docs/connectors.md)
