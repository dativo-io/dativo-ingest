"""Prometheus metrics HTTP server for orchestrated mode.

Exposes /metrics endpoint on configurable port for Prometheus scraping.
Only starts when explicitly enabled (orchestrated mode default: enabled, oneshot default: disabled).
Supports multiprocess mode for collecting metrics from subprocess job runs.
"""

import os
from typing import Optional

from .config import PrometheusConfig
from .logging import get_logger
from .metrics import get_multiprocess_registry

# Optional import for Prometheus
try:
    from prometheus_client import REGISTRY, generate_latest, start_http_server

    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False


class MetricsServer:
    """HTTP server for Prometheus metrics endpoint.

    Supports both standard and multiprocess modes.
    """

    def __init__(self, config: PrometheusConfig):
        """Initialize metrics server.

        Args:
            config: Prometheus configuration
        """
        self.config = config
        self.logger = get_logger()
        self._started = False

    def start(self) -> None:
        """Start the metrics HTTP server.

        Only starts if Prometheus is available and enabled.
        Uses multiprocess registry if configured.
        """
        if not PROMETHEUS_AVAILABLE:
            self.logger.warning(
                "Prometheus client not available. Install prometheus_client to enable metrics server.",
                extra={"event_type": "metrics_server_unavailable"},
            )
            return

        if not self.config.enabled:
            self.logger.debug(
                "Metrics server disabled by configuration",
                extra={"event_type": "metrics_server_disabled"},
            )
            return

        if self._started:
            self.logger.warning(
                "Metrics server already started",
                extra={"event_type": "metrics_server_warning"},
            )
            return

        try:
            # Get appropriate registry (multiprocess or standard)
            registry = get_multiprocess_registry()
            if registry is None:
                registry = REGISTRY
                mode = "standard"
            else:
                mode = "multiprocess"

            # Start HTTP server
            start_http_server(
                port=self.config.port, addr=self.config.host, registry=registry
            )
            self._started = True

            self.logger.info(
                f"Metrics server started on {self.config.host}:{self.config.port}/metrics (mode: {mode})",
                extra={
                    "event_type": "metrics_server_started",
                    "port": self.config.port,
                    "host": self.config.host,
                    "mode": mode,
                    "endpoint": f"http://{self.config.host}:{self.config.port}/metrics",
                },
            )
        except OSError as e:
            self.logger.error(
                f"Failed to start metrics server: {e}",
                extra={
                    "event_type": "metrics_server_error",
                    "port": self.config.port,
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

    try:
        # Use multiprocess registry if configured
        registry = get_multiprocess_registry()
        if registry is None:
            registry = REGISTRY

        return generate_latest(registry).decode("utf-8")
    except Exception as e:
        return f"# Error generating metrics: {e}\n"


def start_metrics_server_from_config(
    config: PrometheusConfig,
) -> Optional[MetricsServer]:
    """Start metrics server from configuration.

    Args:
        config: Prometheus configuration

    Returns:
        MetricsServer instance if started, None if disabled or unavailable
    """
    if not config.enabled:
        return None

    if not PROMETHEUS_AVAILABLE:
        logger = get_logger()
        logger.warning(
            "Prometheus client not available. Install prometheus_client to enable metrics.",
            extra={"event_type": "metrics_unavailable"},
        )
        return None

    # Create and start server
    server = MetricsServer(config)
    server.start()

    return server
