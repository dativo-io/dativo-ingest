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

# Module-level guard against multiple server starts
import threading
_SERVER_STARTED = False
_SERVER_LOCK = threading.Lock()


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
        """Start the metrics HTTP server (best-effort, orchestrated mode only).

        Won't crash if port is busy - logs warning and continues.
        Uses module-level lock to prevent multiple starts.
        """
        global _SERVER_STARTED
        
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

        # Module-level guard against double-start
        with _SERVER_LOCK:
            if _SERVER_STARTED:
                self.logger.debug("Metrics server already started globally, skipping")
                return
                
            if self._started:
                self.logger.debug("Metrics server already started on this instance, skipping")
                return

            try:
                # Get appropriate registry (multiprocess or standard)
                registry = get_multiprocess_registry()
                if registry is None:
                    registry = REGISTRY
                    mode = "standard"
                else:
                    mode = "multiprocess"

                # Start HTTP server (best-effort)
                start_http_server(
                    port=self.config.port, addr=self.config.host, registry=registry
                )
                _SERVER_STARTED = True
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
                # Port busy or bind error - log warning but DON'T CRASH
                self.logger.warning(
                    f"Failed to start metrics server (port {self.config.port} may be in use): {e}. "
                    f"Metrics collection will continue but HTTP endpoint unavailable.",
                    extra={
                        "event_type": "metrics_server_bind_failed",
                        "port": self.config.port,
                        "error": str(e),
                    },
                )

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

    logger = get_logger()

    try:
        # Use multiprocess registry if configured
        registry = get_multiprocess_registry()
        if registry is None:
            registry = REGISTRY

        metrics_bytes = generate_latest(registry)
        return metrics_bytes.decode("utf-8")
    except Exception as e:
        # Log once (avoid spam)
        logger.warning(
            f"Failed to generate Prometheus metrics: {e}",
            extra={"event_type": "metrics_generation_failed"},
        )
        return f"# Error generating metrics: {e}\n"


def start_metrics_server_from_config(
    config: PrometheusConfig,
    mode: str = "orchestrated",
) -> Optional[MetricsServer]:
    """Start metrics server (orchestrated mode only).

    Args:
        config: Prometheus configuration
        mode: Execution mode (must be "orchestrated")

    Returns:
        MetricsServer instance if started, None otherwise
    """
    logger = get_logger()
    
    # Only start in orchestrated mode
    if mode != "orchestrated":
        logger.debug(f"Metrics server not started: mode={mode} (orchestrated only)")
        return None
    
    if not config.enabled:
        return None

    if not PROMETHEUS_AVAILABLE:
        logger.warning(
            "Prometheus client not available. Install prometheus_client to enable metrics.",
            extra={"event_type": "metrics_unavailable"},
        )
        return None

    # Create and start server (best-effort, won't crash)
    server = MetricsServer(config)
    server.start()
    
    # Return server object (critical for tests and orchestrated mode)
    return server
