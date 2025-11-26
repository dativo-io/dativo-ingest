# OpenMetadata Integration Tests

This directory contains integration tests for the OpenMetadata catalog integration.

## Prerequisites

- Docker and Docker Compose installed
- Python 3.10+ with test dependencies

## Running Tests

### 1. Start OpenMetadata

Start the OpenMetadata stack using Docker Compose:

```bash
cd tests/integration
docker-compose -f docker-compose-openmetadata.yml up -d
```

Wait for all services to be healthy (this can take 1-2 minutes):

```bash
# Check service health
docker-compose -f docker-compose-openmetadata.yml ps

# Wait for OpenMetadata to be ready
curl http://localhost:8585/api/v1/system/version
```

### 2. Run Tests

Run the OpenMetadata smoke tests:

```bash
# From workspace root
export RUN_OPENMETADATA_TESTS=1
export OPENMETADATA_HOST_PORT=http://localhost:8585/api

pytest tests/integration/test_openmetadata_smoke.py -v
```

### 3. Stop Services

When done, stop the OpenMetadata stack:

```bash
cd tests/integration
docker-compose -f docker-compose-openmetadata.yml down
```

To also remove volumes:

```bash
docker-compose -f docker-compose-openmetadata.yml down -v
```

## Accessing OpenMetadata UI

The OpenMetadata UI is available at: http://localhost:8080

## Architecture

The test setup includes:

- **PostgreSQL**: Metadata storage backend
- **Elasticsearch**: Search and indexing
- **OpenMetadata Server**: Core API server (port 8585)
- **OpenMetadata UI**: Web interface (port 8080)

## Test Coverage

The integration tests cover:

1. **Basic connectivity**: Verify connection to OpenMetadata API
2. **Entity creation**: Create database service, database, schema, and tables
3. **Lineage push**: Push lineage information with metadata
4. **Tags and owners**: Verify governance metadata propagation
5. **Idempotency**: Ensure repeated pushes don't create duplicates

## Troubleshooting

### Services not starting

Check logs for specific services:

```bash
docker-compose -f docker-compose-openmetadata.yml logs postgresql
docker-compose -f docker-compose-openmetadata.yml logs elasticsearch
docker-compose -f docker-compose-openmetadata.yml logs openmetadata-server
```

### Connection refused

Ensure all services are healthy:

```bash
docker-compose -f docker-compose-openmetadata.yml ps
```

All services should show "healthy" status.

### Elasticsearch memory issues

If Elasticsearch fails to start due to memory, increase Docker memory allocation or reduce Elasticsearch heap size in docker-compose-openmetadata.yml:

```yaml
environment:
  - ES_JAVA_OPTS=-Xms256m -Xmx256m
```

## Quick Test Script

Use the provided script to run all tests:

```bash
./tests/integration/run_openmetadata_tests.sh
```

This script will:
1. Start OpenMetadata services
2. Wait for services to be ready
3. Run integration tests
4. Stop services and cleanup
