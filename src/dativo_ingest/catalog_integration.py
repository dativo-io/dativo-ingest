"""Data catalog integration for lineage and metadata push.

Supports multiple catalog types:
- AWS Glue
- Databricks Unity Catalog
- Nessie
- OpenMetadata
"""

import os
from typing import Any, Dict, List, Optional

from .config import AssetDefinition, JobConfig
from .tag_derivation import derive_tags_from_asset


class CatalogIntegration:
    """Base class for data catalog integrations."""

    def __init__(
        self,
        catalog_config: Dict[str, Any],
        asset_definition: AssetDefinition,
        job_config: JobConfig,
        source_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize catalog integration.

        Args:
            catalog_config: Catalog configuration dictionary
            asset_definition: Asset definition containing schema and metadata
            job_config: Job configuration
            source_tags: Source system tags (optional)
        """
        self.catalog_config = catalog_config
        self.asset_definition = asset_definition
        self.job_config = job_config
        self.source_tags = source_tags or {}

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        file_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Push lineage information to catalog.

        Args:
            source_entities: List of source entity dictionaries
            target_entity: Target entity dictionary
            file_metadata: Optional file metadata from writer

        Returns:
            Dictionary with push result information
        """
        raise NotImplementedError("Subclasses must implement push_lineage")

    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None,
        owners: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Push metadata (tags, owners, etc.) to catalog.

        Args:
            entity: Entity dictionary (table, dataset, etc.)
            tags: Optional tags dictionary
            owners: Optional list of owner emails

        Returns:
            Dictionary with push result information
        """
        raise NotImplementedError("Subclasses must implement push_metadata")

    def _derive_metadata(self) -> Dict[str, Any]:
        """Derive metadata from asset definition and job config.

        Returns:
            Dictionary with all metadata
        """
        # Derive tags using tag derivation
        tags = derive_tags_from_asset(
            asset_definition=self.asset_definition,
            classification_overrides=self.job_config.classification_overrides,
            finops=self.job_config.finops,
            governance_overrides=self.job_config.governance_overrides,
            source_tags=self.source_tags,
        )

        # Extract owners
        owners = []
        if self.asset_definition.team and self.asset_definition.team.owner:
            owners.append(self.asset_definition.team.owner)
        if self.job_config.governance_overrides and self.job_config.governance_overrides.get("owner"):
            owner = self.job_config.governance_overrides["owner"]
            if owner and owner not in owners:
                owners.append(owner)

        # Extract tags list from asset definition
        asset_tags = []
        if self.asset_definition.tags:
            if isinstance(self.asset_definition.tags, list):
                asset_tags.extend(self.asset_definition.tags)
            else:
                asset_tags.append(str(self.asset_definition.tags))

        # Add derived tags to asset_tags
        for key, value in tags.items():
            asset_tags.append(f"{key}:{value}")

        return {
            "tags": tags,
            "asset_tags": asset_tags,
            "owners": owners,
            "domain": self.asset_definition.domain,
            "data_product": getattr(self.asset_definition, "dataProduct", None),
            "description": self.asset_definition.description.purpose if self.asset_definition.description else None,
        }


class OpenMetadataIntegration(CatalogIntegration):
    """OpenMetadata catalog integration."""

    def __init__(
        self,
        catalog_config: Dict[str, Any],
        asset_definition: AssetDefinition,
        job_config: JobConfig,
        source_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize OpenMetadata integration."""
        super().__init__(catalog_config, asset_definition, job_config, source_tags)
        self.api_url = catalog_config.get("api_url") or os.getenv(
            "OPENMETADATA_API_URL", "http://localhost:8585/api"
        )
        self.auth_token = catalog_config.get("auth_token") or os.getenv(
            "OPENMETADATA_AUTH_TOKEN"
        )

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        file_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Push lineage to OpenMetadata.

        Args:
            source_entities: List of source entity dictionaries with 'fqn' (fully qualified name)
            target_entity: Target entity dictionary with 'fqn'
            file_metadata: Optional file metadata

        Returns:
            Dictionary with push result
        """
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests is required for OpenMetadata integration. Install with: pip install requests"
            )

        # Build lineage edges
        edges = []
        for source in source_entities:
            edges.append({
                "fromEntity": {
                    "id": source.get("id"),
                    "type": source.get("type", "table"),
                    "fullyQualifiedName": source.get("fqn"),
                },
                "toEntity": {
                    "id": target_entity.get("id"),
                    "type": target_entity.get("type", "table"),
                    "fullyQualifiedName": target_entity.get("fqn"),
                },
                "description": f"Data ingestion from {source.get('fqn')} to {target_entity.get('fqn')}",
            })

        if not edges:
            return {"status": "skipped", "reason": "no_edges"}

        # Push lineage via OpenMetadata API
        headers = {}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        try:
            # Use OpenMetadata's putLineage endpoint
            response = requests.put(
                f"{self.api_url}/v1/lineage",
                json={"edges": edges},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            return {
                "status": "success",
                "edges_pushed": len(edges),
                "response": response.json() if response.content else None,
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
                "edges_pushed": 0,
            }

    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None,
        owners: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Push metadata to OpenMetadata.

        Args:
            entity: Entity dictionary with 'fqn' and 'type'
            tags: Optional tags dictionary
            owners: Optional list of owner emails

        Returns:
            Dictionary with push result
        """
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests is required for OpenMetadata integration. Install with: pip install requests"
            )

        metadata = self._derive_metadata()
        if tags:
            metadata["tags"].update(tags)
        if owners:
            metadata["owners"].extend(owners)

        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        entity_type = entity.get("type", "table")
        fqn = entity.get("fqn")

        if not fqn:
            return {"status": "error", "error": "fqn is required"}

        try:
            # Get entity by FQN first
            get_url = f"{self.api_url}/v1/{entity_type}s/name/{fqn}"
            get_response = requests.get(get_url, headers=headers, timeout=30)

            if get_response.status_code == 404:
                # Entity doesn't exist, create it
                return self._create_entity(entity, metadata, headers)
            else:
                get_response.raise_for_status()
                entity_data = get_response.json()

                # Update entity with metadata
                return self._update_entity(entity_data, metadata, headers, entity_type)
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def _create_entity(
        self,
        entity: Dict[str, Any],
        metadata: Dict[str, Any],
        headers: Dict[str, str],
    ) -> Dict[str, Any]:
        """Create new entity in OpenMetadata."""
        import requests

        entity_type = entity.get("type", "table")
        fqn = entity.get("fqn")

        # Build entity payload
        payload = {
            "name": fqn.split(".")[-1],
            "fullyQualifiedName": fqn,
            "description": metadata.get("description", ""),
        }

        # Add tags
        if metadata.get("asset_tags"):
            payload["tags"] = [
                {"tagFQN": tag} for tag in metadata["asset_tags"][:10]
            ]  # Limit to 10 tags

        # Add owners
        if metadata.get("owners"):
            payload["owners"] = [
                {"id": owner, "type": "user"} for owner in metadata["owners"]
            ]

        try:
            response = requests.post(
                f"{self.api_url}/v1/{entity_type}s",
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return {
                "status": "success",
                "action": "created",
                "entity_id": response.json().get("id"),
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def _update_entity(
        self,
        entity_data: Dict[str, Any],
        metadata: Dict[str, Any],
        headers: Dict[str, str],
        entity_type: str,
    ) -> Dict[str, Any]:
        """Update existing entity in OpenMetadata."""
        import requests

        entity_id = entity_data.get("id")
        if not entity_id:
            return {"status": "error", "error": "entity_id not found"}

        # Build update payload
        payload = entity_data.copy()

        # Update description
        if metadata.get("description"):
            payload["description"] = metadata["description"]

        # Update tags
        if metadata.get("asset_tags"):
            existing_tags = {tag.get("tagFQN") for tag in payload.get("tags", [])}
            new_tags = [
                {"tagFQN": tag}
                for tag in metadata["asset_tags"][:10]
                if tag not in existing_tags
            ]
            payload["tags"] = payload.get("tags", []) + new_tags

        # Update owners
        if metadata.get("owners"):
            existing_owners = {owner.get("id") for owner in payload.get("owners", [])}
            new_owners = [
                {"id": owner, "type": "user"}
                for owner in metadata["owners"]
                if owner not in existing_owners
            ]
            payload["owners"] = payload.get("owners", []) + new_owners

        try:
            response = requests.put(
                f"{self.api_url}/v1/{entity_type}s/{entity_id}",
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            return {
                "status": "success",
                "action": "updated",
                "entity_id": entity_id,
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
            }


class AWSGlueIntegration(CatalogIntegration):
    """AWS Glue catalog integration."""

    def __init__(
        self,
        catalog_config: Dict[str, Any],
        asset_definition: AssetDefinition,
        job_config: JobConfig,
        source_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize AWS Glue integration."""
        super().__init__(catalog_config, asset_definition, job_config, source_tags)
        self.region = catalog_config.get("region") or os.getenv("AWS_REGION", "us-east-1")

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        file_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Push lineage to AWS Glue.

        Note: AWS Glue doesn't have native lineage API, so we use table properties.
        """
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for AWS Glue integration. Install with: pip install boto3"
            )

        glue_client = boto3.client("glue", region_name=self.region)

        database_name = target_entity.get("database", "default")
        table_name = target_entity.get("table")

        if not table_name:
            return {"status": "error", "error": "table name is required"}

        try:
            # Get current table
            table = glue_client.get_table(DatabaseName=database_name, Name=table_name)
            table_input = table["Table"]["StorageDescriptor"].copy()
            parameters = table["Table"].get("Parameters", {}).copy()

            # Add lineage information to parameters
            if source_entities:
                source_fqns = [s.get("fqn", s.get("table", "")) for s in source_entities]
                parameters["lineage.sources"] = ",".join(source_fqns)
                parameters["lineage.updated_at"] = str(
                    __import__("datetime").datetime.utcnow().isoformat()
                )

            # Update table
            glue_client.update_table(
                DatabaseName=database_name,
                TableInput={
                    "Name": table_name,
                    "StorageDescriptor": table_input,
                    "Parameters": parameters,
                },
            )

            return {
                "status": "success",
                "sources_pushed": len(source_entities),
            }
        except glue_client.exceptions.EntityNotFoundException:
            return {"status": "error", "error": "table not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None,
        owners: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Push metadata to AWS Glue."""
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 is required for AWS Glue integration. Install with: pip install boto3"
            )

        glue_client = boto3.client("glue", region_name=self.region)

        database_name = entity.get("database", "default")
        table_name = entity.get("table")

        if not table_name:
            return {"status": "error", "error": "table name is required"}

        metadata = self._derive_metadata()
        if tags:
            metadata["tags"].update(tags)
        if owners:
            metadata["owners"].extend(owners)

        try:
            # Get current table
            table = glue_client.get_table(DatabaseName=database_name, Name=table_name)
            table_input = table["Table"]["StorageDescriptor"].copy()
            parameters = table["Table"].get("Parameters", {}).copy()

            # Update parameters with metadata
            for key, value in metadata["tags"].items():
                parameters[f"metadata.{key}"] = str(value)

            if metadata.get("owners"):
                parameters["metadata.owners"] = ",".join(metadata["owners"])

            if metadata.get("domain"):
                parameters["metadata.domain"] = metadata["domain"]

            if metadata.get("data_product"):
                parameters["metadata.data_product"] = metadata["data_product"]

            # Update table
            glue_client.update_table(
                DatabaseName=database_name,
                TableInput={
                    "Name": table_name,
                    "StorageDescriptor": table_input,
                    "Parameters": parameters,
                },
            )

            return {"status": "success"}
        except glue_client.exceptions.EntityNotFoundException:
            return {"status": "error", "error": "table not found"}
        except Exception as e:
            return {"status": "error", "error": str(e)}


class DatabricksUnityCatalogIntegration(CatalogIntegration):
    """Databricks Unity Catalog integration."""

    def __init__(
        self,
        catalog_config: Dict[str, Any],
        asset_definition: AssetDefinition,
        job_config: JobConfig,
        source_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize Databricks Unity Catalog integration."""
        super().__init__(catalog_config, asset_definition, job_config, source_tags)
        self.workspace_url = catalog_config.get("workspace_url") or os.getenv(
            "DATABRICKS_WORKSPACE_URL"
        )
        self.token = catalog_config.get("token") or os.getenv("DATABRICKS_TOKEN")

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        file_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Push lineage to Databricks Unity Catalog."""
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests is required for Databricks integration. Install with: pip install requests"
            )

        if not self.workspace_url or not self.token:
            return {"status": "error", "error": "workspace_url and token are required"}

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        # Build lineage edges
        edges = []
        for source in source_entities:
            edges.append({
                "source": {
                    "table": {
                        "catalogName": source.get("catalog", "main"),
                        "schemaName": source.get("schema", "default"),
                        "tableName": source.get("table"),
                    }
                },
                "target": {
                    "table": {
                        "catalogName": target_entity.get("catalog", "main"),
                        "schemaName": target_entity.get("schema", "default"),
                        "tableName": target_entity.get("table"),
                    }
                },
            })

        try:
            response = requests.post(
                f"{self.workspace_url}/api/2.1/unity-catalog/lineage",
                json={"edges": edges},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            return {
                "status": "success",
                "edges_pushed": len(edges),
            }
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
            }

    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None,
        owners: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Push metadata to Databricks Unity Catalog."""
        try:
            import requests
        except ImportError:
            raise ImportError(
                "requests is required for Databricks integration. Install with: pip install requests"
            )

        if not self.workspace_url or not self.token:
            return {"status": "error", "error": "workspace_url and token are required"}

        metadata = self._derive_metadata()
        if tags:
            metadata["tags"].update(tags)
        if owners:
            metadata["owners"].extend(owners)

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        catalog_name = entity.get("catalog", "main")
        schema_name = entity.get("schema", "default")
        table_name = entity.get("table")

        if not table_name:
            return {"status": "error", "error": "table name is required"}

        try:
            # Update table properties
            properties = {}
            for key, value in metadata["tags"].items():
                properties[f"metadata.{key}"] = str(value)

            if metadata.get("owners"):
                properties["metadata.owners"] = ",".join(metadata["owners"])

            response = requests.patch(
                f"{self.workspace_url}/api/2.1/unity-catalog/tables/{catalog_name}.{schema_name}.{table_name}",
                json={"properties": properties},
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            return {"status": "success"}
        except requests.exceptions.RequestException as e:
            return {
                "status": "error",
                "error": str(e),
            }


class NessieIntegration(CatalogIntegration):
    """Nessie catalog integration (via table properties)."""

    def __init__(
        self,
        catalog_config: Dict[str, Any],
        asset_definition: AssetDefinition,
        job_config: JobConfig,
        source_tags: Optional[Dict[str, str]] = None,
    ):
        """Initialize Nessie integration."""
        super().__init__(catalog_config, asset_definition, job_config, source_tags)
        # Nessie lineage is handled via Iceberg table properties
        # This integration is mainly for consistency with other catalogs

    def push_lineage(
        self,
        source_entities: List[Dict[str, Any]],
        target_entity: Dict[str, Any],
        file_metadata: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Push lineage to Nessie (via table properties).

        Note: Nessie doesn't have a separate lineage API, so we use table properties.
        """
        # Lineage is already handled by IcebergCommitter via table properties
        return {
            "status": "success",
            "note": "Lineage handled via Iceberg table properties",
        }

    def push_metadata(
        self,
        entity: Dict[str, Any],
        tags: Optional[Dict[str, str]] = None,
        owners: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Push metadata to Nessie (via table properties).

        Note: Metadata is already handled by IcebergCommitter via table properties.
        """
        return {
            "status": "success",
            "note": "Metadata handled via Iceberg table properties",
        }


def create_catalog_integration(
    catalog_config: Dict[str, Any],
    asset_definition: AssetDefinition,
    job_config: JobConfig,
    source_tags: Optional[Dict[str, str]] = None,
) -> Optional[CatalogIntegration]:
    """Create appropriate catalog integration based on config.

    Args:
        catalog_config: Catalog configuration dictionary with 'type' field
        asset_definition: Asset definition
        job_config: Job configuration
        source_tags: Optional source tags

    Returns:
        CatalogIntegration instance or None if type not supported
    """
    catalog_type = catalog_config.get("type", "").lower()

    if catalog_type == "openmetadata":
        return OpenMetadataIntegration(
            catalog_config, asset_definition, job_config, source_tags
        )
    elif catalog_type == "aws_glue" or catalog_type == "glue":
        return AWSGlueIntegration(
            catalog_config, asset_definition, job_config, source_tags
        )
    elif catalog_type == "databricks" or catalog_type == "unity_catalog":
        return DatabricksUnityCatalogIntegration(
            catalog_config, asset_definition, job_config, source_tags
        )
    elif catalog_type == "nessie":
        return NessieIntegration(
            catalog_config, asset_definition, job_config, source_tags
        )
    else:
        return None
