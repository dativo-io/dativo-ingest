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
}

# Standardized histogram buckets (in seconds)
# Covers jobs from 1s to 1 hour with reasonable granularity
HISTOGRAM_BUCKETS = (1, 2, 5, 10, 30, 60, 120, 300, 600, 1800, 3600)

# Label cardinality limits to prevent explosion
KNOWN_API_TYPES = {"stripe", "hubspot", "salesforce", "postgres", "mysql", "http", "grpc", "unknown"}
KNOWN_ERROR_TYPES = {"timeout", "auth", "rate_limit", "validation", "connection", "unknown"}
KNOWN_PHASES = {"extracted", "written", "invalid", "committed"}

# Global Prometheus metrics (initialized once)
_prometheus_initialized = False
_prom_metrics = {}
_multiproc_mode = False


def _validate_label_value(value: str, known_set: Set[str], default: str = "unknown") -> str:
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


def _setup_multiprocess_mode(multiproc_dir: Optional[str], cleanup_on_startup: bool = False) -> bool:
    """Set up Prometheus multiprocess mode if configured.

    Args:
        multiproc_dir: Directory for multiprocess metrics
        cleanup_on_startup: If True, delete stale *.db files at startup

    Returns:
        True if multiprocess mode enabled
    """
    global _multiproc_mode

    if not PROMETHEUS_AVAILABLE or not multiproc_dir:
        return False

    logger = get_logger()

    try:
        # Create directory if it doesn't exist
        multiproc_path = Path(multiproc_dir)
        multiproc_path.mkdir(parents=True, exist_ok=True)

        # Test write permission
        test_file = multiproc_path / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except (OSError, PermissionError) as e:
            logger.warning(
                f"Prometheus multiprocess directory not writable: {multiproc_dir}. "
                f"Disabling multiprocess mode. Error: {e}",
                extra={"event_type": "metrics_multiproc_not_writable"},
            )
            return False

        # Cleanup stale files if requested
        if cleanup_on_startup:
            try:
                stale_files = list(multiproc_path.glob("*.db"))
                if stale_files:
                    for db_file in stale_files:
                        db_file.unlink()
                    logger.info(
                        f"Cleaned up {len(stale_files)} stale multiprocess db files",
                        extra={"event_type": "metrics_multiproc_cleanup", "count": len(stale_files)},
                    )
            except Exception as cleanup_error:
                logger.warning(
                    f"Failed to cleanup stale multiprocess files: {cleanup_error}",
                    extra={"event_type": "metrics_multiproc_cleanup_failed"},
                )

        # Set environment variable for prometheus_client
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = str(multiproc_path)

        _multiproc_mode = True
        logger.debug(
            f"Prometheus multiprocess mode enabled: {multiproc_dir}",
            extra={"event_type": "metrics_multiproc_enabled"},
        )
        return True

    except Exception as e:
        logger.warning(
            f"Failed to setup Prometheus multiprocess mode: {e}. Disabling multiprocess mode.",
            extra={"event_type": "metrics_multiproc_setup_failed"},
        )
        return False


def _initialize_prometheus_metrics(multiproc_dir: Optional[str] = None, cleanup_on_startup: bool = False) -> None:
    """Initialize Prometheus metrics collectors.

    Args:
        multiproc_dir: Optional directory for multiprocess mode
        cleanup_on_startup: If True, cleanup stale db files
    """
    global _prometheus_initialized, _prom_metrics

    if _prometheus_initialized or not PROMETHEUS_AVAILABLE:
        return

    # Set up multiprocess mode if configured
    _setup_multiprocess_mode(multiproc_dir, cleanup_on_startup)

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

    _prom_metrics["retries_total"] = Counter(
        METRIC_NAMES["retries_total"],
        "Total number of retries",
        ["job_name", "tenant_id", "connector_type", "mode"],
        registry=registry,
    )

    _prom_metrics["api_calls_total"] = Counter(
        METRIC_NAMES["api_calls_total"],
        "Total API calls made",
        ["job_name", "tenant_id", "connector_type", "mode", "api_type"],
        registry=registry,
    )

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
            self.metrics_enabled and OPENTELEMETRY_AVAILABLE and self.config.otel.enabled
        )

        # Initialize Prometheus if enabled
        if self.prometheus_enabled:
            _initialize_prometheus_metrics(
                self.config.prometheus.multiproc_dir,
                self.config.prometheus.cleanup_on_startup
            )

        # Base labels for metrics (cardinality-aware)
        # Use "disabled" for high-cardinality labels when not included to keep schema stable
        self.labels = {
            "job_name": self.job_name if self.config.labels.include_job_name else "disabled",
            "tenant_id": self.tenant_id if self.config.labels.include_tenant_id else "disabled",
            "connector_type": self.connector_type,  # Always included (low cardinality)
            "mode": self.mode if self.config.labels.include_mode else "disabled",
        }

        # Add optional environment label if configured
        if self.config.labels.include_env:
            env = os.getenv("DATIVO_ENVIRONMENT", "production")
            self.labels["environment"] = env

    def _apply_env_overrides(self) -> None:
        """Apply environment variable overrides to configuration."""
        # Prometheus overrides
        if os.getenv("DATIVO_METRICS_PROMETHEUS") is not None:
            self.config.prometheus.enabled = (
                os.getenv("DATIVO_METRICS_PROMETHEUS", "true").lower() == "true"
            )

        if os.getenv("DATIVO_METRICS_PORT") is not None:
            try:
                self.config.prometheus.port = int(os.getenv("DATIVO_METRICS_PORT"))
            except ValueError:
                pass

        if os.getenv("DATIVO_METRICS_HOST") is not None:
            self.config.prometheus.host = os.getenv("DATIVO_METRICS_HOST")

        if os.getenv("PROMETHEUS_MULTIPROC_DIR") is not None:
            self.config.prometheus.multiproc_dir = os.getenv("PROMETHEUS_MULTIPROC_DIR")

        # OTEL overrides
        if os.getenv("DATIVO_METRICS_OTEL") is not None:
            self.config.otel.enabled = (
                os.getenv("DATIVO_METRICS_OTEL", "false").lower() == "true"
            )

        if os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") is not None:
            self.config.otel.endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")

        if os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL") is not None:
            protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")
            if protocol in ("grpc", "http"):
                self.config.otel.protocol = protocol

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
        """Mark the start of load/commit phase."""
        self.load_start_time = time.time()

    def end_load(self) -> None:
        """Mark the end of load phase and record duration."""
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
        extra = {
            "event_type": "metrics_complete",
            "status": status,
            "runtime_seconds": runtime,
            **{k: v for k, v in self.metrics.items() if k not in ["start_time", "end_time"]},
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
