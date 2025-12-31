"""Custom JSON API Reader Plugin"""
import requests
from typing import Iterator, Dict, Any
from dativo_ingest.plugins import BaseReader

class JSONAPIReader(BaseReader):
    """Read data from a JSON API endpoint"""
    
    __version__ = "1.0.0"
    
    def extract(self, state_manager=None) -> Iterator[Dict[str, Any]]:
        """Extract data from API"""
        connection = self.source_config.connection
        base_url = connection.get("base_url")
        endpoint = connection.get("endpoint", "/data")
        
        # Make API request
        response = requests.get(f"{base_url}{endpoint}")
        response.raise_for_status()
        
        # Yield records
        data = response.json()
        if isinstance(data, list):
            for record in data:
                yield record
        elif isinstance(data, dict):
            # Handle paginated responses
            records = data.get("records", data.get("data", []))
            for record in records:
                yield record
    
    def check_connection(self) -> tuple[bool, str, Dict[str, Any]]:
        """Test API connectivity"""
        try:
            connection = self.source_config.connection
            base_url = connection.get("base_url")
            response = requests.get(f"{base_url}/health")
            if response.status_code == 200:
                return True, "API is accessible", {"status": "healthy"}
            return False, f"API returned {response.status_code}", {}
        except Exception as e:
            return False, str(e), {}
    
    def discover(self) -> Dict[str, Any]:
        """Discover available endpoints"""
        return {
            "streams": [
                {"name": "data", "schema": {}}
            ]
        }
