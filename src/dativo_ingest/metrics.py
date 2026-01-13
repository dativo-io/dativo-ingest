"""Metrics collection for job execution and observability.

Supports multiple backends:
- Logging (always enabled)
- Prometheus (configurable, supports multiprocess mode for orchestrated)
- OpenTelemetry (optional, with bounded retry)

Configuration is YAML-first with env var overrides.
"""

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .config import MetricsConfig
from .logging import get_logger

# Optional imports for Prometheus and OpenTelemetry
try:
    from prometheus_client import (
        REGISTRY,
        CollectorRegistry,
        Counter,
        Gauge,
        Histogram,
        multiprocess,
    )

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

try:
    from opentelemetry import metrics as otel_metrics

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


# Canonical metric names (stable schema)
METRIC_NAMES = {
    "records_total": "dativo_ingest_records_total",
    "bytes_total": "dativo_ingest_bytes_total",
    "retries_total": "dativo_ingest_retries_total",
    "api_calls_total": "dativo_ingest_api_calls_total",
    "extract_seconds": "dativo_ingest_extract_seconds",
    "load_seconds": "dativo_ingest_load_seconds",
    "runtime_seconds": "dativo_ingest_runtime_seconds",
    "job_running": "dativo_ingest_job_running",
    "last_success_timestamp": "dativo_ingest_last_success_timestamp_seconds",
    # Validation and dry-run metrics
    "validate_total": "dativo_validate_total",
    "dry_run_total": "dativo_dry_run_total",
}

# Standardized histogram buckets (in seconds)
# Covers jobs from 1s to 1 hour with reasonable granularity
HISTOGRAM_BUCKETS = (1, 2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)

# Label cardinality limits to prevent explosion
KNOWN_API_TYPES = {
    "stripe",
    "hubspot",
    "salesforce",
    "postgres",
    "mysql",
    "http",
    "grpc",
    "unknown",
}
KNOWN_ERROR_TYPES = {
    "timeout",
    "auth",
    "rate_limit",
    "validation",
    "connection",
    "unknown",
}
KNOWN_PHASES = {"extracted", "written", "invalid", "committed"}

# Global Prometheus metrics (initialized once)
_prometheus_initialized = False
_prom_metrics = {}
_multiproc_mode = False


def _validate_label_value(
    value: str, known_set: Set[str], default: str = "unknown"
) -> str:
    """Validate and normalize label values to prevent cardinality explosion.

    Args:
        value: Label value to validate
        known_set: Set of known/allowed values
        default: Default value if not in known set

    Returns:
        Validated label value
    """
    if not value:
        return default
    # Normalize to lowercase and limit length
    normalized = value.lower()[:50]
    return normalized if normalized in known_set else default


def _setup_multiprocess_mode(multiproc_dir: Optional[str]) -> bool:
    """Set up Prometheus multiprocess mode if configured.

    NOTE: Multiprocess cleanup is NOT implemented in this MVP.
    """
    global _multiproc_mode

    if not PROMETHEUS_AVAILABLE or not multiproc_dir:
        return False

    try:
        multiproc_path = Path(multiproc_dir)
        multiproc_path.mkdir(parents=True, exist_ok=True)
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(multiproc_path)
        _multiproc_mode = True
        return True
    except Exception:
        return False


def _initialize_prometheus_metrics(multiproc_dir: Optional[str] = None) -> None:
    """Initialize Prometheus metrics collectors."""
    global _prometheus_initialized

    if _prometheus_initialized or not PROMETHEUS_AVAILABLE:
        return

    _setup_multiprocess_mode(multiproc_dir)

    # Use multiprocess-compatible registry if in multiprocess mode
    if _multiproc_mode:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
    else:
        registry = REGISTRY

    # Counters with phase label
    _prom_metrics["records_total"] = Counter(
        METRIC_NAMES["records_total"],
        "Total number of records processed",
        ["job_name", "tenant_id", "connector_type", "mode", "phase"],
        registry=registry,
    )

    _prom_metrics["bytes_total"] = Counter(
        METRIC_NAMES["bytes_total"],
        "Total bytes processed",
        ["job_name", "tenant_id", "connector_type", "mode", "phase"],
        registry=registry,
    )
    # Note: bytes_total may be zero if file size_bytes is unavailable in metadata.

    _prom_metrics["retries_total"] = Counter(
        METRIC_NAMES["retries_total"],
        "Total number of retries",
        ["job_name", "tenant_id", "connector_type", "mode"],
        registry=registry,
    )
    # Note: retries_total may remain zero unless connector instruments explicitly.

    _prom_metrics["api_calls_total"] = Counter(
        METRIC_NAMES["api_calls_total"],
        "Total API calls made",
        ["job_name", "tenant_id", "connector_type", "mode", "api_type"],
        registry=registry,
    )
    # Note: api_calls_total may remain zero unless connector instruments explicitly.

    # Histograms for timing (standardized buckets)
    _prom_metrics["extract_seconds"] = Histogram(
        METRIC_NAMES["extract_seconds"],
        "Time spent in extraction phase (seconds)",
        ["job_name", "tenant_id", "connector_type", "mode"],
        buckets=HISTOGRAM_BUCKETS,
        registry=registry,
    )

    _prom_metrics["load_seconds"] = Histogram(
        METRIC_NAMES["load_seconds"],
        "Time spent in load/commit phase (seconds)",
        ["job_name", "tenant_id", "connector_type", "mode"],
        buckets=HISTOGRAM_BUCKETS,
        registry=registry,
    )

    _prom_metrics["runtime_seconds"] = Histogram(
        METRIC_NAMES["runtime_seconds"],
        "Total job runtime (seconds)",
        ["job_name", "tenant_id", "connector_type", "mode", "status"],
        buckets=HISTOGRAM_BUCKETS,
        registry=registry,
    )

    # Gauges for current state
    _prom_metrics["job_running"] = Gauge(
        METRIC_NAMES["job_running"],
        "Whether a job is currently running (1=running, 0=not running)",
        ["job_name", "tenant_id", "connector_type", "mode"],
        registry=registry,
    )

    _prom_metrics["last_success_timestamp"] = Gauge(
        METRIC_NAMES["last_success_timestamp"],
        "Unix timestamp of last successful job run",
        ["job_name", "tenant_id", "connector_type", "mode"],
        registry=registry,
    )

    # Validation and dry-run metrics
    _prom_metrics["validate_total"] = Counter(
        METRIC_NAMES["validate_total"],
        "Total validate command executions",
        ["validate_type", "result"],
        registry=registry,
    )

    _prom_metrics["dry_run_total"] = Counter(
        METRIC_NAMES["dry_run_total"],
        "Total dry-run command executions",
        ["result", "connector_type"],
        registry=registry,
    )

    _prometheus_initialized = True


class MetricsCollector:
    """Collects and emits metrics for job execution.

    Configuration precedence: env vars > job config > runner config > defaults
    """

    def __init__(
        self,
        job_name: str,
        tenant_id: str,
        connector_type: str,
        mode: str = "oneshot",
        config: Optional[MetricsConfig] = None,
    ):
        """Initialize metrics collector.

        Args:
            job_name: Name of the job
            tenant_id: Tenant identifier
            connector_type: Type of connector being used
            mode: Execution mode (oneshot or orchestrated)
            config: Metrics configuration (YAML-first)
        """
        self.job_name = job_name
        self.tenant_id = tenant_id
        self.connector_type = connector_type
        self.mode = mode
        self.logger = get_logger()

        # Load configuration with precedence: env > config > defaults
        self.config = config or MetricsConfig()
        self._apply_env_overrides()

        # Timing trackers
        self.start_time: Optional[float] = None
        self.extract_start_time: Optional[float] = None
        self.load_start_time: Optional[float] = None

        # Metrics data
        self.metrics: Dict[str, Any] = {}

        # Backend flags
        self.metrics_enabled = self.config.enabled
        self.prometheus_enabled = (
            self.metrics_enabled
            and PROMETHEUS_AVAILABLE
            and self.config.prometheus.enabled
        )
        self.otel_enabled = (
            self.metrics_enabled
            and OPENTELEMETRY_AVAILABLE
            and self.config.otel.enabled
        )

        # Initialize Prometheus if enabled
        if self.prometheus_enabled:
            _initialize_prometheus_metrics()

        # Base labels for metrics
        self.labels = {
            "job_name": self.job_name,
            "tenant_id": self.tenant_id,
            "connector_type": self.connector_type,
            "mode": self.mode,
        }

    def _apply_env_overrides(self) -> None:
        """Apply minimal environment variable overrides (MVP only)."""
        # Simple port override only
        if os.getenv("DATIVO_METRICS_PORT"):
            try:
                self.config.prometheus.port = int(os.getenv("DATIVO_METRICS_PORT"))
            except ValueError:
                pass

    def start(self) -> None:
        """Start metrics collection."""
        self.start_time = time.time()
        self.metrics = {
            "job_name": self.job_name,
            "tenant_id": self.tenant_id,
            "connector_type": self.connector_type,
            "mode": self.mode,
            "start_time": self.start_time,
        }

        # Set Prometheus gauge
        if self.prometheus_enabled and "job_running" in _prom_metrics:
            _prom_metrics["job_running"].labels(**self.labels).set(1)

    def start_extraction(self) -> None:
        """Mark the start of extraction phase."""
        self.extract_start_time = time.time()

    def end_extraction(self) -> None:
        """Mark the end of extraction phase and record duration."""
        if self.extract_start_time is None:
            return

        duration = time.time() - self.extract_start_time
        self.metrics["extract_seconds"] = duration

        # Record Prometheus histogram
        if self.prometheus_enabled and "extract_seconds" in _prom_metrics:
            _prom_metrics["extract_seconds"].labels(**self.labels).observe(duration)

    def start_load(self) -> None:
        """Mark the start of load phase (writing/commit phase).

        Load phase is defined as: writing files to storage and committing to catalog.
        This includes file uploads and Iceberg catalog commits.
        """
        self.load_start_time = time.time()

    def end_load(self) -> None:
        """Mark the end of load phase (writing/commit phase) and record duration.

        Load phase is defined as: writing files to storage and committing to catalog.
        This includes file uploads and Iceberg catalog commits.
        """
        if self.load_start_time is None:
            return

        duration = time.time() - self.load_start_time
        self.metrics["load_seconds"] = duration

        # Record Prometheus histogram
        if self.prometheus_enabled and "load_seconds" in _prom_metrics:
            _prom_metrics["load_seconds"].labels(**self.labels).observe(duration)

    def record_records(self, count: int, phase: str = "extracted") -> None:
        """Record records processed.

        Args:
            count: Number of records
            phase: Processing phase (extracted, written, invalid, committed)
        """
        phase = _validate_label_value(phase, KNOWN_PHASES, "extracted")
        key = f"records_{phase}"
        self.metrics[key] = self.metrics.get(key, 0) + count

        # Prometheus counter
        if self.prometheus_enabled and "records_total" in _prom_metrics:
            labels = {**self.labels, "phase": phase}
            _prom_metrics["records_total"].labels(**labels).inc(count)

    def record_bytes(self, count: int, phase: str = "written") -> None:
        """Record bytes processed.

        Args:
            count: Number of bytes
            phase: Processing phase (written, committed)
        """
        phase = _validate_label_value(phase, KNOWN_PHASES, "written")
        key = f"bytes_{phase}"
        self.metrics[key] = self.metrics.get(key, 0) + count

        # Prometheus counter
        if self.prometheus_enabled and "bytes_total" in _prom_metrics:
            labels = {**self.labels, "phase": phase}
            _prom_metrics["bytes_total"].labels(**labels).inc(count)

    def record_api_calls(self, count: int, api_type: str = "unknown") -> None:
        """Record API calls.

        Args:
            count: Number of API calls
            api_type: Type of API (validated against known set)
        """
        api_type = _validate_label_value(api_type, KNOWN_API_TYPES, "unknown")

        if "api_calls" not in self.metrics:
            self.metrics["api_calls"] = {}
        self.metrics["api_calls"][api_type] = (
            self.metrics["api_calls"].get(api_type, 0) + count
        )

        # Prometheus counter
        if self.prometheus_enabled and "api_calls_total" in _prom_metrics:
            labels = {**self.labels, "api_type": api_type}
            _prom_metrics["api_calls_total"].labels(**labels).inc(count)

    def record_retry(self) -> None:
        """Record a retry attempt."""
        self.metrics["retries"] = self.metrics.get("retries", 0) + 1

        # Prometheus counter
        if self.prometheus_enabled and "retries_total" in _prom_metrics:
            _prom_metrics["retries_total"].labels(**self.labels).inc()

    def finish(self, status: str = "success") -> Dict[str, Any]:
        """Finish metrics collection and return summary.

        Args:
            status: Final job status (success, failure, partial)

        Returns:
            Complete metrics dictionary
        """
        if self.start_time is None:
            self.logger.warning(
                "Metrics collection finished without start",
                extra={"event_type": "metrics_warning"},
            )
            return self.metrics

        end_time = time.time()
        runtime = end_time - self.start_time

        self.metrics["end_time"] = end_time
        self.metrics["runtime_seconds"] = runtime
        self.metrics["status"] = status

        # Prometheus metrics
        if self.prometheus_enabled:
            # Record runtime histogram
            if "runtime_seconds" in _prom_metrics:
                labels = {**self.labels, "status": status}
                _prom_metrics["runtime_seconds"].labels(**labels).observe(runtime)

            # Update running gauge
            if "job_running" in _prom_metrics:
                _prom_metrics["job_running"].labels(**self.labels).set(0)

            # Update last success timestamp
            if status == "success" and "last_success_timestamp" in _prom_metrics:
                _prom_metrics["last_success_timestamp"].labels(**self.labels).set(
                    end_time
                )

        # Emit final metrics to logs
        # Exclude LogRecord reserved fields and fields already in labels
        log_record_reserved = {
            "message",
            "asctime",
            "name",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
            "exc_info",
            "exc_text",
            "stack_info",
        }
        # Also exclude fields that are already in self.labels (job_name, tenant_id, connector_type, mode)
        label_fields = {"job_name", "tenant_id", "connector_type", "mode"}
        extra = {
            "event_type": "metrics_complete",
            "status": status,
            "runtime_seconds": runtime,
            **{
                k: v
                for k, v in self.metrics.items()
                if k not in ["start_time", "end_time"]
                and k not in log_record_reserved
                and k not in label_fields
            },
        }

        self.logger.info("Job execution metrics", extra=extra)

        return self.metrics


def get_multiprocess_registry() -> Optional[object]:
    """Get Prometheus multiprocess registry for HTTP server.

    Returns:
        CollectorRegistry configured for multiprocess mode, or None
    """
    if not PROMETHEUS_AVAILABLE or not _multiproc_mode:
        return None

    try:
        from prometheus_client import CollectorRegistry, multiprocess

        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        return registry
    except Exception:
        return None


def record_validate_metric(validate_type: str, result: str) -> None:
    """Record validation metric to Prometheus.

    Args:
        validate_type: Type of validation (config or asset)
        result: Result of validation (success, failure)
    """
    if not PROMETHEUS_AVAILABLE:
        return

    _initialize_prometheus_metrics()

    if "validate_total" in _prom_metrics:
        try:
            _prom_metrics["validate_total"].labels(
                validate_type=validate_type, result=result
            ).inc()
        except Exception:
            pass


def record_dry_run_metric(result: str, connector_type: str) -> None:
    """Record dry-run metric to Prometheus.

    Args:
        result: Result of dry-run (success, failure, timeout)
        connector_type: Type of source connector
    """
    if not PROMETHEUS_AVAILABLE:
        return

    _initialize_prometheus_metrics()

    if "dry_run_total" in _prom_metrics:
        try:
            _prom_metrics["dry_run_total"].labels(
                result=result, connector_type=connector_type
            ).inc()
        except Exception:
            pass
