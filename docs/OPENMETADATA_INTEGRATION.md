# OpenMetadata Integration

**Version**: 1.0  
**Date**: 2025-11-07  
**Status**: Design Phase

---

## Executive Summary

OpenMetadata is an open-source metadata platform for data discovery, lineage, quality, and governance. Integrating Dativo with OpenMetadata provides:

1. **Data Discovery**: Automatically catalog all ingested assets
2. **Lineage Tracking**: End-to-end lineage from source → Dativo → destination
3. **Quality Metrics**: Publish data quality scores to metadata catalog
4. **Governance**: Centralized policy management
5. **Collaboration**: Enable data teams to document and discover datasets

### Business Value
- **For Data Teams**: Single pane of glass for all data assets
- **For Compliance**: Centralized audit trail and data classification
- **For ML Teams**: Discover features and understand lineage
- **For Enterprises**: Meet data governance requirements (SOC2, GDPR)

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Integration Points](#integration-points)
3. [Implementation](#implementation)
4. [Lineage Tracking](#lineage-tracking)
5. [Quality Metrics](#quality-metrics)
6. [Implementation Roadmap](#implementation-roadmap)

---

## Architecture Overview

### High-Level Integration

```
┌─────────────────────────────────────────────────────────────┐
│                  Dativo Ingestion Engine                    │
│                                                             │
│  ┌───────────┐   ┌─────────────┐   ┌──────────────┐      │
│  │Extractors │──>│ Validators  │──>│  Writers     │      │
│  └───────────┘   └─────────────┘   └──────────────┘      │
│         │              │                    │              │
│         │              │                    │              │
│         └──────────────┼────────────────────┘              │
│                        │                                    │
│                        ▼                                    │
│               ┌─────────────────┐                          │
│               │ OpenMetadata    │                          │
│               │ Client          │                          │
│               └────────┬────────┘                          │
└────────────────────────┼───────────────────────────────────┘
                         │
                         │ REST API / Python SDK
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              OpenMetadata Platform                          │
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐ │
│  │   Metadata    │  │    Lineage    │  │    Quality    │ │
│  │   Repository  │  │    Engine     │  │   Metrics     │ │
│  └───────────────┘  └───────────────┘  └───────────────┘ │
│                                                             │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐ │
│  │   Discovery   │  │  Governance   │  │ Collaboration │ │
│  │   Portal      │  │   Policies    │  │  (Comments,   │ │
│  │   (Web UI)    │  │               │  │   Tags)       │ │
│  └───────────────┘  └───────────────┘  └───────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### 1. Asset Registration

**When**: After successful ingestion  
**What**: Register Iceberg tables, Parquet files as data assets in OpenMetadata

```python
# File: src/dativo_ingest/metadata/openmetadata_client.py

from metadata.generated.schema.entity.data.table import Table, Column
from metadata.generated.schema.type.entityReference import EntityReference
from metadata.ingestion.ometa.ometa_api import OpenMetadata
from metadata.generated.schema.api.data.createTable import CreateTableRequest
from typing import List, Dict

class OpenMetadataClient:
    """
    OpenMetadata integration client.
    
    Features:
    - Register data assets (tables, files)
    - Update metadata (schema, tags, owner)
    - Track lineage
    - Publish quality metrics
    """
    
    def __init__(self, config: dict):
        self.metadata = OpenMetadata(config)
        self.config = config
    
    def register_asset(
        self,
        asset_config: dict,
        table_location: str,
        schema: List[dict]
    ) -> str:
        """
        Register ingested asset in OpenMetadata.
        
        Args:
            asset_config: Asset definition (from YAML)
            table_location: S3/Iceberg table location
            schema: List of column definitions
        
        Returns:
            str: Fully qualified name of registered asset
        """
        # Create table entity
        table_fqn = f"dativo.{asset_config['tenant_id']}.{asset_config['name']}"
        
        # Build columns
        columns = []
        for col in schema:
            column = Column(
                name=col["name"],
                dataType=self._map_data_type(col["type"]),
                description=col.get("description"),
                dataLength=col.get("length"),
                tags=self._get_column_tags(col)  # PII, sensitive, etc.
            )
            columns.append(column)
        
        # Create table request
        create_table = CreateTableRequest(
            name=asset_config["name"],
            displayName=asset_config.get("display_name", asset_config["name"]),
            description=asset_config.get("description"),
            columns=columns,
            tableType="Iceberg",  # or "External" for Parquet
            service=EntityReference(
                id=self.config["service_id"],
                type="databaseService"
            ),
            database=EntityReference(
                id=self.config["database_id"],
                type="database"
            ),
            databaseSchema=EntityReference(
                id=self.config["schema_id"],
                type="databaseSchema"
            ),
            owner=EntityReference(
                id=self._get_owner_id(asset_config.get("governance", {}).get("owner")),
                type="user"
            ),
            tags=self._get_asset_tags(asset_config)
        )
        
        # Register in OpenMetadata
        table_entity = self.metadata.create_or_update(create_table)
        
        # Add custom properties
        self._add_custom_properties(table_entity, asset_config)
        
        return table_fqn
    
    def _map_data_type(self, dativo_type: str) -> str:
        """Map Dativo data types to OpenMetadata types."""
        type_mapping = {
            "string": "STRING",
            "integer": "INT",
            "float": "FLOAT",
            "boolean": "BOOLEAN",
            "date": "DATE",
            "timestamp": "TIMESTAMP",
            "object": "JSON"
        }
        return type_mapping.get(dativo_type, "STRING")
    
    def _get_column_tags(self, column_config: dict) -> List[str]:
        """Extract tags for column (PII, sensitive, etc.)."""
        tags = []
        
        if column_config.get("classification") == "PII":
            tags.append("PII")
        
        if column_config.get("required"):
            tags.append("Required")
        
        if column_config.get("sensitive"):
            tags.append("Sensitive")
        
        return tags
    
    def _get_asset_tags(self, asset_config: dict) -> List[str]:
        """Extract tags for asset from governance metadata."""
        tags = asset_config.get("governance", {}).get("tags", [])
        
        # Add classification as tags
        classification = asset_config.get("governance", {}).get("classification", [])
        tags.extend(classification)
        
        return tags
```

---

### 2. Lineage Tracking

**Concept**: Track data flow from source → Dativo → destination

```python
# File: src/dativo_ingest/metadata/lineage_tracker.py

from metadata.generated.schema.api.lineage.addLineage import AddLineageRequest
from metadata.generated.schema.type.entityReference import EntityReference
from metadata.generated.schema.type.entityLineage import EntitiesEdge

class LineageTracker:
    """
    Track data lineage in OpenMetadata.
    
    Lineage Graph:
    Source (Stripe API) → Dativo Job → Destination (Iceberg Table)
    """
    
    def __init__(self, metadata_client: OpenMetadataClient):
        self.metadata_client = metadata_client
    
    def track_ingestion_lineage(
        self,
        job_config: dict,
        source_asset: str,
        destination_asset: str
    ):
        """
        Track lineage for ingestion job.
        
        Args:
            job_config: Job configuration
            source_asset: Source system (e.g., stripe.customers)
            destination_asset: Destination table FQN
        """
        # Create lineage edge
        lineage_request = AddLineageRequest(
            edge=EntitiesEdge(
                fromEntity=EntityReference(
                    id=source_asset,
                    type="table"  # or "databaseService" for APIs
                ),
                toEntity=EntityReference(
                    id=destination_asset,
                    type="table"
                ),
                lineageDetails={
                    "pipeline": job_config["job_name"],
                    "source": job_config["source_connector"],
                    "sqlQuery": None,  # For SQL-based transformations
                    "columnsLineage": self._track_column_lineage(job_config)
                }
            )
        )
        
        # Add to OpenMetadata
        self.metadata_client.metadata.add_lineage(lineage_request)
    
    def _track_column_lineage(self, job_config: dict) -> List[dict]:
        """
        Track column-level lineage.
        
        Example:
        stripe.customers.email → iceberg.stripe_customers.email
        stripe.customers.id → iceberg.stripe_customers.customer_id (renamed)
        """
        column_lineage = []
        
        # Get column mappings from job config
        for mapping in job_config.get("column_mappings", []):
            column_lineage.append({
                "fromColumns": [mapping["source_column"]],
                "toColumn": mapping["destination_column"],
                "function": mapping.get("transformation", "DIRECT_COPY")
            })
        
        return column_lineage
```

**Lineage Visualization in OpenMetadata UI**:

```
┌─────────────────────────────────────────────────────────────┐
│             Data Lineage (OpenMetadata UI)                  │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   ┌──────────────┐                                         │
│   │   Stripe     │                                         │
│   │   Customers  │                                         │
│   │   API        │                                         │
│   └──────┬───────┘                                         │
│          │                                                  │
│          │ dativo_job: stripe_customers_to_iceberg         │
│          │ frequency: hourly                               │
│          │ last_run: 2025-11-07 10:00:00                   │
│          │                                                  │
│          ▼                                                  │
│   ┌──────────────┐       ┌──────────────┐                 │
│   │  Dativo Job  │──────>│  Iceberg     │                 │
│   │  (Pipeline)  │       │  Table       │                 │
│   └──────────────┘       │  acme.stripe │                 │
│                          │  _customers  │                 │
│                          └──────┬───────┘                 │
│                                 │                          │
│                                 │ Used by ML model:        │
│                                 │ recommendation_v2        │
│                                 │                          │
│                                 ▼                          │
│                          ┌──────────────┐                 │
│                          │ SageMaker    │                 │
│                          │ Training Job │                 │
│                          └──────────────┘                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

### 3. Quality Metrics Publishing

**Concept**: Publish data quality scores to OpenMetadata

```python
# File: src/dativo_ingest/metadata/quality_publisher.py

from metadata.generated.schema.tests.testCase import TestCase
from metadata.generated.schema.tests.testDefinition import TestDefinition
from metadata.generated.schema.tests.testSuite import TestSuite
from datetime import datetime

class QualityMetricsPublisher:
    """
    Publish data quality metrics to OpenMetadata.
    
    Metrics:
    - Data quality test results (pass/fail)
    - Quality scores (0-100)
    - Data profiling statistics
    - Contract violation history
    """
    
    def __init__(self, metadata_client: OpenMetadataClient):
        self.metadata_client = metadata_client
    
    def publish_quality_results(
        self,
        asset_fqn: str,
        quality_results: dict
    ):
        """
        Publish quality check results to OpenMetadata.
        
        Args:
            asset_fqn: Fully qualified name of asset
            quality_results: Results from quality orchestrator
        """
        # Create test suite if not exists
        test_suite_fqn = f"{asset_fqn}.dativo_quality_checks"
        
        # Publish individual test results
        for check in quality_results.get("checks", []):
            test_case = TestCase(
                name=check["name"],
                displayName=check.get("display_name", check["name"]),
                description=check.get("description"),
                testSuite=EntityReference(
                    id=test_suite_fqn,
                    type="testSuite"
                ),
                entityLink=f"<#E::table::{asset_fqn}>",
                testDefinition=EntityReference(
                    id=check["test_type"],
                    type="testDefinition"
                ),
                parameterValues=[
                    {"name": k, "value": str(v)}
                    for k, v in check.get("parameters", {}).items()
                ]
            )
            
            # Add test result
            test_result = {
                "timestamp": datetime.utcnow().timestamp(),
                "testCaseStatus": "Success" if check["passed"] else "Failed",
                "result": check.get("result"),
                "testResultValue": [
                    {"name": "score", "value": str(check.get("score", 0))}
                ]
            }
            
            self.metadata_client.metadata.add_test_case_results(
                test_case.fullyQualifiedName,
                test_result
            )
    
    def publish_profiling_metrics(
        self,
        asset_fqn: str,
        profiling_results: dict
    ):
        """
        Publish data profiling metrics.
        
        Metrics:
        - Row count
        - Column statistics (min, max, mean, std)
        - Null percentages
        - Distinct value counts
        - Data types
        """
        profile = {
            "timestamp": datetime.utcnow().timestamp(),
            "rowCount": profiling_results["row_count"],
            "columnCount": profiling_results["column_count"],
            "columnProfile": []
        }
        
        for col_name, col_stats in profiling_results.get("columns", {}).items():
            column_profile = {
                "name": col_name,
                "valuesCount": col_stats.get("count"),
                "valuesPercentage": col_stats.get("non_null_percentage"),
                "validCount": col_stats.get("valid_count"),
                "duplicateCount": col_stats.get("duplicate_count"),
                "nullCount": col_stats.get("null_count"),
                "nullProportion": col_stats.get("null_percentage"),
                "uniqueCount": col_stats.get("unique_count"),
                "uniqueProportion": col_stats.get("unique_percentage"),
                "distinctCount": col_stats.get("distinct_count"),
                "distinctProportion": col_stats.get("distinct_percentage"),
                "min": col_stats.get("min"),
                "max": col_stats.get("max"),
                "mean": col_stats.get("mean"),
                "median": col_stats.get("median"),
                "stddev": col_stats.get("std")
            }
            profile["columnProfile"].append(column_profile)
        
        # Add to OpenMetadata
        self.metadata_client.metadata.ingest_profile_data(
            asset_fqn,
            profile
        )
```

---

### 4. Governance Integration

**Concept**: Sync governance policies between Dativo and OpenMetadata

```yaml
# Asset definition with OpenMetadata sync
asset:
  name: stripe_customers
  version: "1.0"
  
  governance:
    owner: data-team@company.com
    tags: [pii, payments, production]
    classification: [PII, Restricted]
    retention_days: 90
    
    # NEW: OpenMetadata governance sync
    openmetadata:
      sync_enabled: true
      
      # Domain assignment
      domain: "customer_data"
      
      # Glossary terms
      glossary_terms:
        - "Customer"
        - "Payment Information"
      
      # Data products
      data_product: "Customer 360"
      
      # Access policies (sync to OpenMetadata)
      access_policies:
        - role: "data_analyst"
          permissions: ["read"]
        - role: "data_engineer"
          permissions: ["read", "write"]
        - role: "ml_engineer"
          permissions: ["read"]
```

**Implementation**:

```python
# File: src/dativo_ingest/metadata/governance_sync.py

class GovernanceSync:
    """
    Sync governance policies between Dativo and OpenMetadata.
    
    Features:
    - Sync owners, tags, classifications
    - Sync access policies
    - Sync glossary terms
    - Sync data products
    """
    
    def sync_governance_metadata(
        self,
        asset_config: dict,
        asset_fqn: str
    ):
        """Sync governance metadata to OpenMetadata."""
        governance = asset_config.get("governance", {})
        
        # Update owner
        if governance.get("owner"):
            self._update_owner(asset_fqn, governance["owner"])
        
        # Update tags
        if governance.get("tags"):
            self._update_tags(asset_fqn, governance["tags"])
        
        # Update classification
        if governance.get("classification"):
            self._update_classification(asset_fqn, governance["classification"])
        
        # Sync access policies
        if governance.get("openmetadata", {}).get("access_policies"):
            self._sync_access_policies(
                asset_fqn,
                governance["openmetadata"]["access_policies"]
            )
```

---

## OpenMetadata UI Benefits

### 1. Data Discovery Portal

```
┌─────────────────────────────────────────────────────────────┐
│           OpenMetadata Discovery Portal                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Search: "customer"                                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │ 🔍 Results (12)                                     │   │
│  │                                                     │   │
│  │ 📊 acme.stripe_customers                           │   │
│  │    Owner: data-team@company.com                    │   │
│  │    Tags: [pii, payments, production]               │   │
│  │    Quality Score: 98/100 ✅                        │   │
│  │    Last Updated: 2 hours ago                       │   │
│  │    → View Details | Query Data | View Lineage      │   │
│  │                                                     │   │
│  │ 📊 acme.hubspot_contacts                           │   │
│  │    Owner: sales-team@company.com                   │   │
│  │    Tags: [pii, crm, production]                    │   │
│  │    Quality Score: 95/100 ✅                        │   │
│  │    → View Details | Query Data | View Lineage      │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  Filters:                                                   │
│  ☑ PII Data                                                │
│  ☐ Public Data                                             │
│  ☑ Production                                              │
│  ☐ Development                                             │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2. Asset Details Page

```
┌─────────────────────────────────────────────────────────────┐
│         acme.stripe_customers (Table)                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Overview | Schema | Quality | Lineage | Activity          │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  📊 Overview                                                │
│  Owner: data-team@company.com                              │
│  Domain: Customer Data                                     │
│  Tags: [pii, payments, production]                         │
│  Quality Score: 98/100 ✅                                  │
│                                                             │
│  Description:                                              │
│  Customer data from Stripe API, ingested hourly via        │
│  Dativo. Contains PII - handle with care.                  │
│                                                             │
│  📋 Schema (8 columns)                                     │
│  ┌──────────────┬─────────┬──────────┬──────────────┐     │
│  │ Column       │ Type    │ Tags     │ Description  │     │
│  ├──────────────┼─────────┼──────────┼──────────────┤     │
│  │ id           │ STRING  │ Required │ Customer ID  │     │
│  │ email        │ STRING  │ PII      │ Email addr   │     │
│  │ balance      │ FLOAT   │          │ Acct balance │     │
│  └──────────────┴─────────┴──────────┴──────────────┘     │
│                                                             │
│  ✅ Data Quality (5 tests)                                 │
│  ✅ Email format validation           100% pass            │
│  ✅ No duplicate emails                100% pass            │
│  ✅ Balance range check                100% pass            │
│  ✅ Freshness check (< 2h)             100% pass            │
│  ✅ Row count (100-1M)                 100% pass            │
│                                                             │
│  💬 Conversations (2)                                      │
│  👤 john@company.com: "What's the retention period?"       │
│  👤 data-team: "90 days per GDPR policy"                   │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation Roadmap

### Phase 1: Basic Integration (Month 6, Week 3-4)
- [ ] Install OpenMetadata SDK
- [ ] Implement basic asset registration
- [ ] Register Iceberg tables on ingestion completion
- [ ] Sync schema and basic metadata

**Deliverables**:
- `src/dativo_ingest/metadata/openmetadata_client.py`
- Configuration for OpenMetadata connection
- Basic asset registration working

---

### Phase 2: Lineage Tracking (Month 7, Week 1-2)
- [ ] Implement lineage tracker
- [ ] Track table-level lineage
- [ ] Track column-level lineage
- [ ] Visualize lineage in OpenMetadata UI

**Deliverables**:
- `src/dativo_ingest/metadata/lineage_tracker.py`
- End-to-end lineage working (Source → Dativo → Destination)

---

### Phase 3: Quality Metrics (Month 7, Week 3-4)
- [ ] Implement quality metrics publisher
- [ ] Publish data quality test results
- [ ] Publish data profiling statistics
- [ ] Quality score dashboard in OpenMetadata

**Deliverables**:
- `src/dativo_ingest/metadata/quality_publisher.py`
- Quality metrics visible in OpenMetadata UI

---

### Phase 4: Governance Sync (Month 8, Week 1-2)
- [ ] Implement governance sync
- [ ] Sync owners, tags, classifications
- [ ] Sync access policies
- [ ] Bidirectional sync (OpenMetadata → Dativo)

**Deliverables**:
- `src/dativo_ingest/metadata/governance_sync.py`
- Governance metadata synced between systems

---

## Configuration

```yaml
# File: configs/openmetadata.yaml
openmetadata:
  enabled: true
  
  # OpenMetadata server
  server:
    host: "http://openmetadata.company.com"
    api_version: "v1"
  
  # Authentication
  auth:
    type: "jwt"  # jwt | basic | oauth
    jwt_token: "${OPENMETADATA_JWT_TOKEN}"
  
  # Dativo service registration
  service:
    name: "dativo_ingestion"
    type: "databaseService"
    description: "Dativo data ingestion platform"
  
  # Sync configuration
  sync:
    # Asset registration
    register_on_completion: true
    update_on_schema_change: true
    
    # Lineage tracking
    track_lineage: true
    track_column_lineage: true
    
    # Quality metrics
    publish_quality_results: true
    publish_profiling_metrics: true
    
    # Governance
    sync_governance_metadata: true
    sync_frequency: "hourly"
  
  # Batch configuration
  batch_size: 100  # Register 100 assets per batch
  retry_config:
    max_attempts: 3
    backoff_seconds: 5
```

---

## Success Metrics

```yaml
Adoption Metrics:
  - Assets registered in OpenMetadata: 100% of ingested assets
  - Lineage completeness: 100% (all jobs tracked)
  - Quality metrics published: 100% of quality checks
  - User engagement: >50% of data team using OpenMetadata monthly

Technical Metrics:
  - Metadata sync latency: <1 minute
  - API success rate: >99.5%
  - Lineage visualization load time: <2 seconds

Business Metrics:
  - Time to discover datasets: -70% (faster discovery)
  - Data quality incidents: -50% (proactive monitoring)
  - Compliance audit preparation: -80% (centralized metadata)
```

---

**Last Updated**: 2025-11-07  
**Document Owner**: Data Platform Team  
**Review Frequency**: Monthly  
**Status**: Design Phase
