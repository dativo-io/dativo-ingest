# LLM-Based Metadata Generation

## Overview

Dativo Ingestion Platform supports optional **LLM-based metadata generation** to enhance data asset discoverability and governance. Inspired by the [Intelligence Lake concept](https://dzone.com/articles/intelligence-lake-iceberg-generative-ai-aws), this feature uses Large Language Models (LLMs) to automatically generate rich semantic metadata from:

- Source API definitions
- Schema information
- Sample data records
- Field names and types

## Benefits

### 🎯 Improved Discoverability
- **Semantic tags** for better search and filtering
- **Business context** explaining data purpose and use cases
- **Related assets** suggestions for data discovery

### 📊 Enhanced Governance
- **Data quality expectations** based on schema analysis
- **Sensitive field detection** for PII/compliance tracking
- **Optimization suggestions** for performance tuning

### 🤖 Automated Documentation
- **Comprehensive descriptions** generated automatically
- **Sample queries** showing how to use the data
- **Lineage hints** for understanding data flow

## Configuration

### Basic Configuration

Add an `llm` section to your job configuration:

```yaml
llm:
  enabled: true
  provider: openai  # or anthropic, bedrock, azure
  model: gpt-4
  api_key: "${OPENAI_API_KEY}"
```

### Full Configuration Options

```yaml
llm:
  # Required fields
  enabled: true                      # Enable/disable LLM generation (default: false)
  provider: openai                   # LLM provider (see supported providers below)
  model: gpt-4                       # Model identifier
  api_key: "${OPENAI_API_KEY}"       # API key (env var reference recommended)
  
  # Optional fields
  endpoint: "https://custom.api.url" # Custom endpoint (for Azure or self-hosted)
  temperature: 0.3                   # Temperature (0.0-1.0, default: 0.3)
  max_tokens: 2000                   # Max tokens (default: 2000)
  sample_records_count: 3            # Sample records to analyze (default: 3)
```

## Supported Providers

### OpenAI

```yaml
llm:
  enabled: true
  provider: openai
  model: gpt-4                       # or gpt-3.5-turbo
  api_key: "${OPENAI_API_KEY}"
```

**Requirements:**
- API key from [OpenAI Platform](https://platform.openai.com/)
- Python package: `pip install openai`

### Anthropic Claude

```yaml
llm:
  enabled: true
  provider: anthropic
  model: claude-3-sonnet-20240229    # or claude-3-opus-20240229
  api_key: "${ANTHROPIC_API_KEY}"
```

**Requirements:**
- API key from [Anthropic Console](https://console.anthropic.com/)
- Python package: `pip install anthropic`

### AWS Bedrock

```yaml
llm:
  enabled: true
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0
  # No api_key - uses AWS credentials from environment
```

**Requirements:**
- AWS credentials (via `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` or `AWS_PROFILE`)
- Bedrock access enabled in your AWS account
- Python package: `pip install boto3`

### Azure OpenAI

```yaml
llm:
  enabled: true
  provider: azure
  model: gpt-4                       # Your deployment name
  api_key: "${AZURE_OPENAI_API_KEY}"
  endpoint: "https://your-resource.openai.azure.com/"
```

**Requirements:**
- Azure OpenAI resource and deployment
- Python package: `pip install openai`

## Generated Metadata

The LLM generates the following metadata fields:

### 1. Enhanced Description
Clear, concise description of the dataset's purpose and contents.

### 2. Business Purpose
Business use cases and value this data provides to stakeholders.

### 3. Data Quality Expectations
Suggested quality rules and validations, for example:
- "Customer email should be valid format"
- "Order total must be positive"
- "Product price should not be null"

### 4. Semantic Tags
Tags for improved discoverability (e.g., "customer-data", "financial", "pii").

### 5. Sample Queries
Example analytical questions that can be answered with this data.

### 6. Sensitive Fields
Fields identified as potentially containing sensitive or PII data.

### 7. Optimization Suggestions
Recommendations for partitioning, indexing, or performance optimization.

### 8. Lineage Hints
Inferred upstream sources and downstream consumers.

### 9. Related Assets
Suggestions for related datasets based on schema and purpose.

## Output

### Enriched Asset Definition

The generated metadata enriches the original asset definition:

```yaml
# Original fields preserved
name: stripe_customers
version: "1.0"
schema:
  - name: id
    type: string
  - name: email
    type: string

# Enhanced with LLM-generated metadata
description:
  purpose: "Customer records from Stripe containing payment and contact information..."
  usage: "Used for customer analytics, billing reports, and CRM integration..."

tags:
  - payments
  - customer-data
  - pii  # Added by LLM

data_quality:
  expectations:
    - description: "Customer email should be valid format"
      source: llm_generated
    - description: "Customer ID must be unique"
      source: llm_generated

compliance:
  classification: [PII]  # Added based on sensitive field detection

# Full LLM metadata stored in target config
target:
  llm_metadata:
    generated_at: "2025-11-18T10:30:00Z"
    provider: openai
    model: gpt-4
    description_enhanced: "..."
    business_purpose: "..."
    data_quality_expectations: [...]
    semantic_tags: [...]
    sample_queries: [...]
    sensitive_fields: [...]
    optimization_suggestions: "..."
    lineage_hints: "..."
    related_assets_hints: [...]
```

### Output File Location

Enriched asset definitions are saved to:
```
.local/llm_metadata/{tenant_id}/{asset_name}_enriched.yaml
```

## Example Job Configurations

### Example 1: Stripe with OpenAI

```yaml
tenant_id: acme
environment: prod

source_connector: stripe
source_connector_path: /app/connectors/stripe.yaml
target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml
asset: stripe_customers
asset_path: /app/assets/stripe/v1.0/customers.yaml

source:
  objects: [customers]

target:
  branch: acme
  warehouse: s3://lake/acme/

llm:
  enabled: true
  provider: openai
  model: gpt-4
  api_key: "${OPENAI_API_KEY}"
  sample_records_count: 5

logging:
  redaction: true
  level: INFO
```

### Example 2: PostgreSQL with Anthropic Claude

```yaml
tenant_id: acme
environment: prod

source_connector: postgres
source_connector_path: /app/connectors/postgres.yaml
target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml
asset: db_orders
asset_path: /app/assets/postgres/v1.0/db_orders.yaml

source:
  tables:
    - schema: sales
      table: orders
      object: orders

target:
  branch: acme
  warehouse: s3://lake/acme/

llm:
  enabled: true
  provider: anthropic
  model: claude-3-sonnet-20240229
  api_key: "${ANTHROPIC_API_KEY}"
  temperature: 0.3
  max_tokens: 2000

logging:
  redaction: true
  level: INFO
```

### Example 3: CSV with AWS Bedrock

```yaml
tenant_id: acme
environment: prod

source_connector: csv
source_connector_path: /app/connectors/csv.yaml
target_connector: iceberg
target_connector_path: /app/connectors/iceberg.yaml
asset: csv_employee
asset_path: /app/assets/csv/v1.0/employee.yaml

source:
  files:
    - path: /data/employees.csv
      object: employees

target:
  branch: acme
  warehouse: s3://lake/acme/

llm:
  enabled: true
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0
  # Uses AWS credentials from environment

logging:
  redaction: true
  level: INFO
```

## Security Best Practices

### 1. API Key Management
Always use environment variables for API keys:

```yaml
llm:
  api_key: "${OPENAI_API_KEY}"  # ✓ Good
  # api_key: "sk-abc123..."     # ✗ Bad - hardcoded
```

### 2. Secrets Management
Store API keys in secure secrets management:
- Environment variables
- AWS Secrets Manager
- HashiCorp Vault
- Kubernetes Secrets

### 3. Cost Control
Monitor LLM API usage and set budgets:
- Use `sample_records_count` to limit context size
- Use lower-cost models for development (e.g., `gpt-3.5-turbo`)
- Enable LLM generation only for production assets

### 4. Rate Limiting
Be aware of provider rate limits:
- OpenAI: Varies by tier
- Anthropic: Varies by plan
- Bedrock: AWS service quotas

## Cost Estimation

### OpenAI GPT-4
- **Input**: ~$0.03 per 1K tokens
- **Output**: ~$0.06 per 1K tokens
- **Typical cost per job**: $0.01-0.05

### Anthropic Claude 3 Sonnet
- **Input**: ~$0.003 per 1K tokens
- **Output**: ~$0.015 per 1K tokens
- **Typical cost per job**: $0.001-0.01

### AWS Bedrock
- **Varies by model**: Check [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)

## Troubleshooting

### Issue: "LLM provider requires api_key"
**Solution**: Set the API key environment variable:
```bash
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

### Issue: "Failed to parse LLM response as JSON"
**Solution**: 
- Check LLM model compatibility
- Try increasing `max_tokens`
- Try adjusting `temperature` (lower = more deterministic)

### Issue: "OpenAI package not installed"
**Solution**: Install required packages:
```bash
pip install openai      # For OpenAI/Azure
pip install anthropic   # For Anthropic
pip install boto3       # For AWS Bedrock
```

### Issue: High API costs
**Solution**:
- Reduce `sample_records_count`
- Use lower-cost models (gpt-3.5-turbo, claude-3-haiku)
- Enable LLM generation selectively

## Integration with Data Catalog

The generated metadata can be consumed by downstream systems:

### 1. OpenMetadata
Export enriched asset definitions to OpenMetadata for catalog integration.

### 2. AWS Glue Data Catalog
Use LLM-generated descriptions and tags for Glue table metadata.

### 3. Databricks Unity Catalog
Import semantic tags and quality expectations.

### 4. Custom Catalogs
Parse the `llm_metadata` section from enriched YAML files.

## Performance Considerations

### Generation Time
- LLM API calls add 2-10 seconds per job
- Runs asynchronously after data ingestion
- Does not block data writing or commit

### When to Enable
- ✓ New data sources requiring documentation
- ✓ Production assets needing governance metadata
- ✓ Data products with multiple consumers
- ✗ Frequently-updated transient tables
- ✗ Development/test environments

## Roadmap

Future enhancements planned:
- [ ] Batch metadata generation across multiple assets
- [ ] Integration with vector databases for semantic search
- [ ] Custom prompt templates for domain-specific metadata
- [ ] Metadata version history and tracking
- [ ] Multi-language support for descriptions

## References

- [Intelligence Lake Architecture (DZone)](https://dzone.com/articles/intelligence-lake-iceberg-generative-ai-aws)
- [OpenAI API Documentation](https://platform.openai.com/docs)
- [Anthropic Claude Documentation](https://docs.anthropic.com/)
- [AWS Bedrock Documentation](https://docs.aws.amazon.com/bedrock/)

## Support

For issues or questions:
1. Check this documentation
2. Review example configurations in `docs/examples/jobs/acme/`
3. Check logs for `llm_generation_*` events
4. File an issue with LLM provider details and error messages
