"""Metrics collection for job execution and observability.

Supports multiple backends:
- Logging (default)
- Prometheus (via prometheus_client)
- OpenTelemetry (via opentelemetry SDK)
"""

import os
import time
from typing import Any, Dict, List, Optional

from .logging import get_logger

# Optional imports for Prometheus and OpenTelemetry
try:
    from prometheus_client import Counter, Gauge, Histogram, Summary

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


# Global Prometheus metrics (initialized once)
_prometheus_initialized = False
_prom_metrics = {}


def _initialize_prometheus_metrics():
    """Initialize Prometheus metrics collectors."""
    global _prometheus_initialized, _prom_metrics

    if _prometheus_initialized or not PROMETHEUS_AVAILABLE:
        return

    # Counters
    _prom_metrics["records_extracted_total"] = Counter(
        "dativo_records_extracted_total",
        "Total number of records extracted",
        ["job_name", "tenant_id", "connector_type"],
    )
    _prom_metrics["records_valid_total"] = Counter(
        "dativo_records_valid_total",
        "Total number of valid records",
        ["job_name", "tenant_id", "connector_type"],
    )
    _prom_metrics["records_invalid_total"] = Counter(
        "dativo_records_invalid_total",
        "Total number of invalid records",
        ["job_name", "tenant_id", "connector_type"],
    )
    _prom_metrics["bytes_written_total"] = Counter(
        "dativo_bytes_written_total",
        "Total bytes written to storage",
        ["job_name", "tenant_id", "connector_type"],
    )
    _prom_metrics["files_written_total"] = Counter(
        "dativo_files_written_total",
        "Total files written",
        ["job_name", "tenant_id", "connector_type"],
    )
    _prom_metrics["api_calls_total"] = Counter(
        "dativo_api_calls_total",
        "Total API calls made",
        ["job_name", "tenant_id", "connector_type", "api_type"],
    )
    _prom_metrics["job_runs_total"] = Counter(
        "dativo_job_runs_total",
        "Total job runs",
        ["job_name", "tenant_id", "connector_type", "status"],
    )
    _prom_metrics["retries_total"] = Counter(
        "dativo_retries_total",
        "Total number of retries",
        ["job_name", "tenant_id", "connector_type"],
    )
    _prom_metrics["errors_total"] = Counter(
        "dativo_errors_total",
        "Total errors by type",
        ["job_name", "tenant_id", "connector_type", "error_type"],
    )

    # Histograms for timing
    _prom_metrics["extraction_duration_seconds"] = Histogram(
        "dativo_extraction_duration_seconds",
        "Time spent extracting data",
        ["job_name", "tenant_id", "connector_type"],
        buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
    )
    _prom_metrics["job_duration_seconds"] = Histogram(
        "dativo_job_duration_seconds",
        "Total job execution time",
        ["job_name", "tenant_id", "connector_type"],
        buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
    )
    _prom_metrics["batch_processing_seconds"] = Histogram(
        "dativo_batch_processing_seconds",
        "Time to process a batch",
        ["job_name", "tenant_id", "connector_type"],
        buckets=(0.1, 0.5, 1, 2, 5, 10, 30, 60),
    )

    # Gauges for current state
    _prom_metrics["job_running"] = Gauge(
        "dativo_job_running",
        "Whether a job is currently running (1=running, 0=not running)",
        ["job_name", "tenant_id", "connector_type"],
    )
    _prom_metrics["last_success_timestamp"] = Gauge(
        "dativo_last_success_timestamp_seconds",
        "Timestamp of last successful job run",
        ["job_name", "tenant_id", "connector_type"],
    )

    # Summary for percentiles
    _prom_metrics["records_per_batch"] = Summary(
        "dativo_records_per_batch",
        "Number of records per batch",
        ["job_name", "tenant_id", "connector_type"],
    )

    _prometheus_initialized = True


class MetricsCollector:
    """Collects and emits metrics for job execution."""

    def __init__(
        self,
        job_name: str,
        tenant_id: str,
        connector_type: str = "unknown",
        enable_prometheus: bool = True,
        enable_otel: bool = False,
    ):
        """Initialize metrics collector.

        Args:
            job_name: Name of the job
            tenant_id: Tenant identifier
            connector_type: Type of connector being used
            enable_prometheus: Whether to emit Prometheus metrics
            enable_otel: Whether to emit OpenTelemetry metrics
        """
        self.job_name = job_name
        self.tenant_id = tenant_id
        self.connector_type = connector_type
        self.logger = get_logger()
        self.start_time: Optional[float] = None
        self.extraction_start_time: Optional[float] = None
        self.metrics: Dict[str, Any] = {}

        # Backend flags
        self.enable_prometheus = (
            enable_prometheus
            and PROMETHEUS_AVAILABLE
            and os.getenv("DATIVO_METRICS_PROMETHEUS", "true").lower() == "true"
        )
        self.enable_otel = (
            enable_otel
            and OPENTELEMETRY_AVAILABLE
            and os.getenv("DATIVO_METRICS_OTEL", "false").lower() == "true"
        )

        # Initialize Prometheus metrics if enabled
        if self.enable_prometheus:
            _initialize_prometheus_metrics()

        # Initialize OpenTelemetry meter if enabled
        self.otel_meter = None
        if self.enable_otel:
            meter_provider = otel_metrics.get_meter_provider()
            self.otel_meter = meter_provider.get_meter("dativo_ingest")

        # Label set for metrics
        self.labels = {
            "job_name": self.job_name,
            "tenant_id": self.tenant_id,
            "connector_type": self.connector_type,
        }

    def start(self) -> None:
        """Start metrics collection."""
        self.start_time = time.time()
        self.metrics = {
            "job_name": self.job_name,
            "tenant_id": self.tenant_id,
            "connector_type": self.connector_type,
            "start_time": self.start_time,
        }

        # Set Prometheus gauge
        if self.enable_prometheus and "job_running" in _prom_metrics:
            _prom_metrics["job_running"].labels(**self.labels).set(1)

    def start_extraction(self) -> None:
        """Mark the start of extraction phase."""
        self.extraction_start_time = time.time()

    def end_extraction(self) -> None:
        """Mark the end of extraction phase and record duration."""
        if self.extraction_start_time is None:
            return

        duration = time.time() - self.extraction_start_time
        self.metrics["extraction_duration_seconds"] = duration

        # Record Prometheus histogram
        if self.enable_prometheus and "extraction_duration_seconds" in _prom_metrics:
            _prom_metrics["extraction_duration_seconds"].labels(**self.labels).observe(
                duration
            )

    def record_extraction(self, records_count: int, files_count: int = 0) -> None:
        """Record extraction metrics.

        Args:
            records_count: Number of records extracted
            files_count: Number of files processed
        """
        self.metrics["records_extracted"] = records_count
        self.metrics["files_processed"] = files_count

        # Prometheus counters
        if self.enable_prometheus and "records_extracted_total" in _prom_metrics:
            _prom_metrics["records_extracted_total"].labels(**self.labels).inc(
                records_count
            )

        # Build extra dict - exclude tenant_id and job_name to avoid conflicts with log factory
        extra = {
            "event_type": "metrics_extraction",
            "records_count": records_count,
            "files_count": files_count,
        }

        self.logger.info("Extraction metrics recorded", extra=extra)

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

        # Prometheus counters
        if self.enable_prometheus:
            if "records_valid_total" in _prom_metrics:
                _prom_metrics["records_valid_total"].labels(**self.labels).inc(
                    valid_records
                )
            if "records_invalid_total" in _prom_metrics:
                _prom_metrics["records_invalid_total"].labels(**self.labels).inc(
                    invalid_records
                )

        # Build extra dict
        extra = {
            "event_type": "metrics_validation",
            "valid_records": valid_records,
            "invalid_records": invalid_records,
            "total_records": total_records,
            "validation_rate_percent": validation_rate,
        }

        self.logger.info("Validation metrics recorded", extra=extra)

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

        # Prometheus counters
        if self.enable_prometheus:
            if "files_written_total" in _prom_metrics:
                _prom_metrics["files_written_total"].labels(**self.labels).inc(
                    files_written
                )
            if "bytes_written_total" in _prom_metrics:
                _prom_metrics["bytes_written_total"].labels(**self.labels).inc(
                    total_bytes
                )

        # Build extra dict
        extra = {
            "event_type": "metrics_writing",
            "files_written": files_written,
            "bytes_written": total_bytes,
            "total_mb": total_mb,
        }

        self.logger.info("Writing metrics recorded", extra=extra)

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

        # Prometheus counter
        if self.enable_prometheus and "api_calls_total" in _prom_metrics:
            labels = {**self.labels, "api_type": api_type or "unknown"}
            _prom_metrics["api_calls_total"].labels(**labels).inc(api_calls)

        # Build extra dict
        extra = {
            "event_type": "metrics_api_calls",
            "api_calls": api_calls,
            "api_type": api_type,
        }

        self.logger.info("API call metrics recorded", extra=extra)

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

        # Prometheus counter
        if self.enable_prometheus and "errors_total" in _prom_metrics:
            labels = {**self.labels, "error_type": error_type}
            _prom_metrics["errors_total"].labels(**labels).inc(error_count)

        # Build extra dict
        extra = {
            "event_type": "metrics_error",
            "error_type": error_type,
            "error_count": error_count,
        }

        self.logger.warning("Error metrics recorded", extra=extra)

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

        # Prometheus counter
        if self.enable_prometheus and "retries_total" in _prom_metrics:
            _prom_metrics["retries_total"].labels(**self.labels).inc()

        # Build extra dict
        extra = {
            "event_type": "metrics_retry",
            "retry_count": self.metrics["retries"]["count"],
            "attempt": attempt,
            "exit_code": exit_code,
        }

        self.logger.info("Retry metrics recorded", extra=extra)

    def record_batch(self, batch_size: int, processing_time: float) -> None:
        """Record batch processing metrics.

        Args:
            batch_size: Number of records in the batch
            processing_time: Time taken to process the batch (seconds)
        """
        # Prometheus metrics
        if self.enable_prometheus:
            if "records_per_batch" in _prom_metrics:
                _prom_metrics["records_per_batch"].labels(**self.labels).observe(
                    batch_size
                )
            if "batch_processing_seconds" in _prom_metrics:
                _prom_metrics["batch_processing_seconds"].labels(
                    **self.labels
                ).observe(processing_time)

    def finish(self, status: str = "success") -> Dict[str, Any]:
        """Finish metrics collection and return summary.

        Args:
            status: Final job status (success, partial, failure)

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

        # Prometheus metrics
        if self.enable_prometheus:
            # Record job run counter
            if "job_runs_total" in _prom_metrics:
                labels = {**self.labels, "status": status}
                _prom_metrics["job_runs_total"].labels(**labels).inc()

            # Record job duration
            if "job_duration_seconds" in _prom_metrics:
                _prom_metrics["job_duration_seconds"].labels(**self.labels).observe(
                    execution_time
                )

            # Update running gauge
            if "job_running" in _prom_metrics:
                _prom_metrics["job_running"].labels(**self.labels).set(0)

            # Update last success timestamp
            if status == "success" and "last_success_timestamp" in _prom_metrics:
                _prom_metrics["last_success_timestamp"].labels(**self.labels).set(
                    end_time
                )

        # Build extra dict
        extra = {
            "event_type": "metrics_complete",
            "status": status,
            "execution_time_seconds": execution_time,
            **{
                k: v
                for k, v in self.metrics.items()
                if k not in ["start_time", "end_time", "tenant_id", "job_name"]
            },
        }

        # Emit final metrics
        self.logger.info("Job execution metrics", extra=extra)

        return self.metrics
