"""Distributed tracing support with OpenTelemetry (optional)."""

import contextlib
from typing import Any, Dict, Optional

from .logging import get_logger

logger = get_logger()

# Try to import OpenTelemetry, but make it optional
try:
    from opentelemetry import trace
    from opentelemetry.trace import Status, StatusCode, Tracer

    OPENTELEMETRY_AVAILABLE = True
except ImportError:
    OPENTELEMETRY_AVAILABLE = False
    trace = None
    Status = None
    StatusCode = None
    Tracer = None


class TracingContext:
    """Context manager for tracing spans."""

    def __init__(
        self,
        tracer: Optional[Any],
        span_name: str,
        attributes: Optional[Dict[str, Any]] = None,
    ):
        """Initialize tracing context.

        Args:
            tracer: OpenTelemetry tracer (or None if not available)
            span_name: Name of the span
            attributes: Span attributes
        """
        self.tracer = tracer
        self.span_name = span_name
        self.attributes = attributes or {}
        self.span = None

    def __enter__(self):
        """Enter tracing context."""
        if OPENTELEMETRY_AVAILABLE and self.tracer:
            self.span = self.tracer.start_span(self.span_name)
            for key, value in self.attributes.items():
                self.span.set_attribute(key, str(value))
            return self.span
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit tracing context."""
        if OPENTELEMETRY_AVAILABLE and self.span:
            if exc_type is not None:
                self.span.set_status(Status(StatusCode.ERROR, str(exc_val)))
                self.span.record_exception(exc_val)
            else:
                self.span.set_status(Status(StatusCode.OK))
            self.span.end()
        return False

    def set_attribute(self, key: str, value: Any) -> None:
        """Set span attribute.

        Args:
            key: Attribute key
            value: Attribute value
        """
        if OPENTELEMETRY_AVAILABLE and self.span:
            self.span.set_attribute(key, str(value))
        elif not OPENTELEMETRY_AVAILABLE:
            logger.debug(
                f"Tracing attribute set (OpenTelemetry not available): {key}={value}",
                extra={"event_type": "tracing_debug", "key": key, "value": str(value)},
            )

    def add_event(self, name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """Add event to span.

        Args:
            name: Event name
            attributes: Event attributes
        """
        if OPENTELEMETRY_AVAILABLE and self.span:
            self.span.add_event(name, attributes or {})
        elif not OPENTELEMETRY_AVAILABLE:
            logger.debug(
                f"Tracing event (OpenTelemetry not available): {name}",
                extra={
                    "event_type": "tracing_debug",
                    "event_name": name,
                    "attributes": attributes,
                },
            )


def get_tracer(service_name: str = "dativo-ingest") -> Optional[Any]:
    """Get OpenTelemetry tracer.

    Args:
        service_name: Name of the service

    Returns:
        Tracer instance or None if OpenTelemetry not available
    """
    if not OPENTELEMETRY_AVAILABLE:
        logger.debug(
            "OpenTelemetry not available, tracing disabled",
            extra={"event_type": "tracing_disabled", "service_name": service_name},
        )
        return None

    try:
        tracer_provider = trace.get_tracer_provider()
        return tracer_provider.get_tracer(service_name)
    except Exception as e:
        logger.warning(
            f"Failed to get tracer: {e}",
            extra={"event_type": "tracing_error", "service_name": service_name},
        )
        return None


@contextlib.contextmanager
def trace_job_execution(
    job_name: str,
    tenant_id: str,
    connector_type: Optional[str] = None,
):
    """Context manager for tracing job execution.

    Args:
        job_name: Name of the job
        tenant_id: Tenant identifier
        connector_type: Type of connector

    Yields:
        TracingContext instance
    """
    tracer = get_tracer()
    attributes = {
        "job.name": job_name,
        "tenant.id": tenant_id,
    }
    if connector_type:
        attributes["connector.type"] = connector_type

    with TracingContext(tracer, f"job.{job_name}", attributes) as span:
        yield span


@contextlib.contextmanager
def trace_phase(phase_name: str, attributes: Optional[Dict[str, Any]] = None):
    """Context manager for tracing a phase of job execution.

    Args:
        phase_name: Name of the phase (e.g., 'extract', 'validate', 'write')
        attributes: Additional attributes

    Yields:
        TracingContext instance
    """
    tracer = get_tracer()
    with TracingContext(tracer, f"phase.{phase_name}", attributes or {}) as span:
        yield span
