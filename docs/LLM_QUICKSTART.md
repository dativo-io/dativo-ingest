# LLM Metadata Generation - Quick Start

Get started with LLM-based metadata generation in under 5 minutes.

## 1. Install LLM Dependencies

```bash
pip install -r requirements-llm.txt
```

This installs:
- `openai` (for OpenAI and Azure OpenAI)
- `anthropic` (for Anthropic Claude)
- `boto3` is already included (for AWS Bedrock)

## 2. Set API Key

Choose your LLM provider and set the API key:

```bash
# OpenAI
export OPENAI_API_KEY="sk-..."

# Anthropic
export ANTHROPIC_API_KEY="sk-ant-..."

# AWS Bedrock (uses AWS credentials)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_REGION="us-east-1"
```

## 3. Update Job Configuration

Add the `llm` section to your job YAML:

```yaml
# Minimal configuration
llm:
  enabled: true
  provider: openai
  model: gpt-4
  api_key: "${OPENAI_API_KEY}"
```

## 4. Run Job

```bash
dativo_ingest run --config /path/to/job.yaml --mode self_hosted
```

## 5. View Results

Enriched metadata is saved to:
```
.local/llm_metadata/{tenant_id}/{asset_name}_enriched.yaml
```

## Example Output

```yaml
# Original asset
name: stripe_customers
schema:
  - name: id
    type: string
  - name: email
    type: string

# After LLM enrichment
description:
  purpose: "Customer records from Stripe containing payment information..."
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

target:
  llm_metadata:
    generated_at: "2025-11-18T10:30:00Z"
    provider: openai
    model: gpt-4
    semantic_tags: [payments, customer-data, pii, revenue]
    sample_queries:
      - "What is the monthly customer churn rate?"
      - "Which customers have the highest lifetime value?"
    sensitive_fields: [email, phone, address]
    optimization_suggestions: "Partition by customer_created_date for efficient time-range queries"
```

## Provider-Specific Examples

### OpenAI (GPT-4)

```yaml
llm:
  enabled: true
  provider: openai
  model: gpt-4  # or gpt-3.5-turbo for lower cost
  api_key: "${OPENAI_API_KEY}"
  temperature: 0.3
  sample_records_count: 3
```

**Cost:** ~$0.01-0.05 per job

### Anthropic (Claude 3)

```yaml
llm:
  enabled: true
  provider: anthropic
  model: claude-3-sonnet-20240229  # or claude-3-opus for higher quality
  api_key: "${ANTHROPIC_API_KEY}"
  temperature: 0.3
```

**Cost:** ~$0.001-0.01 per job

### AWS Bedrock

```yaml
llm:
  enabled: true
  provider: bedrock
  model: anthropic.claude-3-sonnet-20240229-v1:0
  # Uses AWS credentials from environment
  temperature: 0.3
```

**Cost:** See [AWS Bedrock Pricing](https://aws.amazon.com/bedrock/pricing/)

### Azure OpenAI

```yaml
llm:
  enabled: true
  provider: azure
  model: gpt-4  # Your deployment name
  api_key: "${AZURE_OPENAI_API_KEY}"
  endpoint: "https://your-resource.openai.azure.com/"
```

## Complete Example

See `docs/examples/jobs/acme/stripe_customers_to_iceberg_with_llm.yaml` for a complete working example.

## Next Steps

- Read full documentation: [docs/LLM_METADATA_GENERATION.md](LLM_METADATA_GENERATION.md)
- Try different models and compare results
- Integrate enriched metadata with your data catalog
- Set up cost monitoring for LLM API usage

## Troubleshooting

### "LLM provider requires api_key"
Set the environment variable:
```bash
export OPENAI_API_KEY="sk-..."
```

### "OpenAI package not installed"
Install LLM dependencies:
```bash
pip install -r requirements-llm.txt
```

### High API costs
- Reduce `sample_records_count` (default: 3)
- Use lower-cost models (gpt-3.5-turbo, claude-3-haiku)
- Enable LLM only for important production assets

## Support

For detailed documentation, see:
- [LLM_METADATA_GENERATION.md](LLM_METADATA_GENERATION.md) - Full documentation
- [../examples/jobs/acme/](../examples/jobs/acme/) - Example configurations
