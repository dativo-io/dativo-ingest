# Mimesis Synthetic Data Connector - Quick Start Guide

## What is this?

The Mimesis connector generates **realistic synthetic data** for testing, development, and demonstrations. It creates human-readable names, emails, addresses, and more based on your asset schema definitions.

## Installation

The Mimesis library is already added to `requirements.txt`. To install:

```bash
pip install mimesis>=11.0.0
```

Or if you're installing the full project:

```bash
pip install -e .
```

## 30-Second Quick Start

1. **Use the example job** (generates 10,000 synthetic customers):

```bash
python -m dativo_ingest.cli execute examples/jobs/mimesis_customers.yaml
```

2. **Check the output** in your configured S3/MinIO bucket

That's it! 🎉

## How It Works

### 1. Define Your Schema (Asset Definition)

```yaml
# tests/fixtures/assets/mimesis/v1.0/customers.yaml
schema:
  - name: customer_id
    type: integer
    required: true
  - name: name
    type: string
    required: true
  - name: email
    type: string
    required: true
  - name: signup_date
    type: date
    required: true
  - name: account_balance
    type: double
    required: true
```

### 2. Create a Job Config

```yaml
# examples/jobs/mimesis_customers.yaml
source_connector: mimesis
source_connector_path: connectors/examples/mimesis.yaml
asset_path: tests/fixtures/assets/mimesis/v1.0/customers.yaml

source:
  type: mimesis
  engine:
    options:
      row_count: 10000   # How many rows to generate
      seed: 42           # Optional: for reproducible data
```

### 3. Run the Job

```bash
python -m dativo_ingest.cli execute examples/jobs/mimesis_customers.yaml
```

### 4. Get Realistic Data

```json
{
  "customer_id": 1,
  "name": "Anthony Reilly",
  "email": "any1925@gmail.com",
  "signup_date": "2025-02-01",
  "account_balance": 63942.68
}
```

## Common Use Cases

### Use Case 1: Generate 1,000 Test Records

```yaml
source:
  engine:
    options:
      row_count: 1000
```

### Use Case 2: Generate Reproducible Data (Same Every Time)

```yaml
source:
  engine:
    options:
      row_count: 1000
      seed: 42  # Same seed = same data
```

### Use Case 3: Generate 1 Million Rows for Performance Testing

```bash
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml
```

### Use Case 4: Generate International Data (French Names, Addresses)

```yaml
source:
  engine:
    options:
      row_count: 1000
      locale: "fr"  # French locale
```

Available locales: `en`, `es`, `fr`, `de`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`, and [many more](https://mimesis.name/en/master/locales.html)

## Smart Field Mapping

The connector automatically generates appropriate data based on field names and types:

| Field Name | Generated Data |
|------------|----------------|
| `customer_id` | 1, 2, 3, 4, ... (sequential) |
| `email` | `john.doe@example.com` (realistic emails) |
| `name` | `John Smith` (realistic names) |
| `phone_number` | `+1-555-123-4567` (phone numbers) |
| `city` | `New York` (real city names) |
| `country` | `United States` (real countries) |
| `company` | `Acme Corporation` (company names) |
| `signup_date` | Random dates between 2015-2025 |
| `salary` | Random amounts (30,000 - 200,000) |
| `age` | Random ages (18-65) |

**And 10+ more patterns!** See full list in `docs/connectors/mimesis.md`

## Example Schemas

### Customer Data

```yaml
schema:
  - name: customer_id
    type: integer
    required: true
  - name: first_name
    type: string
    required: true
  - name: last_name
    type: string
    required: true
  - name: email
    type: string
    required: true
  - name: phone_number
    type: string
    required: false  # 10% will be null
  - name: city
    type: string
    required: true
  - name: country
    type: string
    required: true
  - name: signup_date
    type: date
    required: true
  - name: account_balance
    type: double
    required: true
```

### Employee Data

```yaml
schema:
  - name: employee_id
    type: integer
    required: true
  - name: name
    type: string
    required: true
  - name: email
    type: string
    required: true
  - name: department
    type: string
    required: true
  - name: job
    type: string
    required: true
  - name: salary
    type: integer
    required: true
  - name: hire_date
    type: date
    required: true
```

## Testing

Run the test suite:

```bash
pytest tests/test_mimesis_connector.py -v
```

Expected output:
```
9 passed in 0.32s
```

## Troubleshooting

### Problem: "mimesis is required for synthetic data generation"

**Solution**: Install mimesis
```bash
pip install mimesis>=11.0.0
```

### Problem: "Asset path is required"

**Solution**: Make sure your job config includes `asset_path`:
```yaml
asset_path: tests/fixtures/assets/mimesis/v1.0/customers.yaml
```

### Problem: "Asset definition not found"

**Solution**: Check the path to your asset YAML file exists

### Problem: Data looks unrealistic

**Solution**: Adjust field names to match patterns (e.g., use `email` not `email_address`)

## Advanced Configuration

### Custom Batch Size

```yaml
source:
  engine:
    options:
      row_count: 100000
      batch_size: 10000  # Process in 10k batches
```

### Multiple Locales (Not Supported Yet)

Currently, one locale per job. For multi-locale data, run multiple jobs.

## Migration from Legacy Scripts

**Before** (deprecated):
```bash
python tests/scripts/generate_perf_test_data.py --size-gb 1.0
```

**After** (recommended):
```bash
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml
```

## Next Steps

1. ✅ Read full documentation: `docs/connectors/mimesis.md`
2. ✅ Try the example: `examples/jobs/mimesis_customers.yaml`
3. ✅ Create your own asset schema
4. ✅ Run your first synthetic data job
5. ✅ Schedule recurring generation (optional): See `configs/runner.yaml`

## Resources

- **Full Documentation**: `docs/connectors/mimesis.md`
- **Example Jobs**: `examples/jobs/mimesis_customers.yaml`
- **Example Assets**: `tests/fixtures/assets/mimesis/v1.0/`
- **Test Suite**: `tests/test_mimesis_connector.py`
- **Mimesis Library**: https://mimesis.name/

## Support

For issues or questions:
1. Check the full documentation in `docs/connectors/mimesis.md`
2. Review test examples in `tests/test_mimesis_connector.py`
3. See implementation summary in `MIMESIS_IMPLEMENTATION_SUMMARY.md`

---

**Happy synthetic data generation! 🎉**
