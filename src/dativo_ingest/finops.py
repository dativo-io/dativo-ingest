"""FinOps integration for cost tracking and telemetry."""

import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from .logging import get_logger


class FinOpsMetrics:
    """Tracks FinOps metrics for cost attribution and optimization."""

    def __init__(
        self,
        tenant_id: str,
        job_name: str,
        cost_center: Optional[str] = None,
    ):
        """Initialize FinOps metrics.

        Args:
            tenant_id: Tenant identifier
            job_name: Job name
            cost_center: Cost center for attribution
        """
        self.tenant_id = tenant_id
        self.job_name = job_name
        self.cost_center = cost_center or tenant_id
        self.logger = get_logger()
        
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        
        # Resource usage metrics
        self.cpu_time_sec = 0.0
        self.memory_peak_mb = 0.0
        self.data_bytes_ingested = 0
        self.data_bytes_written = 0
        self.api_calls_count = 0
        
        # Cost metrics (USD)
        self.compute_cost_usd = 0.0
        self.storage_cost_usd = 0.0
        self.network_cost_usd = 0.0
        self.api_cost_usd = 0.0
        
        # Pricing assumptions (can be overridden)
        self.pricing = {
            "compute_per_cpu_hour": 0.05,  # $0.05 per CPU hour
            "storage_per_gb_month": 0.023,  # $0.023 per GB-month (S3 standard)
            "network_per_gb": 0.09,  # $0.09 per GB transferred
            "api_call_per_1k": 0.0004,  # $0.0004 per 1,000 API calls
        }

    def start(self) -> None:
        """Start metrics collection."""
        self.start_time = time.time()
        self.logger.debug(
            "FinOps metrics collection started",
            extra={
                "event_type": "finops_started",
                "tenant_id": self.tenant_id,
                "job_name": self.job_name,
            },
        )

    def record_cpu_time(self, cpu_seconds: float) -> None:
        """Record CPU time.

        Args:
            cpu_seconds: CPU time in seconds
        """
        self.cpu_time_sec += cpu_seconds
        
        # Calculate compute cost
        cpu_hours = cpu_seconds / 3600
        self.compute_cost_usd = cpu_hours * self.pricing["compute_per_cpu_hour"]
        
        self.logger.debug(
            f"CPU time recorded: {cpu_seconds:.2f}s",
            extra={
                "event_type": "finops_cpu",
                "cpu_seconds": cpu_seconds,
                "compute_cost_usd": self.compute_cost_usd,
            },
        )

    def record_memory_usage(self, memory_mb: float) -> None:
        """Record peak memory usage.

        Args:
            memory_mb: Memory usage in MB
        """
        if memory_mb > self.memory_peak_mb:
            self.memory_peak_mb = memory_mb
        
        self.logger.debug(
            f"Memory usage recorded: {memory_mb:.2f}MB",
            extra={
                "event_type": "finops_memory",
                "memory_mb": memory_mb,
            },
        )

    def record_data_ingested(self, bytes_count: int) -> None:
        """Record data ingested.

        Args:
            bytes_count: Number of bytes ingested
        """
        self.data_bytes_ingested += bytes_count
        
        # Calculate network cost (assuming data transfer)
        gb_transferred = bytes_count / (1024 ** 3)
        self.network_cost_usd += gb_transferred * self.pricing["network_per_gb"]
        
        self.logger.debug(
            f"Data ingested: {bytes_count:,} bytes",
            extra={
                "event_type": "finops_data_ingested",
                "bytes": bytes_count,
                "network_cost_usd": self.network_cost_usd,
            },
        )

    def record_data_written(self, bytes_count: int) -> None:
        """Record data written to storage.

        Args:
            bytes_count: Number of bytes written
        """
        self.data_bytes_written += bytes_count
        
        # Calculate storage cost (assuming 30-day retention)
        gb_stored = bytes_count / (1024 ** 3)
        # Monthly cost prorated for the run
        self.storage_cost_usd += gb_stored * self.pricing["storage_per_gb_month"]
        
        self.logger.debug(
            f"Data written: {bytes_count:,} bytes",
            extra={
                "event_type": "finops_data_written",
                "bytes": bytes_count,
                "storage_cost_usd": self.storage_cost_usd,
            },
        )

    def record_api_calls(self, count: int, api_type: Optional[str] = None) -> None:
        """Record API calls.

        Args:
            count: Number of API calls
            api_type: Type of API (for tracking)
        """
        self.api_calls_count += count
        
        # Calculate API cost
        self.api_cost_usd += (count / 1000) * self.pricing["api_call_per_1k"]
        
        self.logger.debug(
            f"API calls recorded: {count} ({api_type or 'unknown'})",
            extra={
                "event_type": "finops_api_calls",
                "count": count,
                "api_type": api_type,
                "api_cost_usd": self.api_cost_usd,
            },
        )

    def finish(self) -> Dict[str, Any]:
        """Finish metrics collection and return summary.

        Returns:
            FinOps metrics dictionary
        """
        self.end_time = time.time()
        
        if self.start_time is None:
            self.logger.warning(
                "FinOps metrics finished without start",
                extra={"event_type": "finops_warning"},
            )
            execution_time = 0.0
        else:
            execution_time = self.end_time - self.start_time
        
        # If CPU time wasn't explicitly recorded, estimate from wall clock time
        if self.cpu_time_sec == 0 and execution_time > 0:
            self.record_cpu_time(execution_time)
        
        # Calculate total cost
        total_cost_usd = (
            self.compute_cost_usd +
            self.storage_cost_usd +
            self.network_cost_usd +
            self.api_cost_usd
        )
        
        metrics = {
            "tenant_id": self.tenant_id,
            "job_name": self.job_name,
            "cost_center": self.cost_center,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "execution_time_seconds": execution_time,
            "resource_usage": {
                "cpu_time_sec": self.cpu_time_sec,
                "memory_peak_mb": self.memory_peak_mb,
                "data_bytes_ingested": self.data_bytes_ingested,
                "data_bytes_written": self.data_bytes_written,
                "api_calls_count": self.api_calls_count,
            },
            "cost_breakdown_usd": {
                "compute": round(self.compute_cost_usd, 6),
                "storage": round(self.storage_cost_usd, 6),
                "network": round(self.network_cost_usd, 6),
                "api": round(self.api_cost_usd, 6),
                "total": round(total_cost_usd, 6),
            },
            "cost_per_metric": {
                "cost_per_gb_ingested": (
                    round(total_cost_usd / (self.data_bytes_ingested / (1024 ** 3)), 6)
                    if self.data_bytes_ingested > 0
                    else 0.0
                ),
                "cost_per_api_call": (
                    round(total_cost_usd / self.api_calls_count, 6)
                    if self.api_calls_count > 0
                    else 0.0
                ),
            },
        }
        
        self.logger.info(
            f"FinOps metrics: ${total_cost_usd:.6f} total cost",
            extra={
                "event_type": "finops_complete",
                "tenant_id": self.tenant_id,
                "job_name": self.job_name,
                "total_cost_usd": total_cost_usd,
                **metrics["cost_breakdown_usd"],
            },
        )
        
        return metrics

    def detect_anomalies(
        self, historical_metrics: list[Dict[str, Any]]
    ) -> list[Dict[str, str]]:
        """Detect cost anomalies compared to historical data.

        Args:
            historical_metrics: List of historical FinOps metrics

        Returns:
            List of detected anomalies
        """
        if not historical_metrics:
            return []
        
        anomalies = []
        
        # Calculate historical averages
        avg_cost = sum(
            m["cost_breakdown_usd"]["total"] for m in historical_metrics
        ) / len(historical_metrics)
        
        avg_cpu = sum(
            m["resource_usage"]["cpu_time_sec"] for m in historical_metrics
        ) / len(historical_metrics)
        
        # Current metrics
        current_cost = (
            self.compute_cost_usd +
            self.storage_cost_usd +
            self.network_cost_usd +
            self.api_cost_usd
        )
        
        # Detect cost spike (>2x average)
        if current_cost > avg_cost * 2:
            anomalies.append({
                "type": "cost_spike",
                "severity": "high",
                "message": f"Cost spike detected: ${current_cost:.6f} vs avg ${avg_cost:.6f}",
                "current_value": current_cost,
                "baseline_value": avg_cost,
            })
        
        # Detect CPU spike (>2x average)
        if self.cpu_time_sec > avg_cpu * 2:
            anomalies.append({
                "type": "cpu_spike",
                "severity": "medium",
                "message": f"CPU usage spike: {self.cpu_time_sec:.2f}s vs avg {avg_cpu:.2f}s",
                "current_value": self.cpu_time_sec,
                "baseline_value": avg_cpu,
            })
        
        # Detect inefficiency (high cost per GB)
        if self.data_bytes_ingested > 0:
            cost_per_gb = current_cost / (self.data_bytes_ingested / (1024 ** 3))
            if historical_metrics:
                avg_cost_per_gb = sum(
                    m["cost_per_metric"]["cost_per_gb_ingested"]
                    for m in historical_metrics
                    if m["cost_per_metric"]["cost_per_gb_ingested"] > 0
                ) / len([
                    m for m in historical_metrics
                    if m["cost_per_metric"]["cost_per_gb_ingested"] > 0
                ])
                
                if cost_per_gb > avg_cost_per_gb * 1.5:
                    anomalies.append({
                        "type": "inefficiency",
                        "severity": "medium",
                        "message": f"High cost per GB: ${cost_per_gb:.6f} vs avg ${avg_cost_per_gb:.6f}",
                        "current_value": cost_per_gb,
                        "baseline_value": avg_cost_per_gb,
                    })
        
        if anomalies:
            self.logger.warning(
                f"FinOps anomalies detected: {len(anomalies)}",
                extra={
                    "event_type": "finops_anomalies",
                    "anomaly_count": len(anomalies),
                    "anomalies": anomalies,
                },
            )
        
        return anomalies

    def export_for_billing(self) -> Dict[str, Any]:
        """Export metrics in billing-system format.

        Returns:
            Billing-ready metrics dictionary
        """
        return {
            "line_items": [
                {
                    "cost_center": self.cost_center,
                    "resource_type": "compute",
                    "quantity": self.cpu_time_sec / 3600,  # CPU hours
                    "unit": "cpu_hour",
                    "unit_price": self.pricing["compute_per_cpu_hour"],
                    "total_cost": self.compute_cost_usd,
                },
                {
                    "cost_center": self.cost_center,
                    "resource_type": "storage",
                    "quantity": self.data_bytes_written / (1024 ** 3),  # GB
                    "unit": "gb_month",
                    "unit_price": self.pricing["storage_per_gb_month"],
                    "total_cost": self.storage_cost_usd,
                },
                {
                    "cost_center": self.cost_center,
                    "resource_type": "network",
                    "quantity": self.data_bytes_ingested / (1024 ** 3),  # GB
                    "unit": "gb_transferred",
                    "unit_price": self.pricing["network_per_gb"],
                    "total_cost": self.network_cost_usd,
                },
                {
                    "cost_center": self.cost_center,
                    "resource_type": "api_calls",
                    "quantity": self.api_calls_count / 1000,  # Thousands
                    "unit": "1k_calls",
                    "unit_price": self.pricing["api_call_per_1k"],
                    "total_cost": self.api_cost_usd,
                },
            ],
            "summary": {
                "cost_center": self.cost_center,
                "tenant_id": self.tenant_id,
                "job_name": self.job_name,
                "total_cost_usd": (
                    self.compute_cost_usd +
                    self.storage_cost_usd +
                    self.network_cost_usd +
                    self.api_cost_usd
                ),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }
