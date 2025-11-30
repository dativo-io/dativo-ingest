# Postgres incremental sync (local)

This example spins up Postgres + MinIO, seeds a customer table, and runs an incremental job that only reprocesses changes since the last successful run.

## What's included

- `docker-compose.yaml` – Postgres 15 + MinIO.
- `seed.sql` – creates `public.customers` with demo rows.
- `jobs/postgres_customers_incremental.yaml` – incremental job definition.
- `.env.example` – variables consumed by the job/CLI.

## Run it

1. **Copy env file**
   ```bash
   cd examples/postgres_incremental_sync
   cp .env.example .env
   ```

2. **Start the services**
   ```bash
   docker compose up -d
   ```

3. **Create the MinIO bucket once**
   ```bash
   export $(grep -v '^#' .env | xargs)
   AWS_ACCESS_KEY_ID=$MINIO_ACCESS_KEY \
   AWS_SECRET_ACCESS_KEY=$MINIO_SECRET_KEY \
   aws --endpoint-url $MINIO_ENDPOINT \
     s3 mb s3://$MINIO_BUCKET || true
   ```

4. **Run the job from the repo root**
   ```bash
   cd ../..
   source examples/postgres_incremental_sync/.env
   dativo run \
     --config examples/postgres_incremental_sync/jobs/postgres_customers_incremental.yaml \
     --secret-manager env \
     --mode self_hosted
   ```

## Expected output

```
[INFO] Starting job execution | connector_type=postgres event_type=job_started
[INFO] Wrote batch: 3 records, 1 files | event_type=batch_written
[INFO] Files uploaded to S3 (no catalog configured): 1 file(s) | event_type=files_written_no_catalog
[INFO] Job execution completed | records=3 valid_records=3 files_written=1 exit_code=0 event_type=job_finished
```

## Test the incremental path (optional)

```
psql "postgresql://dativo:dativo@localhost:5432/dativo" \
  -c "UPDATE customers SET status = 'active', updated_at = NOW() WHERE email = 'carol@example.com';"

source examples/postgres_incremental_sync/.env
dativo run --config examples/postgres_incremental_sync/jobs/postgres_customers_incremental.yaml \
  --secret-manager env --mode self_hosted
```

You should see only 1 record processed and a new state file under `.local/state/quickstart_postgres/postgres.customers.state.json`.

## Inspect landing zone

```bash
AWS_ACCESS_KEY_ID=$MINIO_ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$MINIO_SECRET_KEY \
aws --endpoint-url $MINIO_ENDPOINT \
  s3 ls s3://$MINIO_BUCKET/examples/postgres/customers/
```

## Tear down

```
docker compose down -v
```
