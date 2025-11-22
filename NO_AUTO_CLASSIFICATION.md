# ⚠️ NO AUTOMATIC CLASSIFICATION

## Important Change

**The tag derivation system does NOT perform automatic classification.** All tags must be explicitly defined.

---

## What This Means

### ❌ NOT Supported
```yaml
# This will NOT automatically classify email as PII
schema:
  - name: email
    type: string
```

### ✅ Supported - Explicit Classification
```yaml
# You MUST explicitly specify classification
schema:
  - name: email
    type: string
    classification: PII  # Explicit tag required
```

---

## Where Tags Come From

Tags are ONLY collected from these sources:

### 1. Asset Schema (Field-Level)
```yaml
schema:
  - name: email
    type: string
    classification: PII  # Explicit field tag
```

### 2. Asset Compliance (Table-Level)
```yaml
compliance:
  classification: [PII, SENSITIVE]  # Explicit table tags
```

### 3. Asset FinOps
```yaml
finops:
  cost_center: HR-001
  business_tags: [hr, payroll]
```

### 4. Job-Level Overrides
```yaml
# In job configuration
classification_overrides:
  email: high_pii
  salary: financial
```

---

## Migration Guide

If you were relying on automatic detection:

### Before (Auto-Detection - NO LONGER WORKS)
```yaml
schema:
  - name: email
    type: string
  # email was auto-detected as PII
```

### After (Explicit Tags - REQUIRED)
```yaml
schema:
  - name: email
    type: string
    classification: PII  # Now required
```

---

## Why This Change?

**Benefits of Explicit Tags:**
1. ✅ **No surprises** - You control all classifications
2. ✅ **Source of truth** - Tags come from asset definitions or source metadata
3. ✅ **No false positives** - Only tag what you explicitly define
4. ✅ **Clear governance** - Classification decisions are explicit and documented

**Use Cases:**
- Tags from source systems (database metadata, API responses)
- Organization-specific classification schemes
- Manual governance workflows
- Compliance-driven tagging

---

## Quick Reference

| Source | Automatic? | Explicit? | Supported? |
|--------|-----------|-----------|------------|
| Field name patterns (email, phone) | ✅ Was | ❌ Now | ❌ **NO** |
| Asset schema classification | ❌ Never | ✅ Always | ✅ **YES** |
| Asset compliance section | ❌ Never | ✅ Always | ✅ **YES** |
| Job-level overrides | ❌ Never | ✅ Always | ✅ **YES** |
| Source metadata | ❌ Never | ✅ Always | ✅ **YES*** |

\* Source metadata support depends on connector implementation

---

## Examples

### ✅ Correct: Explicit Field Classifications
```yaml
asset:
  schema:
    - name: customer_id
      type: integer
      # No classification - will not be tagged
    
    - name: email
      type: string
      classification: PII  # Explicit
    
    - name: salary
      type: double
      classification: SENSITIVE  # Explicit
```

**Result:**
```properties
classification.fields.email=pii
classification.fields.salary=sensitive
# customer_id has no classification property
```

### ✅ Correct: Table-Level Classification
```yaml
asset:
  compliance:
    classification: [PII]  # Explicit table-level
```

**Result:**
```properties
classification.default=pii
```

### ✅ Correct: Job-Level Overrides
```yaml
# Job configuration
classification_overrides:
  email: high_pii
  phone: pii
  ssn: restricted
```

**Result:**
```properties
classification.fields.email=high_pii
classification.fields.phone=pii
classification.fields.ssn=restricted
```

---

## For Connector Developers

If you're implementing a connector that reads tags from source systems:

```python
# Read tags from source (e.g., database column comments)
source_tags = {
    "email": "PII",
    "ssn": "RESTRICTED"
}

# Pass them as classification_overrides to job
job_config = JobConfig(
    ...
    classification_overrides=source_tags
)
```

This allows tags from source systems to flow through without automatic detection.

---

## Summary

**Key Points:**
- ❌ NO automatic field name pattern matching
- ✅ ALL tags must be explicitly defined
- ✅ Use asset schema, compliance section, or job overrides
- ✅ Source metadata can provide tags via connectors

**Documentation:**
- Main guide: `/workspace/docs/TAG_PROPAGATION.md`
- Implementation: `/workspace/src/dativo_ingest/tag_derivation.py`

---

_Updated: 2025-11-08_  
_No automatic classification - explicit tags only_
