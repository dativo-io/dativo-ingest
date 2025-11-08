"""Example custom reader for JSON APIs with pagination support.

This reader demonstrates how to:
- Read from a paginated REST API
- Handle authentication
- Process responses in batches
- Handle errors gracefully
"""

import requests
from typing import Any, Dict, Iterator, List, Optional

# Import base classes from dativo_ingest
import sys
from pathlib import Path

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dativo_ingest.plugins import BaseReader
from dativo_ingest.validator import IncrementalStateManager


class JSONAPIReader(BaseReader):
    """Custom reader for paginated JSON APIs.
    
    Configuration example:
        source:
          custom_reader: "examples/plugins/json_api_reader.py:JSONAPIReader"
          connection:
            base_url: "https://api.example.com/v1"
            timeout: 30
          credentials:
            token: "${API_TOKEN}"
          engine:
            options:
              page_size: 100
              max_pages: null  # null = no limit
          objects: ["users", "orders"]
    """
    
    def __init__(self, source_config):
        """Initialize JSON API reader.
        
        Args:
            source_config: Source configuration with connection and credentials
        """
        super().__init__(source_config)
        
        # Extract configuration
        self.base_url = source_config.connection.get("base_url", "")
        self.timeout = source_config.connection.get("timeout", 30)
        
        # Get credentials
        token = source_config.credentials.get("token") if source_config.credentials else None
        
        # Set up session with authentication
        self.session = requests.Session()
        if token:
            self.session.headers.update({"Authorization": f"Bearer {token}"})
        
        # Engine options
        engine_opts = source_config.engine.get("options", {}) if source_config.engine else {}
        self.page_size = engine_opts.get("page_size", 100)
        self.max_pages = engine_opts.get("max_pages")
    
    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from JSON API.
        
        Args:
            state_manager: Optional state manager for incremental syncs
        
        Yields:
            Batches of records as list of dictionaries
        """
        objects = self.source_config.objects or []
        
        for obj_name in objects:
            # Fetch all pages for this object
            yield from self._fetch_object_pages(obj_name)
    
    def _fetch_object_pages(self, object_name: str) -> Iterator[List[Dict[str, Any]]]:
        """Fetch all pages for a specific object.
        
        Args:
            object_name: Name of the object/endpoint to fetch
        
        Yields:
            Batches of records
        """
        page = 1
        pages_fetched = 0
        
        while True:
            # Check max pages limit
            if self.max_pages and pages_fetched >= self.max_pages:
                break
            
            try:
                # Make API request
                url = f"{self.base_url}/{object_name}"
                response = self.session.get(
                    url,
                    params={
                        "page": page,
                        "page_size": self.page_size,
                    },
                    timeout=self.timeout,
                )
                
                # Raise for HTTP errors
                response.raise_for_status()
                
                # Parse JSON response
                data = response.json()
                
                # Extract records (adjust based on your API structure)
                records = self._extract_records(data)
                
                if not records:
                    break
                
                yield records
                
                pages_fetched += 1
                
                # Check if there are more pages (adjust based on your API)
                if not self._has_next_page(data):
                    break
                
                page += 1
            
            except requests.exceptions.RequestException as e:
                # Handle API errors
                raise RuntimeError(
                    f"Failed to fetch page {page} for {object_name}: {str(e)}"
                ) from e
    
    def _extract_records(self, data: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Extract records from API response.
        
        Override this method to match your API response structure.
        
        Args:
            data: API response data
        
        Returns:
            List of records
        """
        # Common patterns:
        # - data["items"]
        # - data["data"]
        # - data["results"]
        # - data (if response is array)
        
        if isinstance(data, list):
            return data
        
        return data.get("items") or data.get("data") or data.get("results") or []
    
    def _has_next_page(self, data: Dict[str, Any]) -> bool:
        """Check if there are more pages.
        
        Override this method to match your API pagination structure.
        
        Args:
            data: API response data
        
        Returns:
            True if there are more pages
        """
        # Common patterns:
        # - data["has_next"]
        # - data["next"] is not None
        # - data["pagination"]["has_more"]
        
        if "has_next" in data:
            return data["has_next"]
        
        if "next" in data:
            return data["next"] is not None
        
        if "pagination" in data:
            return data["pagination"].get("has_more", False)
        
        return False
    
    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records.
        
        Returns:
            Estimated record count or None
        """
        # If your API provides a count endpoint, implement it here
        return None


def main():
    """Example usage for testing."""
    from dativo_ingest.config import SourceConfig
    
    # Example configuration
    source_config = SourceConfig(
        type="json_api",
        connection={
            "base_url": "https://jsonplaceholder.typicode.com",
            "timeout": 30,
        },
        objects=["posts", "users"],
        engine={
            "options": {
                "page_size": 10,
                "max_pages": 2,
            }
        },
    )
    
    # Create reader
    reader = JSONAPIReader(source_config)
    
    # Extract data
    print("Extracting data from JSON API...")
    for batch_idx, batch in enumerate(reader.extract()):
        print(f"Batch {batch_idx + 1}: {len(batch)} records")
        if batch:
            print(f"Sample record: {batch[0]}")


if __name__ == "__main__":
    main()
