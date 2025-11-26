# Data Catalog Integration Tests

This directory contains tests for data catalog integrations.

## Supported Catalogs

- **AWS Glue**: AWS Glue Data Catalog integration
- **Databricks Unity Catalog**: Databricks Unity Catalog integration
- **Nessie**: Nessie catalog integration
- **OpenMetadata**: OpenMetadata catalog integration (recommended for local testing)

## Running Tests

### Unit Tests

Run all catalog unit tests:

```bash
pytest tests/test_catalog.py -v
```

### OpenMetadata Smoke Tests

OpenMetadata smoke tests require a running OpenMetadata instance. You can start one locally using Docker Compose:

```bash
# Start OpenMetadata stack
docker-compose -f docker-compose.openmetadata.yml up -d

# Wait for services to be ready (about 30-60 seconds)
sleep 60

# Run smoke tests
pytest tests/test_catalog_openmetadata_smoke.py -v -m smoke

# Or set environment variables for custom configuration
export OPENMETADATA_API_ENDPOINT=http://localhost:8585/api
export OPENMETADATA_USERNAME=admin
export OPENMETADATA_PASSWORD=admin
pytest tests/test_catalog_openmetadata_smoke.py -v -m smoke
```

### All Catalog Tests

Run all catalog tests (unit + smoke):

```bash
pytest tests/test_catalog*.py -v
```

## Configuration

### OpenMetadata

Default configuration:
- API Endpoint: `http://localhost:8585/api`
- Username: `admin`
- Password: `admin`
- Database Service: `default`

Override with environment variables:
- `OPENMETADATA_API_ENDPOINT`
- `OPENMETADATA_USERNAME`
- `OPENMETADATA_PASSWORD`
- `OPENMETADATA_DATABASE_SERVICE`

### AWS Glue

Requires AWS credentials configured via:
- AWS credentials file (`~/.aws/credentials`)
- Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
- IAM role (if running on EC2)

### Databricks Unity Catalog

Requires:
- `workspace_url`: Databricks workspace URL
- `access_token`: Personal access token or OAuth token

### Nessie

Default configuration:
- URI: `http://localhost:19120/api/v1`
- Branch: `main`

## Test Structure

- `test_catalog.py`: Unit tests for all catalog integrations
- `test_catalog_openmetadata_smoke.py`: Smoke tests for OpenMetadata (requires running instance)

## Adding New Catalog Tests

1. Add unit tests to `test_catalog.py`
2. If the catalog supports local testing, add smoke tests similar to `test_catalog_openmetadata_smoke.py`
3. Update this README with configuration instructions
