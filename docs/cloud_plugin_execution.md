# Cloud Plugin Execution

This document describes how to run custom plugins (both Python and Rust) in cloud environments using AWS Lambda or GCP Cloud Functions.

## Overview

Cloud plugin execution enables running custom data readers and writers in isolated cloud environments, providing:

- **Better Isolation**: Plugins run in separate cloud functions with their own resources
- **Scalability**: Leverage cloud auto-scaling for plugin execution
- **Resource Management**: Control memory, timeout, and other resources per plugin
- **Cost Optimization**: Pay only for actual execution time (serverless model)
- **Security**: Isolate plugin execution from main application

## Supported Platforms

### AWS Lambda
- **Python Plugins**: Runtime `python3.11`, `python3.10`, `python3.9`
- **Rust Plugins**: Custom runtime `provided.al2` with bootstrap
- **Features**: VPC support, IAM roles, environment variables

### GCP Cloud Functions
- **Python Plugins**: Runtime `python311`, `python310`, `python39`
- **Rust Plugins**: Custom runtime with Python wrapper
- **Features**: Service accounts, regional deployment, environment variables

## Configuration

Cloud execution is configured in the `engine` section of your source or target configuration:

```yaml
source:
  custom_reader: "path/to/plugin.py:MyReader"
  engine:
    cloud_execution:
      enabled: true
      provider: "aws"  # or "gcp"
      runtime: "python3.11"
      memory_mb: 512
      timeout_seconds: 300
      aws:
        role_arn: "arn:aws:iam::account:role/lambda-role"
      gcp:
        project_id: "my-project"
      environment_variables:
        LOG_LEVEL: "INFO"
```

### Configuration Parameters

#### Common Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `enabled` | boolean | Yes | `false` | Enable cloud execution |
| `provider` | string | Yes | `"aws"` | Cloud provider: `"aws"` or `"gcp"` |
| `runtime` | string | No | `"python3.11"` | Runtime environment |
| `memory_mb` | integer | No | `512` | Memory allocation in MB |
| `timeout_seconds` | integer | No | `300` | Execution timeout in seconds |
| `environment_variables` | dict | No | `{}` | Environment variables to pass to function |

#### AWS-Specific Parameters

Configure under `aws` key:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `role_arn` | string | No | IAM role ARN for Lambda execution (creates default if not provided) |
| `security_groups` | list | No | VPC security group IDs |
| `subnets` | list | No | VPC subnet IDs |

#### GCP-Specific Parameters

Configure under `gcp` key:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | Yes | GCP project ID |
| `region` | string | No | Region for deployment (default: `"us-central1"`) |
| `service_account` | string | No | Service account email for function execution |

## Python Plugin Example

### Plugin Code (`json_api_reader.py`)

```python
from dativo_ingest.plugins import BaseReader

class JSONAPIReader(BaseReader):
    __version__ = "1.0.0"
    
    def __init__(self, source_config):
        super().__init__(source_config)
        self.base_url = source_config.connection.get("base_url")
    
    def extract(self, state_manager=None):
        # Your extraction logic
        yield [{"id": 1, "name": "Example"}]
```

### Job Configuration

```yaml
source:
  custom_reader: "/app/plugins/json_api_reader.py:JSONAPIReader"
  connection:
    base_url: "https://api.example.com"
  engine:
    cloud_execution:
      enabled: true
      provider: "aws"
      runtime: "python3.11"
      memory_mb: 512
      timeout_seconds: 300
```

## Rust Plugin Example

### Plugin Code (Rust)

```rust
// In your Cargo.toml:
// [lib]
// crate-type = ["cdylib"]

#[no_mangle]
pub extern "C" fn create_reader(config_json: *const c_char) -> *mut Reader {
    // Your reader implementation
}
```

### Job Configuration

```yaml
source:
  custom_reader: "/app/rust/target/release/libcsv_reader.so:create_reader"
  engine:
    cloud_execution:
      enabled: true
      provider: "aws"
      runtime: "provided.al2"  # Custom runtime for Rust
      memory_mb: 1024
      timeout_seconds: 600
```

## AWS Lambda Setup

### Prerequisites

1. **Install boto3**:
   ```bash
   pip install boto3
   ```

2. **Configure AWS credentials**:
   ```bash
   aws configure
   ```

3. **Create IAM role** (or let the system create it automatically):
   ```bash
   aws iam create-role \
     --role-name lambda-plugin-execution-role \
     --assume-role-policy-document '{
       "Version": "2012-10-17",
       "Statement": [{
         "Effect": "Allow",
         "Principal": {"Service": "lambda.amazonaws.com"},
         "Action": "sts:AssumeRole"
       }]
     }'
   
   aws iam attach-role-policy \
     --role-name lambda-plugin-execution-role \
     --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole
   ```

### VPC Configuration (Optional)

If your plugin needs to access resources in a VPC:

```yaml
aws:
  role_arn: "arn:aws:iam::123456789012:role/lambda-plugin-role"
  security_groups:
    - "sg-0123456789abcdef0"
  subnets:
    - "subnet-0123456789abcdef0"
    - "subnet-0123456789abcdef1"
```

### Python Runtime

Supported runtimes:
- `python3.11` (recommended)
- `python3.10`
- `python3.9`

### Rust Custom Runtime

For Rust plugins, use `runtime: "provided.al2"`. The system automatically packages your Rust shared library with a custom bootstrap.

## GCP Cloud Functions Setup

### Prerequisites

1. **Install google-cloud libraries**:
   ```bash
   pip install google-cloud-functions google-cloud-storage
   ```

2. **Configure GCP credentials**:
   ```bash
   gcloud auth application-default login
   ```

3. **Enable APIs**:
   ```bash
   gcloud services enable cloudfunctions.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   ```

4. **Create service account** (optional):
   ```bash
   gcloud iam service-accounts create plugin-executor \
     --description="Plugin execution service account" \
     --display-name="Plugin Executor"
   ```

### Configuration

```yaml
gcp:
  project_id: "my-gcp-project"
  region: "us-central1"
  service_account: "plugin-executor@my-gcp-project.iam.gserviceaccount.com"
```

### Python Runtime

Supported runtimes:
- `python311` (recommended)
- `python310`
- `python39`

## How It Works

### Deployment Process

1. **Package Plugin**: The system packages your plugin code and dependencies into a deployment package
2. **Deploy Function**: The package is deployed to AWS Lambda or GCP Cloud Functions
3. **Function Creation**: A cloud function is created with your specified configuration
4. **Invocation**: When your job runs, the plugin is invoked remotely

### Execution Flow

```
┌─────────────────┐
│  Dativo Job     │
│  (Main Process) │
└────────┬────────┘
         │
         │ 1. Load plugin config
         ▼
┌─────────────────┐
│ Cloud Executor  │
│ (Local)         │
└────────┬────────┘
         │
         │ 2. Package plugin
         │ 3. Deploy to cloud
         ▼
┌─────────────────┐
│ AWS Lambda /    │
│ GCP Cloud Func  │
└────────┬────────┘
         │
         │ 4. Execute plugin
         │ 5. Return results
         ▼
┌─────────────────┐
│  Dativo Job     │
│  (Main Process) │
└─────────────────┘
```

### Automatic Cleanup

Cloud functions are automatically cleaned up when the job completes or when the plugin object is destroyed.

## Best Practices

### 1. Resource Allocation

- **Memory**: Allocate enough memory for your plugin's data processing needs
  - Small datasets: 512 MB
  - Medium datasets: 1024 MB
  - Large datasets: 2048+ MB

- **Timeout**: Set appropriate timeout for your plugin's execution time
  - API calls: 300 seconds (5 minutes)
  - File processing: 600-900 seconds (10-15 minutes)

### 2. Cost Optimization

- Use cloud execution for:
  - Sporadic workloads (not constant processing)
  - Resource-intensive plugins that need isolation
  - Plugins requiring specific runtime environments

- Use local execution for:
  - Frequent, small data processing
  - Low-latency requirements
  - Development and testing

### 3. Security

- **Credentials**: Store sensitive credentials in environment variables, not in code
- **IAM Roles**: Use least-privilege IAM roles for Lambda/Cloud Functions
- **VPC**: Use VPC configuration when accessing private resources

### 4. Error Handling

Cloud execution includes automatic error handling:
- Connection errors are retried
- Lambda/Cloud Function errors are captured and logged
- Cleanup is performed even on failure

### 5. Monitoring

Monitor your cloud functions:

**AWS Lambda**:
```bash
aws logs tail /aws/lambda/dativo-reader-XXXXXXXX --follow
```

**GCP Cloud Functions**:
```bash
gcloud functions logs read dativo-reader-XXXXXXXX --limit 50
```

## Limitations

### AWS Lambda
- Maximum execution time: 15 minutes
- Maximum memory: 10 GB
- Maximum deployment package size: 250 MB (unzipped)

### GCP Cloud Functions
- Maximum execution time: 60 minutes (2nd gen)
- Maximum memory: 32 GB (2nd gen)
- Maximum deployment package size: 100 MB (compressed)

## Troubleshooting

### Plugin Fails to Deploy

**Issue**: Deployment fails with package size error

**Solution**: 
- Reduce plugin dependencies
- Use minimal dependencies
- Consider splitting into multiple plugins

### Plugin Times Out

**Issue**: Plugin execution times out

**Solution**:
- Increase `timeout_seconds` in configuration
- Optimize plugin code for performance
- Process data in smaller batches

### Permission Errors

**Issue**: Lambda/Cloud Function cannot execute

**Solution**:
- Verify IAM role has correct permissions
- Check VPC configuration if applicable
- Ensure service account has necessary roles (GCP)

### Connection Errors

**Issue**: Cannot connect to external services

**Solution**:
- Configure VPC and security groups (AWS)
- Ensure Cloud Function has internet access (GCP)
- Check firewall rules

## Examples

See the following example configurations:
- [AWS Lambda Python Plugin](../examples/jobs/cloud_plugin_aws_example.yaml)
- [GCP Cloud Functions Python Plugin](../examples/jobs/cloud_plugin_gcp_example.yaml)
- [Rust Plugin with Cloud Execution](../examples/jobs/cloud_plugin_rust_example.yaml)

## API Reference

### CloudExecutionConfig

Configuration class for cloud plugin execution:

```python
from dativo_ingest.cloud_plugin_executor import CloudExecutionConfig

config = CloudExecutionConfig(
    enabled=True,
    provider="aws",
    runtime="python3.11",
    memory_mb=512,
    timeout_seconds=300,
    aws_config={
        "role_arn": "arn:aws:iam::account:role/lambda-role"
    },
    environment_variables={
        "LOG_LEVEL": "INFO"
    }
)
```

### CloudPluginExecutor

Base class for cloud executors:

```python
from dativo_ingest.cloud_plugin_executor import (
    create_cloud_executor,
    CloudExecutionConfig
)

config = CloudExecutionConfig.from_dict({
    "enabled": True,
    "provider": "aws"
})

executor = create_cloud_executor(config)
```

## Support

For issues or questions about cloud plugin execution:
1. Check this documentation
2. Review example configurations
3. Check cloud provider logs
4. Open an issue on GitHub

## Future Enhancements

Planned features:
- Azure Functions support
- Persistent function deployments (reuse across jobs)
- Custom Docker image support
- Streaming data support
- Multi-region deployment
