# Tag Propagation Quick Start

## 🚀 5-Minute Setup

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
      # Auto-detected as SENSITIVE
  
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
dativo-ingest run --config my_job.yaml
```

### 4. Query Iceberg Properties

```sql
SELECT key, value
FROM system.metadata.table_properties
WHERE table_name = 'my_table'
  AND key LIKE 'classification.%'
  OR key LIKE 'finops.%';
```

## 📋 Tag Reference

### Auto-Detected PII Fields
- `email`, `phone`, `mobile`
- `first_name`, `last_name`
- `ssn`, `passport`, `drivers_license`
- `address`, `zip_code`
- `credit_card`, `account_number`

### Auto-Detected Sensitive Fields
- `salary`, `compensation`
- `revenue`, `cost`, `amount`
- `balance`, `profit`

### Tag Namespaces
- `classification.*` - PII/sensitivity
- `governance.*` - Retention/owner
- `finops.*` - Cost attribution
- `asset.*` - Asset metadata

## 📚 Full Documentation

See `/workspace/docs/TAG_PROPAGATION.md` for complete details.

## 🧪 Validate

```bash
python3 validate_tag_derivation.py
```

## 💡 Examples

See:
- `/workspace/assets/csv/v1.0/employee.yaml`
- `/workspace/docs/examples/jobs/acme/employee_with_overrides.yaml`
