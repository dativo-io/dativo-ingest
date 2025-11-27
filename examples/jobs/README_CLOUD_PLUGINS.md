# Cloud Plugin Execution Examples

This directory contains example job configurations demonstrating cloud plugin execution in AWS Lambda and GCP Cloud Functions.

## Examples

### 1. AWS Lambda - Python Plugin (`cloud_plugin_aws_example.yaml`)

Demonstrates running a Python custom reader plugin in AWS Lambda.

**Key Features:**
- AWS Lambda execution with Python 3.11 runtime
- IAM role configuration
- VPC configuration (optional)
- Security groups and subnets
- Environment variables
- Memory and timeout settings

**Use Case:** API data extraction with cloud isolation

### 2. GCP Cloud Functions - Python Plugin (`cloud_plugin_gcp_example.yaml`)

Demonstrates running a Python custom reader plugin in GCP Cloud Functions.

**Key Features:**
- GCP Cloud Functions execution
- Project and region configuration
- Service account support
- Environment variables
- Memory and timeout settings

**Use Case:** API data extraction with GCP infrastructure

### 3. Rust Plugin - AWS Lambda (`cloud_plugin_rust_example.yaml`)

Demonstrates running Rust plugins (both reader and writer) in AWS Lambda with custom runtime.

**Key Features:**
- Custom runtime (`provided.al2`) for Rust
- High-memory allocation (1-2GB)
- Both reader and writer plugins in cloud
- Performance optimization for large datasets

**Use Case:** High-performance data processing in the cloud

## Prerequisites

### AWS Lambda

1. **Install boto3** (already included for S3 access):
   ```bash
   pip install boto3
   ```

2. **Configure AWS credentials**:
   ```bash
   aws configure
   # OR set environment variables:
   export AWS_ACCESS_KEY_ID=your_key
   export AWS_SECRET_ACCESS_KEY=your_secret
   export AWS_DEFAULT_REGION=us-east-1
   ```

3. **Create IAM role** (optional, will be created automatically if not provided):
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

### GCP Cloud Functions

1. **Install Google Cloud libraries**:
   ```bash
   pip install google-cloud-functions google-cloud-storage
   ```

2. **Configure GCP credentials**:
   ```bash
   gcloud auth application-default login
   ```

3. **Enable required APIs**:
   ```bash
   gcloud services enable cloudfunctions.googleapis.com
   gcloud services enable cloudbuild.googleapis.com
   gcloud services enable storage.googleapis.com
   ```

4. **Create service account** (optional):
   ```bash
   gcloud iam service-accounts create plugin-executor \
     --description="Plugin execution service account" \
     --display-name="Plugin Executor"
   ```

## How to Run

### Using AWS Lambda Example

```bash
# Run with AWS Lambda execution
dativo run \
  --config examples/jobs/cloud_plugin_aws_example.yaml \
  --mode self_hosted \
  --secret-manager filesystem \
  --secrets-dir /path/to/secrets
```

### Using GCP Cloud Functions Example

```bash
# Run with GCP Cloud Functions execution
dativo run \
  --config examples/jobs/cloud_plugin_gcp_example.yaml \
  --mode self_hosted \
  --secret-manager filesystem \
  --secrets-dir /path/to/secrets
```

### Using Rust Plugin Example

```bash
# First, build the Rust plugin
cd examples/rust
make build-release

# Then run with cloud execution
dativo run \
  --config examples/jobs/cloud_plugin_rust_example.yaml \
  --mode self_hosted
```

## Configuration Options

### Common Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `enabled` | Yes | `false` | Enable cloud execution |
| `provider` | Yes | `"aws"` | Cloud provider (`"aws"` or `"gcp"`) |
| `runtime` | No | `"python3.11"` | Runtime environment |
| `memory_mb` | No | `512` | Memory allocation in MB |
| `timeout_seconds` | No | `300` | Execution timeout in seconds |
| `environment_variables` | No | `{}` | Environment variables |

### AWS-Specific Parameters

Configure under `engine.cloud_execution.aws`:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `role_arn` | No | IAM role ARN (creates default if not provided) |
| `security_groups` | No | VPC security group IDs |
| `subnets` | No | VPC subnet IDs |

### GCP-Specific Parameters

Configure under `engine.cloud_execution.gcp`:

| Parameter | Required | Description |
|-----------|----------|-------------|
| `project_id` | Yes | GCP project ID |
| `region` | No | Region (default: `"us-central1"`) |
| `service_account` | No | Service account email |

## Customization

### Modifying Memory and Timeout

```yaml
engine:
  cloud_execution:
    enabled: true
    provider: "aws"
    memory_mb: 1024  # Increase for larger datasets
    timeout_seconds: 600  # Increase for longer operations
```

### Adding VPC Configuration (AWS)

```yaml
engine:
  cloud_execution:
    enabled: true
    provider: "aws"
    aws:
      role_arn: "arn:aws:iam::account:role/lambda-role"
      security_groups:
        - "sg-0123456789abcdef0"
      subnets:
        - "subnet-0123456789abcdef0"
        - "subnet-0123456789abcdef1"
```

### Using Custom Service Account (GCP)

```yaml
engine:
  cloud_execution:
    enabled: true
    provider: "gcp"
    gcp:
      project_id: "my-project"
      region: "us-central1"
      service_account: "plugin-executor@my-project.iam.gserviceaccount.com"
```

## When to Use Cloud Execution

### ✅ Good Use Cases

- **Sporadic Workloads**: Jobs that run infrequently
- **Resource-Intensive**: Plugins needing significant memory/CPU
- **Isolation Required**: Security-sensitive operations
- **Variable Load**: Workloads with unpredictable resource needs
- **Multi-Tenant**: Running plugins from different tenants

### ❌ Not Recommended For

- **Frequent Jobs**: Constant, high-frequency execution
- **Low Latency**: Real-time or near-real-time processing
- **Small Data**: Simple transformations on small datasets
- **Development**: Local development and testing

## Cost Considerations

### AWS Lambda Pricing

- **Compute**: $0.0000166667 per GB-second
- **Requests**: $0.20 per 1M requests
- **Free Tier**: 1M requests and 400,000 GB-seconds per month

**Example Cost:**
- 512 MB memory, 10 second execution, 1000 runs/month
- Cost: ~$0.08/month (within free tier)

### GCP Cloud Functions Pricing

- **Compute**: $0.0000025 per GB-second
- **Requests**: $0.40 per 1M requests
- **Free Tier**: 2M requests and 400,000 GB-seconds per month

**Example Cost:**
- 512 MB memory, 10 second execution, 1000 runs/month
- Cost: ~$0.01/month (within free tier)

## Monitoring and Debugging

### View AWS Lambda Logs

```bash
# List functions
aws lambda list-functions --query 'Functions[?starts_with(FunctionName, `dativo-`)]'

# View logs
aws logs tail /aws/lambda/dativo-reader-XXXXXXXX --follow
```

### View GCP Cloud Functions Logs

```bash
# List functions
gcloud functions list --filter="name:dativo-"

# View logs
gcloud functions logs read dativo-reader-XXXXXXXX --limit 50
```

### Enable Verbose Logging

```yaml
engine:
  cloud_execution:
    enabled: true
    provider: "aws"
    environment_variables:
      LOG_LEVEL: "DEBUG"
      RUST_LOG: "debug"  # For Rust plugins
```

## Troubleshooting

### Issue: Deployment Fails

**Solution:**
- Check AWS/GCP credentials are configured
- Verify IAM/service account permissions
- Check plugin file exists at specified path
- Verify runtime version is supported

### Issue: Plugin Times Out

**Solution:**
- Increase `timeout_seconds`
- Optimize plugin code
- Process data in smaller batches
- Increase memory allocation

### Issue: Permission Errors

**Solution:**
- Verify IAM role has necessary permissions (AWS)
- Check service account permissions (GCP)
- For VPC access, verify security groups and subnets
- Check bucket/resource access permissions

### Issue: High Costs

**Solution:**
- Reduce `memory_mb` if possible
- Optimize plugin for faster execution
- Consider local execution for frequent jobs
- Use reserved capacity for predictable workloads

## Next Steps

- Review [Cloud Plugin Execution Guide](../../docs/cloud_plugin_execution.md) for detailed documentation
- See [Plugin Development Guide](../../docs/PLUGIN_DEVELOPMENT.md) for creating custom plugins
- Check [Implementation Summary](../../CLOUD_PLUGIN_IMPLEMENTATION_SUMMARY.md) for technical details

## Support

For issues or questions:
1. Check the documentation and examples
2. Review cloud provider logs
3. Enable verbose logging
4. Open an issue on GitHub with:
   - Job configuration
   - Error messages
   - Cloud provider logs
   - Plugin code (if applicable)
