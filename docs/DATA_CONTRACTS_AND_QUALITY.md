# Data Contracts & Quality Framework

**Version**: 1.0  
**Date**: 2025-11-07  
**Status**: Design Phase

---

## Executive Summary

Data contracts provide a formal agreement between data producers and consumers, ensuring data quality, schema compliance, and SLA guarantees. Integrating with best-in-class tools (Soda, Great Expectations) positions Dativo as an enterprise-grade platform.

### Business Value
- **For ML Teams**: Prevent model degradation from data quality issues
- **For Data Mesh**: Enable domain teams to publish guaranteed data products
- **For Compliance**: Audit trail of data quality checks for SOC2/GDPR

---

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Data Contract Specification](#data-contract-specification)
3. [Integration with Soda](#integration-with-soda)
4. [Integration with Great Expectations](#integration-with-great-expectations)
5. [Quality Check Orchestration](#quality-check-orchestration)
6. [Failed Contract Handling](#failed-contract-handling)
7. [Implementation Roadmap](#implementation-roadmap)

---

## Architecture Overview

### High-Level Flow

```
┌─────────────────────────────────────────────────────────────┐
│                  Data Contract Definition                    │
│  (YAML in asset definition + separate contract files)       │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  Ingestion Pipeline                          │
│  Extract → Validate Schema → Write Parquet                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              Quality Check Orchestration                     │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │    Soda      │  │Great Expec.  │  │   Custom     │     │
│  │  (SQL-based) │  │ (Python-based)│  │   Rules      │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  Contract Evaluation                         │
│  ✅ Pass → Commit to Iceberg                                │
│  ❌ Fail → Send to DLQ, Alert, Block commit                 │
└─────────────────────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│              Metadata & Lineage (OpenMetadata)               │
│  - Quality scores                                            │
│  - Contract violations history                               │
│  - Data lineage                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Data Contract Specification

### Contract YAML Format

```yaml
# File: contracts/stripe_customers_contract.yaml
data_contract:
  name: stripe_customers
  version: "1.0"
  owner: data-platform@company.com
  status: active  # active | deprecated | sunset
  
  # Link to asset definition
  asset_ref: /app/assets/stripe/v1.0/customers.yaml
  
  # SLA guarantees
  sla:
    freshness:
      max_age_hours: 2  # Data must be < 2 hours old
    completeness:
      min_records_per_day: 100
    availability:
      uptime_percentage: 99.5
  
  # Schema contract (references asset schema)
  schema_contract:
    strict_mode: true  # Fail on schema drift
    allow_nullable_expansion: false  # Can't make required → nullable
    allow_type_changes: false
  
  # Data quality checks
  quality_checks:
    # Soda checks (SQL-based)
    soda:
      engine: soda_core  # or soda_cloud
      checks:
        - name: email_format
          type: regex
          column: email
          pattern: "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
          severity: error
        
        - name: no_duplicate_emails
          type: uniqueness
          columns: [email]
          severity: error
        
        - name: amount_range
          type: range
          column: balance
          min: -10000
          max: 1000000
          severity: warning
        
        - name: freshness_check
          type: freshness
          column: created
          max_age_hours: 24
          severity: error
    
    # Great Expectations checks (Python-based)
    great_expectations:
      expectation_suite: stripe_customers_suite
      checks:
        - name: expect_column_values_to_not_be_null
          column: id
        
        - name: expect_column_values_to_be_in_set
          column: currency
          value_set: [USD, EUR, GBP, CAD]
        
        - name: expect_column_values_to_match_regex
          column: email
          regex: "^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$"
        
        - name: expect_table_row_count_to_be_between
          min_value: 100
          max_value: 1000000
    
    # Custom Python checks
    custom:
      - name: ml_feature_validity
        function: validate_ml_features
        description: "Ensure features are within ML model training ranges"
        severity: error
  
  # Handling strategy for contract violations
  violation_handling:
    on_schema_violation: block  # block | warn | quarantine
    on_quality_violation: quarantine  # block | warn | quarantine
    on_sla_violation: warn
    
    notification:
      channels: [slack, email, pagerduty]
      recipients:
        - data-team@company.com
        - ml-team@company.com
    
    quarantine:
      enabled: true
      s3_bucket: "${QUARANTINE_BUCKET}"
      s3_prefix: "quarantine/${TENANT_ID}/${ASSET_NAME}/"
      retention_days: 30
  
  # Metadata for discovery
  tags: [pii, payments, ml-features, production]
  classification: RESTRICTED
  documentation_url: https://docs.company.com/data/stripe_customers
```

### Asset Definition Enhancement

```yaml
# File: assets/stripe/v1.0/customers.yaml
asset:
  name: stripe_customers
  source_type: stripe
  object: customers
  version: "1.0"
  
  # Existing schema definition
  schema:
    - name: id
      type: string
      required: true
    - name: email
      type: string
      required: false
      classification: PII
  
  # NEW: Data contract reference
  data_contract:
    enabled: true
    contract_path: /app/contracts/stripe_customers_contract.yaml
    enforcement_mode: strict  # strict | warn | disabled
    
    # Quick inline quality checks (simpler than full contract)
    inline_checks:
      - type: null_check
        columns: [id, created]
      - type: unique_check
        columns: [id]
      - type: range_check
        column: balance
        min: -10000
        max: 1000000
  
  governance:
    owner: data-team@company.com
    tags: [payments, customer-data, stripe]
    classification: [PII]
    retention_days: 90
  
  target:
    file_format: parquet
    partitioning: [ingest_date]
    mode: strict
```

---

## Integration with Soda

### Soda Core Implementation

```python
# File: src/dativo_ingest/quality/soda_adapter.py

from soda.scan import Scan
from typing import List, Dict, Optional
import yaml

class SodaQualityChecker:
    """
    Soda Core integration for SQL-based data quality checks.
    
    Features:
    - Execute Soda checks on Parquet files (via DuckDB)
    - Execute Soda checks on Iceberg tables (via Spark/Trino)
    - Parse Soda check results
    - Map to contract violation events
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.scan_definition = self._load_scan_definition()
    
    def _load_scan_definition(self) -> dict:
        """
        Generate Soda scan definition from contract.
        
        Example Soda YAML:
        ```
        checks for stripe_customers:
          - missing_count(id) = 0
          - duplicate_count(email) = 0
          - invalid_count(email) = 0:
              valid regex: ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$
          - avg(balance) between -10000 and 1000000
        ```
        """
        pass
    
    def execute_checks(
        self,
        data_source: str,  # parquet | iceberg | duckdb
        data_path: str,
        checks: List[dict]
    ) -> Dict:
        """
        Execute Soda checks and return results.
        
        Args:
            data_source: Type of data source (parquet, iceberg, duckdb)
            data_path: Path to data (S3 path, table name, etc.)
            checks: List of Soda check definitions
        
        Returns:
            dict: Check results with:
                - passed: int
                - failed: int
                - warnings: int
                - violations: List[dict]
                - scan_time: float
        """
        scan = Scan()
        
        # Configure data source
        if data_source == "parquet":
            # Use DuckDB to query Parquet files
            scan.set_data_source_name("duckdb")
            scan.add_duckdb_connection(
                data_source_name="duckdb",
                path=data_path
            )
        elif data_source == "iceberg":
            # Use Spark/Trino to query Iceberg
            scan.set_data_source_name("spark")
            scan.add_spark_session(
                data_source_name="spark",
                catalog="nessie"
            )
        
        # Add checks
        for check in checks:
            scan.add_sodacl_yaml_str(self._convert_check_to_sodacl(check))
        
        # Execute scan
        scan.execute()
        
        # Parse results
        results = {
            "passed": len(scan.get_checks_pass()),
            "failed": len(scan.get_checks_fail()),
            "warnings": len(scan.get_checks_warn()),
            "violations": [],
            "scan_time": scan.scan_time
        }
        
        # Extract violations
        for check in scan.get_checks_fail():
            results["violations"].append({
                "check_name": check.name,
                "severity": "error",
                "message": check.outcome.message,
                "column": check.column,
                "metrics": check.metrics
            })
        
        return results
    
    def _convert_check_to_sodacl(self, check: dict) -> str:
        """Convert contract check to Soda CL YAML format."""
        check_type = check["type"]
        column = check.get("column")
        
        if check_type == "regex":
            return f"""
            checks for {self.config['table_name']}:
              - invalid_count({column}) = 0:
                  valid regex: {check['pattern']}
            """
        elif check_type == "uniqueness":
            columns_str = ", ".join(check["columns"])
            return f"""
            checks for {self.config['table_name']}:
              - duplicate_count({columns_str}) = 0
            """
        elif check_type == "range":
            return f"""
            checks for {self.config['table_name']}:
              - min({column}) >= {check['min']}
              - max({column}) <= {check['max']}
            """
        elif check_type == "freshness":
            return f"""
            checks for {self.config['table_name']}:
              - freshness({column}) < {check['max_age_hours']}h
            """
        
        return ""
```

### Soda Configuration

```yaml
# File: configs/quality/soda_config.yaml
soda:
  # Soda Core (open-source) or Soda Cloud (SaaS)
  engine: soda_core  # soda_core | soda_cloud
  
  # Soda Cloud configuration (if using SaaS)
  cloud:
    api_key: "${SODA_API_KEY}"
    organization: "${SODA_ORG}"
  
  # Data source configuration
  data_sources:
    duckdb:
      type: duckdb
      path: ":memory:"  # In-memory for Parquet files
    
    spark:
      type: spark
      catalog: nessie
      warehouse: s3://lake/warehouse
  
  # Check execution configuration
  execution:
    timeout_seconds: 300
    parallel_checks: true
    max_parallel: 4
  
  # Results storage
  results:
    store_in_s3: true
    s3_bucket: "${QUALITY_RESULTS_BUCKET}"
    s3_prefix: "soda-results/"
    retention_days: 90
```

---

## Integration with Great Expectations

### Great Expectations Implementation

```python
# File: src/dativo_ingest/quality/great_expectations_adapter.py

import great_expectations as gx
from great_expectations.core.batch import RuntimeBatchRequest
from typing import List, Dict, Optional
import pandas as pd

class GreatExpectationsQualityChecker:
    """
    Great Expectations integration for Python-based data quality checks.
    
    Features:
    - Execute expectation suites on Parquet files
    - Execute expectation suites on DataFrames
    - Generate data docs
    - Store validation results
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.context = self._init_context()
    
    def _init_context(self) -> gx.DataContext:
        """
        Initialize Great Expectations data context.
        
        Configuration stored in:
        /app/great_expectations/
          ├── great_expectations.yml
          ├── expectations/
          │   └── stripe_customers_suite.json
          ├── checkpoints/
          │   └── stripe_customers_checkpoint.yml
          └── plugins/
        """
        context = gx.get_context(
            context_root_dir=self.config.get(
                "context_root_dir",
                "/app/great_expectations"
            )
        )
        return context
    
    def execute_expectation_suite(
        self,
        suite_name: str,
        data_path: Optional[str] = None,
        dataframe: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Execute expectation suite on data.
        
        Args:
            suite_name: Name of expectation suite
            data_path: Path to Parquet file (if using file)
            dataframe: Pandas DataFrame (if using in-memory)
        
        Returns:
            dict: Validation results with:
                - success: bool
                - statistics: dict
                - results: List[dict]
                - validation_time: float
        """
        # Create batch request
        if data_path:
            batch_request = RuntimeBatchRequest(
                datasource_name="parquet_datasource",
                data_connector_name="default_runtime_data_connector",
                data_asset_name=suite_name,
                runtime_parameters={
                    "path": data_path
                },
                batch_identifiers={
                    "default_identifier_name": "default_identifier"
                }
            )
        else:
            batch_request = RuntimeBatchRequest(
                datasource_name="pandas_datasource",
                data_connector_name="default_runtime_data_connector",
                data_asset_name=suite_name,
                runtime_parameters={
                    "batch_data": dataframe
                },
                batch_identifiers={
                    "default_identifier_name": "default_identifier"
                }
            )
        
        # Get validator
        validator = self.context.get_validator(
            batch_request=batch_request,
            expectation_suite_name=suite_name
        )
        
        # Run validation
        validation_result = validator.validate()
        
        # Parse results
        results = {
            "success": validation_result.success,
            "statistics": {
                "evaluated_expectations": validation_result.statistics["evaluated_expectations"],
                "successful_expectations": validation_result.statistics["successful_expectations"],
                "unsuccessful_expectations": validation_result.statistics["unsuccessful_expectations"],
                "success_percent": validation_result.statistics["success_percent"]
            },
            "results": [],
            "validation_time": 0  # TODO: track time
        }
        
        # Extract failures
        for result in validation_result.results:
            if not result.success:
                results["results"].append({
                    "expectation_type": result.expectation_config.expectation_type,
                    "column": result.expectation_config.kwargs.get("column"),
                    "success": result.success,
                    "result": result.result
                })
        
        return results
    
    def create_expectation_suite_from_contract(
        self,
        contract: dict,
        suite_name: str
    ) -> str:
        """
        Generate Great Expectations suite from data contract.
        
        Args:
            contract: Data contract definition
            suite_name: Name for expectation suite
        
        Returns:
            str: Path to created suite
        """
        suite = self.context.add_expectation_suite(suite_name)
        
        # Convert contract checks to expectations
        for check in contract.get("quality_checks", {}).get("great_expectations", {}).get("checks", []):
            expectation_type = check["name"]
            kwargs = {k: v for k, v in check.items() if k != "name"}
            
            suite.add_expectation(
                expectation_type,
                **kwargs
            )
        
        # Save suite
        self.context.save_expectation_suite(suite)
        
        return f"/app/great_expectations/expectations/{suite_name}.json"
```

### Expectation Suite Example

```json
{
  "expectation_suite_name": "stripe_customers_suite",
  "expectations": [
    {
      "expectation_type": "expect_column_values_to_not_be_null",
      "kwargs": {
        "column": "id"
      },
      "meta": {
        "severity": "error"
      }
    },
    {
      "expectation_type": "expect_column_values_to_be_unique",
      "kwargs": {
        "column": "id"
      },
      "meta": {
        "severity": "error"
      }
    },
    {
      "expectation_type": "expect_column_values_to_match_regex",
      "kwargs": {
        "column": "email",
        "regex": "^[\\w\\.-]+@[\\w\\.-]+\\.\\w+$"
      },
      "meta": {
        "severity": "error"
      }
    },
    {
      "expectation_type": "expect_column_values_to_be_in_set",
      "kwargs": {
        "column": "currency",
        "value_set": ["USD", "EUR", "GBP", "CAD"]
      },
      "meta": {
        "severity": "warning"
      }
    },
    {
      "expectation_type": "expect_table_row_count_to_be_between",
      "kwargs": {
        "min_value": 100,
        "max_value": 1000000
      },
      "meta": {
        "severity": "warning"
      }
    },
    {
      "expectation_type": "expect_column_mean_to_be_between",
      "kwargs": {
        "column": "balance",
        "min_value": 0,
        "max_value": 10000
      },
      "meta": {
        "severity": "warning"
      }
    }
  ],
  "meta": {
    "great_expectations_version": "0.18.0",
    "created_by": "dativo_ingest",
    "created_at": "2025-11-07T00:00:00Z"
  }
}
```

---

## Quality Check Orchestration

### Orchestration Engine

```python
# File: src/dativo_ingest/quality/orchestrator.py

from typing import Dict, List, Optional
from enum import Enum
import time

class QualityCheckResult(Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"
    QUARANTINE = "quarantine"

class DataQualityOrchestrator:
    """
    Orchestrate data quality checks across multiple engines.
    
    Execution flow:
    1. Load data contract
    2. Execute schema validation (existing)
    3. Execute inline checks (quick)
    4. Execute Soda checks (SQL-based)
    5. Execute Great Expectations (Python-based)
    6. Execute custom checks
    7. Aggregate results
    8. Handle violations
    """
    
    def __init__(
        self,
        soda_checker: Optional[SodaQualityChecker] = None,
        ge_checker: Optional[GreatExpectationsQualityChecker] = None
    ):
        self.soda_checker = soda_checker
        self.ge_checker = ge_checker
    
    def execute_contract_checks(
        self,
        contract: dict,
        data_path: str,
        dataframe: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Execute all checks defined in data contract.
        
        Args:
            contract: Data contract definition
            data_path: Path to Parquet file
            dataframe: Optional DataFrame for in-memory checks
        
        Returns:
            dict: Aggregated check results with:
                - overall_result: QualityCheckResult
                - checks_executed: int
                - checks_passed: int
                - checks_failed: int
                - checks_warned: int
                - violations: List[dict]
                - execution_time: float
        """
        start_time = time.time()
        results = {
            "overall_result": QualityCheckResult.PASS,
            "checks_executed": 0,
            "checks_passed": 0,
            "checks_failed": 0,
            "checks_warned": 0,
            "violations": [],
            "execution_time": 0
        }
        
        # 1. Execute Soda checks
        if self.soda_checker and "soda" in contract.get("quality_checks", {}):
            soda_results = self.soda_checker.execute_checks(
                data_source="parquet",
                data_path=data_path,
                checks=contract["quality_checks"]["soda"]["checks"]
            )
            results["checks_executed"] += soda_results["passed"] + soda_results["failed"]
            results["checks_passed"] += soda_results["passed"]
            results["checks_failed"] += soda_results["failed"]
            results["violations"].extend(soda_results["violations"])
        
        # 2. Execute Great Expectations checks
        if self.ge_checker and "great_expectations" in contract.get("quality_checks", {}):
            ge_results = self.ge_checker.execute_expectation_suite(
                suite_name=contract["quality_checks"]["great_expectations"]["expectation_suite"],
                data_path=data_path,
                dataframe=dataframe
            )
            results["checks_executed"] += ge_results["statistics"]["evaluated_expectations"]
            results["checks_passed"] += ge_results["statistics"]["successful_expectations"]
            results["checks_failed"] += ge_results["statistics"]["unsuccessful_expectations"]
            results["violations"].extend(ge_results["results"])
        
        # 3. Execute custom checks
        if "custom" in contract.get("quality_checks", {}):
            custom_results = self._execute_custom_checks(
                contract["quality_checks"]["custom"],
                dataframe
            )
            results["checks_executed"] += len(custom_results["checks"])
            results["checks_passed"] += custom_results["passed"]
            results["checks_failed"] += custom_results["failed"]
            results["violations"].extend(custom_results["violations"])
        
        # Determine overall result
        if results["checks_failed"] > 0:
            violation_handling = contract.get("violation_handling", {})
            on_quality_violation = violation_handling.get("on_quality_violation", "warn")
            
            if on_quality_violation == "block":
                results["overall_result"] = QualityCheckResult.FAIL
            elif on_quality_violation == "quarantine":
                results["overall_result"] = QualityCheckResult.QUARANTINE
            else:
                results["overall_result"] = QualityCheckResult.WARN
        
        results["execution_time"] = time.time() - start_time
        return results
    
    def _execute_custom_checks(
        self,
        custom_checks: List[dict],
        dataframe: pd.DataFrame
    ) -> Dict:
        """Execute custom Python validation functions."""
        results = {
            "checks": custom_checks,
            "passed": 0,
            "failed": 0,
            "violations": []
        }
        
        for check in custom_checks:
            function_name = check["function"]
            # Import and execute custom function
            # func = import_function(function_name)
            # success = func(dataframe)
            # ... handle result
        
        return results
```

---

## Failed Contract Handling

### Quarantine Strategy

```python
# File: src/dativo_ingest/quality/quarantine.py

import boto3
from datetime import datetime, timedelta
from typing import Dict, Optional

class QuarantineManager:
    """
    Manage quarantined data that failed quality checks.
    
    Features:
    - Store failed data in quarantine bucket
    - Track quarantine metadata
    - Enable data recovery/replay
    - Automatic cleanup after retention period
    """
    
    def __init__(self, s3_client, config: dict):
        self.s3_client = s3_client
        self.quarantine_bucket = config["s3_bucket"]
        self.quarantine_prefix = config["s3_prefix"]
        self.retention_days = config.get("retention_days", 30)
    
    def quarantine_data(
        self,
        data_path: str,
        contract: dict,
        violations: List[dict],
        metadata: dict
    ) -> str:
        """
        Move data to quarantine bucket.
        
        Args:
            data_path: Path to Parquet file that failed checks
            contract: Data contract definition
            violations: List of quality check violations
            metadata: Additional metadata (job_id, tenant_id, etc.)
        
        Returns:
            str: Quarantine record ID
        """
        quarantine_id = self._generate_quarantine_id(metadata)
        
        # Copy data to quarantine
        quarantine_path = f"{self.quarantine_prefix}{quarantine_id}/data.parquet"
        self.s3_client.copy_object(
            CopySource=data_path,
            Bucket=self.quarantine_bucket,
            Key=quarantine_path
        )
        
        # Store quarantine metadata
        metadata_doc = {
            "quarantine_id": quarantine_id,
            "original_path": data_path,
            "contract_name": contract["name"],
            "contract_version": contract["version"],
            "violations": violations,
            "quarantined_at": datetime.utcnow().isoformat(),
            "expires_at": (datetime.utcnow() + timedelta(days=self.retention_days)).isoformat(),
            "metadata": metadata,
            "status": "quarantined",  # quarantined | reviewed | replayed | deleted
            "reviewed_by": None,
            "reviewed_at": None
        }
        
        self._store_quarantine_metadata(quarantine_id, metadata_doc)
        
        # Send notification
        self._send_quarantine_notification(metadata_doc)
        
        return quarantine_id
    
    def replay_quarantined_data(
        self,
        quarantine_id: str,
        skip_quality_checks: bool = False
    ) -> Dict:
        """
        Replay quarantined data through pipeline.
        
        Args:
            quarantine_id: ID of quarantined data
            skip_quality_checks: If True, skip quality checks on replay
        
        Returns:
            dict: Replay result
        """
        # Retrieve quarantined data
        metadata = self._get_quarantine_metadata(quarantine_id)
        data_path = f"{self.quarantine_prefix}{quarantine_id}/data.parquet"
        
        # Trigger re-ingestion
        # ... (integrate with orchestrator)
        
        return {
            "quarantine_id": quarantine_id,
            "replay_status": "success",
            "replayed_at": datetime.utcnow().isoformat()
        }
```

### Notification System

```yaml
# File: configs/quality/notifications.yaml
notifications:
  quality_violations:
    enabled: true
    
    channels:
      slack:
        enabled: true
        webhook_url: "${SLACK_WEBHOOK_URL}"
        channel: "#data-quality-alerts"
        mention_on_critical: ["@data-platform", "@ml-team"]
      
      email:
        enabled: true
        smtp_server: "${SMTP_SERVER}"
        from_email: "dativo-alerts@company.com"
        recipients:
          - data-team@company.com
          - ml-team@company.com
      
      pagerduty:
        enabled: false  # Enable for critical production issues
        api_key: "${PAGERDUTY_API_KEY}"
        service_id: "${PAGERDUTY_SERVICE_ID}"
    
    templates:
      quality_violation:
        subject: "[DATA QUALITY] Contract violation: {contract_name}"
        body: |
          Contract: {contract_name} (v{contract_version})
          Asset: {asset_name}
          Tenant: {tenant_id}
          
          Violations ({violation_count}):
          {violations_list}
          
          Action: Data quarantined to {quarantine_path}
          
          Review: {quarantine_ui_url}
```

---

## Implementation Roadmap

### Phase 1: Foundation (Month 4, Sprint 7)

**Week 1-2: Data Contract Specification**
- [ ] Design data contract YAML schema
- [ ] Extend asset definition with contract reference
- [ ] Implement contract loader and validator
- [ ] Create example contracts for existing connectors

**Deliverables**:
- `schemas/data_contract.schema.json`
- `src/dativo_ingest/quality/contract_loader.py`
- `contracts/` directory with example contracts
- Documentation: `docs/DATA_CONTRACTS.md`

---

### Phase 2: Soda Integration (Month 4, Sprint 8)

**Week 3-4: Soda Core Integration**
- [ ] Install Soda Core dependencies
- [ ] Implement `SodaQualityChecker` adapter
- [ ] Add DuckDB support for Parquet file checks
- [ ] Create Soda configuration templates

**Deliverables**:
- `src/dativo_ingest/quality/soda_adapter.py`
- `configs/quality/soda_config.yaml`
- Integration tests with sample data
- Documentation: `docs/quality/SODA_INTEGRATION.md`

---

### Phase 3: Great Expectations Integration (Month 5, Sprint 9)

**Week 1-2: Great Expectations Integration**
- [ ] Install Great Expectations dependencies
- [ ] Implement `GreatExpectationsQualityChecker` adapter
- [ ] Create expectation suite templates
- [ ] Setup data docs generation

**Deliverables**:
- `src/dativo_ingest/quality/great_expectations_adapter.py`
- `/app/great_expectations/` directory structure
- Expectation suites for existing assets
- Documentation: `docs/quality/GREAT_EXPECTATIONS_INTEGRATION.md`

---

### Phase 4: Orchestration (Month 5, Sprint 10)

**Week 3-4: Quality Check Orchestration**
- [ ] Implement `DataQualityOrchestrator`
- [ ] Integrate with ETL pipeline (post-extraction)
- [ ] Add quarantine manager
- [ ] Setup notification system

**Deliverables**:
- `src/dativo_ingest/quality/orchestrator.py`
- `src/dativo_ingest/quality/quarantine.py`
- `src/dativo_ingest/quality/notifications.py`
- Integration with existing connectors
- Documentation: `docs/quality/ORCHESTRATION.md`

---

### Phase 5: UI & Monitoring (Month 6, Sprint 11-12)

**Week 1-4: Quality Monitoring & Reporting**
- [ ] Grafana dashboard for quality metrics
- [ ] Quarantine UI for reviewing failed data
- [ ] Historical quality trends
- [ ] Contract compliance reports

**Deliverables**:
- `configs/grafana/quality_dashboard.json`
- Quality metrics in Prometheus
- Quarantine review UI (basic)
- Monthly quality reports

---

## Success Metrics

### Engineering Metrics

```yaml
Quality Check Performance:
  - Check execution time: <30 seconds for 1M rows
  - Soda checks: <10 seconds
  - Great Expectations: <20 seconds
  - Overhead: <5% of total pipeline time

Quality Coverage:
  - Assets with contracts: 100% (production assets)
  - Check types: 5+ per asset (null, unique, range, regex, custom)
  - Test coverage: >85%
```

### Product Metrics

```yaml
Quality Improvements:
  - Contract violations caught: Track count over time
  - False positive rate: <5%
  - Data issues prevented: Track incidents avoided
  - Mean time to detection: <1 hour
```

### Business Metrics

```yaml
ML Team Impact:
  - Model degradation incidents: -80% (prevented by quality checks)
  - Data scientist productivity: +30% (fewer data issues)
  - Trust in data: NPS >70 from ML teams
```

---

## Appendix: Integration Examples

### Example: Stripe Customers with Full Contract

```yaml
# Job configuration
tenant_id: acme
environment: prod

source_connector: stripe
source_connector_path: /app/connectors/stripe.yaml

target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml

asset: stripe_customers
asset_path: /app/assets/stripe/v1.0/customers.yaml

# Data contract enforcement enabled
data_contract:
  enabled: true
  contract_path: /app/contracts/stripe_customers_contract.yaml
  enforcement_mode: strict  # Block on violations

source:
  objects: [customers]
  incremental:
    lookback_days: 1

target:
  branch: acme
  warehouse: s3://lake/acme/
```

### Example: ML Feature Store with Quality Checks

```yaml
# Contract for ML features
data_contract:
  name: ml_features_user_behavior
  version: "1.0"
  owner: ml-team@company.com
  
  quality_checks:
    great_expectations:
      expectation_suite: ml_features_suite
      checks:
        # Feature value ranges (critical for model performance)
        - name: expect_column_values_to_be_between
          column: user_engagement_score
          min_value: 0.0
          max_value: 1.0
        
        # Feature freshness
        - name: expect_column_max_to_be_between
          column: feature_timestamp
          min_value: "2 hours ago"
          max_value: "now"
        
        # No missing features
        - name: expect_column_values_to_not_be_null
          column: user_engagement_score
        
        # Distribution checks (detect data drift)
        - name: expect_column_mean_to_be_between
          column: user_engagement_score
          min_value: 0.3
          max_value: 0.7
        
        - name: expect_column_stdev_to_be_between
          column: user_engagement_score
          min_value: 0.1
          max_value: 0.3
  
  violation_handling:
    on_quality_violation: block  # Critical for ML models
    notification:
      channels: [slack, pagerduty]
      recipients:
        - ml-team@company.com
```

---

**Last Updated**: 2025-11-07  
**Document Owner**: Data Platform Team  
**Review Frequency**: Monthly  
**Status**: Design Phase
