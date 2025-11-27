# Cloud Observability Implementation Summary

## Overview

This document summarizes the implementation of optional cloud observability support in Dativo Ingest for AWS CloudWatch and GCP Cloud Monitoring.

## What Was Implemented

### 1. Schema Updates

**File: `schemas/job-config.schema.json`**
- Added new `observability` configuration block to job schema
- Supports optional observability configuration with provider selection
- Includes provider-specific configuration options and metric selection

### 2. Core Observability Module

**File: `src/dativo_ingest/observability.py`**
- Created abstract `ObservabilityProvider` base class
- Implemented `AWSCloudWatchProvider` for AWS CloudWatch integration
- Implemented `GCPCloudMonitoringProvider` for GCP Cloud Monitoring integration
- Factory function `create_observability_provider()` for provider instantiation

**Key Features:**
- Buffered metric publishing for efficiency (20 metrics for AWS, 200 for GCP)
- Automatic batching and flushing
- Error handling with graceful degradation
- Support for custom dimensions/labels
- Standard metrics: job duration, records processed, data volume, errors, retries, API calls

### 3. Configuration Models

**File: `src/dativo_ingest/config.py`**
- Added `ObservabilityConfig` model
- Added `ObservabilityMetricsConfig` model for selective metric collection
- Validation for provider-specific required fields

### 4. Metrics Collector Enhancement

**File: `src/dativo_ingest/metrics.py`**
- Enhanced `MetricsCollector` to accept observability provider
- Integrated observability recording into all metric collection methods:
  - `start()` - Record job start
  - `record_extraction()` - Record extraction metrics
  - `record_writing()` - Record data volume
  - `record_api_calls()` - Record API call counts
  - `record_error()` - Record error events
  - `record_retry()` - Record retry attempts
  - `finish()` - Record job duration and final status

### 5. Job Execution Integration

**File: `src/dativo_ingest/cli.py`**
- Added observability provider initialization in `_execute_single_job()`
- Integrated metric recording at job completion (success/failure)
- Added metric recording for job failures in exception handler
- Graceful handling of observability initialization failures

### 6. Dependencies

**File: `pyproject.toml`**
- Added optional `observability` dependency group
- Includes `boto3` for AWS CloudWatch
- Includes `google-cloud-monitoring` for GCP Cloud Monitoring

### 7. Example Job Configurations

**Files Created:**
- `examples/jobs/csv_to_iceberg_with_observability_aws.yaml` - AWS CloudWatch example
- `examples/jobs/csv_to_iceberg_with_observability_gcp.yaml` - GCP Cloud Monitoring example

Both examples demonstrate:
- Complete observability configuration
- Provider-specific settings
- Custom dimensions
- Metric selection

### 8. Documentation

**Files Created/Updated:**
- `docs/observability.md` - Comprehensive observability guide
- `README.md` - Added Cloud Observability section with quick start

## Metrics Exported

All metrics include base dimensions: `tenant_id`, `job_name`, `environment`, plus any custom dimensions.

### Job Execution Metrics
- `JobStarted` (Count) - Job start event
- `JobDuration` (Seconds) - Total execution time
- `JobSuccess` (Count) - Successful completion
- `JobFailure` (Count) - Job failure with error_type dimension

### Data Processing Metrics
- `RecordsProcessed` (Count) - Records processed by stage (extraction, validation, writing)
- `DataVolume` (Bytes) - Data volume by direction (read, written)

### Reliability Metrics
- `JobRetry` (Count) - Retry attempts with attempt number
- `ApiCalls` (Count) - External API calls with api_type dimension

## Configuration Options

### AWS CloudWatch

```yaml
observability:
  enabled: true
  provider: aws_cloudwatch
  config:
    region: us-east-1                    # Required
    namespace: Dativo/Ingest             # Required
    credentials:                         # Optional (uses IAM if not provided)
      aws_access_key_id: "${AWS_ACCESS_KEY_ID}"
      aws_secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
    dimensions:                          # Optional
      team: data-platform
```

### GCP Cloud Monitoring

```yaml
observability:
  enabled: true
  provider: gcp_cloud_monitoring
  config:
    project_id: my-gcp-project                    # Required
    namespace: custom.googleapis.com/dativo       # Required
    credentials:                                  # Optional (uses default creds if not provided)
      gcp_service_account_key_path: /path/to/key.json
    dimensions:                                   # Optional
      team: data-platform
```

### Selective Metric Collection

```yaml
observability:
  metrics:
    job_duration: true          # Enable/disable (default: true)
    records_processed: true
    errors: true
    retries: true
    data_volume: true
```

## Architecture Decisions

### 1. Optional and Fail-Safe
- Observability is completely optional
- If initialization fails, job continues with warning
- If metric export fails, job continues with warning

### 2. Buffered Publishing
- Metrics are buffered before sending to reduce API calls
- AWS: 20 metrics per request (CloudWatch limit)
- GCP: 200 time series per request (Cloud Monitoring limit)

### 3. Provider Abstraction
- Abstract base class allows easy addition of new providers
- Factory pattern for provider creation
- Consistent interface across all providers

### 4. Minimal Dependencies
- Core functionality doesn't require observability dependencies
- Observability dependencies are optional (`pip install dativo-ingest[observability]`)
- Import errors are caught and handled gracefully

### 5. Integration Point
- Integrated at job execution level in CLI
- Metrics recorded during job execution
- Final flush at job completion (success or failure)

## Testing Recommendations

### Unit Tests
- Test each observability provider independently
- Mock cloud provider APIs
- Test metric buffering and flushing
- Test error handling and graceful degradation

### Integration Tests
- Test with real AWS CloudWatch (sandbox account)
- Test with real GCP Cloud Monitoring (sandbox project)
- Verify metrics appear correctly in cloud consoles
- Test authentication methods (IAM, service accounts)

### Example Test Cases
```python
# Test AWS CloudWatch provider
def test_aws_cloudwatch_provider():
    provider = AWSCloudWatchProvider(
        config={"region": "us-east-1", "namespace": "Test"},
        tenant_id="test",
        job_name="test_job"
    )
    provider.record_job_start()
    provider.record_job_duration(10.5)
    provider.flush()
    # Verify metrics in CloudWatch

# Test GCP Cloud Monitoring provider
def test_gcp_monitoring_provider():
    provider = GCPCloudMonitoringProvider(
        config={"project_id": "test-project", "namespace": "custom.googleapis.com/test"},
        tenant_id="test",
        job_name="test_job"
    )
    provider.record_job_start()
    provider.record_job_duration(10.5)
    provider.flush()
    # Verify metrics in Cloud Monitoring
```

## Future Enhancements

### Additional Providers
- Azure Monitor
- Datadog
- Prometheus/OpenMetrics
- New Relic

### Enhanced Metrics
- Query performance metrics (for database sources)
- Network throughput
- Memory usage
- Custom business metrics

### Advanced Features
- Metric aggregation and rollup
- Custom metric namespaces per tenant
- Metric sampling for high-volume jobs
- Cost optimization features

### Dashboards and Alerts
- Pre-built CloudWatch dashboards
- Pre-built GCP dashboards
- Example alerting policies
- Terraform templates for infrastructure

## Installation

### Basic Installation
```bash
pip install dativo-ingest
```

### With Observability Support
```bash
# All observability providers
pip install dativo-ingest[observability]

# AWS only
pip install dativo-ingest boto3

# GCP only
pip install dativo-ingest google-cloud-monitoring
```

## Usage Example

```yaml
# Job configuration with observability
tenant_id: acme
environment: prod

source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/csv/v1.0/employee.yaml

source:
  files:
    - path: data/employees.csv

target:
  connection:
    s3:
      bucket: my-bucket

observability:
  enabled: true
  provider: aws_cloudwatch
  config:
    region: us-east-1
    namespace: Dativo/Ingest
    dimensions:
      team: data-engineering
      environment: prod
```

Run the job:
```bash
dativo run --config job.yaml --mode self_hosted
```

Metrics will automatically be exported to AWS CloudWatch under the `Dativo/Ingest` namespace.

## Monitoring

### AWS CloudWatch
1. Navigate to CloudWatch → Metrics → Custom Namespaces → `Dativo/Ingest`
2. Create dashboards showing:
   - Job success/failure rates
   - Job duration trends
   - Data volume processed
   - Error rates
3. Set up alarms for:
   - Job failures (`JobFailure` > 0)
   - Long-running jobs (`JobDuration` > threshold)
   - High error rates

### GCP Cloud Monitoring
1. Navigate to Cloud Monitoring → Metrics Explorer
2. Search for custom metrics under `custom.googleapis.com/dativo`
3. Create dashboards and alerts similar to AWS

## Troubleshooting

### Metrics Not Appearing
1. Check job logs for observability-related warnings
2. Verify credentials have permission to write metrics
3. Verify configuration (region, project_id, namespace)
4. Check network connectivity to cloud provider

### Authentication Errors
- **AWS**: Verify IAM permissions include `cloudwatch:PutMetricData`
- **GCP**: Verify service account has `monitoring.metricWriter` role

### High Costs
- Consider sampling metrics for high-frequency jobs
- Reduce custom dimensions
- Monitor metric API calls

## Conclusion

The cloud observability implementation provides a robust, optional, and extensible framework for monitoring Dativo Ingest jobs in AWS and GCP. The implementation follows best practices for error handling, performance, and maintainability while remaining completely optional and fail-safe.
