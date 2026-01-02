"""Enhanced connector registry with catalog support and resolution logic."""

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .catalog_loader import CatalogLoader, ExternalConnector


def resolve_image_and_version(
    *,
    job_image: Optional[str] = None,
    job_version: Optional[str] = None,
    catalog_image: Optional[str] = None,
    catalog_version: Optional[str] = None,
    registry_image_default: Optional[str] = None,
    registry_version_default: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """Resolve docker image and version with explicit precedence.

    Resolution precedence:
    1. Job override (highest priority)
    2. Catalog metadata
    3. Registry defaults
    4. None (lowest priority)

    Args:
        job_image: Job-level docker image override
        job_version: Job-level version override
        catalog_image: Catalog docker image default
        catalog_version: Catalog version default
        registry_image_default: Registry docker image default
        registry_version_default: Registry version default

    Returns:
        Tuple of (resolved_image, resolved_version)
    """
    # Image resolution
    resolved_image = job_image or catalog_image or registry_image_default

    # Version resolution
    resolved_version = job_version or catalog_version or registry_version_default

    return resolved_image, resolved_version


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
        """Get Docker image with resolution priority."""
        image, _ = resolve_image_and_version(
            job_image=self.job_overrides.get("docker_image"),
            catalog_image=(
                self.catalog_entry.docker_image_default if self.catalog_entry else None
            ),
            registry_image_default=self.registry_entry.get("docker_image_default"),
        )
        return image

    @property
    def version(self) -> Optional[str]:
        """Get version with resolution priority."""
        _, version = resolve_image_and_version(
            job_version=self.job_overrides.get("version"),
            catalog_version=(
                self.catalog_entry.version_default if self.catalog_entry else None
            ),
            registry_version_default=self.registry_entry.get("version_default"),
        )
        return version

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


class RegistryNotFoundError(Exception):
    """Raised when connector registry file cannot be found."""

    pass


class RegistryLoadError(Exception):
    """Raised when connector registry file cannot be loaded or parsed."""

    pass


class ConnectorRegistry:
    """Enhanced connector registry with catalog support."""

    @classmethod
    def _get_default_registry_paths(cls) -> List[Path]:
        """Get list of default paths to search for registry file.

        Returns:
            List of paths to try, in order of precedence
        """
        return [
            Path("/app/registry/connectors.yaml"),
            Path("registry/connectors.yaml"),
            Path(__file__).parent.parent.parent.parent / "registry" / "connectors.yaml",
        ]

    @classmethod
    def _find_registry_path(cls) -> Optional[Path]:
        """Find registry file in default locations.

        Returns:
            Path to registry file if found, None otherwise
        """
        for path in cls._get_default_registry_paths():
            if path.exists():
                return path
        return None

    @classmethod
    def from_default_paths(cls) -> "ConnectorRegistry":
        """Create registry instance using default paths.

        This is the recommended way to create a registry instance.
        It searches standard locations and raises clear errors if not found.

        Returns:
            ConnectorRegistry instance

        Raises:
            RegistryNotFoundError: If registry file not found in any default location
            RegistryLoadError: If registry file exists but cannot be loaded
        """
        registry_path = cls._find_registry_path()
        if registry_path is None:
            possible_paths_str = [str(p) for p in cls._get_default_registry_paths()]
            raise RegistryNotFoundError(
                f"Connector registry not found. Tried: {possible_paths_str}\n"
                f"Mount registry/connectors.yaml in Docker image or set DATIVO_REGISTRY_PATH env var."
            )
        return cls(registry_path=registry_path)

    def __init__(
        self,
        registry_path: Optional[Path] = None,
        catalog_loader: Optional[CatalogLoader] = None,
    ):
        """Initialize connector registry.

        Args:
            registry_path: Path to connectors.yaml (if None, searches default paths)
            catalog_loader: Optional catalog loader instance (for testing)

        Raises:
            RegistryNotFoundError: If registry file not found
            RegistryLoadError: If registry file cannot be loaded
        """
        if registry_path is None:
            registry_path = self._find_registry_path()
            if registry_path is None:
                possible_paths_str = [
                    str(p) for p in self._get_default_registry_paths()
                ]
                raise RegistryNotFoundError(
                    f"Connector registry not found. Tried: {possible_paths_str}\n"
                    f"Mount registry/connectors.yaml in Docker image or set DATIVO_REGISTRY_PATH env var."
                )

        if not registry_path.exists():
            raise RegistryNotFoundError(
                f"Connector registry file does not exist: {registry_path}\n"
                f"Mount registry/connectors.yaml in Docker image or set DATIVO_REGISTRY_PATH env var."
            )

        self.registry_path = registry_path
        self.registry_data = self._load_registry()

        # Initialize catalog loader (internal implementation detail)
        self._catalog_loader = catalog_loader or CatalogLoader()

    def _load_registry(self) -> Dict[str, Any]:
        """Load connector registry from YAML.

        Returns:
            Registry data as dictionary

        Raises:
            RegistryLoadError: If file cannot be read or parsed
        """
        try:
            with open(self.registry_path, "r") as f:
                data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise RegistryLoadError(
                f"Failed to parse connector registry YAML: {self.registry_path}\n"
                f"YAML Error: {e}"
            ) from e
        except OSError as e:
            raise RegistryLoadError(
                f"Failed to read connector registry file: {self.registry_path}\n"
                f"Error: {e}"
            ) from e

        if data is None:
            raise RegistryLoadError(
                f"Connector registry file is empty: {self.registry_path}"
            )

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
        strict_mode: bool = True,
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
            strict_mode: If True, raise error if metadata is missing/incomplete

        Returns:
            ResolvedConnector or None if not found

        Raises:
            ValueError: If strict_mode is True and resolution fails
        """
        # Get registry entry
        registry_entry = self.get_connector_entry(connector_name, role)
        if not registry_entry:
            if strict_mode:
                raise ValueError(f"Connector '{connector_name}' not found in registry")
            return None

        # Prepare job overrides (copy to avoid mutating caller's dict)
        overrides = dict(job_overrides) if job_overrides else {}
        if engine:
            overrides["engine"] = engine

        # Determine effective engine
        effective_engine = engine or registry_entry.get("default_engine", "native")

        # Get catalog entry if using external engine (internal implementation detail)
        catalog_entry = None
        if effective_engine in ["airbyte", "singer", "meltano"]:
            # Try to find connector in catalog
            catalog_name = effective_engine
            catalog_entry = self._catalog_loader.get_connector(
                connector_name, catalog_name
            )

            # If not found in specific catalog, try all catalogs
            if not catalog_entry:
                catalog_entry = self._catalog_loader.get_connector(connector_name)

        resolved = ResolvedConnector(
            name=connector_name,
            connector_type=connector_name,
            registry_entry=registry_entry,
            catalog_entry=catalog_entry,
            job_overrides=overrides,
        )

        # Strict validation
        # Only validate docker_image/version for engines that require Docker images
        # Meltano uses Python packages, not Docker images, so it doesn't need docker_image/version
        if strict_mode and effective_engine in ["airbyte", "singer"]:
            if not resolved.docker_image or not resolved.version:
                lookup_key = resolved.external_id or "unknown"
                error_msg = (
                    f"Failed to resolve docker image/version for connector '{connector_name}' "
                    f"using engine '{effective_engine}'.\n"
                    f"Lookup key: {lookup_key}\n"
                    f"Catalog entry found: {'Yes' if catalog_entry else 'No'}\n"
                    f"Please run 'dativo connectors sync {effective_engine}' or provide job override."
                )
                raise ValueError(error_msg)

        return resolved

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
