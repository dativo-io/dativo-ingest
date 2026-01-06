"""Metrics configuration resolution (MVP).

Simple precedence rule: job config > runner config > disabled
"""

from typing import Optional

from .config import MetricsConfig
from .logging import get_logger


def resolve_metrics_config(
    job_metrics: Optional[MetricsConfig],
    runner_metrics: Optional[MetricsConfig],
    mode: str,
) -> MetricsConfig:
    """Resolve effective metrics configuration.

    Explicit precedence rule:
    1. If job_metrics provided → use it
    2. Else if runner_metrics provided → use it
    3. Else → return disabled config

    Args:
        job_metrics: Job-level metrics config (may be None)
        runner_metrics: Runner-level metrics config (may be None)
        mode: Execution mode (orchestrated/oneshot)

    Returns:
        Effective MetricsConfig (never None, but may be disabled)
    """
    # 1. Job config takes precedence
    if job_metrics is not None:
        return job_metrics

    # 2. Fall back to runner config
    if runner_metrics is not None:
        return runner_metrics

    # 3. Default: disabled
    return MetricsConfig(enabled=False)


def log_resolved_metrics_config(
    config: MetricsConfig,
    mode: str,
) -> None:
    """Log resolved metrics configuration at startup.

    Args:
        config: Resolved metrics config (never None)
        mode: Execution mode (orchestrated/oneshot)
    """
    logger = get_logger()

    # Log resolved config (DO NOT log OTEL headers - may contain secrets)
    logger.info(
        f"Metrics: enabled={config.enabled} "
        f"prometheus={config.prometheus.enabled} "
        f"port={config.prometheus.port} "
        f"otel={config.otel.enabled} "
        f"mode={mode}",
        extra={
            "event_type": "metrics_config_resolved",
            "mode": mode,
            "metrics_enabled": config.enabled,
            "prometheus_enabled": config.prometheus.enabled,
            "prometheus_port": config.prometheus.port,
            "otel_enabled": config.otel.enabled,
            "otel_endpoint_configured": bool(config.otel.endpoint),
        },
    )
