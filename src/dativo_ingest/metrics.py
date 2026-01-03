"""Metrics collection for job execution and observability."""

import os
import time
import threading
from typing import Any, Dict, Optional, Union

from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
    OTLPMetricExporter as OTLPHttpMetricExporter,
)
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from prometheus_client import start_http_server

from .logging import get_logger
from .config import MetricsConfig

# Global state for singleton initialization
_LOCK = threading.Lock()
_INITIALIZED = False
_METER = None


class MetricsManager:
    """Singleton manager for OpenTelemetry and Prometheus configuration."""

    @staticmethod
    def initialize(
        config: Optional[MetricsConfig] = None,
        service_name: str = "dativo-ingest",
        instance_id: Optional[str] = None,
    ) -> None:
        """Initialize metrics subsystem.

        Args:
            config: Metrics configuration
            service_name: Service name for OTEL resource
            instance_id: Unique instance ID
        """
        global _INITIALIZED, _METER

        with _LOCK:
            if _INITIALIZED:
                return

            # Default config if not provided
            if config is None:
                config = MetricsConfig(enabled=True)

            if not config.enabled:
                _INITIALIZED = True
                return

            resource = Resource.create(
                {
                    "service.name": service_name,
                    "service.instance.id": instance_id or os.uname().nodename,
                }
            )

            readers = []

            # 1. Prometheus Exporter (if configured)
            # The PrometheusMetricReader registers itself with the default prometheus_client registry
            if config.prometheus_port:
                reader = PrometheusMetricReader()
                readers.append(reader)
                
                # Start the HTTP server for scraping
                # We catch errors in case port is in use (common in dev/tests)
                try:
                    start_http_server(config.prometheus_port)
                    get_logger().info(
                        f"Prometheus metrics server started on port {config.prometheus_port}",
                        extra={"event_type": "metrics_server_started", "port": config.prometheus_port}
                    )
                except OSError as e:
                    get_logger().warning(
                        f"Failed to start Prometheus metrics server on port {config.prometheus_port}: {e}",
                        extra={"event_type": "metrics_server_error"}
                    )

            # 2. OTLP Exporter (if configured)
            if config.otlp_endpoint:
                protocol = "grpc" if "http" not in config.otlp_endpoint else "http/protobuf"
                
                if protocol == "http/protobuf":
                    exporter = OTLPHttpMetricExporter(
                        endpoint=config.otlp_endpoint,
                        headers=config.otlp_headers or {},
                    )
                else:
                    exporter = OTLPMetricExporter(
                        endpoint=config.otlp_endpoint,
                        headers=config.otlp_headers or {},
                    )
                
                reader = PeriodicExportingMetricReader(exporter)
                readers.append(reader)

            # Initialize MeterProvider
            provider = MeterProvider(resource=resource, metric_readers=readers)
            metrics.set_meter_provider(provider)
            _METER = metrics.get_meter("dativo.ingest")
            _INITIALIZED = True


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
        
        # Ensure system is initialized (best effort)
        if not _INITIALIZED:
            MetricsManager.initialize()
            
        self.meter = _METER or metrics.get_meter("dativo.ingest")

        # Define instruments
        self.counter_records_extracted = self.meter.create_counter(
            "dativo_ingest_records_extracted_total",
            description="Total number of records extracted",
        )
        self.counter_records_valid = self.meter.create_counter(
            "dativo_ingest_records_valid_total",
            description="Total number of valid records",
        )
        self.counter_records_invalid = self.meter.create_counter(
            "dativo_ingest_records_invalid_total",
            description="Total number of invalid records",
        )
        self.counter_files_processed = self.meter.create_counter(
            "dativo_ingest_files_processed_total",
            description="Total number of source files processed",
        )
        self.counter_files_written = self.meter.create_counter(
            "dativo_ingest_files_written_total",
            description="Total number of output files written",
        )
        self.counter_bytes_written = self.meter.create_counter(
            "dativo_ingest_bytes_written_total",
            description="Total bytes written to storage",
            unit="bytes",
        )
        self.counter_api_calls = self.meter.create_counter(
            "dativo_ingest_api_calls_total",
            description="Total number of API calls made",
        )
        self.counter_retries = self.meter.create_counter(
            "dativo_ingest_retries_total",
            description="Total number of retries",
        )
        self.counter_errors = self.meter.create_counter(
            "dativo_ingest_errors_total",
            description="Total number of errors encountered",
        )
        
        self.histogram_duration = self.meter.create_histogram(
            "dativo_ingest_job_duration_seconds",
            description="Job execution duration in seconds",
            unit="s",
        )
        self.histogram_extraction_duration = self.meter.create_histogram(
            "dativo_ingest_extraction_duration_seconds",
            description="Extraction phase duration in seconds",
            unit="s",
        )

        # Base attributes for all metrics
        self.base_attributes = {
            "job_name": job_name,
            "tenant_id": tenant_id,
        }

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

        self.counter_records_extracted.add(records_count, self.base_attributes)
        if files_count > 0:
            self.counter_files_processed.add(files_count, self.base_attributes)

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

        self.counter_records_valid.add(valid_records, self.base_attributes)
        self.counter_records_invalid.add(invalid_records, self.base_attributes)

        validation_rate = (
            (valid_records / total_records * 100) if total_records > 0 else 0
        )

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

        self.counter_files_written.add(files_written, self.base_attributes)
        self.counter_bytes_written.add(total_bytes, self.base_attributes)

        total_mb = total_bytes / (1024 * 1024) if total_bytes > 0 else 0

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
        
        key = api_type or "total"
        if api_type:
            self.metrics["api_calls"][api_type] = api_calls
        else:
            self.metrics["api_calls"]["total"] = api_calls

        attrs = self.base_attributes.copy()
        if api_type:
            attrs["api_type"] = api_type
            
        self.counter_api_calls.add(api_calls, attrs)

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

        attrs = self.base_attributes.copy()
        attrs["error_type"] = error_type
        self.counter_errors.add(error_count, attrs)

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
        
        attrs = self.base_attributes.copy()
        if exit_code is not None:
            attrs["exit_code"] = str(exit_code)
        
        self.counter_retries.add(1, attrs)

        extra = {
            "event_type": "metrics_retry",
            "retry_count": self.metrics["retries"]["count"],
            "attempt": attempt,
            "exit_code": exit_code,
        }
        self.logger.info("Retry metrics recorded", extra=extra)

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
        
        # Record duration
        attrs = self.base_attributes.copy()
        attrs["status"] = status
        self.histogram_duration.record(execution_time, attrs)

        # Calculate rates
        if "records_extracted" in self.metrics:
            records_per_second = (
                self.metrics["records_extracted"] / execution_time
                if execution_time > 0
                else 0
            )
            self.metrics["records_per_second"] = records_per_second

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

        self.logger.info("Job execution metrics", extra=extra)
        
        # Force flush if needed (in oneshot mode, important to flush before exit)
        try:
            provider = metrics.get_meter_provider()
            if hasattr(provider, "force_flush"):
                provider.force_flush()
        except Exception:
            # Ignore flush errors
            pass

        return self.metrics
