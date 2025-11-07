Repository layout (refined architecture)
registry/
  connectors.yaml

connectors/
  sources/
    stripe.yaml
    hubspot.yaml
    postgres.yaml
    mysql.yaml
    gdrive_csv.yaml
    google_sheets.yaml
  targets/
    iceberg.yaml
    s3.yaml
    minio.yaml

assets/
  stripe/v1.0/customers.yaml
  hubspot/v1.0/contacts.yaml
  postgres/v1.0/db_orders.yaml
  mysql/v1.0/db_customers.yaml
  gdrive_csv/v1.0/deals_daily.yaml
  google_sheets/v1.0/vendors_master.yaml

jobs/
  acme/
    stripe_customers_to_iceberg.yaml
    hubspot_contacts_to_iceberg.yaml
    postgres_orders_to_iceberg.yaml
    mysql_customers_to_s3.yaml
    gdrive_deals_to_iceberg.yaml
    gsheets_vendors_to_minio.yaml

configs/
  runner.yaml
  policy.yaml


Notes:
• Connectors are tenant-agnostic recipes that define HOW to connect
• Assets define WHAT structure to ingest (schema, governance)
• Jobs are tenant-specific strategy implementations that compose connectors with assets
• Secrets come from env/files (no secrets in YAML)
• Incremental strategy is always explicit and commented
