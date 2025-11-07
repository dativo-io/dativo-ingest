# SOC2 & GDPR Compliance Operations

**Version**: 1.0  
**Date**: 2025-11-07  
**Status**: Design Phase

---

## Executive Summary

SOC2 Type II and GDPR compliance require operational capabilities beyond technical controls. This document outlines the implementation of data subject rights (DSR) operations: data download, deletion, and account termination requests.

### Business Value
- **SOC2 Certification**: Required for enterprise customers
- **GDPR Compliance**: Legal requirement for EU customers
- **Competitive Advantage**: 90% of enterprise RFPs require compliance
- **Trust & Brand**: Demonstrates data privacy commitment

---

## Table of Contents

1. [Compliance Requirements](#compliance-requirements)
2. [Data Subject Rights (DSR) Operations](#data-subject-rights-dsr-operations)
3. [Architecture](#architecture)
4. [Implementation](#implementation)
5. [Audit Logging](#audit-logging)
6. [Verification & Testing](#verification--testing)
7. [Implementation Roadmap](#implementation-roadmap)

---

## Compliance Requirements

### SOC2 Type II Requirements

```yaml
SOC2 Trust Service Criteria:
  
  Security (CC6):
    - CC6.1: Logical and physical access controls
    - CC6.2: Prior to issuing system credentials and during periodic reviews
    - CC6.3: Removes access when job role changes or user leaves
    - CC6.7: Restricts access to data and system resources
  
  Confidentiality (C1):
    - C1.1: Confidential information is protected
    - C1.2: Disposal of confidential information
  
  Privacy (P4):
    - P4.1: Collects information consistent with privacy notice
    - P4.2: Retains personal information consistent with policy
    - P4.3: Securely disposes of personal information
    - P4.4: Provides notification of breaches
```

### GDPR Requirements (Articles)

```yaml
GDPR Data Subject Rights:
  
  Article 15 - Right of Access:
    Description: "Data subjects can request copies of their personal data"
    Timeframe: Within 1 month
    Format: "Commonly used, machine-readable format"
  
  Article 17 - Right to Erasure (Right to be Forgotten):
    Description: "Data subjects can request deletion of their personal data"
    Timeframe: Without undue delay
    Scope: "All copies, including backups"
  
  Article 18 - Right to Restriction:
    Description: "Data subjects can request restriction of processing"
    Timeframe: Without undue delay
  
  Article 20 - Right to Data Portability:
    Description: "Receive personal data in structured, machine-readable format"
    Timeframe: Within 1 month
    Format: JSON, CSV, or similar
  
  Article 30 - Records of Processing Activities:
    Description: "Maintain records of all data processing activities"
    Retention: Ongoing
```

### Penalties for Non-Compliance

```
GDPR Fines:
  - Up to €20M or 4% of global annual turnover (whichever is higher)
  - Examples:
    - Amazon: €746M (2021)
    - WhatsApp: €225M (2021)
    - Google: €90M (2020)

SOC2 Impact:
  - Failed audit = lost enterprise deals
  - Average enterprise deal size: $50K-500K/year
  - Time to remediate: 6-12 months
```

---

## Data Subject Rights (DSR) Operations

### Overview of Operations

```
┌────────────────────────────────────────────────────────────────┐
│                  DSR Operation Types                           │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  1. Data Download Request (GDPR Art. 15, 20)                  │
│     - Export all personal data                                │
│     - Machine-readable format (JSON/CSV)                      │
│     - Deliver within 30 days                                  │
│                                                                │
│  2. Data Deletion Request (GDPR Art. 17)                      │
│     - Delete all personal data                                │
│     - Include backups and replicas                            │
│     - Verify deletion completion                              │
│     - Maintain proof of deletion (audit log)                  │
│                                                                │
│  3. Account Termination Request (SOC2 CC6.3)                  │
│     - Revoke all access                                       │
│     - Delete credentials                                      │
│     - Optional: retain anonymized data for analytics          │
│     - Audit trail of termination                              │
│                                                                │
│  4. Data Access Restriction (GDPR Art. 18)                    │
│     - Mark data as "restricted"                               │
│     - Block further processing                                │
│     - Allow storage only                                      │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Architecture

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     DSR Request Portal                          │
│  (Web UI or API for submitting DSR requests)                   │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                  DSR Orchestrator                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │  Request    │  │  Identity   │  │  Workflow   │            │
│  │  Validator  │  │  Verifier   │  │  Engine     │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Data Discovery Engine                          │
│  - Scan all data stores (S3, Iceberg, databases)               │
│  - Identify PII/personal data by tenant/user                   │
│  - Build data map for subject                                  │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Execution Engine                               │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │   Download   │  │   Deletion   │  │ Termination  │         │
│  │   Executor   │  │   Executor   │  │  Executor    │         │
│  └──────────────┘  └──────────────┘  └──────────────┘         │
└──────────────────┬──────────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────────┐
│                  Verification & Audit                           │
│  - Verify operation completion                                  │
│  - Generate compliance reports                                  │
│  - Store audit trail (immutable)                                │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation

### 1. DSR Request API

```python
# File: src/dativo_ingest/compliance/dsr_api.py

from fastapi import FastAPI, HTTPException, BackgroundTasks
from pydantic import BaseModel, EmailStr
from typing import Optional, List
from enum import Enum
import uuid
from datetime import datetime

class DSRRequestType(str, Enum):
    DATA_DOWNLOAD = "data_download"
    DATA_DELETION = "data_deletion"
    ACCOUNT_TERMINATION = "account_termination"
    PROCESSING_RESTRICTION = "processing_restriction"

class DSRRequestStatus(str, Enum):
    PENDING = "pending"
    IDENTITY_VERIFICATION = "identity_verification"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class DSRRequest(BaseModel):
    """Data Subject Rights request."""
    request_id: str
    request_type: DSRRequestType
    tenant_id: str
    subject_email: EmailStr
    subject_id: Optional[str] = None  # User ID if known
    reason: Optional[str] = None
    requested_at: datetime
    requestor_ip: str
    status: DSRRequestStatus = DSRRequestStatus.PENDING
    completed_at: Optional[datetime] = None
    
    # For data download requests
    delivery_format: Optional[str] = "json"  # json | csv | parquet
    
    # For deletion requests
    deletion_scope: Optional[str] = "all"  # all | specific_assets
    assets_to_delete: Optional[List[str]] = None

class DSRRequestCreate(BaseModel):
    """Create new DSR request."""
    request_type: DSRRequestType
    tenant_id: str
    subject_email: EmailStr
    subject_id: Optional[str] = None
    reason: Optional[str] = None
    delivery_format: Optional[str] = "json"
    deletion_scope: Optional[str] = "all"
    assets_to_delete: Optional[List[str]] = None

app = FastAPI()

@app.post("/api/v1/dsr/requests", response_model=DSRRequest)
async def create_dsr_request(
    request: DSRRequestCreate,
    background_tasks: BackgroundTasks,
    requestor_ip: str = None
):
    """
    Create a new Data Subject Rights request.
    
    Process:
    1. Validate request
    2. Generate unique request ID
    3. Send identity verification email
    4. Queue for processing
    5. Return request status
    """
    # Generate request ID
    request_id = str(uuid.uuid4())
    
    # Create DSR request record
    dsr_request = DSRRequest(
        request_id=request_id,
        request_type=request.request_type,
        tenant_id=request.tenant_id,
        subject_email=request.subject_email,
        subject_id=request.subject_id,
        reason=request.reason,
        requested_at=datetime.utcnow(),
        requestor_ip=requestor_ip,
        status=DSRRequestStatus.IDENTITY_VERIFICATION,
        delivery_format=request.delivery_format,
        deletion_scope=request.deletion_scope,
        assets_to_delete=request.assets_to_delete
    )
    
    # Store request in database
    await store_dsr_request(dsr_request)
    
    # Send identity verification email
    background_tasks.add_task(
        send_identity_verification_email,
        request_id,
        request.subject_email
    )
    
    # Log to audit trail
    await log_dsr_event(
        request_id=request_id,
        event_type="REQUEST_CREATED",
        details={
            "request_type": request.request_type,
            "tenant_id": request.tenant_id,
            "subject_email": request.subject_email
        }
    )
    
    return dsr_request

@app.post("/api/v1/dsr/requests/{request_id}/verify")
async def verify_identity(
    request_id: str,
    verification_token: str,
    background_tasks: BackgroundTasks
):
    """
    Verify identity and start processing DSR request.
    
    Process:
    1. Validate verification token
    2. Update request status
    3. Queue for processing
    """
    # Retrieve request
    dsr_request = await get_dsr_request(request_id)
    if not dsr_request:
        raise HTTPException(status_code=404, detail="Request not found")
    
    # Validate token
    if not await validate_verification_token(request_id, verification_token):
        raise HTTPException(status_code=401, detail="Invalid verification token")
    
    # Update status
    dsr_request.status = DSRRequestStatus.IN_PROGRESS
    await update_dsr_request(dsr_request)
    
    # Queue for processing
    background_tasks.add_task(
        process_dsr_request,
        request_id
    )
    
    # Log to audit trail
    await log_dsr_event(
        request_id=request_id,
        event_type="IDENTITY_VERIFIED",
        details={"verified_at": datetime.utcnow().isoformat()}
    )
    
    return {"status": "processing", "request_id": request_id}

@app.get("/api/v1/dsr/requests/{request_id}", response_model=DSRRequest)
async def get_dsr_request_status(request_id: str):
    """Get status of DSR request."""
    dsr_request = await get_dsr_request(request_id)
    if not dsr_request:
        raise HTTPException(status_code=404, detail="Request not found")
    return dsr_request
```

---

### 2. Data Discovery Engine

```python
# File: src/dativo_ingest/compliance/data_discovery.py

from typing import List, Dict, Optional
import boto3
from pyiceberg.catalog import load_catalog

class DataDiscoveryEngine:
    """
    Discover all personal data for a given subject across all data stores.
    
    Features:
    - Scan S3 buckets for Parquet files
    - Scan Iceberg tables
    - Scan state files
    - Identify PII columns based on asset definitions
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.s3_client = boto3.client('s3')
        self.catalog = load_catalog("nessie", **config.get("catalog", {}))
    
    async def discover_subject_data(
        self,
        tenant_id: str,
        subject_id: Optional[str] = None,
        subject_email: Optional[str] = None
    ) -> Dict:
        """
        Discover all data for a data subject.
        
        Args:
            tenant_id: Tenant identifier
            subject_id: Subject's user ID (if known)
            subject_email: Subject's email address
        
        Returns:
            dict: Data map with:
                - data_stores: List of stores containing subject data
                - total_records: Estimated count
                - pii_fields: List of PII fields found
                - estimated_size_mb: Total data size
        """
        data_map = {
            "data_stores": [],
            "total_records": 0,
            "pii_fields": set(),
            "estimated_size_mb": 0
        }
        
        # 1. Scan Iceberg tables
        iceberg_data = await self._scan_iceberg_tables(
            tenant_id,
            subject_id,
            subject_email
        )
        data_map["data_stores"].extend(iceberg_data["tables"])
        data_map["total_records"] += iceberg_data["total_records"]
        data_map["pii_fields"].update(iceberg_data["pii_fields"])
        
        # 2. Scan S3 Parquet files (for tables not in Iceberg)
        s3_data = await self._scan_s3_parquet(
            tenant_id,
            subject_id,
            subject_email
        )
        data_map["data_stores"].extend(s3_data["files"])
        data_map["total_records"] += s3_data["total_records"]
        
        # 3. Scan state files
        state_data = await self._scan_state_files(tenant_id, subject_id)
        data_map["data_stores"].extend(state_data["state_files"])
        
        # 4. Scan audit logs
        audit_data = await self._scan_audit_logs(tenant_id, subject_id)
        data_map["data_stores"].extend(audit_data["log_files"])
        
        return data_map
    
    async def _scan_iceberg_tables(
        self,
        tenant_id: str,
        subject_id: Optional[str],
        subject_email: Optional[str]
    ) -> Dict:
        """Scan Iceberg tables for subject data."""
        results = {
            "tables": [],
            "total_records": 0,
            "pii_fields": set()
        }
        
        # List all tables for tenant
        namespace = f"dativo.{tenant_id}"
        tables = self.catalog.list_tables(namespace)
        
        for table_identifier in tables:
            table = self.catalog.load_table(table_identifier)
            
            # Check if table has PII columns
            pii_columns = self._identify_pii_columns(table.schema())
            if not pii_columns:
                continue
            
            # Build query to count records for subject
            # Example: SELECT COUNT(*) FROM table WHERE email = ?
            count_query = self._build_subject_query(
                table_identifier,
                pii_columns,
                subject_id,
                subject_email
            )
            
            record_count = await self._execute_count_query(count_query)
            
            if record_count > 0:
                results["tables"].append({
                    "type": "iceberg_table",
                    "identifier": str(table_identifier),
                    "record_count": record_count,
                    "pii_columns": list(pii_columns)
                })
                results["total_records"] += record_count
                results["pii_fields"].update(pii_columns)
        
        return results
    
    def _identify_pii_columns(self, schema) -> List[str]:
        """
        Identify PII columns based on:
        1. Asset definition classification
        2. Column name patterns (email, ssn, phone, etc.)
        3. Data type inference
        """
        pii_columns = []
        
        # Common PII column patterns
        pii_patterns = [
            "email", "phone", "ssn", "social_security",
            "address", "name", "firstname", "lastname",
            "credit_card", "passport", "license"
        ]
        
        for field in schema.fields:
            # Check column name
            for pattern in pii_patterns:
                if pattern in field.name.lower():
                    pii_columns.append(field.name)
                    break
            
            # Check asset metadata (if available)
            if field.doc and "PII" in field.doc:
                pii_columns.append(field.name)
        
        return pii_columns
```

---

### 3. Data Download Executor

```python
# File: src/dativo_ingest/compliance/download_executor.py

import pandas as pd
import json
from typing import Dict, List
from datetime import datetime

class DataDownloadExecutor:
    """
    Execute data download requests (GDPR Article 15, 20).
    
    Process:
    1. Discover all subject data
    2. Extract data from all stores
    3. Format in requested format (JSON/CSV)
    4. Encrypt and upload to secure location
    5. Send download link to subject
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.discovery_engine = DataDiscoveryEngine(config)
        self.s3_client = boto3.client('s3')
        self.download_bucket = config["download_bucket"]
        self.download_expiry_hours = config.get("download_expiry_hours", 72)
    
    async def execute_download_request(
        self,
        request_id: str,
        dsr_request: DSRRequest
    ) -> Dict:
        """
        Execute data download request.
        
        Returns:
            dict: Download result with:
                - download_url: Presigned S3 URL
                - expires_at: Expiry timestamp
                - file_size_mb: Size of download package
                - record_count: Total records
        """
        # 1. Discover subject data
        data_map = await self.discovery_engine.discover_subject_data(
            tenant_id=dsr_request.tenant_id,
            subject_id=dsr_request.subject_id,
            subject_email=dsr_request.subject_email
        )
        
        # 2. Extract data from all stores
        extracted_data = await self._extract_all_data(data_map)
        
        # 3. Format data
        if dsr_request.delivery_format == "json":
            formatted_data = self._format_as_json(extracted_data)
        elif dsr_request.delivery_format == "csv":
            formatted_data = self._format_as_csv(extracted_data)
        else:
            formatted_data = self._format_as_parquet(extracted_data)
        
        # 4. Encrypt and upload
        download_path = f"downloads/{request_id}/{dsr_request.subject_email}/"
        encrypted_file = self._encrypt_data(formatted_data)
        
        s3_key = f"{download_path}data.{dsr_request.delivery_format}.gpg"
        self.s3_client.put_object(
            Bucket=self.download_bucket,
            Key=s3_key,
            Body=encrypted_file,
            ServerSideEncryption='AES256',
            Metadata={
                "request_id": request_id,
                "tenant_id": dsr_request.tenant_id,
                "subject_email": dsr_request.subject_email,
                "created_at": datetime.utcnow().isoformat()
            }
        )
        
        # 5. Generate presigned URL (expires in 72 hours)
        download_url = self.s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': self.download_bucket, 'Key': s3_key},
            ExpiresIn=self.download_expiry_hours * 3600
        )
        
        # 6. Send email with download link
        await self._send_download_email(
            dsr_request.subject_email,
            download_url,
            self.download_expiry_hours
        )
        
        return {
            "download_url": download_url,
            "expires_at": datetime.utcnow().isoformat(),
            "file_size_mb": len(encrypted_file) / (1024 * 1024),
            "record_count": data_map["total_records"]
        }
    
    def _format_as_json(self, data: Dict) -> bytes:
        """
        Format extracted data as JSON.
        
        Structure:
        {
          "request_info": {...},
          "data_stores": [
            {
              "store_type": "iceberg_table",
              "identifier": "stripe_customers",
              "records": [...]
            }
          ]
        }
        """
        formatted = {
            "request_info": {
                "generated_at": datetime.utcnow().isoformat(),
                "format": "json",
                "total_records": sum(len(store["records"]) for store in data["stores"])
            },
            "data_stores": data["stores"]
        }
        
        return json.dumps(formatted, indent=2).encode('utf-8')
```

---

### 4. Data Deletion Executor

```python
# File: src/dativo_ingest/compliance/deletion_executor.py

from typing import Dict, List
import boto3

class DataDeletionExecutor:
    """
    Execute data deletion requests (GDPR Article 17).
    
    CRITICAL: Must delete from:
    1. Iceberg tables (current data)
    2. S3 Parquet files (archived data)
    3. State files
    4. Audit logs (anonymize, don't delete)
    5. Backups (S3 versioning, snapshots)
    
    Process:
    1. Discover all subject data
    2. Create deletion plan
    3. Execute deletions (with verification)
    4. Verify deletion completion
    5. Generate proof of deletion certificate
    """
    
    def __init__(self, config: dict):
        self.config = config
        self.discovery_engine = DataDiscoveryEngine(config)
        self.s3_client = boto3.client('s3')
        self.catalog = load_catalog("nessie", **config.get("catalog", {}))
    
    async def execute_deletion_request(
        self,
        request_id: str,
        dsr_request: DSRRequest
    ) -> Dict:
        """
        Execute data deletion request.
        
        Returns:
            dict: Deletion result with:
                - records_deleted: Count of deleted records
                - files_deleted: Count of deleted files
                - tables_affected: List of affected tables
                - verification_status: Verification result
                - deletion_certificate_path: Path to proof certificate
        """
        # 1. Discover subject data
        data_map = await self.discovery_engine.discover_subject_data(
            tenant_id=dsr_request.tenant_id,
            subject_id=dsr_request.subject_id,
            subject_email=dsr_request.subject_email
        )
        
        # 2. Create deletion plan
        deletion_plan = self._create_deletion_plan(data_map, dsr_request)
        
        # 3. Execute deletions
        deletion_results = {
            "records_deleted": 0,
            "files_deleted": 0,
            "tables_affected": [],
            "operations": []
        }
        
        # Delete from Iceberg tables
        for table_info in deletion_plan["iceberg_tables"]:
            result = await self._delete_from_iceberg_table(
                table_info,
                dsr_request.subject_id,
                dsr_request.subject_email
            )
            deletion_results["records_deleted"] += result["records_deleted"]
            deletion_results["tables_affected"].append(table_info["identifier"])
            deletion_results["operations"].append(result)
        
        # Delete S3 Parquet files
        for file_info in deletion_plan["s3_files"]:
            result = await self._delete_from_s3_parquet(
                file_info,
                dsr_request.subject_id,
                dsr_request.subject_email
            )
            deletion_results["files_deleted"] += result["files_deleted"]
            deletion_results["operations"].append(result)
        
        # Delete state files
        for state_file in deletion_plan["state_files"]:
            await self._delete_state_file(state_file)
            deletion_results["files_deleted"] += 1
        
        # Anonymize audit logs (don't delete for compliance)
        for log_entry in deletion_plan["audit_logs"]:
            await self._anonymize_audit_log(log_entry, dsr_request.subject_id)
        
        # 4. Verify deletion
        verification_result = await self._verify_deletion(
            dsr_request.tenant_id,
            dsr_request.subject_id,
            dsr_request.subject_email
        )
        
        # 5. Generate deletion certificate
        certificate_path = await self._generate_deletion_certificate(
            request_id,
            dsr_request,
            deletion_results,
            verification_result
        )
        
        return {
            **deletion_results,
            "verification_status": verification_result["status"],
            "deletion_certificate_path": certificate_path
        }
    
    async def _delete_from_iceberg_table(
        self,
        table_info: Dict,
        subject_id: str,
        subject_email: str
    ) -> Dict:
        """
        Delete records from Iceberg table.
        
        NOTE: Iceberg supports row-level deletes via DELETE statements
        or merge-on-read with delete files.
        """
        table = self.catalog.load_table(table_info["identifier"])
        
        # Build DELETE statement
        # Example: DELETE FROM table WHERE email = 'user@example.com'
        delete_filter = self._build_delete_filter(
            table_info["pii_columns"],
            subject_id,
            subject_email
        )
        
        # Execute delete (via Spark/Trino)
        records_deleted = await self._execute_iceberg_delete(
            table,
            delete_filter
        )
        
        return {
            "operation": "iceberg_delete",
            "table": table_info["identifier"],
            "records_deleted": records_deleted,
            "timestamp": datetime.utcnow().isoformat()
        }
    
    async def _verify_deletion(
        self,
        tenant_id: str,
        subject_id: str,
        subject_email: str
    ) -> Dict:
        """
        Verify that all subject data has been deleted.
        
        Re-run data discovery and confirm zero results.
        """
        data_map = await self.discovery_engine.discover_subject_data(
            tenant_id=tenant_id,
            subject_id=subject_id,
            subject_email=subject_email
        )
        
        if data_map["total_records"] == 0 and len(data_map["data_stores"]) == 0:
            return {
                "status": "VERIFIED",
                "message": "All subject data successfully deleted",
                "verified_at": datetime.utcnow().isoformat()
            }
        else:
            return {
                "status": "FAILED",
                "message": f"Found {data_map['total_records']} remaining records",
                "remaining_stores": data_map["data_stores"],
                "verified_at": datetime.utcnow().isoformat()
            }
    
    async def _generate_deletion_certificate(
        self,
        request_id: str,
        dsr_request: DSRRequest,
        deletion_results: Dict,
        verification_result: Dict
    ) -> str:
        """
        Generate proof of deletion certificate (for compliance).
        
        Certificate includes:
        - Request details
        - Deletion operations performed
        - Verification results
        - Digital signature
        """
        certificate = {
            "certificate_id": f"DEL-{request_id}",
            "request_id": request_id,
            "tenant_id": dsr_request.tenant_id,
            "subject_email": dsr_request.subject_email,
            "subject_id": dsr_request.subject_id,
            "requested_at": dsr_request.requested_at.isoformat(),
            "completed_at": datetime.utcnow().isoformat(),
            "deletion_summary": {
                "records_deleted": deletion_results["records_deleted"],
                "files_deleted": deletion_results["files_deleted"],
                "tables_affected": deletion_results["tables_affected"]
            },
            "operations": deletion_results["operations"],
            "verification": verification_result,
            "compliance_frameworks": ["GDPR Article 17", "SOC2 CC6"],
            "certified_by": "Dativo Ingestion Platform",
            "signature": self._sign_certificate(deletion_results)
        }
        
        # Store certificate in immutable storage
        certificate_path = f"certificates/deletion/{request_id}.json"
        self.s3_client.put_object(
            Bucket=self.config["certificates_bucket"],
            Key=certificate_path,
            Body=json.dumps(certificate, indent=2),
            ServerSideEncryption='AES256',
            Metadata={
                "certificate_type": "deletion",
                "request_id": request_id,
                "tenant_id": dsr_request.tenant_id
            }
        )
        
        return certificate_path
```

---

### 5. Account Termination Executor

```python
# File: src/dativo_ingest/compliance/termination_executor.py

class AccountTerminationExecutor:
    """
    Execute account termination requests (SOC2 CC6.3).
    
    Process:
    1. Revoke all access (API keys, OAuth tokens)
    2. Delete user credentials
    3. Optional: Delete or anonymize user data
    4. Archive account metadata
    5. Audit trail of termination
    """
    
    async def execute_termination_request(
        self,
        request_id: str,
        dsr_request: DSRRequest,
        delete_data: bool = False
    ) -> Dict:
        """
        Execute account termination.
        
        Args:
            request_id: DSR request ID
            dsr_request: DSR request details
            delete_data: If True, also delete all user data
        
        Returns:
            dict: Termination result
        """
        results = {
            "access_revoked": False,
            "credentials_deleted": False,
            "data_deleted": False,
            "operations": []
        }
        
        # 1. Revoke API access
        await self._revoke_api_keys(dsr_request.tenant_id, dsr_request.subject_id)
        await self._revoke_oauth_tokens(dsr_request.tenant_id, dsr_request.subject_id)
        results["access_revoked"] = True
        results["operations"].append({
            "operation": "revoke_access",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # 2. Delete credentials
        await self._delete_credentials(dsr_request.tenant_id, dsr_request.subject_id)
        results["credentials_deleted"] = True
        results["operations"].append({
            "operation": "delete_credentials",
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # 3. Optionally delete data
        if delete_data:
            deletion_executor = DataDeletionExecutor(self.config)
            deletion_result = await deletion_executor.execute_deletion_request(
                request_id,
                dsr_request
            )
            results["data_deleted"] = True
            results["operations"].append({
                "operation": "delete_data",
                "result": deletion_result,
                "timestamp": datetime.utcnow().isoformat()
            })
        
        # 4. Archive account metadata
        await self._archive_account_metadata(dsr_request.tenant_id, dsr_request.subject_id)
        
        return results
```

---

## Audit Logging

### Immutable Audit Trail

```python
# File: src/dativo_ingest/compliance/audit_trail.py

class ComplianceAuditLogger:
    """
    Immutable audit trail for compliance operations.
    
    Requirements:
    - Tamper-proof (append-only, cryptographic hashing)
    - Searchable
    - Long-term retention (7+ years)
    - Exportable for audits
    """
    
    def __init__(self, config: dict):
        self.s3_client = boto3.client('s3')
        self.audit_bucket = config["audit_bucket"]
        self.audit_prefix = "compliance-audit/"
    
    async def log_dsr_event(
        self,
        request_id: str,
        event_type: str,
        actor: str,
        details: Dict
    ):
        """
        Log DSR event to immutable audit trail.
        
        Event types:
        - REQUEST_CREATED
        - IDENTITY_VERIFIED
        - PROCESSING_STARTED
        - DATA_DISCOVERED
        - DATA_EXPORTED
        - DATA_DELETED
        - REQUEST_COMPLETED
        - REQUEST_FAILED
        """
        event = {
            "event_id": str(uuid.uuid4()),
            "request_id": request_id,
            "event_type": event_type,
            "actor": actor,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details,
            "previous_event_hash": await self._get_previous_event_hash(request_id)
        }
        
        # Calculate event hash (for tamper detection)
        event["event_hash"] = self._calculate_event_hash(event)
        
        # Store in S3 (append-only bucket with versioning)
        event_key = f"{self.audit_prefix}{request_id}/{event['event_id']}.json"
        self.s3_client.put_object(
            Bucket=self.audit_bucket,
            Key=event_key,
            Body=json.dumps(event, indent=2),
            ServerSideEncryption='AES256',
            Metadata={
                "event_type": event_type,
                "request_id": request_id,
                "timestamp": event["timestamp"]
            }
        )
```

---

## Implementation Roadmap

### Phase 1: DSR API & Discovery (Month 4, Week 3-4)
- [ ] Implement DSR request API (FastAPI)
- [ ] Build data discovery engine
- [ ] PII column identification logic
- [ ] Testing with sample data

### Phase 2: Data Download (Month 5, Week 1-2)
- [ ] Implement data download executor
- [ ] Multi-format support (JSON, CSV, Parquet)
- [ ] Encryption and secure delivery
- [ ] Email notification system

### Phase 3: Data Deletion (Month 5, Week 3-4)
- [ ] Implement deletion executor
- [ ] Iceberg row-level deletes
- [ ] S3 Parquet rewriting (for non-Iceberg files)
- [ ] Deletion verification
- [ ] Proof of deletion certificates

### Phase 4: Account Termination (Month 6, Week 1)
- [ ] Implement termination executor
- [ ] API key/token revocation
- [ ] Credential deletion
- [ ] Account archival

### Phase 5: Audit & Compliance (Month 6, Week 2)
- [ ] Immutable audit trail
- [ ] Compliance reporting dashboards
- [ ] SOC2 audit preparation documentation
- [ ] GDPR compliance documentation

---

## Success Metrics

```yaml
Operational Metrics:
  - DSR request processing time: <30 days (GDPR requirement)
  - Data discovery accuracy: >99.9% (zero missed PII)
  - Deletion verification: 100% (must verify all deletions)
  - Audit trail completeness: 100%

Compliance Metrics:
  - SOC2 audit pass rate: 100%
  - GDPR compliance score: 100%
  - Data subject satisfaction: >90%
  - Audit findings: 0 critical issues
```

---

**Last Updated**: 2025-11-07  
**Document Owner**: Compliance Team  
**Review Frequency**: Quarterly  
**Status**: Design Phase
