# Tag Precedence & Override Hierarchy

## 🎯 Three-Level Tag Hierarchy

Tags flow from source systems through asset definitions to Iceberg table properties, with each level able to override the previous one.

```
Source System → Asset Definition → Job Configuration → Iceberg Properties
 (LOWEST)          (MEDIUM)            (HIGHEST)
```

---

## 📊 Precedence Order

### Level 1: Source System Tags (LOWEST PRIORITY)
**Source:** Connector metadata from source databases, APIs, etc.  
**When:** Connector reads metadata during extraction

**Example:**
```python
# PostgreSQL column comment
CREATE TABLE employees (
    email VARCHAR(255) COMMENT 'PII'
);

# Connector extracts:
source_tags = {
    "email": "PII"
}
```

### Level 2: Asset Definition (MEDIUM PRIORITY)
**Source:** Asset YAML files  
**When:** Asset definition is loaded

**Example:**
```yaml
# assets/employees.yaml
asset:
  schema:
    - name: email
      type: string
      classification: SENSITIVE_PII  # Overrides source "PII"
  
  compliance:
    classification: [PII, SENSITIVE]
  
  finops:
    cost_center: HR-001
```

### Level 3: Job Configuration (HIGHEST PRIORITY)
**Source:** Job YAML files  
**When:** Job execution time

**Example:**
```yaml
# jobs/employee_prod.yaml
classification_overrides:
  email: HIGH_PII  # Overrides asset "SENSITIVE_PII"

finops:
  cost_center: HR-PROD-001  # Overrides asset "HR-001"
  environment: production

governance_overrides:
  retention_days: 365  # Overrides asset default
```

---

## 🔄 Complete Example

### Scenario: Email field classification

```
┌─────────────────────────────────────────────────────────────┐
│ Level 1: Source System                                      │
│ PostgreSQL column comment: 'PII'                            │
│ Result: email → "PII"                                       │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Level 2: Asset Definition                                   │
│ schema.email.classification: "SENSITIVE_PII"                │
│ Result: email → "SENSITIVE_PII" (overrides source)          │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Level 3: Job Configuration                                  │
│ classification_overrides.email: "HIGH_PII"                  │
│ Result: email → "HIGH_PII" (overrides asset)                │
└─────────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Iceberg Table Property                                      │
│ classification.fields.email=high_pii                        │
└─────────────────────────────────────────────────────────────┘
```

---

## 📝 Detailed Examples

### Example 1: All Three Levels

**Source System (PostgreSQL):**
```sql
COMMENT ON COLUMN employees.email IS 'PII';
COMMENT ON COLUMN employees.salary IS 'SENSITIVE';
```

**Asset Definition:**
```yaml
schema:
  - name: email
    type: string
    classification: SENSITIVE_PII  # Override source "PII"
  
  - name: salary
    type: double
    # No classification - uses source "SENSITIVE"
  
  - name: ssn
    type: string
    classification: RESTRICTED  # Not in source - defined here
```

**Job Configuration:**
```yaml
classification_overrides:
  email: HIGH_PII  # Override asset "SENSITIVE_PII"
  # salary not mentioned - uses asset/source
  ssn: HIGHLY_RESTRICTED  # Override asset "RESTRICTED"
```

**Final Result:**
```properties
classification.fields.email=high_pii           # From job (Level 3)
classification.fields.salary=sensitive          # From source (Level 1)
classification.fields.ssn=highly_restricted     # From job (Level 3)
```

---

### Example 2: FinOps Metadata

**Source System:**
```python
# Source provides cost center from database metadata
source_metadata = {
    "cost_center": "ENG-001"
}
```

**Asset Definition:**
```yaml
finops:
  cost_center: HR-001  # Override source "ENG-001"
  business_tags: [hr, payroll]
  project: employee-platform
```

**Job Configuration:**
```yaml
finops:
  cost_center: HR-PROD-001  # Override asset "HR-001"
  environment: production   # Add new tag
  # business_tags not mentioned - uses asset
```

**Final Result:**
```properties
finops.cost_center=HR-PROD-001          # From job (Level 3)
finops.business_tags=hr,payroll          # From asset (Level 2)
finops.project=employee-platform         # From asset (Level 2)
finops.environment=production            # From job (Level 3)
```

---

### Example 3: Governance Metadata

**Asset Definition:**
```yaml
compliance:
  classification: [PII]
  retention_days: 90
  regulations: [GDPR, CCPA]

team:
  owner: data-team@company.com
```

**Job Configuration:**
```yaml
governance_overrides:
  retention_days: 365  # Override asset 90 days
  owner: hr-data-team@company.com  # Override asset owner
  # regulations not mentioned - uses asset
```

**Final Result:**
```properties
governance.retention_days=365                    # From job (Level 3)
governance.owner=hr-data-team@company.com        # From job (Level 3)
governance.regulations=GDPR,CCPA                 # From asset (Level 2)
classification.default=pii                        # From asset (Level 2)
```

---

## 🛠️ Implementation Details

### Tag Derivation Flow

```python
# src/dativo_ingest/tag_derivation.py

def derive_field_classifications(self) -> Dict[str, str]:
    """Three-level hierarchy for field classifications."""
    classifications = {}
    
    for field in self.asset_definition.schema:
        field_name = field["name"]
        
        # Level 3: Source system (LOWEST)
        if field_name in self.source_tags:
            classifications[field_name] = self.source_tags[field_name]
        
        # Level 2: Asset definition (MEDIUM - overrides source)
        if "classification" in field:
            classifications[field_name] = field["classification"]
        
        # Level 1: Job config (HIGHEST - overrides all)
        if field_name in self.classification_overrides:
            classifications[field_name] = self.classification_overrides[field_name]
    
    return classifications
```

### Connector Integration (Future)

```python
# Future: Connectors can provide source tags

class PostgresExtractor:
    def extract_metadata(self) -> Dict[str, str]:
        """Extract tags from PostgreSQL column comments."""
        source_tags = {}
        
        cursor.execute("""
            SELECT column_name, col_description(oid, ordinal_position)
            FROM information_schema.columns
            WHERE table_name = %s
        """, (table_name,))
        
        for column, comment in cursor.fetchall():
            if comment:
                source_tags[column] = comment
        
        return source_tags

# Usage in job execution
source_tags = connector.extract_metadata()  # Get from source
committer = IcebergCommitter(
    asset_definition=asset_definition,
    source_tags=source_tags,  # Pass to committer
    classification_overrides=job_config.classification_overrides,
)
```

---

## 🎯 Use Cases by Level

### When to Use Source System Tags

**Use for:**
- ✅ Default classifications from database schemas
- ✅ Metadata already maintained in source systems
- ✅ Organization-wide tagging standards
- ✅ Automated metadata discovery

**Example:**
```sql
-- DBA maintains tags in PostgreSQL
COMMENT ON COLUMN users.email IS 'PII';
COMMENT ON COLUMN transactions.amount IS 'FINANCIAL';
```

### When to Use Asset Definition Tags

**Use for:**
- ✅ Data contract specifications
- ✅ Override incorrect source metadata
- ✅ Add missing source metadata
- ✅ Standardize across different sources

**Example:**
```yaml
# Standardize classification across sources
schema:
  - name: email
    classification: PII  # Standard term across all sources
```

### When to Use Job Configuration Tags

**Use for:**
- ✅ Environment-specific tags (dev/staging/prod)
- ✅ Temporary overrides for testing
- ✅ Cost attribution by deployment
- ✅ Runtime governance decisions

**Example:**
```yaml
# Production job
classification_overrides:
  email: HIGH_PII  # Stricter in production

finops:
  environment: production
  cost_center: HR-PROD-001
```

---

## 📋 Tag Merge Rules

### Merging Behavior

1. **Field-level tags:** Exact override (no merging)
   ```yaml
   # Asset: email → "PII"
   # Job: email → "HIGH_PII"
   # Result: email → "HIGH_PII" (job wins, no merge)
   ```

2. **Object-level tags:** Field-by-field merge
   ```yaml
   # Asset finops:
   finops:
     cost_center: HR-001
     project: platform
   
   # Job finops:
   finops:
     cost_center: HR-PROD-001
     environment: production
   
   # Result:
   finops.cost_center=HR-PROD-001     # Job override
   finops.project=platform             # Asset preserved
   finops.environment=production       # Job added
   ```

3. **Arrays:** Replaced, not merged
   ```yaml
   # Asset:
   business_tags: [hr, payroll]
   
   # Job:
   business_tags: [hr, compliance]
   
   # Result:
   business_tags: [hr, compliance]  # Job replaces asset
   ```

---

## ✅ Best Practices

### 1. Choose the Right Level

| Scenario | Use Level |
|----------|-----------|
| Default classification | Source System |
| Data contract spec | Asset Definition |
| Prod vs dev differences | Job Configuration |
| Temporary testing | Job Configuration |
| Organization standard | Source System |
| Override incorrect source | Asset Definition |

### 2. Documentation

Always document why you're overriding:

```yaml
# Job configuration
classification_overrides:
  email: HIGH_PII  # Elevated for production compliance
  
governance_overrides:
  retention_days: 365  # Legal requirement: 1 year retention
```

### 3. Minimize Overrides

- Use source system tags when possible
- Asset definitions for stable overrides
- Job configs only for environment-specific needs

### 4. Audit Trail

All three levels are visible in logs:

```log
[INFO] Tag derivation for field 'email':
  Source: PII
  Asset: SENSITIVE_PII (override source)
  Job: HIGH_PII (override asset)
  Final: HIGH_PII
```

---

## 🔍 Querying Tags in Iceberg

All tags end up in Iceberg table properties:

```sql
-- Query table properties
SHOW TBLPROPERTIES my_table;

-- Specific tag
SHOW TBLPROPERTIES my_table('classification.fields.email');

-- All classification tags
SHOW TBLPROPERTIES my_table LIKE 'classification%';
```

---

## 📚 Related Documentation

- **Tag Propagation:** `/workspace/docs/TAG_PROPAGATION.md`
- **No Auto-Classification:** `/workspace/NO_AUTO_CLASSIFICATION.md`
- **ODCS Compliance:** `/workspace/ODCS_COMPLIANCE_REPORT.md`

---

_Updated: 2025-11-08_  
_Three-level tag hierarchy: Source → Asset → Job_
