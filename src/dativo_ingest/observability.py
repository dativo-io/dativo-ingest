"""Cloud observability integrations for metrics and log forwarding."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import boto3

from .config import ObservabilityConfig
from .logging import get_logger

try:  # pragma: no cover - optional dependency import guard
    from google.cloud import logging_v2, monitoring_v3
    from google.oauth2 import service_account
except ImportError:  # pragma: no cover - optional dependency import guard
    logging_v2 = None
    monitoring_v3 = None
    service_account = None


class ObservabilityAdapter:
    """Wrapper around provider-specific observability backends."""

    def __init__(
        self,
        config: Optional[ObservabilityConfig],
        job_context: Optional[Dict[str, Any]] = None,
    ):
        self.logger = get_logger()
        self.config = config
        self.job_context = job_context or {}
        self._backend = None

        if not config:
            return

        try:
            if config.provider == "aws":
                self._backend = AWSObservabilityBackend(config, self.job_context)
            elif config.provider == "gcp":
                self._backend = GCPObservabilityBackend(config, self.job_context)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.warning(
                f"Observability backend initialization failed: {exc}",
                extra={
                    "event_type": "observability_init_failed",
                    "provider": config.provider,
                },
            )
            self._backend = None

    def emit_job_summary(
        self,
        *,
        status: str,
        metrics: Dict[str, Any],
        mode: str,
        validation_mode: str,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Emit job summary payload to the configured backend."""
        if not self._backend:
            return

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "mode": mode,
            "validation_mode": validation_mode,
            "metrics": metrics,
            "job": self.job_context,
            "extra": extra or {},
        }

        try:
            self._backend.emit(payload)
        except Exception as exc:  # pragma: no cover - defensive logging
            self.logger.warning(
                f"Failed to emit observability payload: {exc}",
                extra={
                    "event_type": "observability_emit_failed",
                    "provider": self.config.provider if self.config else None,
                },
            )


class AWSObservabilityBackend:
    """Emit metrics/logs to AWS CloudWatch."""

    def __init__(self, config: ObservabilityConfig, job_context: Dict[str, Any]):
        self.logger = get_logger()
        self.config = config
        self.job_context = job_context
        self.sequence_token: Optional[str] = None
        self._log_group_ready = False
        self._log_stream_ready = False

        aws_cfg = config.aws
        if aws_cfg is None:
            raise ValueError("AWS observability configuration is missing")

        region = aws_cfg.region or os.getenv("AWS_REGION") or "us-east-1"
        client_kwargs: Dict[str, Any] = {"region_name": region}
        if aws_cfg.endpoint_url:
            client_kwargs["endpoint_url"] = aws_cfg.endpoint_url

        if aws_cfg.profile:
            from boto3 import session

            session_obj = session.Session(profile_name=aws_cfg.profile, region_name=region)
            client_factory = session_obj.client
        else:
            client_factory = boto3.client

        self.cloudwatch = (
            client_factory("cloudwatch", **client_kwargs)
            if config.metrics_enabled
            else None
        )
        self.logs_client = (
            client_factory("logs", **client_kwargs) if config.logs_enabled else None
        )

        self.namespace = aws_cfg.cloudwatch_namespace or "Dativo/Jobs"
        self.log_group = aws_cfg.log_group or f"/dativo/{job_context.get('tenant_id', 'default')}"
        stream_prefix = aws_cfg.log_stream_prefix or job_context.get("job_name", "job")
        self.log_stream = f"{stream_prefix}-{int(time.time())}"
        self.create_log_group = aws_cfg.create_log_group
        self.create_log_stream = aws_cfg.create_log_stream

        default_dimensions = [
            {"Name": "JobName", "Value": job_context.get("job_name", "unknown")},
            {"Name": "TenantId", "Value": job_context.get("tenant_id", "unknown")},
        ]
        if aws_cfg.dimensions:
            default_dimensions.extend(
                {"Name": key, "Value": value} for key, value in aws_cfg.dimensions.items()
            )
        self.dimensions = default_dimensions

    def emit(self, payload: Dict[str, Any]) -> None:
        """Emit payload to AWS services."""
        if self.cloudwatch:
            self._emit_metrics(payload.get("metrics", {}))
        if self.logs_client:
            self._emit_logs(payload)

    def _emit_metrics(self, metrics: Dict[str, Any]) -> None:
        if not metrics:
            return

        metric_data = []
        for name, value in metrics.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            metric_data.append(
                {
                    "MetricName": name,
                    "Value": float(value),
                    "Unit": "Seconds" if "second" in name else "Count",
                    "Dimensions": self.dimensions,
                }
            )

        if not metric_data:
            return

        # CloudWatch accepts max 20 metrics per request
        for idx in range(0, len(metric_data), 20):
            chunk = metric_data[idx : idx + 20]
            self.cloudwatch.put_metric_data(Namespace=self.namespace, MetricData=chunk)

    def _emit_logs(self, payload: Dict[str, Any]) -> None:
        self._ensure_log_resources()
        message = json.dumps(payload)
        log_event = {
            "logGroupName": self.log_group,
            "logStreamName": self.log_stream,
            "logEvents": [
                {
                    "timestamp": int(time.time() * 1000),
                    "message": message,
                }
            ],
        }
        if self.sequence_token:
            log_event["sequenceToken"] = self.sequence_token

        try:
            response = self.logs_client.put_log_events(**log_event)
            self.sequence_token = response.get("nextSequenceToken", self.sequence_token)
        except self.logs_client.exceptions.InvalidSequenceTokenException as exc:
            expected = exc.response.get("expectedSequenceToken")
            if expected:
                self.sequence_token = expected
                log_event["sequenceToken"] = expected
                response = self.logs_client.put_log_events(**log_event)
                self.sequence_token = response.get(
                    "nextSequenceToken", self.sequence_token
                )
        except self.logs_client.exceptions.DataAlreadyAcceptedException:
            # Safe to ignore duplicate submissions
            return

    def _ensure_log_resources(self) -> None:
        if not self.logs_client:
            return

        if not self._log_group_ready:
            try:
                self.logs_client.create_log_group(logGroupName=self.log_group)
            except self.logs_client.exceptions.ResourceAlreadyExistsException:
                pass
            finally:
                self._log_group_ready = True

        if not self._log_stream_ready:
            if self.create_log_stream:
                try:
                    self.logs_client.create_log_stream(
                        logGroupName=self.log_group, logStreamName=self.log_stream
                    )
                    self.sequence_token = None
                except self.logs_client.exceptions.ResourceAlreadyExistsException:
                    streams = self.logs_client.describe_log_streams(
                        logGroupName=self.log_group,
                        logStreamNamePrefix=self.log_stream,
                        limit=1,
                    ).get("logStreams", [])
                    if streams:
                        self.sequence_token = streams[0].get("uploadSequenceToken")
                finally:
                    self._log_stream_ready = True


class GCPObservabilityBackend:
    """Emit metrics/logs to Google Cloud Monitoring and Logging."""

    def __init__(self, config: ObservabilityConfig, job_context: Dict[str, Any]):
        if logging_v2 is None or monitoring_v3 is None:
            raise ImportError(
                "google-cloud-logging and google-cloud-monitoring must be installed for GCP observability"
            )

        self.logger = get_logger()
        self.config = config
        self.job_context = job_context

        gcp_cfg = config.gcp
        if gcp_cfg is None:
            raise ValueError("GCP observability configuration is missing")

        credentials = None
        if gcp_cfg.credentials_path:
            if service_account is None:
                raise ImportError(
                    "google-auth is required to load service account credentials"
                )
            credentials = service_account.Credentials.from_service_account_file(
                gcp_cfg.credentials_path
            )

        client_kwargs = {"credentials": credentials} if credentials else {}
        self.metric_client = (
            monitoring_v3.MetricServiceClient(**client_kwargs)
            if config.metrics_enabled
            else None
        )
        self.logging_client = (
            logging_v2.Client(project=gcp_cfg.project_id, **client_kwargs)
            if config.logs_enabled
            else None
        )
        self.project_id = gcp_cfg.project_id
        self.project_name = f"projects/{self.project_id}"
        self.metric_prefix = gcp_cfg.metric_prefix.rstrip("/")
        resource_labels = {"project_id": self.project_id}
        if gcp_cfg.labels:
            resource_labels.update(gcp_cfg.labels)
        self.resource = {
            "type": gcp_cfg.resource_type,
            "labels": resource_labels,
        }
        self.log_name = gcp_cfg.log_name

    def emit(self, payload: Dict[str, Any]) -> None:
        if self.metric_client:
            self._emit_metrics(payload.get("metrics", {}))
        if self.logging_client:
            logger = self.logging_client.logger(self.log_name)
            logger.log_struct(payload, resource=self.resource)

    def _emit_metrics(self, metrics: Dict[str, Any]) -> None:
        if not metrics:
            return

        time_series = []
        for name, value in metrics.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            sanitized = name.replace(" ", "_").lower()
            series = monitoring_v3.TimeSeries()
            series.metric.type = f"{self.metric_prefix}/{sanitized}"
            series.metric.labels["job_name"] = self.job_context.get("job_name", "unknown")
            series.metric.labels["tenant_id"] = self.job_context.get("tenant_id", "unknown")
            series.resource.type = self.resource["type"]
            series.resource.labels.update(self.resource["labels"])

            point = monitoring_v3.Point()
            point.interval.end_time.FromDatetime(datetime.now(timezone.utc))
            point.value.double_value = float(value)
            series.points.append(point)
            time_series.append(series)

        if time_series:
            self.metric_client.create_time_series(
                name=self.project_name,
                time_series=time_series,
            )
