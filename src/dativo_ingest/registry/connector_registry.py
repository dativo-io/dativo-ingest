"""Enhanced connector registry with catalog support and resolution logic."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .catalog_loader import CatalogLoader, ExternalConnector


class ResolvedConnector:
    """Fully resolved connector with merged metadata from registry and catalogs."""

    def __init__(
        self,
        name: str,
        connector_type: str,
        registry_entry: Dict[str, Any],
        catalog_entry: Optional[ExternalConnector] = None,
        job_overrides: Optional[Dict[str, Any]] = None,
    ):
        """Initialize resolved connector.

        Args:
            name: Connector name
            connector_type: Connector type
            registry_entry: Entry from connectors.yaml
            catalog_entry: Optional external catalog entry
            job_overrides: Optional job-level overrides
        """
        self.name = name
        self.connector_type = connector_type
        self.registry_entry = registry_entry
        self.catalog_entry = catalog_entry
        self.job_overrides = job_overrides or {}

    @property
    def roles(self) -> List[str]:
        """Get connector roles."""
        return self.registry_entry.get("roles", ["source"])

    @property
    def default_engine(self) -> str:
        """Get default engine."""
        # Job override takes precedence
        if "engine" in self.job_overrides:
            return self.job_overrides["engine"]
        return self.registry_entry.get("default_engine", "native")

    @property
    def engines_supported(self) -> List[str]:
        """Get supported engines."""
        return self.registry_entry.get("engines_supported", [])

    @property
    def docker_image(self) -> Optional[str]:
        """Get Docker image with resolution priority:
        1. Job-level override
        2. Catalog entry
        3. Registry entry
        """
        # Job override
        if "docker_image" in self.job_overrides:
            return self.job_overrides["docker_image"]

        # Catalog entry
        if self.catalog_entry and self.catalog_entry.docker_image_default:
            return self.catalog_entry.docker_image_default

        # Registry entry
        return self.registry_entry.get("docker_image_default")

    @property
    def version(self) -> Optional[str]:
        """Get version with resolution priority:
        1. Job-level override
        2. Catalog entry
        3. Registry entry
        """
        # Job override
        if "version" in self.job_overrides:
            return self.job_overrides["version"]

        # Catalog entry
        if self.catalog_entry and self.catalog_entry.version_default:
            return self.catalog_entry.version_default

        # Registry entry
        return self.registry_entry.get("version_default")

    @property
    def external_id(self) -> Optional[str]:
        """Get external ID from catalog or registry."""
        # Catalog entry
        if self.catalog_entry:
            return self.catalog_entry.external_id

        # Registry entry
        return self.registry_entry.get("external_id")

    @property
    def source_of_truth(self) -> str:
        """Get source of truth."""
        # Registry entry takes precedence
        return self.registry_entry.get("source_of_truth", "native")

    @property
    def capabilities(self) -> List[str]:
        """Get capabilities from catalog or registry."""
        # Merge capabilities from both sources
        capabilities = []

        # From registry
        if self.registry_entry.get("supports_incremental"):
            capabilities.append("incremental")
        if self.registry_entry.get("supports_queries"):
            capabilities.append("queries")
        if self.registry_entry.get("supports_schema_evolution"):
            capabilities.append("schema_evolution")

        # From catalog
        if self.catalog_entry:
            capabilities.extend(self.catalog_entry.capabilities)

        return list(set(capabilities))  # Remove duplicates

    @property
    def category(self) -> Optional[str]:
        """Get connector category."""
        return self.registry_entry.get("category")

    @property
    def allowed_in_cloud(self) -> bool:
        """Check if connector is allowed in cloud mode."""
        return self.registry_entry.get("allowed_in_cloud", True)

    @property
    def supports_incremental(self) -> bool:
        """Check if connector supports incremental sync."""
        return self.registry_entry.get("supports_incremental", False)

    @property
    def incremental_strategy_default(self) -> Optional[str]:
        """Get default incremental strategy."""
        return self.registry_entry.get("incremental_strategy_default")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "type": self.connector_type,
            "roles": self.roles,
            "default_engine": self.default_engine,
            "engines_supported": self.engines_supported,
            "docker_image": self.docker_image,
            "version": self.version,
            "external_id": self.external_id,
            "source_of_truth": self.source_of_truth,
            "capabilities": self.capabilities,
            "category": self.category,
            "allowed_in_cloud": self.allowed_in_cloud,
            "supports_incremental": self.supports_incremental,
            "incremental_strategy_default": self.incremental_strategy_default,
        }


class ConnectorRegistry:
    """Enhanced connector registry with catalog support."""

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        catalog_loader: Optional[CatalogLoader] = None,
    ):
        """Initialize connector registry.

        Args:
            registry_path: Path to connectors.yaml
            catalog_loader: Optional catalog loader instance
        """
        if registry_path is None:
            # Try multiple possible paths
            possible_paths = [
                Path("/app/registry/connectors.yaml"),
                Path("registry/connectors.yaml"),
                Path(__file__).parent.parent.parent.parent
                / "registry"
                / "connectors.yaml",
            ]
            for path in possible_paths:
                if path.exists():
                    registry_path = path
                    break

        if registry_path is None or not registry_path.exists():
            possible_paths_str = [
                str(p)
                for p in [
                    Path("/app/registry/connectors.yaml"),
                    Path("registry/connectors.yaml"),
                    Path(__file__).parent.parent.parent.parent
                    / "registry"
                    / "connectors.yaml",
                ]
            ]
            raise FileNotFoundError(
                f"Connector registry not found. Tried: {possible_paths_str}"
            )

        self.registry_path = registry_path
        self.registry_data = self._load_registry()

        # Initialize catalog loader
        self.catalog_loader = catalog_loader or CatalogLoader()

    def _load_registry(self) -> Dict[str, Any]:
        """Load connector registry from YAML."""
        try:
            with open(self.registry_path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            print(
                f"ERROR: Failed to parse connector registry: {self.registry_path}\n"
                f"YAML Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)
        except Exception as e:
            print(
                f"ERROR: Failed to read connector registry: {self.registry_path}\n"
                f"Error: {e}",
                file=sys.stderr,
            )
            sys.exit(2)

        if data is None:
            print(
                f"ERROR: Connector registry is empty: {self.registry_path}",
                file=sys.stderr,
            )
            sys.exit(2)

        return data

    def get_connector_entry(
        self, connector_name: str, role: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get connector entry from registry.

        Args:
            connector_name: Connector name
            role: Optional role filter ('source' or 'target')

        Returns:
            Connector entry dict or None
        """
        # Support both unified and legacy formats
        connectors = self.registry_data.get("connectors", {})
        sources = self.registry_data.get("sources", {})
        targets = self.registry_data.get("targets", {})

        # Try unified format first
        if connector_name in connectors:
            entry = connectors[connector_name]
            if role and role not in entry.get("roles", []):
                return None
            return entry

        # Try legacy format
        if role == "source" and connector_name in sources:
            return sources[connector_name]
        if role == "target" and connector_name in targets:
            return targets[connector_name]

        # Search without role filter
        if connector_name in sources:
            return sources[connector_name]
        if connector_name in targets:
            return targets[connector_name]

        return None

    def resolve_connector(
        self,
        connector_name: str,
        engine: Optional[str] = None,
        job_overrides: Optional[Dict[str, Any]] = None,
        role: Optional[str] = None,
    ) -> Optional[ResolvedConnector]:
        """Resolve connector with catalog and job overrides.

        Resolution priority:
        1. Job-level overrides (docker_image, version, engine)
        2. If engine=airbyte and catalog entry exists, use catalog defaults
        3. If no catalog entry, fall back to registry

        Args:
            connector_name: Connector name
            engine: Optional engine override
            job_overrides: Optional job-level overrides
            role: Optional role filter ('source' or 'target')

        Returns:
            ResolvedConnector or None if not found
        """
        # Get registry entry
        registry_entry = self.get_connector_entry(connector_name, role)
        if not registry_entry:
            return None

        # Prepare job overrides
        overrides = job_overrides or {}
        if engine:
            overrides["engine"] = engine

        # Determine effective engine
        effective_engine = engine or registry_entry.get("default_engine", "native")

        # Get catalog entry if using external engine
        catalog_entry = None
        if effective_engine in ["airbyte", "singer", "meltano"]:
            # Try to find connector in catalog
            catalog_name = effective_engine
            catalog_entry = self.catalog_loader.get_connector(
                connector_name, catalog_name
            )

            # If not found in specific catalog, try all catalogs
            if not catalog_entry:
                catalog_entry = self.catalog_loader.get_connector(connector_name)

        return ResolvedConnector(
            name=connector_name,
            connector_type=connector_name,
            registry_entry=registry_entry,
            catalog_entry=catalog_entry,
            job_overrides=overrides,
        )

    def list_connectors(self, role: Optional[str] = None) -> List[str]:
        """List all connector names from registry.

        Args:
            role: Optional role filter ('source' or 'target')

        Returns:
            List of connector names
        """
        connectors = []

        # Unified format
        for name, entry in self.registry_data.get("connectors", {}).items():
            if role is None or role in entry.get("roles", []):
                connectors.append(name)

        # Legacy format
        if role is None or role == "source":
            connectors.extend(self.registry_data.get("sources", {}).keys())
        if role is None or role == "target":
            connectors.extend(self.registry_data.get("targets", {}).keys())

        return list(set(connectors))  # Remove duplicates

    def validate_connector(
        self, connector_name: str, role: str, mode: str = "self_hosted"
    ) -> Dict[str, Any]:
        """Validate connector exists and supports role/mode.

        Args:
            connector_name: Connector name
            role: Role to validate ('source' or 'target')
            mode: Execution mode ('self_hosted' or 'cloud')

        Returns:
            Connector entry

        Raises:
            SystemExit: If validation fails
        """
        entry = self.get_connector_entry(connector_name, role)
        if not entry:
            available = self.list_connectors(role)
            print(
                f"ERROR: Connector '{connector_name}' not found in registry.\n"
                f"Available {role} connectors: {', '.join(available)}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check mode restriction
        if mode == "cloud" and not entry.get("allowed_in_cloud", True):
            print(
                f"ERROR: Connector '{connector_name}' is not allowed in cloud mode.\n"
                f"Database connectors can only run in self_hosted mode.",
                file=sys.stderr,
            )
            sys.exit(2)

        return entry
