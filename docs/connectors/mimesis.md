# Mimesis Connector

The Mimesis connector generates realistic synthetic data conforming to a provided asset definition schema. It is useful for:

- **Performance testing**: Generate large datasets for benchmarking
- **Development & demos**: Create sample data without external dependencies
- **Testing**: Generate test fixtures with realistic-looking data
- **Offline development**: Work without network access or external data sources

## Overview

The Mimesis connector uses the [Mimesis](https://github.com/lk-geimfari/mimesis) library to generate synthetic data that matches your asset definition schema. It automatically maps field types and names to appropriate generators (e.g., `email` → email addresses, `age` → age values, `salary` → salary ranges).

### Key Features

- **Fully offline**: No external services or network I/O required
- **Deterministic**: Reproducible output when `seed` is provided
- **Configurable**: Rich set of engine options for customization
- **Schema-aware**: Automatically handles `ingest_date` and respects field types
- **Batch generation**: Efficient memory usage for large datasets

## Configuration

### Basic Configuration

```yaml
source:
  type: mimesis
  object: customers
  engine:
    type: native
    options:
      native:
        row_count: 1000  # Number of rows to generate
```

### Engine Options

All options are specified under `source.engine.options.native`:

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `row_count` | int | 1000 | Total number of rows to generate |
| `batch_size` | int | 10,000 | Number of rows per batch |
| `locale` | string | "en" | Locale for data generation (en, ru, de, es, fr, it, ja, ko, pl, pt, zh) |
| `seed` | int/string | null | Seed for reproducible generation |
| `null_probability` | float | 0.1 | Probability of None for optional fields (0.0-1.0) |
| `integer_start` | int | 1 | Start range for integer fields |
| `integer_end` | int | 1,000,000 | End range for integer fields |
| `float_start` | float | 0.0 | Start range for float fields |
| `float_end` | float | 10,000.0 | End range for float fields |
| `float_precision` | int | 2 | Decimal precision for float fields |

### Example Configuration

```yaml
source:
  type: mimesis
  object: customers
  engine:
    type: native
    options:
      native:
        row_count: 5000
        batch_size: 1000
        locale: "en"
        seed: 42  # For reproducible output
        null_probability: 0.15
        integer_start: 1
        integer_end: 1000000
        float_start: 0.0
        float_end: 10000.0
        float_precision: 2
```

## Field Mapping

The connector automatically maps field types and names to appropriate generators:

### Integer Fields

- `*id*` → Sequential incrementing IDs
- `*age*` → Age values (18-80)
- `*salary*` → Salary values (30,000-200,000)
- Other → Random integers in configured range

### Float/Double Fields

- `*salary*`, `*amount*`, `*balance*` → Monetary values (0-100,000, 2 decimals)
- `*commission*`, `*pct*`, `*percentage*` → Percentage values (0-1, 4 decimals)
- Other → Random floats in configured range with specified precision

### String Fields

- `*email*` → Email addresses
- `*first_name*` → First names
- `*last_name*` → Last names
- `*full_name*`, `*name*` → Full names
- `*company*` → Company names
- `*job*`, `*role*`, `*title*` → Job titles/occupations
- `*department*` → Department names
- `*status*` → Status values (active/inactive/pending)
- `*phone*`, `*mobile*`, `*telephone*` → Phone numbers
- `*street*`, `*address*` → Street addresses
- `*city*` → City names
- `*state*`, `*province*` → State/province names
- `*country*` → Country names
- `*zip*`, `*postal*` → ZIP/postal codes
- Other → Random words

### Date/Time Fields

- `date` → ISO date strings (YYYY-MM-DD)
- `timestamp`, `datetime` → ISO datetime strings with timezone

### Boolean Fields

- `boolean` → True/False values

## Ingest Date

The `ingest_date` column is automatically added to all generated records:

- **Always present**: Even if not defined in the schema
- **Type-aware**: Respects schema type if defined:
  - `type: date` → Python `date` object
  - `type: string` → ISO date string (YYYY-MM-DD)
  - `type: timestamp`/`datetime` → ISO datetime string with UTC timezone
- **UTC-based**: Always uses current UTC date

## Example Asset Definition

```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: mimesis_customers
version: "1.0"
source_type: mimesis
object: customers

schema:
  - name: customer_id
    type: integer
    required: true
  - name: email
    type: string
    required: true
  - name: first_name
    type: string
    required: true
  - name: last_name
    type: string
    required: true
  - name: age
    type: integer
    required: false
  - name: signup_date
    type: date
    required: true
  - name: account_balance
    type: double
    required: false

target:
  file_format: parquet
  partitioning: [ingest_date]

team:
  owner: data-engineering@example.com

compliance:
  classification: []
```

## Complete Job Configuration

```yaml
tenant_id: acme
environment: dev

source_connector: mimesis
source_connector_path: connectors/examples/mimesis.yaml

target_connector: iceberg
target_connector_path: connectors/examples/iceberg.yaml

asset: mimesis_customers
asset_path: configs/assets/mimesis_customers.yaml

source:
  type: mimesis
  object: customers
  engine:
    type: native
    options:
      native:
        row_count: 1000
        batch_size: 10000
        locale: "en"
        seed: 42
        null_probability: 0.1

target:
  type: iceberg
  connection:
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: "${S3_BUCKET}"
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      region: "${AWS_REGION}"
      path_style_access: true
  catalog: nessie
  branch: main
  partitioning: [ingest_date]

schema_validation_mode: warn

logging:
  redaction: false
  level: INFO
```

## Deterministic Generation

To generate reproducible data, set a `seed`:

```yaml
source:
  type: mimesis
  engine:
    options:
      native:
        seed: 42  # Same seed = same output
```

With the same seed and configuration, the connector will produce identical output across runs. This is useful for:
- Testing: Consistent test fixtures
- Debugging: Reproducible data for troubleshooting
- Documentation: Stable examples

## Optional Fields and Nullability

Fields marked as `required: false` in the schema may be `None` based on `null_probability`:

```yaml
schema:
  - name: optional_field
    type: string
    required: false  # May be None
```

The `null_probability` option controls the likelihood of `None` values:
- `0.0` → Never null (all optional fields have values)
- `1.0` → Always null (all optional fields are None)
- `0.1` → 10% chance of None (default)

## Connector Type

- **Type**: `mimesis`

Use `type: mimesis` in your source configuration. The `synthetic` type is not supported and will fail validation.

## Troubleshooting

### Common Issues

**Issue**: `ValueError: row_count must be >= 0`
- **Solution**: Ensure `row_count` is a non-negative integer

**Issue**: `ValueError: batch_size must be > 0`
- **Solution**: Ensure `batch_size` is a positive integer

**Issue**: `ValueError: null_probability must be between 0.0 and 1.0`
- **Solution**: Ensure `null_probability` is between 0.0 and 1.0

**Issue**: `ValueError: Mimesis connector requires asset_definition`
- **Solution**: Ensure the asset definition is loaded before initializing the extractor (this should be automatic in normal job execution)

**Issue**: Different output with same seed
- **Solution**: Ensure all configuration options are identical, including `row_count`, `batch_size`, `locale`, and field definitions

### Debugging Row Count / Batch Size

- **Large `row_count`**: Use appropriate `batch_size` to avoid memory issues (default 10,000 is usually fine)
- **Small batches**: If you see many small batches, check that `batch_size` is reasonable relative to `row_count`
- **No output**: Check that `row_count > 0` (row_count=0 yields no batches)

## Performance Considerations

- **Batch generation**: Data is generated in batches to avoid memory issues
- **Large datasets**: For millions of rows, consider:
  - Increasing `batch_size` (within memory limits)
  - Using appropriate `row_count` for your use case
  - Writing directly to Parquet (more efficient than CSV)

## See Also

- [Connector Examples](../../connectors/examples/mimesis.yaml)
- [Job Configuration Examples](../../configs/jobs/mimesis.yaml)
- [Performance Test Configuration](../../configs/jobs/mimesis_perf_test.yaml)
