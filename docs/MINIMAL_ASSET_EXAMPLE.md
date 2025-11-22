# Minimal Asset Definition Example

This guide shows the **minimal required fields** for creating an asset definition. Start here, then add optional fields as needed.

## Minimal Working Example

```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: my_asset
version: "1.0"
source_type: csv
object: my_object
schema:
  - name: id
    type: integer
    required: true
  - name: name
    type: string
    required: true
target:
  file_format: parquet
  partitioning: [ingest_date]
team:
  owner: your-email@company.com
compliance:
  classification: []
```

## Required Fields Explained

### Basic Metadata
- `$schema`: Path to ODCS schema (always use this)
- `apiVersion`: ODCS version (always `v3.0.2`)
- `kind`: Always `DataContract`
- `name`: Unique asset name
- `version`: Semantic version (e.g., "1.0")

### Source Configuration
- `source_type`: Connector type (csv, stripe, postgres, etc.)
- `object`: Object name within the source

### Schema Definition
- `schema`: List of fields with:
  - `name`: Field name
  - `type`: Data type (string, integer, double, date, timestamp)
  - `required`: true/false

### Target Configuration
- `target.file_format`: Output format (parquet)
- `target.partitioning`: Partition columns (usually `[ingest_date]`)

### Governance (Required)
- `team.owner`: Email of data owner
- `compliance.classification`: List of classifications (empty `[]` if none)

## Adding Optional Fields

Once you have a working minimal asset, you can add:

### Field Classifications
```yaml
schema:
  - name: email
    type: string
    required: true
    classification: PII  # Mark sensitive fields
```

### Compliance Details
```yaml
compliance:
  classification: [PII]
  regulations: [GDPR, CCPA]
  retention_days: 90
```

### Data Quality
```yaml
data_quality:
  monitoring:
    enabled: true
    oncall_rotation: data-ops@company.com
```

### FinOps Tags
```yaml
finops:
  cost_center: "ENG-001"
  business_tags: [engineering, analytics]
```

## Validation

Validate your asset definition:
```bash
make schema-validate
```

## Full Example

See `assets/csv/v1.0/employee.yaml` for a complete example with all optional fields.

