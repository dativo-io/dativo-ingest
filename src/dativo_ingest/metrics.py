"""Metrics collection for job execution and observability."""

import time
from typing import Any, Dict, Optional

from .logging import get_logger


class MetricsCollector:
    """Collects and emits metrics for job execution."""

    def __init__(self, job_name: str, tenant_id: str):
        """Initialize metrics collector.

        Args:
            job_name: Name of the job
            tenant_id: Tenant identifier
        """
        self.job_name = job_name
        self.tenant_id = tenant_id
        self.logger = get_logger()
        self.start_time: Optional[float] = None
        self.metrics: Dict[str, Any] = {}

    def start(self) -> None:
        """Start metrics collection."""
        self.start_time = time.time()
        self.metrics = {
            "job_name": self.job_name,
            "tenant_id": self.tenant_id,
            "start_time": self.start_time,
        }

    def record_extraction(self, records_count: int, files_count: int = 0) -> None:
        """Record extraction metrics.

        Args:
            records_count: Number of records extracted
            files_count: Number of files processed
        """
        self.metrics["records_extracted"] = records_count
        self.metrics["files_processed"] = files_count

        self.logger.info(
            "Extraction metrics recorded",
            extra={
                "event_type": "metrics_extraction",
                "records_count": records_count,
                "files_count": files_count,
                "job_name": self.job_name,
                "tenant_id": self.tenant_id,
            },
        )

    def record_validation(
        self, valid_records: int, invalid_records: int, total_records: int
    ) -> None:
        """Record validation metrics.

        Args:
            valid_records: Number of valid records
            invalid_records: Number of invalid records
            total_records: Total records validated
        """
        self.metrics["records_valid"] = valid_records
        self.metrics["records_invalid"] = invalid_records
        self.metrics["records_total"] = total_records

        validation_rate = (
            (valid_records / total_records * 100) if total_records > 0 else 0
        )

        self.logger.info(
            "Validation metrics recorded",
            extra={
                "event_type": "metrics_validation",
                "valid_records": valid_records,
                "invalid_records": invalid_records,
                "total_records": total_records,
                "validation_rate_percent": validation_rate,
                "job_name": self.job_name,
                "tenant_id": self.tenant_id,
            },
        )

    def record_writing(
        self, files_written: int, total_bytes: int, file_sizes: Optional[list] = None
    ) -> None:
        """Record writing metrics.

        Args:
            files_written: Number of files written
            total_bytes: Total bytes written
            file_sizes: List of individual file sizes (optional)
        """
        self.metrics["files_written"] = files_written
        self.metrics["bytes_written"] = total_bytes
        self.metrics["file_sizes"] = file_sizes or []

        total_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else 0

        self.logger.info(
            "Writing metrics recorded",
            extra={
                "event_type": "metrics_writing",
                "files_written": files_written,
                "bytes_written": total_bytes,
                "total_mb": total_mb,
                "job_name": self.job_name,
                "tenant_id": self.tenant_id,
            },
        )

    def record_api_calls(self, api_calls: int, api_type: Optional[str] = None) -> None:
        """Record API call metrics.

        Args:
            api_calls: Number of API calls made
            api_type: Type of API (e.g., 'stripe', 'hubspot')
        """
        if "api_calls" not in self.metrics:
            self.metrics["api_calls"] = {}
        if api_type:
            self.metrics["api_calls"][api_type] = api_calls
        else:
            self.metrics["api_calls"]["total"] = api_calls

        self.logger.info(
            "API call metrics recorded",
            extra={
                "event_type": "metrics_api_calls",
                "api_calls": api_calls,
                "api_type": api_type,
                "job_name": self.job_name,
                "tenant_id": self.tenant_id,
            },
        )

    def record_error(self, error_type: str, error_count: int = 1) -> None:
        """Record error metrics.

        Args:
            error_type: Type of error
            error_count: Number of errors
        """
        if "errors" not in self.metrics:
            self.metrics["errors"] = {}
        self.metrics["errors"][error_type] = (
            self.metrics["errors"].get(error_type, 0) + error_count
        )

        self.logger.warning(
            "Error metrics recorded",
            extra={
                "event_type": "metrics_error",
                "error_type": error_type,
                "error_count": error_count,
                "job_name": self.job_name,
                "tenant_id": self.tenant_id,
            },
        )

    def record_retry(self, attempt: int, exit_code: Optional[int] = None) -> None:
        """Record retry metrics.

        Args:
            attempt: Retry attempt number
            exit_code: Exit code that triggered retry
        """
        if "retries" not in self.metrics:
            self.metrics["retries"] = {"count": 0, "attempts": []}
        self.metrics["retries"]["count"] += 1
        self.metrics["retries"]["attempts"].append(
            {"attempt": attempt, "exit_code": exit_code}
        )

        self.logger.info(
            "Retry metrics recorded",
            extra={
                "event_type": "metrics_retry",
                "retry_count": self.metrics["retries"]["count"],
                "attempt": attempt,
                "exit_code": exit_code,
                "job_name": self.job_name,
                "tenant_id": self.tenant_id,
            },
        )

    def finish(self, status: str = "success") -> Dict[str, Any]:
        """Finish metrics collection and return summary.

        Args:
            status: Final job status

        Returns:
            Complete metrics dictionary
        """
        if self.start_time is None:
            self.logger.warning(
                "Metrics collection finished without start",
                extra={"event_type": "metrics_warning", "job_name": self.job_name},
            )
            return self.metrics

        end_time = time.time()
        execution_time = end_time - self.start_time

        self.metrics["end_time"] = end_time
        self.metrics["execution_time_seconds"] = execution_time
        self.metrics["status"] = status

        # Calculate rates
        if "records_extracted" in self.metrics:
            records_per_second = (
                self.metrics["records_extracted"] / execution_time
                if execution_time > 0
                else 0
            )
            self.metrics["records_per_second"] = records_per_second

        # Emit final metrics
        self.logger.info(
            "Job execution metrics",
            extra={
                "event_type": "metrics_complete",
                "job_name": self.job_name,
                "tenant_id": self.tenant_id,
                "status": status,
                "execution_time_seconds": execution_time,
                **{
                    k: v
                    for k, v in self.metrics.items()
                    if k not in ["start_time", "end_time"]
                },
            },
        )

        return self.metrics
