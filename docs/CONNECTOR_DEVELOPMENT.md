# Connector Development Guide

This guide explains how to develop new connectors for Dativo Ingestion Platform.

## Who Should Read This?

- Developers adding support for new data sources or targets
- Contributors extending connector capabilities
- Teams building custom integrations

## Prerequisites

- Understanding of Dativo's architecture (see [README.md](../README.md))
- Familiarity with Python
- Knowledge of the data source/target API or protocol
- Understanding of YAML configuration structure

## Connector Types

Dativo supports two types of connectors:

1. **Built-in Connectors**: Native Python implementations (e.g., CSV, Postgres)
2. **Engine-based Connectors**: Wrappers around external tools (e.g., Airbyte, Meltano)

This guide focuses on **built-in connectors**. For engine-based connectors, see the engine framework documentation.

## Directory Structure

```
connectors/
  {connector_name}.yaml          # Connector recipe
registry/
  connectors.yaml                # Registry entry
src/dativo_ingest/connectors/
  {connector_name}_extractor.py  # Source connector implementation
  {connector_name}_writer.py     # Target connector implementation (if applicable)
```

## Step-by-Step: Creating a New Connector

### 1. Create Connector Recipe

Create `connectors/my_connector.yaml`:

```yaml
name: my_connector
type: source  # or "target" or "source,target"
description: "My custom connector"
engine:
  type: native  # or "airbyte", "meltano", "singer"
  version: "1.0.0"
modes:
  - self_hosted
  # - cloud  # if supported
incremental:
  strategies:
    - timestamp
    - cursor
  # - id  # if supported
```

### 2. Register in Connector Registry

Add entry to `registry/connectors.yaml`:

```yaml
my_connector:
  name: my_connector
  type: source
  engine:
    type: native
  modes:
    - self_hosted
  incremental:
    strategies:
      - timestamp
```

### 3. Implement Extractor (Source Connector)

Create `src/dativo_ingest/connectors/my_connector_extractor.py`:

```python
from typing import Any, Dict, Iterator, List, Optional
from dativo_ingest.config import SourceConfig
from dativo_ingest.state import IncrementalStateManager
from dativo_ingest.logging import get_logger

logger = get_logger(__name__)


class MyConnectorExtractor:
    """Extractor for My Connector."""
    
    def __init__(
        self,
        source_config: SourceConfig,
        state_manager: Optional[IncrementalStateManager] = None,
    ):
        self.source_config = source_config
        self.state_manager = state_manager
        self.connection = source_config.connection
        
    def extract(self) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from source.
        
        Yields:
            Batches of records as lists of dictionaries
        """
        # 1. Initialize connection
        # 2. Determine sync strategy (full vs incremental)
        # 3. Fetch data in batches
        # 4. Yield batches
        
        # Example:
        batch = []
        for record in self._fetch_records():
            batch.append(record)
            if len(batch) >= 1000:  # Batch size
                yield batch
                batch = []
        
        if batch:
            yield batch
    
    def _fetch_records(self) -> Iterator[Dict[str, Any]]:
        """Fetch records from source API/database."""
        # Implementation here
        pass
    
    def check_connection(self) -> Dict[str, Any]:
        """Check connection to source.
        
        Returns:
            Dict with 'success' (bool) and 'message' (str)
        """
        try:
            # Test connection
            return {"success": True, "message": "Connection successful"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def discover(self) -> Dict[str, Any]:
        """Discover available objects/streams.
        
        Returns:
            Dict with 'objects' (list) and metadata
        """
        # List available tables/streams
        return {
            "objects": [
                {
                    "name": "table1",
                    "type": "table",
                    "schema": {...}
                }
            ]
        }
```

### 4. Integrate with CLI

Update `src/dativo_ingest/cli.py` to handle your connector:

```python
# In the run_command function, add connector mapping:
from .connectors.my_connector_extractor import MyConnectorExtractor

CONNECTOR_EXTRACTORS = {
    "my_connector": MyConnectorExtractor,
    # ... other connectors
}
```

### 5. Create Asset Schema (Optional)

If your connector needs custom schema definitions, create:

```
assets/my_connector/v1.0/
  object1.yaml
  object2.yaml
```

See [MINIMAL_ASSET_EXAMPLE.md](MINIMAL_ASSET_EXAMPLE.md) for asset schema format.

### 6. Add Tests

Create `tests/test_my_connector.py`:

```python
import pytest
from dativo_ingest.connectors.my_connector_extractor import MyConnectorExtractor
from dativo_ingest.config import SourceConfig

def test_extractor_initialization():
    config = SourceConfig(...)
    extractor = MyConnectorExtractor(config)
    assert extractor is not None

def test_connection_check():
    config = SourceConfig(...)
    extractor = MyConnectorExtractor(config)
    result = extractor.check_connection()
    assert result["success"] is True

def test_discover():
    config = SourceConfig(...)
    extractor = MyConnectorExtractor(config)
    result = extractor.discover()
    assert "objects" in result
```

## Example: HTTP API Connector

Here's a complete example for a simple HTTP API connector:

```python
import requests
from typing import Any, Dict, Iterator, List, Optional
from dativo_ingest.config import SourceConfig
from dativo_ingest.state import IncrementalStateManager
from dativo_ingest.logging import get_logger

logger = get_logger(__name__)


class HttpApiExtractor:
    """Extractor for HTTP API endpoints."""
    
    def __init__(
        self,
        source_config: SourceConfig,
        state_manager: Optional[IncrementalStateManager] = None,
    ):
        self.source_config = source_config
        self.state_manager = state_manager
        self.connection = source_config.connection
        self.endpoint = self.connection.get("endpoint")
        self.api_key = self.connection.get("api_key")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
    def extract(self) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from HTTP API."""
        url = f"{self.endpoint}/data"
        page = 1
        
        while True:
            response = requests.get(
                url,
                headers=self.headers,
                params={"page": page, "per_page": 100}
            )
            response.raise_for_status()
            
            data = response.json()
            records = data.get("items", [])
            
            if not records:
                break
            
            yield records
            page += 1
    
    def check_connection(self) -> Dict[str, Any]:
        """Check API connection."""
        try:
            response = requests.get(
                f"{self.endpoint}/health",
                headers=self.headers,
                timeout=5
            )
            response.raise_for_status()
            return {"success": True, "message": "API accessible"}
        except Exception as e:
            return {"success": False, "message": str(e)}
    
    def discover(self) -> Dict[str, Any]:
        """Discover available endpoints."""
        try:
            response = requests.get(
                f"{self.endpoint}/schema",
                headers=self.headers
            )
            response.raise_for_status()
            schema = response.json()
            return {
                "objects": [
                    {
                        "name": obj["name"],
                        "type": "endpoint",
                        "schema": obj.get("schema", {})
                    }
                    for obj in schema.get("endpoints", [])
                ]
            }
        except Exception as e:
            logger.error(f"Discovery failed: {e}")
            return {"objects": []}
```

## Incremental Sync Support

To support incremental sync, use the state manager:

```python
def extract(self) -> Iterator[List[Dict[str, Any]]]:
    """Extract with incremental sync."""
    if self.source_config.incremental:
        # Get last sync state
        state = self.state_manager.get_state(
            tenant_id=self.source_config.tenant_id,
            connector_type="my_connector",
            object_name="my_object"
        )
        
        last_sync = state.get("last_sync_timestamp")
        
        # Fetch only new records
        for record in self._fetch_since(last_sync):
            yield [record]
        
        # Update state after successful extraction
        self.state_manager.update_state(
            tenant_id=self.source_config.tenant_id,
            connector_type="my_connector",
            object_name="my_object",
            state={"last_sync_timestamp": current_timestamp}
        )
    else:
        # Full sync
        yield from self._fetch_all()
```

## Error Handling

Implement proper error handling:

```python
from dativo_ingest.exceptions import (
    ConnectionError,
    AuthenticationError,
    TransientError,
)

def extract(self) -> Iterator[List[Dict[str, Any]]]:
    try:
        # Extraction logic
        pass
    except requests.exceptions.ConnectionError as e:
        raise ConnectionError(f"Failed to connect: {e}")
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            raise AuthenticationError("Invalid API key")
        elif e.response.status_code >= 500:
            raise TransientError(f"Server error: {e}")
        else:
            raise
```

## Testing Your Connector

1. **Unit Tests**: Test individual methods
2. **Integration Tests**: Test with mock API/database
3. **Smoke Tests**: End-to-end test with real job config

See [tests/README.md](../tests/README.md) for testing guidelines.

## Documentation

Document your connector:

1. **Connector Recipe**: Add description and examples
2. **README**: Create `docs/connectors/my_connector.md` with:
   - Setup instructions
   - Configuration options
   - Example job configs
   - Troubleshooting tips

## Submitting Your Connector

1. **Create PR** with:
   - Connector recipe
   - Registry entry
   - Implementation code
   - Tests
   - Documentation

2. **Follow Guidelines**:
   - Code style (black, isort, flake8)
   - Type hints
   - Docstrings
   - Test coverage

See [CONTRIBUTING.md](../.github/CONTRIBUTING.md) for details.

## Resources

- **[Config Reference](CONFIG_REFERENCE.md)** - Configuration options
- **[Custom Plugins](CUSTOM_PLUGINS.md)** - Alternative approach using plugins
- **[Plugin Decision Tree](PLUGIN_DECISION_TREE.md)** - When to use connectors vs. plugins
- **[Example Connectors](../src/dativo_ingest/connectors/)** - Reference implementations

---

**Questions?** Open an issue or check existing [connector examples](../src/dativo_ingest/connectors/).
