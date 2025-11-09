# DBT-GenAI Integration & ODCS v3.0.2 Compliance

## Overview

This document describes the DBT-GenAI Integration features that extend Dativo Ingest to support AI-assisted analytics workflows while maintaining full ODCS v3.0.2 compliance.

## 🎯 Purpose

Extend Dativo Ingest to support dbt-GenAI workflows while remaining fully ODCS v3.0.2 compliant — linking data contracts, lineage, cost telemetry and governance for AI-assisted analytics.

## 🏗️ Architecture

### Components

1. **Contract Management** (`contracts.py`)
   - Semantic versioning for data contracts
   - Breaking change detection
   - Version history and comparison
   - Storage under `/specs/<source>/vMAJOR.MINOR/`

2. **DBT Integration** (`dbt_integration.py`)
   - Generate dbt-compatible YAML (sources, models, exposures)
   - Preserve classification and ownership tags
   - Map ODCS v3.0.2 → dbt YAML

3. **Lineage Tracking** (`lineage.py`)
   - End-to-end lineage from Ingest → Iceberg → dbt → Downstream
   - OpenLineage format export
   - Upstream/downstream traversal

4. **AI Context API** (`ai_context_api.py`)
   - Policy-guarded metadata access
   - Schema, classification, lineage, governance status
   - FinOps metrics exposure
   - Search and discovery

5. **FinOps Integration** (`finops.py`)
   - Cost tracking (compute, storage, network, API)
   - Anomaly detection
   - Cost attribution by tenant/job
   - Billing export format

## 🚀 Quick Start

### 1. Define ODCS v3.0.2 Compliant Asset

```yaml
# assets/stripe/v1.0/customers.yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
id: stripe-customers-001
name: stripe_customers
version: "1.0.0"
status: active
source_type: stripe
object: customers

# Governance
team:
  owner: data-team@company.com
  roles:
    - name: Data Steward
      email: steward@company.com
      responsibility: Data quality oversight

compliance:
  classification: [PII, SENSITIVE]
  regulations: [GDPR, CCPA]
  retention_days: 90
  security:
    access_control: role_based
    encryption_required: true
  user_consent_required: true

# Schema
schema:
  - name: id
    type: string
    required: true
    unique: true
    description: Unique customer identifier
  
  - name: email
    type: string
    required: true
    classification: PII
    description: Customer email address
  
  - name: created_at
    type: timestamp
    required: true
    description: Account creation timestamp

# Data Quality
data_quality:
  monitoring:
    enabled: true
    oncall_rotation: data-oncall@company.com
  expectations:
    - type: not_null
      column: id
    - type: unique
      column: id
    - type: accepted_values
      column: status
      values: [active, inactive, suspended]

# Change Management
change_management:
  policy: non-breaking
  approval_required: true
  notification_channels: [slack, email]
  version_history: true

# Metadata
description:
  purpose: Customer data from Stripe payments platform
  usage: Analytics, reporting, ML training
  limitations: Historical data limited to 90 days

tags: [stripe, customers, payments]
domain: customer-data
dataProduct: customer-360
```

### 2. Save Contract with Versioning

```python
from dativo_ingest.contracts import ContractManager
from dativo_ingest.config import AssetDefinition

# Load asset definition
asset = AssetDefinition.from_yaml("assets/stripe/v1.0/customers.yaml")

# Initialize contract manager
manager = ContractManager(specs_dir="/specs")

# Save contract (with breaking change detection)
version = manager.save_contract(
    contract=asset,
    author="data-engineer@company.com",
    force=False  # Fail if breaking changes detected
)

print(f"Contract saved: {version.version} ({version.change_type})")
```

### 3. Generate DBT YAML

```python
from dativo_ingest.dbt_integration import DBTGenerator

generator = DBTGenerator(output_dir="/dbt")

# Generate source YAML
generator.save_dbt_yaml(
    asset=asset,
    yaml_type="source",
    catalog_name="raw_stripe"
)

# Generate staging model YAML
generator.save_dbt_yaml(
    asset=asset,
    yaml_type="model",
    model_name="stg_stripe_customers"
)

# Generate exposure YAML
generator.save_dbt_yaml(
    asset=asset,
    yaml_type="exposure"
)
```

### 4. Track Lineage

```python
from dativo_ingest.lineage import LineageTracker

tracker = LineageTracker()

# Add nodes
source_node = tracker.add_source_node("stripe", "customers")
asset_node = tracker.add_asset_node(asset)
transform_node = tracker.add_transformation_node("schema_validation")
target_node = tracker.add_target_node("iceberg", "bronze", "stripe_customers")

# Add edges
tracker.add_edge(source_node, asset_node, "validates_against")
tracker.add_edge(asset_node, transform_node, "applies")
tracker.add_edge(transform_node, target_node, "writes_to")

# Record run
lineage_record = tracker.record_run(
    tenant_id="acme",
    job_name="stripe-customers-ingest",
    status="success",
    metrics={"records_processed": 10000}
)
```

### 5. Collect FinOps Metrics

```python
from dativo_ingest.finops import FinOpsMetrics

finops = FinOpsMetrics(
    tenant_id="acme",
    job_name="stripe-customers-ingest",
    cost_center="analytics"
)

finops.start()

# Record resource usage
finops.record_cpu_time(120.5)  # seconds
finops.record_memory_usage(1024.0)  # MB
finops.record_data_ingested(1024 * 1024 * 1024)  # 1GB
finops.record_data_written(512 * 1024 * 1024)  # 512MB
finops.record_api_calls(1000, api_type="stripe")

# Finish and get cost breakdown
summary = finops.finish()
print(f"Total cost: ${summary['cost_breakdown_usd']['total']:.6f}")
```

### 6. Access Metadata via AI Context API

```python
from dativo_ingest.ai_context_api import AIContextAPI, PolicyGuard

# Configure policy
policy = PolicyGuard({
    "allowed_requesters": ["ai-agent-1", "analyst-bot"],
    "restricted_classifications": ["PII", "SENSITIVE"],
    "elevated_requesters": ["admin-bot"]
})

api = AIContextAPI(policy_guard=policy)

# Get asset context
context = api.get_asset_context(
    source_type="stripe",
    object_name="customers",
    version="1.0.0",
    requester="ai-agent-1"
)

print(f"Schema fields: {context['schema']['field_count']}")
print(f"Owner: {context['governance']['owner']}")
print(f"Classification: {context['governance']['classification']}")

# Search for assets
results = api.search_assets(
    classification=["PII"],
    tags=["stripe"],
    requester="ai-agent-1",
    limit=10
)
```

## 📋 ODCS v3.0.2 Compliance Checklist

### Required Fields
- ✅ `apiVersion`: v3.0.2
- ✅ `kind`: DataContract
- ✅ `id`: Unique identifier (UUID)
- ✅ `version`: Semantic version (MAJOR.MINOR.PATCH)
- ✅ `status`: active, proposed, deprecated, retired
- ✅ `team.owner`: Strong ownership requirement

### Schema Requirements
- ✅ Each field must have `name` and `type`
- ✅ Support for `required`, `unique`, `classification`
- ✅ Typed fields (string, integer, float, boolean, date, timestamp)
- ✅ Field-level data quality tests

### Governance & Compliance
- ✅ Classification tags (PII, SENSITIVE, PUBLIC, etc.)
- ✅ Retention policies (`retention_days`)
- ✅ Regulations (GDPR, CCPA, HIPAA)
- ✅ Security configuration (access control, encryption)
- ✅ User consent tracking

### Lineage & Audit
- ✅ `from_asset` and `to_asset` relationships
- ✅ Contract version tracking
- ✅ Author and timestamp for all changes
- ✅ Change type (breaking vs non-breaking)

### Data Quality
- ✅ Monitoring configuration
- ✅ On-call rotation
- ✅ Data quality expectations/rules
- ✅ Alert channels and thresholds

## 🔄 Semantic Versioning for Contracts

### Version Bump Rules

**MAJOR version** (breaking changes):
- Removing required fields
- Changing field types
- Making optional fields required
- Removing fields that downstream depends on

**MINOR version** (non-breaking changes):
- Adding new optional fields
- Relaxing constraints
- Adding documentation

**PATCH version** (no structural changes):
- Documentation updates
- Metadata changes
- Non-functional updates

### Example

```python
# Initial version: 1.0.0
asset_v1 = AssetDefinition(
    version="1.0.0",
    schema=[
        {"name": "id", "type": "string", "required": True},
        {"name": "email", "type": "string", "required": True},
    ]
)

# Add optional field → 1.1.0 (non-breaking)
asset_v11 = AssetDefinition(
    version="1.1.0",
    schema=[
        {"name": "id", "type": "string", "required": True},
        {"name": "email", "type": "string", "required": True},
        {"name": "phone", "type": "string", "required": False},  # New optional field
    ]
)

# Remove required field → 2.0.0 (breaking)
asset_v2 = AssetDefinition(
    version="2.0.0",
    schema=[
        {"name": "id", "type": "string", "required": True},
        # email field removed - BREAKING CHANGE
    ]
)
```

## 🤖 AI Agent Integration

### Metadata Access Pattern

```python
# AI agent retrieves context
context = api.get_asset_context(
    source_type="stripe",
    object_name="customers",
    requester="analytics-bot"
)

# Agent uses metadata to generate SQL
agent_prompt = f"""
Generate SQL query for the following table:

Schema: {context['schema']['fields']}
Owner: {context['governance']['owner']}
Classification: {context['governance']['classification']}

Note: This table contains {context['governance']['classification']} data.
Ensure compliance with retention policy: {context['governance']['retention_days']} days.
"""

# Agent generates compliant query
sql = generate_sql(agent_prompt)
```

### Policy-Guarded Access

```python
# Configure fine-grained access control
policy = PolicyGuard({
    "allowed_requesters": ["analytics-bot", "ml-training-agent"],
    "restricted_classifications": ["PII", "SENSITIVE"],
    "elevated_requesters": ["admin-bot", "compliance-agent"],
})

# Attempt to access PII data
try:
    context = api.get_asset_context(
        source_type="stripe",
        object_name="customers",
        requester="untrusted-agent"  # Not in elevated_requesters
    )
except PermissionError as e:
    print(f"Access denied: {e}")
```

## 💰 FinOps & Cost Attribution

### Cost Tracking

```python
finops = FinOpsMetrics("acme", "stripe-ingest", cost_center="analytics")
finops.start()

# ... run ingestion ...

summary = finops.finish()

# Cost breakdown
print(summary['cost_breakdown_usd'])
# {
#   'compute': 0.002778,
#   'storage': 0.000012,
#   'network': 0.000090,
#   'api': 0.000004,
#   'total': 0.002884
# }

# Cost per metric
print(summary['cost_per_metric'])
# {
#   'cost_per_gb_ingested': 0.002884,
#   'cost_per_api_call': 0.000003
# }
```

### Anomaly Detection

```python
# Compare against historical metrics
anomalies = finops.detect_anomalies(historical_metrics)

for anomaly in anomalies:
    if anomaly['severity'] == 'high':
        print(f"⚠️ {anomaly['type']}: {anomaly['message']}")
        alert_oncall(anomaly)
```

## 📊 DBT Integration

### Generated Source YAML

```yaml
# models/staging/stripe__customers.yml
version: 2

sources:
  - name: raw_stripe
    description: Stripe data source
    tables:
      - name: customers
        description: Customer data from Stripe
        columns:
          - name: id
            data_type: string
            description: Unique customer identifier
            tests:
              - not_null
              - unique
          
          - name: email
            data_type: string
            description: Customer email address
            tests:
              - not_null
            tags:
              - pii
        
        meta:
          owner: data-team@company.com
          contract_version: "1.0.0"
          odcs_version: v3.0.2
          classification: [PII, SENSITIVE]
          retention_days: 90
          regulations: [GDPR, CCPA]
        
        tags:
          - stripe
          - customers
          - pii
          - sensitive
```

### Generated Model YAML

```yaml
# models/staging/stg_stripe_customers.yml
version: 2

models:
  - name: stg_stripe_customers
    description: Staging model for Stripe customers
    columns:
      - name: id
        data_type: string
        tests:
          - not_null
          - unique
      
      - name: email
        data_type: string
        tests:
          - not_null
        tags:
          - pii
    
    meta:
      owner: data-team@company.com
      contract_version: "1.0.0"
      contract_id: stripe-customers-001
      classification: [PII, SENSITIVE]
      monitoring:
        enabled: true
        oncall: data-oncall@company.com
    
    tags:
      - stripe
      - customers
      - pii
```

## 🔍 Lineage Visualization

### End-to-End Lineage

```
Source                    Asset Contract           Transformation         Target
┌──────────────┐         ┌────────────────┐       ┌──────────────┐       ┌──────────────────┐
│ Stripe API   │────────▶│ ODCS v3.0.2    │──────▶│ Schema       │──────▶│ Iceberg Table    │
│ /customers   │         │ Contract v1.0  │       │ Validation   │       │ bronze.customers │
└──────────────┘         └────────────────┘       └──────────────┘       └──────────────────┘
                                 │                                                │
                                 │                                                │
                                 ▼                                                ▼
                         ┌────────────────┐                               ┌──────────────────┐
                         │ DBT Source     │                               │ DBT Model        │
                         │ YAML           │                               │ stg_customers    │
                         └────────────────┘                               └──────────────────┘
```

## 🛡️ Security & Compliance

### Access Control

1. **Policy-Based Access**: Fine-grained control via PolicyGuard
2. **Classification-Based Restrictions**: Automatic PII/SENSITIVE handling
3. **Audit Trail**: All access logged with requester, timestamp
4. **No Raw Data Access**: AI agents only access metadata, never raw data

### Compliance Enforcement

1. **Retention Policy**: Automatic enforcement at query time
2. **User Consent**: Tracked in contract, enforced in queries
3. **Regulation Mapping**: GDPR, CCPA, HIPAA compliance markers
4. **Encryption Requirements**: Enforced for sensitive classifications

## 📚 Additional Resources

- [ODCS v3.0.2 Specification](https://github.com/bitol-io/open-data-contract-standard)
- [DBT Documentation](https://docs.getdbt.com/)
- [OpenLineage Specification](https://openlineage.io/)
- [dbt-GenAI Article](https://medium.com/tech-with-abhishek/dbt-genai-the-next-era-of-analytics-engineering-60ecf985e354)

## 🔧 Troubleshooting

### Common Issues

1. **Contract validation fails**: Check ODCS v3.0.2 required fields
2. **Breaking change detected**: Review schema changes, bump MAJOR version
3. **Access denied**: Verify PolicyGuard configuration and requester permissions
4. **Cost anomaly**: Compare with historical metrics, investigate resource usage spike

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable detailed logging
from dativo_ingest.logging import setup_logging
setup_logging(level="DEBUG", redact_secrets=False)
```
