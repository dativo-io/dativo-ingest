"""Cloud observability integration for metrics and monitoring.

This module provides support for exporting job metrics to cloud monitoring services:
- AWS CloudWatch
- GCP Cloud Monitoring (formerly Stackdriver)

Metrics are collected during job execution and pushed to the configured cloud provider.
"""

import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from .logging import get_logger


class ObservabilityProvider(ABC):
    """Abstract base class for cloud observability providers."""

    def __init__(
        self,
        config: Dict[str, Any],
        tenant_id: str,
        job_name: str,
        environment: Optional[str] = None,
    ):
        """Initialize observability provider.

        Args:
            config: Provider-specific configuration
            tenant_id: Tenant identifier
            job_name: Job name
            environment: Environment name (e.g., 'prod', 'dev')
        """
        self.config = config
        self.tenant_id = tenant_id
        self.job_name = job_name
        self.environment = environment or "unknown"
        self.logger = get_logger()
        self.dimensions = self._build_base_dimensions()

    def _build_base_dimensions(self) -> Dict[str, str]:
        """Build base dimensions/labels for all metrics.

        Returns:
            Dictionary of dimension name to value
        """
        dimensions = {
            "tenant_id": self.tenant_id,
            "job_name": self.job_name,
            "environment": self.environment,
        }

        # Add custom dimensions from config
        if "dimensions" in self.config:
            dimensions.update(self.config["dimensions"])

        return dimensions

    @abstractmethod
    def put_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "None",
        dimensions: Optional[Dict[str, str]] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """Put a single metric data point.

        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement (e.g., 'Count', 'Seconds', 'Bytes')
            dimensions: Additional dimensions to merge with base dimensions
            timestamp: Unix timestamp (defaults to current time)
        """
        pass

    @abstractmethod
    def put_metrics_batch(
        self, metrics: List[Dict[str, Any]]
    ) -> None:
        """Put multiple metric data points in a batch.

        Args:
            metrics: List of metric dictionaries with keys:
                - metric_name: str
                - value: float
                - unit: str (optional)
                - dimensions: Dict[str, str] (optional)
                - timestamp: float (optional)
        """
        pass

    @abstractmethod
    def flush(self) -> None:
        """Flush any buffered metrics to the cloud provider."""
        pass

    def record_job_start(self) -> None:
        """Record job start event."""
        self.put_metric(
            metric_name="JobStarted",
            value=1,
            unit="Count",
        )

    def record_job_duration(self, duration_seconds: float) -> None:
        """Record job execution duration.

        Args:
            duration_seconds: Job duration in seconds
        """
        self.put_metric(
            metric_name="JobDuration",
            value=duration_seconds,
            unit="Seconds",
        )

    def record_job_success(self) -> None:
        """Record successful job completion."""
        self.put_metric(
            metric_name="JobSuccess",
            value=1,
            unit="Count",
        )

    def record_job_failure(self, error_type: Optional[str] = None) -> None:
        """Record job failure.

        Args:
            error_type: Type of error that caused failure
        """
        dimensions = {}
        if error_type:
            dimensions["error_type"] = error_type

        self.put_metric(
            metric_name="JobFailure",
            value=1,
            unit="Count",
            dimensions=dimensions,
        )

    def record_records_processed(self, count: int, stage: str = "extraction") -> None:
        """Record number of records processed.

        Args:
            count: Number of records
            stage: Processing stage (e.g., 'extraction', 'validation', 'writing')
        """
        self.put_metric(
            metric_name="RecordsProcessed",
            value=count,
            unit="Count",
            dimensions={"stage": stage},
        )

    def record_data_volume(self, bytes_count: int, direction: str = "written") -> None:
        """Record data volume processed.

        Args:
            bytes_count: Number of bytes
            direction: Data direction ('read', 'written')
        """
        self.put_metric(
            metric_name="DataVolume",
            value=bytes_count,
            unit="Bytes",
            dimensions={"direction": direction},
        )

    def record_retry(self, attempt: int, max_attempts: int) -> None:
        """Record retry attempt.

        Args:
            attempt: Current attempt number
            max_attempts: Maximum number of attempts
        """
        self.put_metric(
            metric_name="JobRetry",
            value=1,
            unit="Count",
            dimensions={
                "attempt": str(attempt),
                "max_attempts": str(max_attempts),
            },
        )

    def record_api_calls(self, count: int, api_type: Optional[str] = None) -> None:
        """Record API calls made during job execution.

        Args:
            count: Number of API calls
            api_type: Type of API (e.g., 'stripe', 'hubspot')
        """
        dimensions = {}
        if api_type:
            dimensions["api_type"] = api_type

        self.put_metric(
            metric_name="ApiCalls",
            value=count,
            unit="Count",
            dimensions=dimensions,
        )


class AWSCloudWatchProvider(ObservabilityProvider):
    """AWS CloudWatch observability provider."""

    def __init__(
        self,
        config: Dict[str, Any],
        tenant_id: str,
        job_name: str,
        environment: Optional[str] = None,
    ):
        """Initialize AWS CloudWatch provider.

        Args:
            config: CloudWatch configuration with keys:
                - region: AWS region
                - namespace: CloudWatch namespace
                - credentials: Optional AWS credentials
            tenant_id: Tenant identifier
            job_name: Job name
            environment: Environment name
        """
        super().__init__(config, tenant_id, job_name, environment)

        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for AWS CloudWatch observability. "
                "Install with: pip install boto3"
            )

        # Extract configuration
        self.region = config.get("region", "us-east-1")
        self.namespace = config.get("namespace", "Dativo/Ingest")

        # Initialize CloudWatch client
        credentials = config.get("credentials", {})
        session_kwargs = {"region_name": self.region}

        if credentials.get("aws_access_key_id"):
            session_kwargs["aws_access_key_id"] = credentials["aws_access_key_id"]
        if credentials.get("aws_secret_access_key"):
            session_kwargs["aws_secret_access_key"] = credentials["aws_secret_access_key"]

        session = boto3.Session(**session_kwargs)
        self.cloudwatch = session.client("cloudwatch")

        # Buffer for batch operations
        self.metric_buffer: List[Dict[str, Any]] = []
        self.buffer_max_size = 20  # CloudWatch limit is 20 metrics per request

        self.logger.info(
            "AWS CloudWatch observability initialized",
            extra={
                "event_type": "observability_init",
                "provider": "aws_cloudwatch",
                "region": self.region,
                "namespace": self.namespace,
                "tenant_id": self.tenant_id,
                "job_name": self.job_name,
            },
        )

    def _convert_dimensions(
        self, dimensions: Optional[Dict[str, str]] = None
    ) -> List[Dict[str, str]]:
        """Convert dimensions dict to CloudWatch format.

        Args:
            dimensions: Additional dimensions to merge

        Returns:
            List of dimension dictionaries
        """
        merged_dimensions = self.dimensions.copy()
        if dimensions:
            merged_dimensions.update(dimensions)

        return [
            {"Name": name, "Value": value}
            for name, value in merged_dimensions.items()
        ]

    def put_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "None",
        dimensions: Optional[Dict[str, str]] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """Put a single metric data point to CloudWatch.

        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: CloudWatch unit (Count, Seconds, Bytes, etc.)
            dimensions: Additional dimensions
            timestamp: Unix timestamp
        """
        metric_data = {
            "MetricName": metric_name,
            "Value": value,
            "Unit": unit,
            "Dimensions": self._convert_dimensions(dimensions),
            "Timestamp": timestamp or time.time(),
        }

        self.metric_buffer.append(metric_data)

        # Flush if buffer is full
        if len(self.metric_buffer) >= self.buffer_max_size:
            self.flush()

    def put_metrics_batch(self, metrics: List[Dict[str, Any]]) -> None:
        """Put multiple metrics to CloudWatch in batches.

        Args:
            metrics: List of metric dictionaries
        """
        for metric in metrics:
            self.put_metric(
                metric_name=metric["metric_name"],
                value=metric["value"],
                unit=metric.get("unit", "None"),
                dimensions=metric.get("dimensions"),
                timestamp=metric.get("timestamp"),
            )

    def flush(self) -> None:
        """Flush buffered metrics to CloudWatch."""
        if not self.metric_buffer:
            return

        try:
            self.cloudwatch.put_metric_data(
                Namespace=self.namespace,
                MetricData=self.metric_buffer,
            )

            self.logger.debug(
                f"Flushed {len(self.metric_buffer)} metrics to CloudWatch",
                extra={
                    "event_type": "observability_flush",
                    "provider": "aws_cloudwatch",
                    "metric_count": len(self.metric_buffer),
                    "tenant_id": self.tenant_id,
                    "job_name": self.job_name,
                },
            )

            self.metric_buffer.clear()

        except Exception as e:
            self.logger.error(
                f"Failed to flush metrics to CloudWatch: {e}",
                extra={
                    "event_type": "observability_error",
                    "provider": "aws_cloudwatch",
                    "error": str(e),
                    "tenant_id": self.tenant_id,
                    "job_name": self.job_name,
                },
            )


class GCPCloudMonitoringProvider(ObservabilityProvider):
    """GCP Cloud Monitoring (formerly Stackdriver) observability provider."""

    def __init__(
        self,
        config: Dict[str, Any],
        tenant_id: str,
        job_name: str,
        environment: Optional[str] = None,
    ):
        """Initialize GCP Cloud Monitoring provider.

        Args:
            config: Cloud Monitoring configuration with keys:
                - project_id: GCP project ID
                - namespace: Metric type prefix (default: 'custom.googleapis.com/dativo')
                - credentials: Optional service account key path
            tenant_id: Tenant identifier
            job_name: Job name
            environment: Environment name
        """
        super().__init__(config, tenant_id, job_name, environment)

        try:
            from google.cloud import monitoring_v3
        except ImportError:
            raise ImportError(
                "google-cloud-monitoring is required for GCP Cloud Monitoring observability. "
                "Install with: pip install google-cloud-monitoring"
            )

        # Extract configuration
        self.project_id = config.get("project_id")
        if not self.project_id:
            raise ValueError("project_id is required for GCP Cloud Monitoring")

        self.namespace = config.get("namespace", "custom.googleapis.com/dativo")

        # Initialize Cloud Monitoring client
        credentials = config.get("credentials", {})
        client_kwargs = {}

        if credentials.get("gcp_service_account_key_path"):
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(
                credentials["gcp_service_account_key_path"]
            )
            client_kwargs["credentials"] = creds

        self.client = monitoring_v3.MetricServiceClient(**client_kwargs)
        self.project_name = f"projects/{self.project_id}"

        # Buffer for batch operations
        self.metric_buffer: List[Any] = []
        self.buffer_max_size = 200  # GCP allows 200 time series per request

        self.logger.info(
            "GCP Cloud Monitoring observability initialized",
            extra={
                "event_type": "observability_init",
                "provider": "gcp_cloud_monitoring",
                "project_id": self.project_id,
                "namespace": self.namespace,
                "tenant_id": self.tenant_id,
                "job_name": self.job_name,
            },
        )

    def _convert_labels(
        self, dimensions: Optional[Dict[str, str]] = None
    ) -> Dict[str, str]:
        """Convert dimensions to GCP labels.

        Args:
            dimensions: Additional dimensions to merge

        Returns:
            Dictionary of labels
        """
        merged_dimensions = self.dimensions.copy()
        if dimensions:
            merged_dimensions.update(dimensions)

        return merged_dimensions

    def _create_time_series(
        self,
        metric_name: str,
        value: float,
        metric_kind: str = "GAUGE",
        value_type: str = "DOUBLE",
        dimensions: Optional[Dict[str, str]] = None,
        timestamp: Optional[float] = None,
    ) -> Any:
        """Create a time series object for GCP.

        Args:
            metric_name: Name of the metric
            value: Metric value
            metric_kind: GAUGE or CUMULATIVE
            value_type: DOUBLE, INT64, or BOOL
            dimensions: Additional dimensions
            timestamp: Unix timestamp

        Returns:
            TimeSeries object
        """
        from google.cloud import monitoring_v3

        series = monitoring_v3.TimeSeries()

        # Set metric type and labels
        series.metric.type = f"{self.namespace}/{metric_name}"
        series.metric.labels.update(self._convert_labels(dimensions))

        # Set resource (generic_task)
        series.resource.type = "generic_task"
        series.resource.labels["project_id"] = self.project_id
        series.resource.labels["location"] = "global"
        series.resource.labels["namespace"] = "dativo_ingest"
        series.resource.labels["job"] = self.job_name
        series.resource.labels["task_id"] = self.tenant_id

        # Create data point
        now = time.time() if timestamp is None else timestamp
        interval = monitoring_v3.TimeInterval(
            {
                "end_time": {"seconds": int(now), "nanos": int((now % 1) * 1e9)},
            }
        )

        point = monitoring_v3.Point(
            {
                "interval": interval,
                "value": {value_type.lower() + "_value": value},
            }
        )

        series.points = [point]
        series.metric_kind = getattr(monitoring_v3.MetricDescriptor.MetricKind, metric_kind)
        series.value_type = getattr(monitoring_v3.MetricDescriptor.ValueType, value_type)

        return series

    def put_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "None",
        dimensions: Optional[Dict[str, str]] = None,
        timestamp: Optional[float] = None,
    ) -> None:
        """Put a single metric data point to Cloud Monitoring.

        Args:
            metric_name: Name of the metric
            value: Metric value
            unit: Unit of measurement (for documentation)
            dimensions: Additional dimensions
            timestamp: Unix timestamp
        """
        series = self._create_time_series(
            metric_name=metric_name,
            value=value,
            dimensions=dimensions,
            timestamp=timestamp,
        )

        self.metric_buffer.append(series)

        # Flush if buffer is full
        if len(self.metric_buffer) >= self.buffer_max_size:
            self.flush()

    def put_metrics_batch(self, metrics: List[Dict[str, Any]]) -> None:
        """Put multiple metrics to Cloud Monitoring in batches.

        Args:
            metrics: List of metric dictionaries
        """
        for metric in metrics:
            self.put_metric(
                metric_name=metric["metric_name"],
                value=metric["value"],
                unit=metric.get("unit", "None"),
                dimensions=metric.get("dimensions"),
                timestamp=metric.get("timestamp"),
            )

    def flush(self) -> None:
        """Flush buffered metrics to Cloud Monitoring."""
        if not self.metric_buffer:
            return

        try:
            self.client.create_time_series(
                name=self.project_name,
                time_series=self.metric_buffer,
            )

            self.logger.debug(
                f"Flushed {len(self.metric_buffer)} metrics to Cloud Monitoring",
                extra={
                    "event_type": "observability_flush",
                    "provider": "gcp_cloud_monitoring",
                    "metric_count": len(self.metric_buffer),
                    "tenant_id": self.tenant_id,
                    "job_name": self.job_name,
                },
            )

            self.metric_buffer.clear()

        except Exception as e:
            self.logger.error(
                f"Failed to flush metrics to Cloud Monitoring: {e}",
                extra={
                    "event_type": "observability_error",
                    "provider": "gcp_cloud_monitoring",
                    "error": str(e),
                    "tenant_id": self.tenant_id,
                    "job_name": self.job_name,
                },
            )


def create_observability_provider(
    provider_type: str,
    config: Dict[str, Any],
    tenant_id: str,
    job_name: str,
    environment: Optional[str] = None,
) -> ObservabilityProvider:
    """Factory function to create observability provider.

    Args:
        provider_type: Provider type ('aws_cloudwatch' or 'gcp_cloud_monitoring')
        config: Provider-specific configuration
        tenant_id: Tenant identifier
        job_name: Job name
        environment: Environment name

    Returns:
        ObservabilityProvider instance

    Raises:
        ValueError: If provider type is not supported
    """
    if provider_type == "aws_cloudwatch":
        return AWSCloudWatchProvider(config, tenant_id, job_name, environment)
    elif provider_type == "gcp_cloud_monitoring":
        return GCPCloudMonitoringProvider(config, tenant_id, job_name, environment)
    else:
        raise ValueError(
            f"Unsupported observability provider: {provider_type}. "
            f"Supported providers: aws_cloudwatch, gcp_cloud_monitoring"
        )
