"""Tests for FinOps metrics."""

import pytest

from dativo_ingest.finops import FinOpsMetrics


def test_finops_metrics_initialization():
    """Test FinOps metrics initialization."""
    metrics = FinOpsMetrics(
        tenant_id="test-tenant",
        job_name="test-job",
        cost_center="engineering",
    )
    
    assert metrics.tenant_id == "test-tenant"
    assert metrics.job_name == "test-job"
    assert metrics.cost_center == "engineering"


def test_record_cpu_time():
    """Test recording CPU time."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    metrics.start()
    
    metrics.record_cpu_time(3600.0)  # 1 hour
    
    assert metrics.cpu_time_sec == 3600.0
    assert metrics.compute_cost_usd > 0


def test_record_memory_usage():
    """Test recording memory usage."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    
    metrics.record_memory_usage(1024.0)  # 1GB
    
    assert metrics.memory_peak_mb == 1024.0


def test_record_data_ingested():
    """Test recording data ingested."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    
    metrics.record_data_ingested(1024 * 1024 * 1024)  # 1GB
    
    assert metrics.data_bytes_ingested == 1024 * 1024 * 1024
    assert metrics.network_cost_usd > 0


def test_record_data_written():
    """Test recording data written."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    
    metrics.record_data_written(1024 * 1024 * 1024)  # 1GB
    
    assert metrics.data_bytes_written == 1024 * 1024 * 1024
    assert metrics.storage_cost_usd > 0


def test_record_api_calls():
    """Test recording API calls."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    
    metrics.record_api_calls(1000, api_type="stripe")
    
    assert metrics.api_calls_count == 1000
    assert metrics.api_cost_usd > 0


def test_finish():
    """Test finishing metrics collection."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    metrics.start()
    
    metrics.record_cpu_time(100.0)
    metrics.record_data_written(1024 * 1024)  # 1MB
    
    summary = metrics.finish()
    
    assert "tenant_id" in summary
    assert "cost_breakdown_usd" in summary
    assert "resource_usage" in summary
    assert summary["cost_breakdown_usd"]["total"] > 0


def test_cost_breakdown():
    """Test cost breakdown calculation."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    metrics.start()
    
    # Record various resource usage
    metrics.record_cpu_time(3600.0)  # 1 CPU hour
    metrics.record_data_ingested(1024 * 1024 * 1024)  # 1GB
    metrics.record_data_written(1024 * 1024 * 1024)  # 1GB
    metrics.record_api_calls(10000)  # 10k API calls
    
    summary = metrics.finish()
    
    cost_breakdown = summary["cost_breakdown_usd"]
    
    assert cost_breakdown["compute"] > 0
    assert cost_breakdown["network"] > 0
    assert cost_breakdown["storage"] > 0
    assert cost_breakdown["api"] > 0
    assert cost_breakdown["total"] > 0
    
    # Total should be sum of components
    assert abs(
        cost_breakdown["total"] -
        (cost_breakdown["compute"] +
         cost_breakdown["network"] +
         cost_breakdown["storage"] +
         cost_breakdown["api"])
    ) < 0.000001


def test_cost_per_metric():
    """Test cost per metric calculation."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    metrics.start()
    
    metrics.record_cpu_time(100.0)
    metrics.record_data_ingested(1024 * 1024 * 1024)  # 1GB
    metrics.record_api_calls(1000)
    
    summary = metrics.finish()
    
    assert "cost_per_metric" in summary
    assert summary["cost_per_metric"]["cost_per_gb_ingested"] > 0
    assert summary["cost_per_metric"]["cost_per_api_call"] > 0


def test_detect_anomalies():
    """Test anomaly detection."""
    metrics = FinOpsMetrics("test-tenant", "test-job")
    metrics.start()
    
    # Record high CPU usage
    metrics.record_cpu_time(10000.0)
    
    # Historical data with normal usage
    historical = [
        {
            "resource_usage": {"cpu_time_sec": 100.0},
            "cost_breakdown_usd": {"total": 0.01},
            "cost_per_metric": {"cost_per_gb_ingested": 0.001, "cost_per_api_call": 0.0001},
        }
        for _ in range(10)
    ]
    
    anomalies = metrics.detect_anomalies(historical)
    
    # Should detect CPU spike
    assert len(anomalies) > 0
    assert any(a["type"] == "cpu_spike" for a in anomalies)


def test_export_for_billing():
    """Test exporting metrics for billing."""
    metrics = FinOpsMetrics("test-tenant", "test-job", cost_center="analytics")
    metrics.start()
    
    metrics.record_cpu_time(3600.0)
    metrics.record_data_written(1024 * 1024 * 1024)
    
    billing_export = metrics.export_for_billing()
    
    assert "line_items" in billing_export
    assert "summary" in billing_export
    assert len(billing_export["line_items"]) > 0
    assert billing_export["summary"]["cost_center"] == "analytics"
