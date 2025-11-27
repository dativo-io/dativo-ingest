"""Cloud observability helpers for AWS CloudWatch and GCP Cloud Logging."""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    AWSObservabilityConfig,
    GCPObservabilityConfig,
    JobConfig,
    ObservabilityConfig,
)
from .logging import StructuredJSONFormatter


class ObservabilityManager:
    """Configures optional cloud observability backends for a job run."""

    def __init__(
        self,
        job_config: JobConfig,
        logger: Optional[logging.Logger] = None,
        redact_secrets: bool = False,
    ) -> None:
        self.job_config = job_config
        self.logger = logger or logging.getLogger("dativo_ingest")
        self.redact_secrets = redact_secrets
        self.start_time: Optional[float] = None
        self.handlers: List[logging.Handler] = []
        self._aws_metrics_client: Optional[Any] = None
        self._aws_metrics_namespace: Optional[str] = None
        self._aws_dimensions: List[Dict[str, str]] = []
        self._metrics_emitted = False
        self._started = False

    def start(self) -> None:
        """Attach log handlers for every configured observability backend."""
        if self._started:
            return

        self._started = True
        self.start_time = time.time()

        config: Optional[ObservabilityConfig] = getattr(
            self.job_config, "observability", None
        )
        if not config:
            return

        if config.aws and config.aws.enabled:
            self._configure_aws_logging(config.aws)
        if config.gcp and config.gcp.enabled:
            self._configure_gcp_logging(config.gcp)

    def notify_completion(
        self,
        exit_code: int,
        status: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit optional metrics once the job has completed."""
        if self._metrics_emitted:
            return

        duration = None
        if self.start_time is not None:
            duration = max(time.time() - self.start_time, 0)

        if self._aws_metrics_client and self._aws_metrics_namespace:
            metric_data = self._build_aws_metric_payload(duration, status, metadata)
            if metric_data:
                try:
                    self._aws_metrics_client.put_metric_data(
                        Namespace=self._aws_metrics_namespace,
                        MetricData=metric_data,
                    )
                except Exception as exc:  # pragma: no cover - network failures
                    self.logger.warning(
                        f"Failed to push CloudWatch metrics: {exc}",
                        extra={"event_type": "observability_metric_failed"},
                    )

        self._metrics_emitted = True

    def close(self) -> None:
        """Flush and detach any cloud logging handlers."""
        for handler in self.handlers:
            self.logger.removeHandler(handler)
            try:
                handler.flush()
            except Exception:  # pragma: no cover - best effort cleanup
                pass
            handler.close()
        self.handlers.clear()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _configure_aws_logging(self, config: AWSObservabilityConfig) -> None:
        try:
            import boto3
            import watchtower
        except ImportError:  # pragma: no cover - dependency missing at runtime
            self.logger.warning(
                "AWS observability requested but boto3/watchtower are not installed",
                extra={"event_type": "observability_aws_missing_deps"},
            )
            return

        session = boto3.session.Session(region_name=config.region)
        stream_name = config.log_stream_name or self._build_stream_name(
            provider_prefix=config.log_stream_prefix or "dativo"
        )

        try:
            handler = watchtower.CloudWatchLogHandler(
                boto3_session=session,
                log_group=config.log_group,
                stream_name=stream_name,
                create_log_group=config.create_log_group,
                log_group_retention_days=config.retention_days,
            )
        except Exception as exc:  # pragma: no cover - AWS SDK failures
            self.logger.warning(
                f"Unable to configure CloudWatch logging: {exc}",
                extra={"event_type": "observability_aws_handler_failed"},
            )
            return
        handler.setFormatter(StructuredJSONFormatter(redact_secrets=self.redact_secrets))
        self.logger.addHandler(handler)
        self.handlers.append(handler)

        if config.metrics_namespace:
            self._aws_metrics_namespace = config.metrics_namespace
            try:
                self._aws_metrics_client = session.client("cloudwatch")
            except Exception as exc:  # pragma: no cover - AWS SDK failures
                self.logger.warning(
                    f"Failed to initialize CloudWatch metrics client: {exc}",
                    extra={"event_type": "observability_aws_metric_client_failed"},
                )
                self._aws_metrics_client = None
            base_dimensions = [
                {"Name": "TenantId", "Value": self.job_config.tenant_id},
                {"Name": "Job", "Value": self._job_identifier()},
            ]
            if config.metric_dimensions:
                for key, value in config.metric_dimensions.items():
                    base_dimensions.append({"Name": key, "Value": str(value)})
            self._aws_dimensions = base_dimensions

        self.logger.info(
            "AWS CloudWatch logging enabled",
            extra={
                "event_type": "observability_aws_enabled",
                "log_group": config.log_group,
                "log_stream": stream_name,
                "metrics_namespace": config.metrics_namespace,
            },
        )

    def _configure_gcp_logging(self, config: GCPObservabilityConfig) -> None:
        try:
            from google.cloud import logging as gcp_logging
            from google.cloud.logging_v2.handlers import CloudLoggingHandler
            from google.oauth2 import service_account
        except ImportError:  # pragma: no cover - dependency missing at runtime
            self.logger.warning(
                "GCP observability requested but google-cloud-logging is not installed",
                extra={"event_type": "observability_gcp_missing_deps"},
            )
            return

        credentials = None
        if config.credentials_path:
            credentials = service_account.Credentials.from_service_account_file(
                os.path.expandvars(config.credentials_path)
            )

        client = gcp_logging.Client(project=config.project_id, credentials=credentials)
        resource = {"type": config.resource_type, "labels": config.labels or {}}
        try:
            handler = CloudLoggingHandler(
                client,
                name=config.log_name,
                resource=resource,
                labels=config.labels,
            )
        except Exception as exc:  # pragma: no cover - GCP SDK failures
            self.logger.warning(
                f"Unable to configure GCP Cloud Logging: {exc}",
                extra={"event_type": "observability_gcp_handler_failed"},
            )
            return
        handler.setFormatter(StructuredJSONFormatter(redact_secrets=self.redact_secrets))
        self.logger.addHandler(handler)
        self.handlers.append(handler)

        self.logger.info(
            "GCP Cloud Logging enabled",
            extra={
                "event_type": "observability_gcp_enabled",
                "project_id": config.project_id,
                "log_name": config.log_name,
            },
        )

    def _job_identifier(self) -> str:
        if self.job_config.asset:
            return self.job_config.asset
        if self.job_config.asset_path:
            return Path(self.job_config.asset_path).stem
        return "job"

    def _build_stream_name(self, provider_prefix: str) -> str:
        job_part = self._job_identifier()
        tenant = self.job_config.tenant_id or "tenant"
        return f"{provider_prefix}/{tenant}/{job_part}"

    def _build_aws_metric_payload(
        self,
        duration: Optional[float],
        status: str,
        metadata: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        if not self._aws_dimensions:
            return []

        metric_data: List[Dict[str, Any]] = []

        if duration is not None:
            metric_data.append(
                {
                    "MetricName": "ExecutionTimeSeconds",
                    "Dimensions": self._aws_dimensions,
                    "Value": duration,
                    "Unit": "Seconds",
                }
            )

        metric_data.append(
            {
                "MetricName": "JobStatus",
                "Dimensions": self._aws_dimensions
                + [{"Name": "Status", "Value": status}],
                "Value": 1,
                "Unit": "Count",
            }
        )

        if metadata:
            if "total_records" in metadata and metadata["total_records"] is not None:
                metric_data.append(
                    {
                        "MetricName": "RecordsProcessed",
                        "Dimensions": self._aws_dimensions,
                        "Value": float(metadata["total_records"]),
                        "Unit": "Count",
                    }
                )
            if "files_written" in metadata and metadata["files_written"] is not None:
                metric_data.append(
                    {
                        "MetricName": "FilesWritten",
                        "Dimensions": self._aws_dimensions,
                        "Value": float(metadata["files_written"]),
                        "Unit": "Count",
                    }
                )

        return metric_data

