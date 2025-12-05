# Dativo Demo

This directory contains demo configurations for the Dativo Ingestion Platform.

## Quick Start

Run the complete demo with one command:

```bash
docker compose -f docker-compose.demo.yml up --build
```

This will:
1. Start MinIO (S3-compatible storage) on port 9000
2. Start Nessie (Iceberg catalog) on port 19120
3. Run a demo CSV-to-Iceberg ingestion job
4. Display results and next steps

## What's Included

- **jobs/csv_to_iceberg.yaml** - Demo job configuration
- **data/employees.csv** - Sample employee data

## Viewing Results

After the demo completes:

- **MinIO Console**: http://localhost:9001 (minioadmin/minioadmin)
- **Browse data**: `mc ls local/demo-bucket --recursive`
- **Nessie API**: http://localhost:19120/api/v1

## Customizing the Demo

Edit `jobs/csv_to_iceberg.yaml` to modify the job configuration, then restart:

```bash
docker compose -f docker-compose.demo.yml restart dativo-runner
```

