"""Custom JSON API Reader Plugin"""
import requests
from typing import Iterator, Dict, Any, List, Optional
from dativo_ingest.plugins import BaseReader, ConnectionTestResult, DiscoveryResult
from dativo_ingest.validator import IncrementalStateManager

class JSONAPIReader(BaseReader):
    """Read data from a JSON API endpoint"""
    
    __version__ = "1.0.0"
    
    def extract(
        self,
        state_manager: Optional[IncrementalStateManager] = None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from API
        
        Args:
            state_manager: Optional state manager for incremental syncs
            checkpoint_context: Optional checkpoint context for WAL resume
            
        Yields:
            Batches of records as list of dictionaries
        """
        connection = self.source_config.connection
        base_url = connection.get("base_url")
        endpoint = connection.get("endpoint", "/data")
        
        # Make API request
        response = requests.get(f"{base_url}{endpoint}")
        response.raise_for_status()
        
        # Yield records as batches (BaseReader expects batches)
        data = response.json()
        records = []
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Handle paginated responses
            records = data.get("records", data.get("data", []))
        
        # Yield as a single batch (list of records)
        if records:
            yield records
    
    def check_connection(self) -> ConnectionTestResult:
        """Test API connectivity"""
        try:
            connection = self.source_config.connection
            base_url = connection.get("base_url")
            response = requests.get(f"{base_url}/health")
            if response.status_code == 200:
                return ConnectionTestResult(
                    success=True,
                    message="API is accessible",
                    details={"status": "healthy"}
                )
            return ConnectionTestResult(
                success=False,
                message=f"API returned {response.status_code}",
                error_code="HTTP_ERROR"
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=str(e),
                error_code="CONNECTION_ERROR"
            )
    
    def discover(self) -> DiscoveryResult:
        """Discover available endpoints"""
        return DiscoveryResult(
            objects=[
                {"name": "data", "type": "stream", "schema": {}}
            ],
            metadata={"endpoint": "/data"}
        )
