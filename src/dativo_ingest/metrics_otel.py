"""OpenTelemetry metrics configuration and export.

Supports OTLP export to collectors like Grafana Agent, OTEL Collector, etc.
"""

import os
from typing import Optional

from .logging import get_logger

# Optional imports for OpenTelemetry
try:
    from opentelemetry import metrics
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
        OTLPMetricExporter,
    )
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False


def configure_otel_metrics(
    endpoint: Optional[str] = None,
    export_interval_millis: int = 60000,
    service_name: str = "dativo-ingest",
    service_version: str = "0.5.1",
) -> bool:
    """Configure OpenTelemetry metrics with OTLP exporter.

    Args:
        endpoint: OTLP endpoint (e.g., 'http://localhost:4317')
        export_interval_millis: Export interval in milliseconds (default: 60s)
        service_name: Service name for resource attributes
        service_version: Service version for resource attributes

    Returns:
        True if configured successfully, False otherwise
    """
    logger = get_logger()

    # Check if OTEL is enabled
    if os.getenv("DATIVO_METRICS_OTEL", "false").lower() != "true":
        logger.debug(
            "OpenTelemetry metrics disabled (DATIVO_METRICS_OTEL=false)",
            extra={"event_type": "otel_disabled"},
        )
        return False

    if not OPENTELEMETRY_AVAILABLE:
        logger.warning(
            "OpenTelemetry SDK not available. Install opentelemetry-sdk and "
            "opentelemetry-exporter-otlp to enable OTEL metrics.",
            extra={"event_type": "otel_unavailable"},
        )
        return False

    # Get OTLP endpoint from environment or parameter
    otlp_endpoint = endpoint or os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
    )

    try:
        # Create resource with service metadata
        resource = Resource.create(
            {
                "service.name": service_name,
                "service.version": service_version,
                "deployment.environment": os.getenv("DATIVO_ENVIRONMENT", "production"),
            }
        )

        # Create OTLP exporter
        otlp_exporter = OTLPMetricExporter(
            endpoint=otlp_endpoint,
            insecure=os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "false").lower()
            == "true",
        )

        # Create metric reader with periodic export
        metric_reader = PeriodicExportingMetricReader(
            exporter=otlp_exporter,
            export_interval_millis=export_interval_millis,
        )

        # Create and set meter provider
        meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
        )
        metrics.set_meter_provider(meter_provider)

        logger.info(
            f"OpenTelemetry metrics configured with endpoint: {otlp_endpoint}",
            extra={
                "event_type": "otel_configured",
                "endpoint": otlp_endpoint,
                "export_interval_ms": export_interval_millis,
                "service_name": service_name,
            },
        )

        return True

    except Exception as e:
        logger.error(
            f"Failed to configure OpenTelemetry metrics: {e}",
            extra={
                "event_type": "otel_configuration_error",
                "endpoint": otlp_endpoint,
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


class OTELMetricsHelper:
    """Helper class for creating and managing OTEL metrics."""

    def __init__(self, meter_name: str = "dativo_ingest"):
        """Initialize OTEL metrics helper.

        Args:
            meter_name: Name for the meter
        """
        self.logger = get_logger()
        self.meter = get_otel_meter(meter_name)
        self.instruments = {}

        if not self.meter:
            self.logger.warning(
                "OTEL meter not available",
                extra={"event_type": "otel_meter_unavailable"},
            )

    def create_counter(
        self, name: str, description: str = "", unit: str = ""
    ) -> Optional[object]:
        """Create or get a counter instrument.

        Args:
            name: Counter name
            description: Counter description
            unit: Unit of measurement

        Returns:
            Counter instrument or None if not available
        """
        if not self.meter:
            return None

        key = f"counter_{name}"
        if key not in self.instruments:
            self.instruments[key] = self.meter.create_counter(
                name=name,
                description=description,
                unit=unit,
            )

        return self.instruments[key]

    def create_histogram(
        self, name: str, description: str = "", unit: str = ""
    ) -> Optional[object]:
        """Create or get a histogram instrument.

        Args:
            name: Histogram name
            description: Histogram description
            unit: Unit of measurement

        Returns:
            Histogram instrument or None if not available
        """
        if not self.meter:
            return None

        key = f"histogram_{name}"
        if key not in self.instruments:
            self.instruments[key] = self.meter.create_histogram(
                name=name,
                description=description,
                unit=unit,
            )

        return self.instruments[key]

    def create_up_down_counter(
        self, name: str, description: str = "", unit: str = ""
    ) -> Optional[object]:
        """Create or get an up-down counter instrument.

        Args:
            name: Up-down counter name
            description: Counter description
            unit: Unit of measurement

        Returns:
            Up-down counter instrument or None if not available
        """
        if not self.meter:
            return None

        key = f"updowncounter_{name}"
        if key not in self.instruments:
            self.instruments[key] = self.meter.create_up_down_counter(
                name=name,
                description=description,
                unit=unit,
            )

        return self.instruments[key]

    def create_observable_gauge(
        self, name: str, callbacks: list, description: str = "", unit: str = ""
    ) -> Optional[object]:
        """Create or get an observable gauge instrument.

        Args:
            name: Gauge name
            callbacks: List of callback functions
            description: Gauge description
            unit: Unit of measurement

        Returns:
            Observable gauge instrument or None if not available
        """
        if not self.meter:
            return None

        key = f"gauge_{name}"
        if key not in self.instruments:
            self.instruments[key] = self.meter.create_observable_gauge(
                name=name,
                callbacks=callbacks,
                description=description,
                unit=unit,
            )

        return self.instruments[key]
