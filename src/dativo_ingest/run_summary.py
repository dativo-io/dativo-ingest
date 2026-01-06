from datetime import datetime
from typing import Any, Dict, Optional, List
from pydantic import BaseModel, Field

class RunAssetInfo(BaseModel):
    id: Optional[str] = None
    name: str
    version: str

class RunConnectorInfo(BaseModel):
    source_type: str
    target_type: str
    extractor_class: Optional[str] = None
    writer_class: Optional[str] = None

class RunMetrics(BaseModel):
    records_extracted: int = 0
    records_written: int = 0  # valid records
    records_invalid: int = 0
    files_written: int = 0
    bytes_written: int = 0
    retries: int = 0

class RunCommitInfo(BaseModel):
    commit_id: Optional[str] = None
    files_added: Optional[int] = None
    table_name: Optional[str] = None
    branch: Optional[str] = None
    partition_stats: Optional[Dict[str, Any]] = None

class RunErrorInfo(BaseModel):
    has_errors: bool = False
    error_summary: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None

class RunSummary(BaseModel):
    tenant_id: str
    job_name: str
    run_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    status: str = "running"
    exit_code: Optional[int] = None
    
    asset: RunAssetInfo
    connector: RunConnectorInfo
    metrics: RunMetrics = Field(default_factory=RunMetrics)
    commit: Optional[RunCommitInfo] = None
    error: Optional[RunErrorInfo] = None
    
    metadata: Dict[str, Any] = Field(default_factory=dict)
