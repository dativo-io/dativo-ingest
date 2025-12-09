# Mimesis Synthetic Data Connector

The Mimesis connector generates realistic synthetic data using the [Mimesis](https://github.com/lk-geimfari/mimesis) Python library. This connector is ideal for:

- Testing and development
- Performance benchmarking
- Demonstrations and training
- Data privacy compliance (replacing real data with synthetic data)

## Features

- **Realistic Data**: Generates human-readable names, emails, addresses, dates, and more
- **Schema-Driven**: Uses Dativo asset definitions to determine fields and types
- **Reproducible**: Optional seed parameter for consistent results
- **Flexible**: Configurable row counts and batch sizes
- **Offline**: Runs completely offline with no external dependencies

## Configuration

### Connector Recipe

The connector recipe is located at `connectors/examples/mimesis.yaml`:

```yaml
name: mimesis
type: mimesis
roles: [source]
description: "Mimesis synthetic data generator connector"
default_engine:
  type: native
  options:
    row_count: 1000    # Number of rows to generate
    batch_size: 1000   # Rows per batch
    locale: "en"       # Locale for generated data
    seed: null         # Optional random seed
credentials:
  type: none
incremental:
  strategy: none       # Synthetic data doesn't support incremental
```

### Asset Definition

Define your schema in an asset YAML file. The connector will generate data matching this schema:

```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: mimesis_customers
version: "1.0"
source_type: mimesis
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

See `tests/fixtures/assets/mimesis/v1.0/customers.yaml` for a complete example.

### Job Configuration

Create a job config that references the mimesis connector:

```yaml
tenant_id: demo_tenant
environment: production

source_connector: mimesis
source_connector_path: connectors/examples/mimesis.yaml
target_connector: iceberg
target_connector_path: connectors/examples/iceberg.yaml

asset: mimesis_customers
asset_path: tests/fixtures/assets/mimesis/v1.0/customers.yaml

source:
  type: mimesis
  engine:
    options:
      row_count: 10000    # Generate 10k rows
      batch_size: 1000
      locale: "en"
      seed: 42            # Optional: for reproducible data

target:
  connection:
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: "${S3_BUCKET}"
      # ... other S3 config
```

See `examples/jobs/mimesis_customers.yaml` for a complete example.

## Field Mapping

The connector intelligently maps Dativo field types and names to appropriate Mimesis generators:

### Integer Fields

| Field Name Pattern | Generated Data |
|-------------------|----------------|
| Contains "id" | Sequential incrementing numbers (1, 2, 3, ...) |
| Contains "age" | Random ages between 18-65 |
| Contains "salary" | Random salaries between 30,000-200,000 |
| Other | Random integers between 1-100,000 |

### String Fields

| Field Name Pattern | Generated Data |
|-------------------|----------------|
| Contains "email" | Realistic email addresses |
| Contains "phone" | Phone numbers |
| Contains "first_name" | First names |
| Contains "last_name" | Last names |
| Contains "name" (not company) | Full names |
| Contains "company" | Company names |
| Contains "address" | Street addresses |
| Contains "city" | City names |
| Contains "country" | Country names |
| Contains "state" or "province" | State/province names |
| Contains "zip" or "postal" | ZIP/postal codes |
| Contains "department" | Department names (Engineering, Sales, etc.) |
| Contains "status" | Status values (active, inactive, etc.) |
| Contains "job" | Job titles/occupations |
| Contains "title" | Titles |
| Contains "description" | Sentences |
| Contains "url" or "website" | URLs |
| Other | Random words |

### Numeric Fields (double/float/decimal)

| Field Name Pattern | Generated Data |
|-------------------|----------------|
| Contains "salary", "balance", "amount" | Random floats 0-100,000 (2 decimal places) |
| Contains "commission", "pct", "percentage" | Random floats 0-1 (4 decimal places) |
| Other | Random floats 0-10,000 (2 decimal places) |

### Date and Timestamp Fields

| Type | Generated Data |
|------|----------------|
| `date` | Random dates between 2015-2025 |
| `timestamp` | Random timestamps between 2015-2025 |

### Nullable Fields

Fields with `required: false` have a 10% chance of being `null`.

## Usage Examples

### Generate Test Data

```bash
# Generate synthetic customer data
python -m dativo_ingest.cli execute examples/jobs/mimesis_customers.yaml
```

### Performance Testing

```bash
# Generate 1 million rows for performance testing
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml
```

### Reproducible Data (with seed)

```yaml
source:
  type: mimesis
  engine:
    options:
      row_count: 1000
      seed: 42  # Same seed = same data
```

### Custom Locale

```yaml
source:
  type: mimesis
  engine:
    options:
      row_count: 1000
      locale: "fr"  # French names, addresses, etc.
```

Available locales: `en`, `es`, `fr`, `de`, `it`, `pt`, `ru`, `zh`, `ja`, `ko`, and many more. See [Mimesis documentation](https://mimesis.name/en/master/locales.html) for full list.

## Testing

Run the test suite:

```bash
pytest tests/test_mimesis_connector.py -v
```

## Migration from Legacy Scripts

The Mimesis connector replaces legacy synthetic data generation scripts:

**Before:**
```bash
python tests/scripts/generate_perf_test_data.py --size-gb 1.0
```

**After:**
```bash
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml
```

Benefits of the new approach:
- More realistic data (Mimesis vs. hardcoded patterns)
- Schema-driven (automatically matches your asset definition)
- Consistent with other connectors
- Better logging and monitoring
- Reproducible with seeds

## Limitations

1. **No Incremental Support**: Synthetic data generation doesn't support incremental extraction
2. **No Custom Reader**: Mimesis is a native connector only
3. **Schema Required**: Must have an asset definition with schema
4. **Target Required**: Data must be written somewhere (typically Iceberg/Parquet or CSV)

## See Also

- [Mimesis Documentation](https://mimesis.name/)
- [Asset Definition Schema](../schemas/)
- [Job Configuration Guide](../job-config.md)
- [Performance Testing Guide](../../tests/PERFORMANCE_TESTS.md)
