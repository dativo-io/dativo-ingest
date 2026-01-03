"""OpenTelemetry metrics configuration and export.

Supports OTLP export to collectors via gRPC or HTTP protocols.
Includes bounded retry logic and graceful degradation.
"""

import os
import time
from typing import Optional

from .config import OtelConfig
from .logging import get_logger

# Optional imports for OpenTelemetry
try:
    from opentelemetry import metrics
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False

# Track last export failure time for throttled warnings
_last_export_failure_log = 0
_export_failure_log_interval = 300  # Log at most once per 5 minutes


def _get_otel_exporter(config: OtelConfig):
    """Get appropriate OTEL exporter based on protocol.

    Args:
        config: OTEL configuration

    Returns:
        OTLP exporter instance

    Raises:
        ImportError: If required exporter package not available
        ValueError: If endpoint not configured
    """
    if not config.endpoint:
        raise ValueError("OTEL endpoint not configured")

    if config.protocol == "grpc":
        try:
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )

            return OTLPMetricExporter(
                endpoint=config.endpoint,
                headers=config.headers or {},
                timeout=config.timeout_seconds,
            )
        except ImportError:
            raise ImportError(
                "opentelemetry-exporter-otlp-proto-grpc not installed. "
                "Install with: pip install opentelemetry-exporter-otlp-proto-grpc"
            )
    elif config.protocol == "http":
        try:
            from opentelemetry.exporter.otlp.proto.http.metric_exporter import (
                OTLPMetricExporter,
            )

            return OTLPMetricExporter(
                endpoint=config.endpoint,
                headers=config.headers or {},
                timeout=config.timeout_seconds,
            )
        except ImportError:
            raise ImportError(
                "opentelemetry-exporter-otlp-proto-http not installed. "
                "Install with: pip install opentelemetry-exporter-otlp-proto-http"
            )
    else:
        raise ValueError(f"Unknown OTEL protocol: {config.protocol}")


class ThrottledExportMetricReader(PeriodicExportingMetricReader):
    """Metric reader with throttled error logging.

    Prevents log spam when OTEL collector is down.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.logger = get_logger()
        self._consecutive_failures = 0

    def _export(self):
        """Override export to add throttled logging."""
        global _last_export_failure_log

        try:
            result = super()._export()
            # Reset failure counter on success
            if self._consecutive_failures > 0:
                self.logger.info(
                    "OTEL export resumed successfully",
                    extra={"event_type": "otel_export_resumed"},
                )
            self._consecutive_failures = 0
            return result
        except Exception as e:
            self._consecutive_failures += 1

            # Log failures with throttling
            current_time = time.time()
            should_log = (current_time - _last_export_failure_log) > _export_failure_log_interval

            if should_log or self._consecutive_failures == 1:
                self.logger.warning(
                    f"OTEL metrics export failed (consecutive failures: {self._consecutive_failures}): {e}",
                    extra={
                        "event_type": "otel_export_failed",
                        "consecutive_failures": self._consecutive_failures,
                    },
                )
                _last_export_failure_log = current_time

            # Don't crash the job, just skip this export
            return


def configure_otel_metrics(
    config: OtelConfig,
    service_name: str = "dativo-ingest",
    service_version: str = "0.5.1",
    environment: Optional[str] = None,
) -> bool:
    """Configure OpenTelemetry metrics with OTLP exporter.

    Args:
        config: OTEL configuration
        service_name: Service name for resource attributes
        service_version: Service version for resource attributes
        environment: Deployment environment (from job config)

    Returns:
        True if configured successfully, False otherwise
    """
    logger = get_logger()

    # Silent return if not enabled
    if not config.enabled:
        logger.debug(
            "OpenTelemetry metrics disabled by configuration",
            extra={"event_type": "otel_disabled"},
        )
        return False

    if not OPENTELEMETRY_AVAILABLE:
        logger.warning(
            "OpenTelemetry SDK not available. Install opentelemetry-sdk to enable OTEL metrics.",
            extra={"event_type": "otel_unavailable"},
        )
        return False

    if not config.endpoint:
        logger.warning(
            "OTEL endpoint not configured. Set otel.endpoint in config or OTEL_EXPORTER_OTLP_ENDPOINT env var.",
            extra={"event_type": "otel_no_endpoint"},
        )
        return False

    try:
        # Create resource with service metadata
        resource_attrs = {
            "service.name": service_name,
            "service.version": service_version,
        }

        # Add environment if provided
        if environment:
            resource_attrs["deployment.environment"] = environment
        else:
            resource_attrs["deployment.environment"] = os.getenv(
                "DATIVO_ENVIRONMENT", "production"
            )

        resource = Resource.create(resource_attrs)

        # Create OTLP exporter (protocol-specific)
        otlp_exporter = _get_otel_exporter(config)

        # Create metric reader with throttled error handling
        metric_reader = ThrottledExportMetricReader(
            exporter=otlp_exporter,
            export_interval_millis=config.export_interval_seconds * 1000,
            export_timeout_millis=config.timeout_seconds * 1000,
        )

        # Create and set meter provider
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        metrics.set_meter_provider(meter_provider)

        # Log configuration (do NOT log headers - may contain secrets)
        logger.info(
            f"OpenTelemetry metrics configured with {config.protocol} endpoint: {config.endpoint}",
            extra={
                "event_type": "otel_configured",
                "endpoint": config.endpoint,
                "protocol": config.protocol,
                "export_interval_seconds": config.export_interval_seconds,
                "service_name": service_name,
                "headers_configured": bool(config.headers),  # Log presence, not values
            },
        )

        return True

    except ImportError as e:
        logger.error(
            f"Failed to configure OpenTelemetry metrics: {e}",
            extra={
                "event_type": "otel_import_error",
                "error": str(e),
            },
        )
        return False
    except Exception as e:
        logger.error(
            f"Failed to configure OpenTelemetry metrics: {e}",
            extra={
                "event_type": "otel_configuration_error",
                "endpoint": config.endpoint,
                "protocol": config.protocol,
                "error": str(e),
            },
            exc_info=True,
        )
        return False


def get_otel_meter(name: str = "dativo_ingest") -> Optional[object]:
    """Get OpenTelemetry meter instance.

    Args:
        name: Meter name

    Returns:
        Meter instance or None if OTEL not available
    """
    if not OPENTELEMETRY_AVAILABLE:
        return None

    try:
        meter_provider = metrics.get_meter_provider()
        return meter_provider.get_meter(name)
    except Exception:
        return None
