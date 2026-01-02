from abc import ABC, abstractmethod
from typing import Any, Dict, List


class BaseAdapter(ABC):
    """Base adapter for normalizing external connector catalogs."""

    @abstractmethod
    def normalize(self, raw_data: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize raw catalog data into standard format.

        Args:
            raw_data: The raw JSON data from the source.
            metadata: Metadata about the fetch (fetched_at, source_url, etc.)

        Returns:
            Normalized catalog dictionary matching external_catalog.schema.json
        """
        pass
