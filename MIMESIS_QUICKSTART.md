# Mimesis Connector - Quick Start

Generate realistic synthetic data in 3 simple steps.

## Installation

```bash
pip install mimesis>=11.0.0
```

Or install the full project:

```bash
pip install -e .
```

## Quick Start (30 seconds)

### 1. Run the Example

```bash
python -m dativo_ingest.cli execute examples/jobs/mimesis_customers.yaml
```

This generates 10,000 synthetic customer records with realistic names, emails, dates, and balances.

### 2. Check the Output

Find your generated data in the configured S3/MinIO bucket as Parquet files.

That's it! 🎉

## How It Works

### Your Schema Defines the Data

```yaml
# Asset definition
schema:
  - name: customer_id
    type: integer
    required: true
  - name: email
    type: string
    required: true
  - name: signup_date
    type: date
    required: true
```

### Generated Data Looks Real

```json
{
  "customer_id": 1,
  "email": "anthony.reilly@example.com",
  "signup_date": "2024-03-15",
  "ingest_date": "2024-12-10"
}
```

## Common Configurations

### Generate 1,000 Test Records

```yaml
source:
  engine:
    options:
      row_count: 1000
```

### Generate Reproducible Data

```yaml
source:
  engine:
    options:
      row_count: 1000
      seed: 42  # Same seed = same data every time
```

### Generate French Data

```yaml
source:
  engine:
    options:
      row_count: 1000
      locale: "fr"  # French names, addresses, etc.
```

### Generate 1 Million Rows (Performance Test)

```bash
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml
```

## Smart Field Mapping

The connector automatically generates appropriate data based on field names:

| Field Name → Generated Data |
|-----------------------------|
| `customer_id` → 1, 2, 3, 4... |
| `email` → realistic emails |
| `name` → full names |
| `phone_number` → phone numbers |
| `city` → city names |
| `signup_date` → dates |
| `salary` → dollar amounts |

**20+ patterns supported!** See [full docs](docs/connectors/mimesis.md) for complete list.

## Create Your Own

### 1. Define Your Schema

Create an asset YAML with your desired fields:

```yaml
# my_asset.yaml
schema:
  - name: id
    type: integer
    required: true
  - name: name
    type: string
    required: true
  - name: created_at
    type: timestamp
    required: true
```

### 2. Create Job Config

```yaml
# my_job.yaml
source_connector: mimesis
source_connector_path: connectors/examples/mimesis.yaml
asset_path: path/to/my_asset.yaml

source:
  type: mimesis
  engine:
    options:
      row_count: 5000

target:
  # Your target configuration...
```

### 3. Run It

```bash
python -m dativo_ingest.cli execute my_job.yaml
```

## Configuration Options

Common options in `source.engine.options`:

```yaml
row_count: 1000        # How many rows
batch_size: 10000      # Batch size for memory efficiency
locale: "en"           # Data locale (en, es, fr, de, etc.)
seed: 42               # For reproducible data
null_probability: 0.1  # 10% nulls for optional fields
```

Advanced numeric controls:

```yaml
integer_start: 1       # Min for integer fields
integer_end: 100000    # Max for integer fields
float_start: 0.0       # Min for float fields
float_end: 10000.0     # Max for float fields
float_precision: 2     # Decimal places
```

## Examples

All examples in the repository:

```bash
# Customers (10k rows)
python -m dativo_ingest.cli execute examples/jobs/mimesis_customers.yaml

# Test data (1k rows)
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_customers_to_iceberg.yaml

# Performance test (1M rows)
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml
```

## Troubleshooting

### Error: "mimesis is required"

**Solution:**
```bash
pip install mimesis>=11.0.0
```

### Error: "Asset path is required"

**Solution:** Add `asset_path` to your job config:
```yaml
asset_path: tests/fixtures/assets/mimesis/v1.0/customers.yaml
```

### Data doesn't look realistic

**Solution:** Use field names that match the patterns (e.g., `email` not `email_address`). See [field mapping table](docs/connectors/mimesis.md#field-mapping).

## Next Steps

1. ✅ Read [full documentation](docs/connectors/mimesis.md)
2. ✅ Review [example configs](examples/jobs/)
3. ✅ Create your own asset schema
4. ✅ Generate synthetic data!

## Resources

- **Full Documentation**: [docs/connectors/mimesis.md](docs/connectors/mimesis.md)
- **Example Jobs**: [examples/jobs/](examples/jobs/)
- **Example Assets**: [tests/fixtures/assets/mimesis/](tests/fixtures/assets/mimesis/)
- **Mimesis Library**: https://mimesis.name/

---

**Happy synthetic data generation! 🎉**
