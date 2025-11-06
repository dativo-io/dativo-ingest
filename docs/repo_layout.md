Repository layout (suggested)
registry/
  connectors.yaml
  templates/
    hubspot.yaml
    stripe.yaml
    gdrive_csv.yaml
    google_sheets.yaml
    postgres.yaml
    mysql.yaml

configs/
  runner.yaml
  policy.yaml
  jobs/
    hubspot.yaml
    gdrive_csv.yaml
    google_sheets.yaml
    postgres.yaml

specs/
  hubspot/v1.0/contacts.yaml
  gdrive_csv/v1.0/deals_daily.yaml
  google_sheets/v1.0/vendors_master.yaml
  postgres/v1.0/db_orders.yaml


Notes:
• These job configs assume self-hosted execution with Dagster bundled (or oneshot).
• Secrets come from env/files (no secrets in YAML).
• Incremental strategy is always explicit and commented.
