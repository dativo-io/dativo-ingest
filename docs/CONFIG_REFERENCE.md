tenant_id: acme
environment: prod
source:
  type: hubspot
  credentials:
    from_env: HUBSPOT_TOKEN
    scope: tenant
  objects: [contacts]
  incremental:
    strategy: updated_after
    cursor_field: updatedAt
    lookback_days: 1
    state_path: /state/acme/hubspot.contacts.state.json
  rate_limits:
    rps: 5
    burst: 10
    retry: { max_retries: 5, backoff: exponential, max_backoff_seconds: 64 }
  test_mode: { enabled: false }
target:
  type: iceberg
  catalog: nessie
  branch: acme
  warehouse: s3://lake/acme/
  file_format: parquet
  partitioning: [ingest_date]
asset_definition: /app/specs/hubspot/v1.0/contacts.yaml
logging:
  redaction: true
  level: INFO