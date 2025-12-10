"""Connector resolution logic with catalog support.

This module handles connector resolution with the following priority:
1. Job-level overrides (highest priority)
2. External catalog entries (if engine=airbyte and catalog entry exists)
3. connectors.yaml registry (fallback)
"""

from pathlib import Path
from typing import Any, Dict, Optional

from ..config import ConnectorRecipe
from ..logging import get_logger
from .catalog import ConnectorCatalog, ConnectorCatalogEntry


class ConnectorResolver:
    """Resolves connector configuration with catalog support."""

    def __init__(self, catalog_dir: Optional[Path] = None):
        """Initialize connector resolver.

        Args:
            catalog_dir: Directory containing catalog JSON files.
                        If None, uses default registry/catalogs directory.
        """
        self.catalog = ConnectorCatalog(catalog_dir)
        self.logger = get_logger()

    def resolve_docker_image(
        self,
        connector_name: str,
        engine_type: str,
        connector_recipe: Optional[ConnectorRecipe] = None,
        job_override: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve Docker image for a connector.

        Priority order:
        1. Job-level override (if provided)
        2. Catalog entry (if engine=airbyte and catalog entry exists)
        3. Connector recipe default_engine.options.airbyte.docker_image
        4. connectors.yaml docker_image_default
        5. None

        Args:
            connector_name: Connector name (e.g., "stripe", "hubspot")
            engine_type: Engine type (e.g., "airbyte", "singer")
            connector_recipe: Optional connector recipe
            job_override: Optional job-level override

        Returns:
            Docker image string or None
        """
        # Priority 1: Job-level override
        if job_override:
            self.logger.debug(
                f"Using job-level docker_image override for {connector_name}: {job_override}",
                extra={
                    "event_type": "connector_resolution",
                    "connector": connector_name,
                    "source": "job_override",
                },
            )
            return job_override

        # Priority 2: Catalog entry (for airbyte engine)
        if engine_type == "airbyte":
            catalog_entry = self.catalog.get_entry(connector_name)
            if catalog_entry and catalog_entry.docker_image_default:
                self.logger.debug(
                    f"Using catalog docker_image for {connector_name}: {catalog_entry.docker_image_default}",
                    extra={
                        "event_type": "connector_resolution",
                        "connector": connector_name,
                        "source": "catalog",
                    },
                )
                return catalog_entry.docker_image_default

        # Priority 3: Connector recipe
        if connector_recipe:
            default_engine = connector_recipe.default_engine
            if isinstance(default_engine, dict):
                engine_options = default_engine.get("options", {})
                airbyte_opts = engine_options.get("airbyte", {})
                docker_image = airbyte_opts.get("docker_image")
                if docker_image:
                    self.logger.debug(
                        f"Using connector recipe docker_image for {connector_name}: {docker_image}",
                        extra={
                            "event_type": "connector_resolution",
                            "connector": connector_name,
                            "source": "recipe",
                        },
                    )
                    return docker_image

        # Priority 4: connectors.yaml (would need to load registry, but for now return None)
        # This could be implemented by loading the registry YAML and checking docker_image_default

        return None

    def resolve_version(
        self,
        connector_name: str,
        engine_type: str,
        connector_recipe: Optional[ConnectorRecipe] = None,
        job_override: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve version for a connector.

        Priority order:
        1. Job-level override (if provided)
        2. Catalog entry (if engine=airbyte and catalog entry exists)
        3. Connector recipe default_engine.options.airbyte.version
        4. connectors.yaml version_default
        5. None

        Args:
            connector_name: Connector name (e.g., "stripe", "hubspot")
            engine_type: Engine type (e.g., "airbyte", "singer")
            connector_recipe: Optional connector recipe
            job_override: Optional job-level override

        Returns:
            Version string or None
        """
        # Priority 1: Job-level override
        if job_override:
            self.logger.debug(
                f"Using job-level version override for {connector_name}: {job_override}",
                extra={
                    "event_type": "connector_resolution",
                    "connector": connector_name,
                    "source": "job_override",
                },
            )
            return job_override

        # Priority 2: Catalog entry (for airbyte engine)
        if engine_type == "airbyte":
            catalog_entry = self.catalog.get_entry(connector_name)
            if catalog_entry and catalog_entry.version_default:
                self.logger.debug(
                    f"Using catalog version for {connector_name}: {catalog_entry.version_default}",
                    extra={
                        "event_type": "connector_resolution",
                        "connector": connector_name,
                        "source": "catalog",
                    },
                )
                return catalog_entry.version_default

        # Priority 3: Connector recipe
        if connector_recipe:
            default_engine = connector_recipe.default_engine
            if isinstance(default_engine, dict):
                engine_options = default_engine.get("options", {})
                airbyte_opts = engine_options.get("airbyte", {})
                version = airbyte_opts.get("version")
                if version:
                    self.logger.debug(
                        f"Using connector recipe version for {connector_name}: {version}",
                        extra={
                            "event_type": "connector_resolution",
                            "connector": connector_name,
                            "source": "recipe",
                        },
                    )
                    return version

        return None

    def resolve_capabilities(
        self,
        connector_name: str,
        engine_type: str,
        connector_recipe: Optional[ConnectorRecipe] = None,
    ) -> list[str]:
        """Resolve capabilities for a connector.

        Args:
            connector_name: Connector name
            engine_type: Engine type
            connector_recipe: Optional connector recipe

        Returns:
            List of capability strings
        """
        capabilities = []

        # Get from catalog if available
        if engine_type == "airbyte":
            catalog_entry = self.catalog.get_entry(connector_name)
            if catalog_entry:
                capabilities.extend(catalog_entry.capabilities)

        return list(set(capabilities))  # Remove duplicates

    def get_resolved_info(
        self,
        connector_name: str,
        engine_type: str,
        connector_recipe: Optional[ConnectorRecipe] = None,
        job_overrides: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get fully resolved connector information.

        Args:
            connector_name: Connector name
            engine_type: Engine type
            connector_recipe: Optional connector recipe
            job_overrides: Optional job-level overrides (e.g., {"docker_image": "...", "version": "..."})

        Returns:
            Dictionary with resolved connector information
        """
        job_overrides = job_overrides or {}

        docker_image = self.resolve_docker_image(
            connector_name=connector_name,
            engine_type=engine_type,
            connector_recipe=connector_recipe,
            job_override=job_overrides.get("docker_image"),
        )

        version = self.resolve_version(
            connector_name=connector_name,
            engine_type=engine_type,
            connector_recipe=connector_recipe,
            job_override=job_overrides.get("version"),
        )

        capabilities = self.resolve_capabilities(
            connector_name=connector_name,
            engine_type=engine_type,
            connector_recipe=connector_recipe,
        )

        # Get catalog entry for additional metadata
        catalog_entry = None
        if engine_type == "airbyte":
            catalog_entry = self.catalog.get_entry(connector_name)

        return {
            "connector_name": connector_name,
            "engine_type": engine_type,
            "docker_image": docker_image,
            "version": version,
            "capabilities": capabilities,
            "catalog_entry": catalog_entry,
            "external_id": catalog_entry.external_id if catalog_entry else None,
        }
