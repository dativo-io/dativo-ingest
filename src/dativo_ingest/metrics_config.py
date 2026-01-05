"""Metrics configuration resolution (MVP).

Simple precedence rule: job config > runner config > None
"""

from typing import Optional

from .config import JobConfig, MetricsConfig, RunnerConfig
from .logging import get_logger


def resolve_metrics_config(
    job_config: JobConfig,
    runner_config: Optional[RunnerConfig] = None,
) -> Optional[MetricsConfig]:
    """Resolve effective metrics configuration.
    
    Precedence: job config > runner config > None
    
    Args:
        job_config: Job configuration (may have metrics override)
        runner_config: Runner configuration (orchestrated mode only)
        
    Returns:
        Effective MetricsConfig or None if metrics disabled
    """
    # Job config takes precedence
    if job_config.metrics is not None:
        return job_config.metrics
    
    # Fall back to runner config (orchestrated mode)
    if runner_config is not None and runner_config.metrics is not None:
        return runner_config.metrics
    
    # No metrics config
    return None


def log_resolved_metrics_config(
    config: Optional[MetricsConfig],
    mode: str,
) -> None:
    """Log resolved metrics configuration at startup.
    
    Args:
        config: Resolved metrics config (or None)
        mode: Execution mode (orchestrated/oneshot)
    """
    logger = get_logger()
    
    if config is None:
        logger.info(
            f"Metrics: disabled mode={mode}",
            extra={"event_type": "metrics_config_resolved"},
        )
        return
    
    # Log resolved config (DO NOT log OTEL headers - secrets)
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
