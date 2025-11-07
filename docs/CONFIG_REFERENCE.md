# Configuration Reference

## Job Configuration (New Architecture)

Job configs define the source connector, target connector, asset, and tenant-specific overrides:

```yaml
tenant_id: acme
environment: prod

# Reference to source connector recipe
source_connector: hubspot
source_connector_path: /app/connectors/sources/hubspot.yaml

# Reference to target connector recipe
target_connector: iceberg
target_connector_path: /app/connectors/targets/iceberg.yaml

# Reference to asset definition
asset: hubspot_contacts
asset_path: /app/assets/hubspot/v1.0/contacts.yaml

# Tenant-specific overrides
source_overrides:
  objects: [contacts]
  incremental:
    lookback_days: 1

target_overrides:
  branch: acme
  warehouse: s3://lake/acme/
  connection:
    nessie:
      uri: "http://nessie.acme.internal:19120/api/v1"
    s3:
      bucket: "acme-data-lake"
      prefix: "raw/hubspot/contacts"

logging:
  redaction: true
  level: INFO
```

## Architecture

- **Connectors** (`/connectors/`): Tenant-agnostic recipes that define HOW to connect
- **Assets** (`/assets/`): Schema and governance definitions that define WHAT structure to ingest
- **Jobs** (`/jobs/<tenant>/`): Tenant-specific strategy implementations that compose connectors with assets
