from datetime import datetime
from typing import Any, Dict

from .base import BaseAdapter


class MeltanoAdapter(BaseAdapter):
    """Adapter for Meltano catalog format (Stub)."""

    def normalize(self, raw_data: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "catalog": "meltano",
            "schema_version": 1,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "meta": metadata,
            "connectors": [],  # Stub
        }
