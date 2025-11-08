# Tag Propagation Testing

This directory includes tests to verify that tags are properly propagated from source systems through asset definitions to Iceberg table properties.

---

## Test Files

### 1. `test_tag_propagation_smoke.py`
**Type:** Unit/Integration test  
**Purpose:** Test tag derivation logic with pytest

**Tests:**
- ✅ Basic tag derivation from asset definitions
- ✅ Three-level hierarchy (Source → Asset → Job)
- ✅ Explicit tags only (no auto-detection)
- ✅ Job override precedence
- ✅ Asset metadata tags

**Run:**
```bash
pytest tests/test_tag_propagation_smoke.py -v
```

---

### 2. `verify_tag_propagation.py`
**Type:** E2E verification script  
**Purpose:** Verify tags in actual Iceberg tables via Nessie catalog

**Verifies:**
- ✅ Tags exist in Iceberg table properties
- ✅ Tag values match expected values
- ✅ Classification, governance, and finops tags

**Run:**
```bash
# Set environment
export NESSIE_URI=http://localhost:19120/api/v1
export WAREHOUSE=s3://test-bucket/warehouse

# Run verification
python tests/verify_tag_propagation.py
```

**Requirements:**
- PyIceberg installed
- Nessie catalog running
- Tables created by smoke tests

---

### 3. `smoke_tests.sh`
**Type:** End-to-end smoke test  
**Purpose:** Run CLI with test fixtures + verify tag propagation

**Flow:**
1. Run ingestion jobs from `tests/fixtures/jobs/`
2. Verify jobs completed successfully
3. If Nessie available, verify tags in tables
4. Cleanup temporary files

**Run:**
```bash
bash tests/smoke_tests.sh
```

**Enhanced Output:**
```
╔══════════════════════════════════════════════════════════════════════╗
║                         SMOKE TESTS                                   ║
╚══════════════════════════════════════════════════════════════════════╝

📦 Running ingestion jobs...
✅ Ingestion jobs completed successfully

🔍 Verifying tag propagation...
  ✓ classification.default=pii
  ✓ governance.retention_days=90
  ✓ finops.cost_center=HR-001

✅ Tag propagation verified

╔══════════════════════════════════════════════════════════════════════╗
║                    ✅ SMOKE TESTS PASSED                             ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Test Hierarchy

### Level 1: Unit Tests (Fastest)
**File:** `test_tag_propagation_smoke.py`  
**Duration:** < 5 seconds  
**Dependencies:** None (pure Python)

Tests the tag derivation logic without external dependencies.

```bash
pytest tests/test_tag_propagation_smoke.py -v
```

### Level 2: Integration Tests
**Directory:** `tests/integration/`  
**Duration:** < 60 seconds  
**Dependencies:** PYTHONPATH=src

Tests module integration and system integration.

```bash
make test-integration
```

### Level 3: Smoke Tests (E2E)
**File:** `smoke_tests.sh`  
**Duration:** Variable (depends on data size)  
**Dependencies:** Full stack (Postgres, MySQL, MinIO, Nessie)

Tests the complete system with real data and services.

```bash
make test-smoke
```

---

## Tag Hierarchy Tested

### Source System Tags (LOWEST Priority)
```python
# From connector metadata
source_tags = {
    "email": "PII",
    "phone": "PII"
}
```

### Asset Definition Tags (MEDIUM Priority)
```yaml
# In asset YAML
schema:
  - name: email
    classification: SENSITIVE_PII  # Overrides source "PII"
```

### Job Configuration Tags (HIGHEST Priority)
```yaml
# In job YAML
classification_overrides:
  email: HIGH_PII  # Overrides asset "SENSITIVE_PII"
```

---

## Test Coverage

### What's Tested ✅

| Feature | Unit Test | Integration Test | Smoke Test |
|---------|-----------|------------------|------------|
| Tag derivation | ✅ | ✅ | ✅ |
| Three-level hierarchy | ✅ | ✅ | ✅ |
| Explicit tags only | ✅ | ✅ | - |
| Job overrides | ✅ | ✅ | ✅ |
| FinOps tags | ✅ | ✅ | ✅ |
| Governance tags | ✅ | ✅ | ✅ |
| Asset metadata | ✅ | ✅ | ✅ |
| Iceberg properties | - | - | ✅ |
| Nessie catalog | - | - | ✅ |

### What's NOT Tested ❌

- **Source system tag extraction** - Future (needs connector support)
- **dbt meta propagation** - Future (needs dbt integration)
- **Data catalog integration** - Future (needs catalog integration)

---

## CI/CD Integration

### GitHub Actions

**Workflow:** `.github/workflows/tests.yml`

```yaml
- name: Run smoke tests
  run: make test-smoke
  env:
    NESSIE_URI: http://localhost:19120/api/v1
    WAREHOUSE: s3://test-bucket/warehouse
```

**Workflow:** `.github/workflows/integration-tests.yml`

```yaml
- name: Run tag propagation tests
  run: pytest tests/test_tag_propagation_smoke.py -v
```

---

## Example Test Output

### Unit Test
```bash
$ pytest tests/test_tag_propagation_smoke.py -v

tests/test_tag_propagation_smoke.py::test_tag_derivation_basic PASSED
tests/test_tag_propagation_smoke.py::test_tag_hierarchy_source_to_job PASSED
tests/test_tag_propagation_smoke.py::test_explicit_tags_only PASSED
tests/test_tag_propagation_smoke.py::test_job_override_precedence PASSED
tests/test_tag_propagation_smoke.py::test_asset_metadata_tags PASSED

========================= 5 passed in 0.12s =========================
```

### E2E Verification
```bash
$ python tests/verify_tag_propagation.py

======================================================================
TAG PROPAGATION VERIFICATION
======================================================================

Nessie URI: http://localhost:19120/api/v1
Warehouse: s3://test-bucket/warehouse

🔍 Verifying tags for test_tenant.csv_employee...
  ✓ classification.default=pii
  ✓ governance.retention_days=90
  ✓ finops.cost_center=HR-001
  ✓ asset.name=csv_employee
  ✓ asset.source_type=csv

  📋 All classification tags:
     classification.default=pii
     classification.fields.email=pii

  📋 All governance tags:
     governance.owner=data-team@company.com
     governance.retention_days=90

  📋 All finops tags:
     finops.business_tags=hr,payroll
     finops.cost_center=HR-001
     finops.environment=production
     finops.project=employee-data-platform

======================================================================
VERIFICATION SUMMARY
======================================================================
✓ PASS     csv_employee
✓ PASS     stripe_customers

✅ All 2 tag verification tests passed!
```

---

## Debugging

### Check Tags in Iceberg

**Using Spark SQL:**
```sql
SHOW TBLPROPERTIES my_table;
SHOW TBLPROPERTIES my_table('classification.default');
SHOW TBLPROPERTIES my_table LIKE 'classification%';
```

**Using PyIceberg:**
```python
from pyiceberg.catalog import load_catalog

catalog = load_catalog("nessie", uri="http://localhost:19120/api/v1")
table = catalog.load_table("test_tenant.csv_employee")
properties = table.properties

# Show all tags
for key, value in sorted(properties.items()):
    if key.startswith(('classification', 'governance', 'finops', 'asset')):
        print(f"{key}={value}")
```

### Common Issues

**Issue:** Tags not showing up in Iceberg  
**Solution:** Check that `IcebergCommitter._derive_table_properties()` is being called

**Issue:** Tags have wrong values  
**Solution:** Check precedence - job overrides > asset > source

**Issue:** PyIceberg import error in verification  
**Solution:** Expected - verification is skipped if PyIceberg not installed

---

## Future Enhancements

### Planned
- [ ] Source system tag extraction from connectors
- [ ] Verify tags in dbt meta
- [ ] Data catalog integration tests
- [ ] Tag audit trail logging
- [ ] Tag diff between runs

### Nice to Have
- [ ] Tag visualization in CI
- [ ] Tag coverage reports
- [ ] Performance benchmarks
- [ ] Load testing with many tags

---

## Related Documentation

- **Tag Precedence:** `/workspace/docs/TAG_PRECEDENCE.md`
- **Tag Propagation:** `/workspace/docs/TAG_PROPAGATION.md`
- **Test Organization:** `/workspace/TEST_ORGANIZATION_SUMMARY.md`

---

_Updated: 2025-11-08_  
_Tag propagation testing complete_
