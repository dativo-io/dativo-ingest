from datetime import datetime
from typing import Any, Dict, Optional, List, Union
from pydantic import BaseModel, Field

class RunInfo(BaseModel):
    id: str
    type: str = Field(..., description="Run type: incremental | replay | full_refresh")
    start_time: datetime
    end_time: Optional[datetime] = None
    tenant_id: str
    job_name: str
    triggered_by: Optional[str] = None
    environment: Optional[str] = None
    # Replay metadata
    replay_reason: Optional[str] = None

class IngestionInfo(BaseModel):
    status: str
    duration_seconds: Optional[float] = None
    exit_code: Optional[int] = None
    error: Optional['RunErrorInfo'] = None

class VolumeInfo(BaseModel):
    records_extracted: int = 0
    records_written: int = 0
    records_invalid: int = 0
    files_written: int = 0
    bytes_written: int = 0
    retries: int = 0

class TimeInfo(BaseModel):
    event_time_field: Optional[str] = None
    watermark: Optional[Dict[str, Any]] = None
    # Replay metadata
    replay_range_start: Optional[datetime] = None
    replay_range_end: Optional[datetime] = None

class SchemaInfo(BaseModel):
    version: str
    enforcement_mode: str

class StorageInfo(BaseModel):
    format: Optional[str] = None
    target_type: str
    commit_id: Optional[str] = None
    files_added: Optional[int] = None
    branch: Optional[str] = None
    partition_stats: Optional[Dict[str, Any]] = None

class ResourceInfo(BaseModel):
    cpu_seconds: Optional[float] = None
    memory_mb: Optional[float] = None
    api_calls: Optional[int] = None

class CostInfo(BaseModel):
    estimated_usd: Optional[float] = None

class RunErrorInfo(BaseModel):
    has_errors: bool = False
    error_summary: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    error_type: Optional[str] = None

class RunAssetInfo(BaseModel):
    id: Optional[str] = None
    name: str
    version: str

class RunSummary(BaseModel):
    """
    Run Summary Artifact.

    Contains ingestion facts only. Interpretation is out of scope.
    Written once per run. Immutable.
    """
    run: RunInfo
    ingestion: IngestionInfo
    volume: VolumeInfo = Field(default_factory=VolumeInfo)
    time: TimeInfo = Field(default_factory=TimeInfo)
    schema_info: SchemaInfo = Field(..., alias="schema")
    storage: StorageInfo
    resources: ResourceInfo = Field(default_factory=ResourceInfo)
    cost: CostInfo = Field(default_factory=CostInfo)
    
    # Asset info is critical for identification
    asset: RunAssetInfo

    # Extra metadata if needed
    metadata: Dict[str, Any] = Field(default_factory=dict)
