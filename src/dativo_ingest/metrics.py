"""Metrics export (Prometheus + OpenTelemetry)."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from .logging import get_logger

logger = get_logger()

# -----------------------------
# Prometheus (pull) metrics
# -----------------------------

try:
    from prometheus_client import CollectorRegistry, Counter, Histogram, make_wsgi_app
    from prometheus_client.multiprocess import MultiProcessCollector

    PROMETHEUS_AVAILABLE = True
except Exception:  # pragma: no cover
    PROMETHEUS_AVAILABLE = False
    CollectorRegistry = None  # type: ignore[assignment]
    Counter = None  # type: ignore[assignment]
    Histogram = None  # type: ignore[assignment]
    make_wsgi_app = None  # type: ignore[assignment]
    MultiProcessCollector = None  # type: ignore[assignment]


_PROM_RECORDS = None
_PROM_BYTES = None
_PROM_RETRIES = None
_PROM_API_CALLS = None
_PROM_EXTRACT_SECONDS = None
_PROM_LOAD_SECONDS = None
_PROM_RUNTIME_SECONDS = None

_PROM_INIT_LOCK = threading.Lock()


def _prom_init() -> None:
    """Initialize Prometheus metrics (idempotent)."""
    global _PROM_RECORDS
    global _PROM_BYTES
    global _PROM_RETRIES
    global _PROM_API_CALLS
    global _PROM_EXTRACT_SECONDS
    global _PROM_LOAD_SECONDS
    global _PROM_RUNTIME_SECONDS

    if not PROMETHEUS_AVAILABLE:
        return

    with _PROM_INIT_LOCK:
        if _PROM_RECORDS is not None:
            return

        labels = ["tenant_id", "job_name", "connector_type", "mode"]

        _PROM_RECORDS = Counter(
            "dativo_ingest_records_total",
            "Records processed by ingestion jobs",
            labels + ["phase"],
        )
        _PROM_BYTES = Counter(
            "dativo_ingest_bytes_total",
            "Bytes processed by ingestion jobs",
            labels + ["phase"],
        )
        _PROM_RETRIES = Counter(
            "dativo_ingest_retries_total",
            "Retries performed by ingestion jobs",
            labels,
        )
        _PROM_API_CALLS = Counter(
            "dativo_ingest_api_calls_total",
            "API calls performed by ingestion jobs",
            labels + ["api_type"],
        )
        _PROM_EXTRACT_SECONDS = Histogram(
            "dativo_ingest_extract_seconds",
            "Extraction duration in seconds",
            labels,
            buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
        )
        _PROM_LOAD_SECONDS = Histogram(
            "dativo_ingest_load_seconds",
            "Load/commit duration in seconds",
            labels,
            buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
        )
        _PROM_RUNTIME_SECONDS = Histogram(
            "dativo_ingest_runtime_seconds",
            "Total runtime duration in seconds",
            labels,
            buckets=(0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
        )


def start_prometheus_metrics_http_server(
    *,
    host: str = "0.0.0.0",
    port: int = 9400,
    multiprocess_dir: Optional[str] = None,
) -> None:
    """Expose Prometheus metrics over HTTP at `/:9400/metrics` (default).

    In orchestrated mode, jobs often run in subprocesses. If `multiprocess_dir`
    (or env `PROMETHEUS_MULTIPROC_DIR`) is configured, this endpoint aggregates
    metrics across processes.
    """
    if not PROMETHEUS_AVAILABLE:
        logger.warning(
            "Prometheus client not available; metrics endpoint disabled",
            extra={"event_type": "metrics_prometheus_disabled"},
        )
        return

    _prom_init()

    # If multiprocess_dir is set, it MUST be present before workers start.
    mp_dir = multiprocess_dir or os.getenv("PROMETHEUS_MULTIPROC_DIR")
    registry = CollectorRegistry()
    if mp_dir:
        os.environ["PROMETHEUS_MULTIPROC_DIR"] = mp_dir
        os.makedirs(mp_dir, exist_ok=True)
        MultiProcessCollector(registry)

    app = make_wsgi_app(registry)

    def _serve() -> None:
        from wsgiref.simple_server import make_server

        httpd = make_server(host, port, app)
        logger.info(
            "Prometheus metrics endpoint started",
            extra={
                "event_type": "metrics_prometheus_started",
                "host": host,
                "port": port,
                "path": "/metrics",
                "multiprocess_dir": mp_dir,
            },
        )
        httpd.serve_forever()

    # Run the server in a daemon thread; orchestrated mode is long-running anyway.
    t = threading.Thread(target=_serve, name="prometheus-metrics", daemon=True)
    t.start()


# -----------------------------
# OpenTelemetry (push) metrics
# -----------------------------

try:
    from opentelemetry import metrics as otel_metrics
    from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    OTEL_AVAILABLE = True
except Exception:  # pragma: no cover
    OTEL_AVAILABLE = False
    otel_metrics = None  # type: ignore[assignment]
    OTLPMetricExporter = None  # type: ignore[assignment]
    MeterProvider = None  # type: ignore[assignment]
    PeriodicExportingMetricReader = None  # type: ignore[assignment]
    Resource = None  # type: ignore[assignment]


_OTEL_PROVIDER: Optional[Any] = None
_OTEL_METER: Optional[Any] = None
_OTEL_RECORDS = None
_OTEL_BYTES = None
_OTEL_RETRIES = None
_OTEL_API_CALLS = None
_OTEL_EXTRACT_SECONDS = None
_OTEL_LOAD_SECONDS = None
_OTEL_RUNTIME_SECONDS = None

_OTEL_INIT_LOCK = threading.Lock()


def init_otel_metrics(
    *,
    service_name: str = "dativo-ingest",
    endpoint: Optional[str] = None,
    export_interval_seconds: int = 10,
) -> None:
    """Initialize OTEL metrics export via OTLP/HTTP (idempotent)."""
    global _OTEL_PROVIDER
    global _OTEL_METER
    global _OTEL_RECORDS
    global _OTEL_BYTES
    global _OTEL_RETRIES
    global _OTEL_API_CALLS
    global _OTEL_EXTRACT_SECONDS
    global _OTEL_LOAD_SECONDS
    global _OTEL_RUNTIME_SECONDS

    if not OTEL_AVAILABLE:
        return

    with _OTEL_INIT_LOCK:
        if _OTEL_PROVIDER is not None:
            return

        otlp_endpoint = (
            endpoint
            or os.getenv("DATIVO_OTEL_METRICS_ENDPOINT")
            or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        )
        if not otlp_endpoint:
            return

        resource = Resource.create({"service.name": service_name})
        exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
        reader = PeriodicExportingMetricReader(
            exporter, export_interval_millis=export_interval_seconds * 1000
        )
        provider = MeterProvider(resource=resource, metric_readers=[reader])
        otel_metrics.set_meter_provider(provider)
        meter = otel_metrics.get_meter(service_name)

        _OTEL_PROVIDER = provider
        _OTEL_METER = meter

        # Mirror the Prometheus names as closely as possible.
        _OTEL_RECORDS = meter.create_counter(
            "dativo_ingest_records_total", unit="1", description="Records processed"
        )
        _OTEL_BYTES = meter.create_counter(
            "dativo_ingest_bytes_total", unit="By", description="Bytes processed"
        )
        _OTEL_RETRIES = meter.create_counter(
            "dativo_ingest_retries_total", unit="1", description="Retries performed"
        )
        _OTEL_API_CALLS = meter.create_counter(
            "dativo_ingest_api_calls_total", unit="1", description="API calls performed"
        )
        _OTEL_EXTRACT_SECONDS = meter.create_histogram(
            "dativo_ingest_extract_seconds",
            unit="s",
            description="Extraction duration in seconds",
        )
        _OTEL_LOAD_SECONDS = meter.create_histogram(
            "dativo_ingest_load_seconds",
            unit="s",
            description="Load/commit duration in seconds",
        )
        _OTEL_RUNTIME_SECONDS = meter.create_histogram(
            "dativo_ingest_runtime_seconds",
            unit="s",
            description="Total runtime duration in seconds",
        )

        logger.info(
            "OpenTelemetry metrics enabled",
            extra={
                "event_type": "metrics_otel_enabled",
                "endpoint": otlp_endpoint,
                "service_name": service_name,
                "export_interval_seconds": export_interval_seconds,
            },
        )


def shutdown_otel_metrics(timeout_seconds: int = 5) -> None:
    """Flush metrics for short-lived oneshot runs."""
    if not OTEL_AVAILABLE:
        return
    global _OTEL_PROVIDER
    global _OTEL_METER
    global _OTEL_RECORDS
    global _OTEL_BYTES
    global _OTEL_RETRIES
    global _OTEL_API_CALLS
    global _OTEL_EXTRACT_SECONDS
    global _OTEL_LOAD_SECONDS
    global _OTEL_RUNTIME_SECONDS

    provider = _OTEL_PROVIDER
    if provider is None:
        return
    try:
        provider.force_flush(timeout_millis=timeout_seconds * 1000)
        provider.shutdown()
        _OTEL_PROVIDER = None
        _OTEL_METER = None
        _OTEL_RECORDS = None
        _OTEL_BYTES = None
        _OTEL_RETRIES = None
        _OTEL_API_CALLS = None
        _OTEL_EXTRACT_SECONDS = None
        _OTEL_LOAD_SECONDS = None
        _OTEL_RUNTIME_SECONDS = None
    except Exception:
        # Never fail a job because metrics couldn't flush.
        logger.debug(
            "Failed to flush OTEL metrics",
            extra={"event_type": "metrics_otel_flush_failed"},
        )


def flush_otel_metrics(timeout_seconds: int = 5) -> None:
    """Force-flush OTEL metrics without shutting down the provider."""
    if not OTEL_AVAILABLE:
        return
    provider = _OTEL_PROVIDER
    if provider is None:
        return
    try:
        provider.force_flush(timeout_millis=timeout_seconds * 1000)
    except Exception:
        logger.debug(
            "Failed to flush OTEL metrics",
            extra={"event_type": "metrics_otel_flush_failed"},
        )


# -----------------------------
# Public API used by executors/connectors
# -----------------------------


@dataclass(frozen=True)
class MetricLabels:
    tenant_id: str
    job_name: str
    connector_type: str
    mode: str

    def as_dict(self) -> Dict[str, str]:
        return {
            "tenant_id": self.tenant_id,
            "job_name": self.job_name,
            "connector_type": self.connector_type,
            "mode": self.mode,
        }


class JobRunMetrics:
    """Small helper to update global counters/histograms for a single job run."""

    def __init__(self, labels: MetricLabels):
        self.labels = labels
        self._t0 = time.perf_counter()

        _prom_init()
        init_otel_metrics()

    def inc_records(self, count: int, *, phase: str) -> None:
        if count <= 0:
            return
        if PROMETHEUS_AVAILABLE and _PROM_RECORDS is not None:
            _PROM_RECORDS.labels(**self.labels.as_dict(), phase=phase).inc(count)
        if OTEL_AVAILABLE and _OTEL_RECORDS is not None:
            _OTEL_RECORDS.add(count, {**self.labels.as_dict(), "phase": phase})

    def inc_bytes(self, count: int, *, phase: str) -> None:
        if count <= 0:
            return
        if PROMETHEUS_AVAILABLE and _PROM_BYTES is not None:
            _PROM_BYTES.labels(**self.labels.as_dict(), phase=phase).inc(count)
        if OTEL_AVAILABLE and _OTEL_BYTES is not None:
            _OTEL_BYTES.add(count, {**self.labels.as_dict(), "phase": phase})

    def inc_retries(self, count: int = 1) -> None:
        if count <= 0:
            return
        if PROMETHEUS_AVAILABLE and _PROM_RETRIES is not None:
            _PROM_RETRIES.labels(**self.labels.as_dict()).inc(count)
        if OTEL_AVAILABLE and _OTEL_RETRIES is not None:
            _OTEL_RETRIES.add(count, self.labels.as_dict())

    def inc_api_calls(self, count: int = 1, *, api_type: str = "unknown") -> None:
        if count <= 0:
            return
        if PROMETHEUS_AVAILABLE and _PROM_API_CALLS is not None:
            _PROM_API_CALLS.labels(**self.labels.as_dict(), api_type=api_type).inc(count)
        if OTEL_AVAILABLE and _OTEL_API_CALLS is not None:
            _OTEL_API_CALLS.add(count, {**self.labels.as_dict(), "api_type": api_type})

    def observe_extract_seconds(self, seconds: float) -> None:
        if seconds < 0:
            return
        if PROMETHEUS_AVAILABLE and _PROM_EXTRACT_SECONDS is not None:
            _PROM_EXTRACT_SECONDS.labels(**self.labels.as_dict()).observe(seconds)
        if OTEL_AVAILABLE and _OTEL_EXTRACT_SECONDS is not None:
            _OTEL_EXTRACT_SECONDS.record(seconds, self.labels.as_dict())

    def observe_load_seconds(self, seconds: float) -> None:
        if seconds < 0:
            return
        if PROMETHEUS_AVAILABLE and _PROM_LOAD_SECONDS is not None:
            _PROM_LOAD_SECONDS.labels(**self.labels.as_dict()).observe(seconds)
        if OTEL_AVAILABLE and _OTEL_LOAD_SECONDS is not None:
            _OTEL_LOAD_SECONDS.record(seconds, self.labels.as_dict())

    def observe_runtime_seconds(self, seconds: float) -> None:
        if seconds < 0:
            return
        if PROMETHEUS_AVAILABLE and _PROM_RUNTIME_SECONDS is not None:
            _PROM_RUNTIME_SECONDS.labels(**self.labels.as_dict()).observe(seconds)
        if OTEL_AVAILABLE and _OTEL_RUNTIME_SECONDS is not None:
            _OTEL_RUNTIME_SECONDS.record(seconds, self.labels.as_dict())

    def finish(self) -> None:
        elapsed = time.perf_counter() - self._t0
        self.observe_runtime_seconds(elapsed)
        # For short-lived runs, force-flush so metrics reach the collector.
        if os.getenv("DATIVO_METRICS_ONESHOT_FLUSH", "true").lower() in ("1", "true"):
            flush_otel_metrics()


def metrics_enabled() -> bool:
    return os.getenv("DATIVO_METRICS_ENABLED", "true").lower() in ("1", "true")


def build_job_labels(
    *,
    tenant_id: str,
    job_name: str,
    connector_type: str,
    mode: str,
) -> MetricLabels:
    return MetricLabels(
        tenant_id=tenant_id or "unknown",
        job_name=job_name or "unknown",
        connector_type=connector_type or "unknown",
        mode=mode or "unknown",
    )


def start_orchestrated_metrics_endpoint_if_enabled() -> None:
    """Start `/metrics` endpoint for orchestrated mode (best-effort)."""
    if not metrics_enabled():
        return
    if os.getenv("DATIVO_METRICS_PROMETHEUS_ENABLED", "true").lower() not in (
        "1",
        "true",
    ):
        return

    port = int(os.getenv("DATIVO_METRICS_PROMETHEUS_PORT", "9400"))
    host = os.getenv("DATIVO_METRICS_PROMETHEUS_HOST", "0.0.0.0")
    mp_dir = os.getenv("DATIVO_PROMETHEUS_MULTIPROC_DIR", ".local/prometheus")

    # Enable Prometheus multiprocess mode so subprocess job runs contribute.
    os.environ.setdefault("PROMETHEUS_MULTIPROC_DIR", mp_dir)

    # Reset stale metrics files on orchestrator start (best-effort).
    if os.getenv("DATIVO_PROMETHEUS_MULTIPROC_RESET", "true").lower() in ("1", "true"):
        try:
            os.makedirs(mp_dir, exist_ok=True)
            for name in os.listdir(mp_dir):
                if name.endswith(".db"):
                    try:
                        os.remove(os.path.join(mp_dir, name))
                    except OSError:
                        pass
        except OSError:
            pass

    start_prometheus_metrics_http_server(host=host, port=port, multiprocess_dir=mp_dir)


# -----------------------------------------------------------------------------
# Backward-compatibility shim (older tests + code paths)
# -----------------------------------------------------------------------------


class MetricsCollector:
    """Backwards-compatible metrics collector (structured logs + counters).

    This is kept to avoid breaking older integrations/tests that expect the
    `MetricsCollector` interface. New code should prefer `JobRunMetrics`.
    """

    def __init__(self, job_name: str, tenant_id: str):
        self.job_name = job_name
        self.tenant_id = tenant_id
        self.logger = get_logger()
        self.start_time: Optional[float] = None
        self.metrics: Dict[str, Any] = {}

        self._job_metrics: Optional[JobRunMetrics] = None
        if metrics_enabled():
            self._job_metrics = JobRunMetrics(
                build_job_labels(
                    tenant_id=tenant_id,
                    job_name=job_name,
                    connector_type="unknown",
                    mode=os.getenv("DATIVO_EXECUTION_MODE", "unknown"),
                )
            )

    def start(self) -> None:
        self.start_time = time.time()
        self.metrics = {
            "job_name": self.job_name,
            "tenant_id": self.tenant_id,
            "start_time": self.start_time,
        }

    def record_extraction(self, records_count: int, files_count: int = 0) -> None:
        self.metrics["records_extracted"] = records_count
        self.metrics["files_processed"] = files_count
        if self._job_metrics:
            self._job_metrics.inc_records(records_count, phase="extracted")
        self.logger.info(
            "Extraction metrics recorded",
            extra={
                "event_type": "metrics_extraction",
                "records_count": records_count,
                "files_count": files_count,
            },
        )

    def record_validation(
        self, valid_records: int, invalid_records: int, total_records: int
    ) -> None:
        self.metrics["records_valid"] = valid_records
        self.metrics["records_invalid"] = invalid_records
        self.metrics["records_total"] = total_records
        if self._job_metrics:
            self._job_metrics.inc_records(valid_records, phase="validated")
            self._job_metrics.inc_records(invalid_records, phase="invalid")
        validation_rate = (valid_records / total_records * 100) if total_records > 0 else 0
        self.logger.info(
            "Validation metrics recorded",
            extra={
                "event_type": "metrics_validation",
                "valid_records": valid_records,
                "invalid_records": invalid_records,
                "total_records": total_records,
                "validation_rate_percent": validation_rate,
            },
        )

    def record_writing(
        self, files_written: int, total_bytes: int, file_sizes: Optional[list] = None
    ) -> None:
        self.metrics["files_written"] = files_written
        self.metrics["bytes_written"] = total_bytes
        self.metrics["file_sizes"] = file_sizes or []
        if self._job_metrics:
            self._job_metrics.inc_bytes(total_bytes, phase="written")
        total_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else 0
        self.logger.info(
            "Writing metrics recorded",
            extra={
                "event_type": "metrics_writing",
                "files_written": files_written,
                "bytes_written": total_bytes,
                "total_mb": total_mb,
            },
        )

    def record_api_calls(self, api_calls: int, api_type: Optional[str] = None) -> None:
        if "api_calls" not in self.metrics:
            self.metrics["api_calls"] = {}
        self.metrics["api_calls"][api_type or "total"] = api_calls
        if self._job_metrics:
            self._job_metrics.inc_api_calls(api_calls, api_type=api_type or "unknown")
        self.logger.info(
            "API call metrics recorded",
            extra={
                "event_type": "metrics_api_calls",
                "api_calls": api_calls,
                "api_type": api_type,
            },
        )

    def record_error(self, error_type: str, error_count: int = 1) -> None:
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
            },
        )

    def record_retry(self, attempt: int, exit_code: Optional[int] = None) -> None:
        if "retries" not in self.metrics:
            self.metrics["retries"] = {"count": 0, "attempts": []}
        self.metrics["retries"]["count"] += 1
        self.metrics["retries"]["attempts"].append(
            {"attempt": attempt, "exit_code": exit_code}
        )
        if self._job_metrics:
            self._job_metrics.inc_retries(1)
        self.logger.info(
            "Retry metrics recorded",
            extra={
                "event_type": "metrics_retry",
                "retry_count": self.metrics["retries"]["count"],
                "attempt": attempt,
                "exit_code": exit_code,
            },
        )

    def finish(self, status: str = "success") -> Dict[str, Any]:
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
        if "records_extracted" in self.metrics:
            self.metrics["records_per_second"] = (
                self.metrics["records_extracted"] / execution_time
                if execution_time > 0
                else 0
            )
        if self._job_metrics:
            self._job_metrics.observe_runtime_seconds(execution_time)
            self._job_metrics.finish()
        self.logger.info(
            "Job execution metrics",
            extra={
                "event_type": "metrics_complete",
                "status": status,
                "execution_time_seconds": execution_time,
                **{
                    k: v
                    for k, v in self.metrics.items()
                    if k not in ["start_time", "end_time", "tenant_id", "job_name"]
                },
            },
        )
        return self.metrics

