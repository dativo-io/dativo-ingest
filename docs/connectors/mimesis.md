# Mimesis Synthetic Data Connector

Generate realistic synthetic data for testing, development, and demonstrations using the [Mimesis](https://github.com/lk-geimfari/mimesis) library.

## Overview

The Mimesis connector creates schema-driven synthetic data that automatically matches your asset definitions. It's ideal for:

- **Testing & Development**: Generate realistic test data without exposing production data
- **Performance Benchmarking**: Create large datasets for performance testing
- **Demonstrations & Training**: Populate demos with human-readable synthetic data
- **Data Privacy**: Replace sensitive data with realistic synthetic alternatives

## Quick Start

### 1. Define Your Schema

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

### 2. Create Job Configuration

```yaml
# examples/jobs/mimesis_customers.yaml
source_connector: mimesis
source_connector_path: connectors/examples/mimesis.yaml
asset_path: tests/fixtures/assets/mimesis/v1.0/customers.yaml

source:
  type: mimesis
  engine:
    options:
      row_count: 10000
      seed: 42  # Optional: for reproducible data
```

### 3. Run the Job

```bash
python -m dativo_ingest.cli execute examples/jobs/mimesis_customers.yaml
```

## Configuration Options

### Engine Options

All options go in `source.engine.options`:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `row_count` | int | 1000 | Number of rows to generate |
| `batch_size` | int | 10000 | Rows per batch (memory efficiency) |
| `locale` | string | "en" | Data locale (en, es, fr, de, etc.) |
| `seed` | int | null | Random seed for reproducibility |
| `integer_start` | int | 1 | Min value for integer fields |
| `integer_end` | int | 100000 | Max value for integer fields |
| `float_start` | float | 0.0 | Min value for float fields |
| `float_end` | float | 10000.0 | Max value for float fields |
| `float_precision` | int | 2 | Decimal places for floats |
| `null_probability` | float | 0.1 | Probability of null for optional fields |

### Example Configuration

```yaml
source:
  type: mimesis
  engine:
    options:
      row_count: 100000      # Generate 100k rows
      batch_size: 10000      # Process in 10k batches
      locale: "fr"           # French locale
      seed: 42               # Reproducible data
      integer_start: 1000    # IDs start at 1000
      float_precision: 3     # 3 decimal places
      null_probability: 0.2  # 20% nulls for optional fields
```

## Field Mapping

The connector intelligently maps field names and types to appropriate generators:

### Integer Fields

| Pattern | Generated Data | Example |
|---------|---------------|---------|
| `*_id` | Sequential (1, 2, 3...) | `customer_id: 1` |
| `age` | Ages 18-65 | `age: 42` |
| `salary` | 30,000-200,000 | `salary: 75000` |
| Other | Configurable range | `quantity: 523` |

### String Fields

| Pattern | Generated Data | Example |
|---------|---------------|---------|
| `email` | Email addresses | `john.doe@example.com` |
| `phone*` | Phone numbers | `+1-555-123-4567` |
| `name` | Full names | `Jane Smith` |
| `first_name` | First names | `John` |
| `last_name` | Last names | `Doe` |
| `company` | Company names | `Acme Corporation` |
| `city` | City names | `New York` |
| `country` | Countries | `United States` |
| `address` | Street addresses | `123 Main St` |
| `department` | Departments | `Engineering` |
| `status` | Status values | `active` |

### Numeric Fields (double/float)

| Pattern | Generated Data |
|---------|---------------|
| `salary`, `balance`, `amount` | 0-100,000 |
| `commission`, `pct`, `percentage` | 0-1.0 |
| Other | Configurable range |

### Date & Timestamp

| Type | Generated Data |
|------|---------------|
| `date` | Random dates 2015-2025 |
| `timestamp` | Random timestamps 2015-2025 |

## Special Features

### Automatic ingest_date

All records automatically include an `ingest_date` field:

```python
# If schema defines ingest_date with type 'date'
{"ingest_date": date(2024, 12, 10)}

# If schema defines ingest_date with type 'string'  
{"ingest_date": "2024-12-10"}

# If not defined in schema (default)
{"ingest_date": date(2024, 12, 10)}
```

### Nullable Fields

Fields with `required: false` get null values based on `null_probability`:

```yaml
schema:
  - name: phone_number
    type: string
    required: false  # Will be null ~10% of the time
```

### Reproducible Data

Use `seed` for deterministic generation:

```yaml
source:
  engine:
    options:
      seed: 42  # Same seed = same data every time
```

## Common Use Cases

### Performance Testing

```yaml
# tests/fixtures/jobs/mimesis_perf_test.yaml
source:
  engine:
    options:
      row_count: 1000000  # 1 million rows
      batch_size: 10000
      seed: 42
```

### International Data

```yaml
source:
  engine:
    options:
      locale: "fr"  # French names, addresses, phone numbers
```

Available locales: `en`, `es`, `fr`, `de`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`, [and more](https://mimesis.name/en/master/locales.html)

### Reproducible Demos

```yaml
source:
  engine:
    options:
      row_count: 1000
      seed: 12345  # Always same demo data
```

## Connector Registry

Registered in `registry/connectors.yaml`:

```yaml
mimesis:
  roles: [source]
  category: synthetic
  default_engine: native
  engines_supported: [native]
  allowed_in_cloud: true
  supports_incremental: false
  objects_supported: ["synthetic"]
```

## Limitations

- **Source only**: Cannot be used as a target connector
- **No incremental support**: Generates fresh data each run
- **Schema required**: Must have an asset definition with schema
- **No custom patterns**: Uses built-in field mapping logic

## Testing

Run the test suite:

```bash
pytest tests/test_mimesis_connector.py -v
```

## See Also

- [Mimesis Documentation](https://mimesis.name/)
- [Quick Start Guide](../../MIMESIS_QUICKSTART.md)
- [Asset Definition Schema](../schemas/)
- [Performance Testing Guide](../../tests/PERFORMANCE_TESTS.md)
