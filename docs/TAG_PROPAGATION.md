# Source Tags → Asset Spec → Iceberg Properties

## Quick Start (5-Minute Setup)

### 1. Update Your Asset Definition

Add `finops` and `compliance` sections:

```yaml
asset:
  name: my_asset
  source_type: postgres
  object: my_table
  
  schema:
    - name: email
      type: string
      classification: PII  # Explicit classification
    - name: salary
      type: double
      classification: SENSITIVE
  
  compliance:
    classification: [PII, SENSITIVE]
    retention_days: 90
    regulations: [GDPR]
  
  finops:
    cost_center: FIN-001
    business_tags: [finance, reporting]
    project: my-project
    environment: production
```

### 2. (Optional) Add Job-Level Overrides

```yaml
tenant_id: my_tenant
asset_path: /app/assets/my_asset.yaml

# Override classifications
classification_overrides:
  email: high_pii
  salary: financial

# Override/add FinOps tags
finops:
  cost_center: FIN-002
  business_tags: [sensitive, regulated]
  environment: production

# Override governance
governance_overrides:
  retention_days: 365
```

### 3. Run Ingestion

```bash
dativo run --config my_job.yaml --mode self_hosted
```

### 4. Query Iceberg Properties

```sql
SELECT key, value
FROM system.metadata.table_properties
WHERE table_name = 'my_table'
  AND (key LIKE 'classification.%' OR key LIKE 'finops.%');
```

---

## Overview

This implementation ensures that metadata tags flow from source definitions through asset specs to Iceberg table properties, enabling automatic propagation to dbt and data catalogs.

## Why It Matters

- **Governance:** Keep PII/GDPR classifications consistent from source to storage
- **FinOps:** Maintain `cost_center` and `business_tags` for cost attribution
- **Compliance:** Track retention policies and regulatory requirements
- **Future-Proof:** dbt and Trino/Spark adapters can read these via Iceberg `table.properties`

📘 Reference: [Dremio — Extending Apache Iceberg with Metadata Properties](https://www.dremio.com/blog/extending-apache-iceberg/)

## Tag Namespaces

All tags are stored in Iceberg table properties using namespaced keys:

| Namespace | Purpose | Examples |
|-----------|---------|----------|
| `classification.*` | Sensitivity / PII classification | `classification.default=pii`<br>`classification.fields.email=pii` |
| `governance.*` | Retention / ownership / regulations | `governance.retention_days=365`<br>`governance.owner=team@company.com`<br>`governance.regulations=GDPR,CCPA` |
| `finops.*` | Cost attribution / tracking | `finops.cost_center=FIN-001`<br>`finops.business_tags=payments,revenue`<br>`finops.project=data-platform` |
| `asset.*` | Asset metadata | `asset.name=employees`<br>`asset.source_type=postgres`<br>`asset.version=1.0` |

## Implementation

### 1. Explicit Classification Only

**⚠️ IMPORTANT: NO AUTOMATIC CLASSIFICATION**

The tag derivation system does **NOT** perform automatic classification. All tags must be explicitly defined. This ensures:
- ✅ **No surprises** - You control exactly what gets tagged
- ✅ **Source of truth** - Tags from asset definitions or source metadata
- ✅ **No false positives** - Only tag what you explicitly define
- ✅ **Clear governance** - Classification decisions are documented

**What This Means:**

❌ This will **NOT** automatically classify email as PII:
```yaml
schema:
  - name: email
    type: string
```

✅ You **MUST** explicitly specify classification:
```yaml
schema:
  - name: email
    type: string
    classification: PII  # Must be explicit
```

**Where Tags Come From:**

Tags are **ONLY** collected from these explicit sources:

1. **Asset schema** - Field-level `classification` attribute
2. **Asset compliance** - Table-level classification
3. **Job config** - Classification overrides
4. **Source metadata** - Tags from source systems (via connectors, future)

**Migration from Auto-Detection:**

If you were relying on automatic detection, you need to update your asset definitions:

**Before (relied on auto-detection):**
```yaml
schema:
  - name: email
    type: string
  # Would auto-detect as PII ❌
```

**After (explicit required):**
```yaml
schema:
  - name: email
    type: string
    classification: PII  # ✅ Explicit
```

**Benefits of Explicit Tags:**

| Feature | Auto-Detection | Explicit Tags |
|---------|----------------|---------------|
| Requires setup | ❌ No | ✅ Yes |
| False positives | ⚠️ Possible | ✅ None |
| Customizable | ⚠️ Limited | ✅ Fully |
| Source metadata | ❌ No | ✅ Yes |
| Governance | ⚠️ Implicit | ✅ Explicit |
| Audit trail | ❌ Hard | ✅ Easy |

### 2. Asset Definition Structure

Assets support three metadata sections:

```yaml
asset:
  name: csv_employee
  source_type: csv
  object: Employee_Complete_Dataset
  version: "1.0"
  
  schema:
    - name: email
      type: string
      classification: PII  # Explicit field-level classification
    - name: salary
      type: double
      classification: SENSITIVE
  
  governance:
    owner: data-team@company.com
    tags: [employee, hr, test-data]
  
  compliance:
    classification: [PII, SENSITIVE]  # Table-level classifications
    retention_days: 90
    regulations: [GDPR, CCPA]
  
  finops:
    cost_center: HR-001
    business_tags: [hr, payroll]
    project: employee-data-platform
    environment: production
```

### 3. Job-Level Overrides

Job configurations can override or extend asset-level tags:

```yaml
tenant_id: acme
asset_path: /app/assets/csv/v1.0/employee.yaml

# Override field-level classifications
classification_overrides:
  email: high_pii
  salary: financial
  default: pii  # Override table-level default

# FinOps metadata (merged with asset finops)
finops:
  cost_center: HR-001
  business_tags: [hr, payroll, compliance]
  project: employee-data-platform
  environment: production

# Governance overrides
governance_overrides:
  retention_days: 365  # Override asset retention
  owner: hr-data-team@acme.com
```

### 4. Iceberg Table Properties

Tags are written as Iceberg table properties and merged idempotently:

```properties
# Classification tags
classification.default=pii
classification.fields.email=high_pii
classification.fields.phone_number=high_pii
classification.fields.salary=financial

# Governance tags
governance.retention_days=365
governance.owner=hr-data-team@acme.com
governance.regulations=GDPR,CCPA

# FinOps tags
finops.cost_center=HR-001
finops.business_tags=hr,payroll,compliance
finops.project=employee-data-platform
finops.environment=production

# Asset metadata
asset.name=csv_employee
asset.version=1.0
asset.source_type=csv
asset.object=Employee_Complete_Dataset
```

## Query Table Properties

Use Iceberg's metadata tables to query properties:

```sql
-- Trino / Spark
SELECT key, value
FROM system.metadata.table_properties
WHERE table_name = 'employees'
  AND key LIKE 'classification.%'
  OR key LIKE 'governance.%'
  OR key LIKE 'finops.%';
```

## dbt Integration (Future)

dbt can read and propagate these tags:

```yaml
# dbt model configuration
models:
  - name: employees
    meta:
      # Auto-populated from Iceberg properties
      classification: "{{ source_classification }}"
      pii_fields: "{{ source_pii_fields }}"
      cost_center: "{{ source_cost_center }}"
      retention_days: "{{ source_retention_days }}"
```

## Tag Precedence

Tags are merged in this order (later overrides earlier):

1. **Asset schema** explicit field-level classifications
2. **Asset compliance** section for table-level defaults
3. **Asset finops** section for cost attribution
4. **Job-level overrides** from job configuration

**NO AUTOMATIC DETECTION:** All tags must be explicitly defined.

## Security Notes

- **Never include actual PII values** in tags - only classifications
- Tags are **metadata only** and don't modify data
- All tag values are stored as **strings** in Iceberg properties
- Properties are **merged idempotently** - existing unrelated properties are preserved

## Examples

### Example 1: Basic Asset with Explicit Classifications

```yaml
asset:
  schema:
    - name: email
      classification: PII          # Must be explicit
    - name: first_name
      classification: PII          # Must be explicit
    - name: salary
      classification: SENSITIVE    # Must be explicit
```

**Result:**
```properties
classification.fields.email=pii
classification.fields.first_name=pii
classification.fields.salary=sensitive
```

### Example 2: Explicit Classifications

```yaml
asset:
  schema:
    - name: customer_id
      classification: INTERNAL
    - name: ssn
      classification: HIGH_PII
  compliance:
    classification: [HIGH_PII, INTERNAL]
```

**Result:**
```properties
classification.default=high_pii
classification.fields.customer_id=internal
classification.fields.ssn=high_pii
```

### Example 3: Job-Level Overrides

```yaml
# Job config
classification_overrides:
  ssn: restricted
finops:
  cost_center: SECURITY-001
```

**Result:**
```properties
classification.fields.ssn=restricted  # Overridden
finops.cost_center=SECURITY-001       # Added from job
```

## API Usage

### Python API

```python
from dativo_ingest.tag_derivation import derive_tags_from_asset
from dativo_ingest.config import AssetDefinition

# Load asset
asset = AssetDefinition.from_yaml("assets/employee.yaml")

# Derive all tags
tags = derive_tags_from_asset(
    asset_definition=asset,
    classification_overrides={"email": "high_pii"},
    finops={"cost_center": "HR-001"},
    governance_overrides={"retention_days": 365},
)

# tags = {
#     "classification.default": "pii",
#     "classification.fields.email": "high_pii",
#     "governance.retention_days": "365",
#     "finops.cost_center": "HR-001",
#     ...
# }
```

### IcebergCommitter Integration

Tags are automatically applied when creating or updating tables:

```python
from dativo_ingest.iceberg_committer import IcebergCommitter

committer = IcebergCommitter(
    asset_definition=asset,
    target_config=target_config,
    classification_overrides={"email": "high_pii"},
    finops={"cost_center": "HR-001"},
    governance_overrides={"retention_days": 365},
)

# Properties are set during table creation
committer.ensure_table_exists()

# Properties are updated during commits (idempotent)
committer.commit_files(file_metadata)
```

## Data Catalog Publishing

Set the `catalog` block in your job configuration to push the derived metadata (classifications, owners, FinOps, lineage edges) into external catalog systems immediately after each successful run:

- **AWS Glue** – Parameters are updated via `UpdateTable`, making tags/owners queryable in Glue Data Catalog.
- **Databricks Unity Catalog** – Lineage payloads (including column mappings) are pushed through the `/unity-catalog/lineage` REST API.
- **Nessie** – Table properties inside Nessie/PyIceberg are refreshed even if the target catalog is not used for commits.
- **OpenMetadata** – Lineage edges and metadata are posted to `/api/v1/lineage/addLineage`. A local smoke test is available via `pytest tests/test_data_catalogs.py::test_openmetadata_publisher_smoke`.

Example job snippet:

```yaml
catalog:
  targets:
    - type: aws_glue
      database: analytics
      table: employee_profile
      region: us-east-1
    - type: openmetadata
      service: demo_lake
      database: analytics
      schema: hr
      table: employee_profile
      uri: http://localhost:8585/api
```

## Testing

Run the tag derivation tests:

```bash
pytest tests/test_tag_derivation.py -v
```

Example test output:
```
tests/test_tag_derivation.py::test_derive_field_classifications PASSED
tests/test_tag_derivation.py::test_derive_default_classification PASSED
tests/test_tag_derivation.py::test_derive_governance_tags PASSED
tests/test_tag_derivation.py::test_derive_finops_tags PASSED
tests/test_tag_derivation.py::test_derive_all_tags PASSED
```

## Next Steps

1. **Catalog Integration:** Configure one or more catalog targets via the `catalog` block (Glue, Unity, Nessie, OpenMetadata)
2. **dbt Macros:** Create dbt macros to propagate tags to downstream models
3. **Monitoring:** Set up alerts for tables missing required classifications
4. **Audit:** Query Iceberg properties to ensure compliance across all tables

## References

- [Iceberg Table Properties Documentation](https://iceberg.apache.org/docs/latest/configuration/)
- [Dremio: Extending Apache Iceberg with Metadata Properties](https://www.dremio.com/blog/extending-apache-iceberg/)
- [PyIceberg Documentation](https://py.iceberg.apache.org/)
