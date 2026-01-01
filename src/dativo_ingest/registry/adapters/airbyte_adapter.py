from typing import Any, Dict, List
from datetime import datetime
from .base import BaseAdapter

class AirbyteAdapter(BaseAdapter):
    """Adapter for Airbyte catalog format."""

    def normalize(self, raw_data: Any, metadata: Dict[str, Any]) -> Dict[str, Any]:
        connectors = []
        
        # Handle both "sources" (Airbyte format) and list (fallback)
        sources = raw_data.get("sources", []) if isinstance(raw_data, dict) else raw_data
        if not isinstance(sources, list):
            sources = []

        for item in sources:
            connector = self._normalize_connector(item)
            if connector:
                connectors.append(connector)

        return {
            "catalog": "airbyte",
            "schema_version": 1,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "meta": metadata,
            "connectors": connectors
        }

    def _normalize_connector(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a single Airbyte connector entry."""
        try:
            name = item.get("name", "").lower().replace(" ", "_").replace("-", "_")
            external_id = item.get("sourceDefinitionId")
            docker_repo = item.get("dockerRepository")
            docker_tag = item.get("dockerImageTag")
            
            if not (external_id and docker_repo and docker_tag):
                return None

            docker_image = f"{docker_repo}:{docker_tag}"
            
            # Capability mapping
            capabilities = {
                "supports_incremental": False, # Default false
                "supports_state": True, # Most airbyte connectors support state
                "supports_discover": True, # Standard for Airbyte
                "requires_tables": False,
                "supports_queries": False
            }
            
            # Attempt to infer incremental support from documentation or other fields if available
            # Note: Airbyte catalog JSON doesn't strictly explicitly list "incremental" as a capability flag often,
            # but sometimes has specific fields. For now, we default to False unless we find evidence.
            # However, prompt says "Best-effort inference... if unknown, default false."
            # In Airbyte registry, "releaseStage" or "supportLevel" might indicate quality but not capability.
            
            return {
                "external_id": external_id,
                "name": name,
                "docker_image": docker_image,
                "version": docker_tag,
                "capabilities": capabilities,
                "metadata": {
                    "documentation_url": item.get("documentationUrl"),
                    "support_level": item.get("supportLevel"),
                    "release_stage": item.get("releaseStage"),
                    "icon": item.get("icon")
                }
            }
        except Exception:
            return None
