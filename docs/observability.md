# Cloud Observability

Dativo Ingest provides built-in support for exporting job execution metrics to cloud monitoring services. This enables comprehensive observability, monitoring, and alerting for your data pipelines.

## Supported Providers

### AWS CloudWatch
Export metrics to AWS CloudWatch for monitoring and alerting within the AWS ecosystem.

### GCP Cloud Monitoring
Export metrics to Google Cloud Monitoring (formerly Stackdriver) for monitoring within the Google Cloud Platform.

## Configuration

Observability is configured in the job YAML file under the `observability` section:

```yaml
observability:
  enabled: true
  provider: aws_cloudwatch  # or gcp_cloud_monitoring
  config:
    # Provider-specific configuration
  metrics:
    # Metric collection configuration
```

## AWS CloudWatch Configuration

### Required Configuration

```yaml
observability:
  enabled: true
  provider: aws_cloudwatch
  config:
    region: us-east-1                    # AWS region
    namespace: Dativo/Ingest             # CloudWatch namespace
```

### Optional Configuration

```yaml
observability:
  enabled: true
  provider: aws_cloudwatch
  config:
    region: us-east-1
    namespace: Dativo/Ingest
    
    # Credentials (optional - uses default AWS credential chain if not provided)
    credentials:
      aws_access_key_id: "${AWS_ACCESS_KEY_ID}"
      aws_secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
    
    # Additional dimensions for all metrics (optional)
    dimensions:
      team: data-platform
      environment: production
      cost_center: engineering
```

### Authentication

CloudWatch authentication follows the standard AWS credential chain:
1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
2. IAM role (recommended for EC2/ECS/Lambda)
3. Explicit credentials in configuration (not recommended for production)

### Metrics in CloudWatch

Metrics are published to CloudWatch with the following structure:
- **Namespace**: As configured (e.g., `Dativo/Ingest`)
- **Dimensions**: `tenant_id`, `job_name`, `environment`, plus any custom dimensions
- **Units**: Appropriate units for each metric (Count, Seconds, Bytes, etc.)

## GCP Cloud Monitoring Configuration

### Required Configuration

```yaml
observability:
  enabled: true
  provider: gcp_cloud_monitoring
  config:
    project_id: my-gcp-project                              # GCP project ID
    namespace: custom.googleapis.com/dativo                  # Metric type prefix
```

### Optional Configuration

```yaml
observability:
  enabled: true
  provider: gcp_cloud_monitoring
  config:
    project_id: my-gcp-project
    namespace: custom.googleapis.com/dativo
    
    # Service account credentials (optional - uses default credentials if not provided)
    credentials:
      gcp_service_account_key_path: /path/to/service-account-key.json
    
    # Additional labels for all metrics (optional)
    dimensions:
      team: data-platform
      environment: production
      cost_center: engineering
```

### Authentication

GCP authentication follows the standard Google Cloud credential chain:
1. Service account key file (via `GOOGLE_APPLICATION_CREDENTIALS` environment variable)
2. Explicit service account key path in configuration
3. Default application credentials (recommended for GCE/GKE/Cloud Run)

### Metrics in Cloud Monitoring

Metrics are published to Cloud Monitoring with the following structure:
- **Metric Type**: `{namespace}/{metric_name}` (e.g., `custom.googleapis.com/dativo/JobDuration`)
- **Resource Type**: `generic_task` with labels for project, namespace, job, and tenant
- **Labels**: `tenant_id`, `job_name`, `environment`, plus any custom labels

## Collected Metrics

The following metrics are collected and exported to the configured cloud provider:

### Job Execution Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| `JobStarted` | Count | Incremented when a job starts |
| `JobDuration` | Seconds | Total job execution time |
| `JobSuccess` | Count | Incremented when a job completes successfully |
| `JobFailure` | Count | Incremented when a job fails (includes `error_type` dimension) |

### Data Processing Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| `RecordsProcessed` | Count | Number of records processed (includes `stage` dimension: extraction, validation, writing) |
| `DataVolume` | Bytes | Volume of data processed (includes `direction` dimension: read, written) |

### Reliability Metrics

| Metric | Unit | Description |
|--------|------|-------------|
| `JobRetry` | Count | Retry attempts (includes `attempt` and `max_attempts` dimensions) |
| `ApiCalls` | Count | External API calls made (includes `api_type` dimension for Stripe, HubSpot, etc.) |

### Metric Dimensions/Labels

All metrics include the following base dimensions:
- `tenant_id`: Tenant identifier
- `job_name`: Job name (asset name)
- `environment`: Environment (dev, staging, prod, etc.)

Plus any custom dimensions configured in the `observability.config.dimensions` section.

## Metric Collection Configuration

You can selectively enable or disable specific metric categories:

```yaml
observability:
  enabled: true
  provider: aws_cloudwatch
  config:
    # ... provider config ...
  metrics:
    job_duration: true          # Enable/disable job duration metrics
    records_processed: true     # Enable/disable records processed metrics
    errors: true                # Enable/disable error metrics
    retries: true               # Enable/disable retry metrics
    data_volume: true           # Enable/disable data volume metrics
```

All metrics are enabled by default. Set to `false` to disable specific metrics.

## Example Configurations

### AWS CloudWatch with IAM Role

```yaml
tenant_id: acme
environment: prod
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/csv/v1.0/employee.yaml

observability:
  enabled: true
  provider: aws_cloudwatch
  config:
    region: us-east-1
    namespace: Dativo/Ingest
    dimensions:
      team: data-engineering
```

### GCP Cloud Monitoring with Service Account

```yaml
tenant_id: acme
environment: prod
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/csv/v1.0/employee.yaml

observability:
  enabled: true
  provider: gcp_cloud_monitoring
  config:
    project_id: my-gcp-project
    namespace: custom.googleapis.com/dativo
    credentials:
      gcp_service_account_key_path: /secrets/gcp-sa-key.json
    dimensions:
      team: data-engineering
```

### Minimal Configuration (AWS)

```yaml
tenant_id: acme
environment: prod
source_connector_path: connectors/csv.yaml
target_connector_path: connectors/iceberg.yaml
asset_path: assets/csv/v1.0/employee.yaml

observability:
  enabled: true
  provider: aws_cloudwatch
  config:
    region: us-east-1
    namespace: Dativo/Ingest
```

## Monitoring and Alerting

### AWS CloudWatch

Once metrics are being exported to CloudWatch, you can:

1. **View Metrics**: Navigate to CloudWatch → Metrics → Custom Namespaces → `Dativo/Ingest`
2. **Create Dashboards**: Build custom dashboards showing job performance, error rates, data volumes
3. **Set Alarms**: Configure CloudWatch Alarms for:
   - Job failures (`JobFailure` metric)
   - Long-running jobs (`JobDuration` exceeding threshold)
   - High error rates
   - Data volume anomalies

### GCP Cloud Monitoring

Once metrics are being exported to Cloud Monitoring, you can:

1. **View Metrics**: Navigate to Cloud Monitoring → Metrics Explorer → Custom Metrics → `custom.googleapis.com/dativo`
2. **Create Dashboards**: Build custom dashboards showing job performance, error rates, data volumes
3. **Set Alerts**: Configure alerting policies for:
   - Job failures (based on `JobFailure` metric)
   - Long-running jobs (based on `JobDuration` threshold)
   - High error rates
   - Data volume anomalies

## Best Practices

### 1. Use IAM Roles / Service Accounts

In production, use IAM roles (AWS) or service accounts (GCP) instead of hardcoded credentials:

**AWS**: Attach an IAM role to your EC2/ECS/Lambda with `cloudwatch:PutMetricData` permission
**GCP**: Use Workload Identity or attach a service account with `monitoring.metricWriter` role

### 2. Add Custom Dimensions

Use custom dimensions to organize and filter metrics:

```yaml
observability:
  config:
    dimensions:
      team: data-engineering
      cost_center: eng-001
      priority: high
```

### 3. Set Appropriate Namespaces

Use meaningful namespaces that match your organization's structure:
- AWS: `MyCompany/DataPlatform/Ingest`
- GCP: `custom.googleapis.com/mycompany/ingest`

### 4. Monitor Metric Costs

Be aware of metric costs:
- **AWS CloudWatch**: Charges for custom metrics (first 10,000 metrics free tier)
- **GCP Cloud Monitoring**: Charges for custom metrics (first 150 MB/month free)

### 5. Test Observability Configuration

Use the `--dry-run` mode or test in a development environment before enabling in production.

## Troubleshooting

### Metrics Not Appearing

1. **Check Credentials**: Ensure the configured credentials have permission to write metrics
2. **Check Configuration**: Verify the configuration is correct (region, project_id, namespace)
3. **Check Logs**: Look for observability-related warnings in the job logs
4. **Check Network**: Ensure the job can reach the cloud provider's API endpoints

### Metrics Delayed

- **AWS CloudWatch**: Metrics may have up to 1-minute delay
- **GCP Cloud Monitoring**: Metrics may have up to 2-minute delay

### Authentication Errors

**AWS**: Verify IAM permissions include `cloudwatch:PutMetricData`
**GCP**: Verify service account has `monitoring.metricWriter` role

## Dependencies

To use cloud observability, install the optional dependencies:

```bash
# For AWS CloudWatch
pip install boto3

# For GCP Cloud Monitoring
pip install google-cloud-monitoring

# Or install all observability dependencies
pip install dativo-ingest[observability]
```

## Disabling Observability

To temporarily disable observability without removing the configuration:

```yaml
observability:
  enabled: false  # Set to false to disable
  # ... rest of config ...
```

Observability is fail-safe: if initialization or metric export fails, the job will continue executing normally with a warning logged.
