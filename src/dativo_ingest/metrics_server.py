"""Prometheus metrics HTTP server for orchestrated mode.

Exposes /metrics endpoint on configurable port for Prometheus scraping.
"""

import os
import threading
from typing import Optional

from .logging import get_logger

# Optional import for Prometheus
try:
    from prometheus_client import REGISTRY, generate_latest, start_http_server

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class MetricsServer:
    """HTTP server for Prometheus metrics endpoint."""

    def __init__(self, port: int = 9400, host: str = "0.0.0.0"):
        """Initialize metrics server.

        Args:
            port: Port to listen on (default: 9400)
            host: Host to bind to (default: 0.0.0.0)
        """
        self.port = port
        self.host = host
        self.logger = get_logger()
        self._server_thread: Optional[threading.Thread] = None
        self._started = False

    def start(self) -> None:
        """Start the metrics HTTP server in a background thread."""
        if not PROMETHEUS_AVAILABLE:
            self.logger.warning(
                "Prometheus client not available. Install prometheus_client to enable metrics server.",
                extra={"event_type": "metrics_server_unavailable"},
            )
            return

        if self._started:
            self.logger.warning(
                "Metrics server already started",
                extra={"event_type": "metrics_server_warning"},
            )
            return

        try:
            # Start Prometheus HTTP server
            start_http_server(port=self.port, addr=self.host, registry=REGISTRY)
            self._started = True

            self.logger.info(
                f"Metrics server started on {self.host}:{self.port}/metrics",
                extra={
                    "event_type": "metrics_server_started",
                    "port": self.port,
                    "host": self.host,
                    "endpoint": f"http://{self.host}:{self.port}/metrics",
                },
            )
        except OSError as e:
            self.logger.error(
                f"Failed to start metrics server: {e}",
                extra={
                    "event_type": "metrics_server_error",
                    "port": self.port,
                    "error": str(e),
                },
            )
            raise

    def stop(self) -> None:
        """Stop the metrics HTTP server.

        Note: prometheus_client's start_http_server doesn't provide a clean shutdown mechanism.
        The server will continue running until the process exits.
        """
        if not self._started:
            return

        self.logger.info(
            "Metrics server shutdown requested (will stop when process exits)",
            extra={"event_type": "metrics_server_stopping"},
        )

    def is_running(self) -> bool:
        """Check if the metrics server is running.

        Returns:
            True if server is started, False otherwise
        """
        return self._started


def get_metrics_text() -> str:
    """Get current metrics in Prometheus text format.

    Returns:
        Metrics in Prometheus exposition format
    """
    if not PROMETHEUS_AVAILABLE:
        return "# Prometheus client not available\n"

    return generate_latest(REGISTRY).decode("utf-8")


def start_metrics_server(
    port: Optional[int] = None, host: Optional[str] = None
) -> Optional[MetricsServer]:
    """Start metrics server with configuration from environment or defaults.

    Args:
        port: Port to listen on (overrides DATIVO_METRICS_PORT env var)
        host: Host to bind to (overrides DATIVO_METRICS_HOST env var)

    Returns:
        MetricsServer instance if started, None if disabled or unavailable
    """
    # Check if metrics server is enabled
    if os.getenv("DATIVO_METRICS_PROMETHEUS", "true").lower() != "true":
        return None

    if not PROMETHEUS_AVAILABLE:
        logger = get_logger()
        logger.warning(
            "Prometheus client not available. Install prometheus_client to enable metrics.",
            extra={"event_type": "metrics_unavailable"},
        )
        return None

    # Get configuration from environment or use defaults
    server_port = port or int(os.getenv("DATIVO_METRICS_PORT", "9400"))
    server_host = host or os.getenv("DATIVO_METRICS_HOST", "0.0.0.0")

    # Create and start server
    server = MetricsServer(port=server_port, host=server_host)
    server.start()

    return server
