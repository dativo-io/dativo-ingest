# Stripe → MinIO/Iceberg (local quickstart)

Spin up MinIO + `stripe-mock`, run a single ingestion job, and land Markdown-KV-friendly Parquet files without touching real infrastructure.

## What's included

- `docker-compose.yaml` – MinIO + `stripe/stripe-mock`.
- `jobs/stripe_customers_to_iceberg.yaml` – uses the JSON API plugin to hit the mock API.
- `.env.example` – environment variables consumed by both Dativo and the sample job.

## Run it

1. **Copy the env file**
   ```bash
   cd examples/stripe_to_s3_iceberg
   cp .env.example .env
   ```

2. **Start MinIO + stripe-mock**
   ```bash
   docker compose up -d
   ```

3. **Create the landing bucket once**
   ```bash
   export $(grep -v '^#' .env | xargs)  # loads MINIO_* vars
   AWS_ACCESS_KEY_ID=$MINIO_ACCESS_KEY \
   AWS_SECRET_ACCESS_KEY=$MINIO_SECRET_KEY \
   aws --endpoint-url $MINIO_ENDPOINT \
     s3 mb s3://$MINIO_BUCKET || true
   ```
   (Feel free to use `mc alias set local $MINIO_ENDPOINT $MINIO_ACCESS_KEY $MINIO_SECRET_KEY` if you prefer MinIO's CLI.)

4. **Run the job from the repo root**
   ```bash
   cd ../..   # back to repo root
   source examples/stripe_to_s3_iceberg/.env
   dativo run \
     --config examples/stripe_to_s3_iceberg/jobs/stripe_customers_to_iceberg.yaml \
     --secret-manager env \
     --mode self_hosted
   ```

## What you should see

```
[INFO] Starting job execution | connector_type=stripe event_type=job_started
[INFO] Wrote batch: 25 records, 1 files | event_type=batch_written
[INFO] Files uploaded to S3 (no catalog configured): 1 file(s) | event_type=files_written_no_catalog
[INFO] Job execution completed | records=25 valid_records=25 files_written=1 exit_code=0 event_type=job_finished
```

## Inspect the results

```bash
AWS_ACCESS_KEY_ID=$MINIO_ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$MINIO_SECRET_KEY \
aws --endpoint-url $MINIO_ENDPOINT \
  s3 ls s3://$MINIO_BUCKET/examples/stripe/customers/

AWS_ACCESS_KEY_ID=$MINIO_ACCESS_KEY \
AWS_SECRET_ACCESS_KEY=$MINIO_SECRET_KEY \
aws --endpoint-url $MINIO_ENDPOINT \
  s3 cp s3://$MINIO_BUCKET/examples/stripe/customers/part-0.parquet .
```

## Tear down

```
docker compose down -v
```

> Going to production? Replace the plugin with the native Stripe connector + Airbyte engine, switch secrets to Vault/AWS/GCP, and point the target at your real S3 bucket or Iceberg catalog.
