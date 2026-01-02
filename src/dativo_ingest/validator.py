"""Connector validation and incremental strategy implementation."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .config import JobConfig
from .registry import ConnectorRegistry, RegistryLoadError, RegistryNotFoundError


class ConnectorValidator:
    """Validates job configurations against connector registry."""

    def __init__(self, registry_path: Optional[Path] = None):
        """Initialize validator with registry path.

        Args:
            registry_path: Path to connectors.yaml (if None, uses default paths)

        Raises:
            RegistryNotFoundError: If registry file not found
            RegistryLoadError: If registry file cannot be loaded
        """
        # Use new ConnectorRegistry for enhanced functionality
        if registry_path is None:
            self.registry = ConnectorRegistry.from_default_paths()
        else:
            self.registry = ConnectorRegistry(registry_path=registry_path)

        # Keep old interface for backward compatibility
        self.registry_path = self.registry.registry_path

        # Legacy attribute for compatibility
        # This is the raw YAML data
        self.registry_data = self.registry.registry_data

    def _load_registry(self) -> Dict[str, Any]:
        """Load connector registry from YAML.

        DEPRECATED: This method is kept for backward compatibility.
        Use self.registry instead.

        Returns:
            Registry data as dictionary
        """
        return self.registry.registry_data

    def validate_connector_type(
        self, connector_type: str, role: str = "source"
    ) -> Dict[str, Any]:
        """Validate connector type exists in registry and supports the specified role.

        Args:
            connector_type: Connector type to validate
            role: Role to validate ('source' or 'target')

        Returns:
            Connector definition from registry

        Raises:
            SystemExit: Exit code 2 if connector not found or doesn't support role
        """
        # Use enhanced registry for validation
        entry = self.registry.get_connector_entry(connector_type, role)
        if not entry:
            available = self.registry.list_connectors(role)
            print(
                f"ERROR: Connector type '{connector_type}' not found in registry.\n"
                f"Available {role} connectors: {', '.join(available)}",
                file=sys.stderr,
            )
            sys.exit(2)

        return entry

    def validate_mode_restriction(
        self, connector_type: str, mode: str, connector_def: Dict[str, Any]
    ) -> None:
        """Validate connector is allowed in specified mode.

        Args:
            connector_type: Connector type
            mode: Execution mode (self_hosted or cloud)
            connector_def: Connector definition from registry (already validated)

        Raises:
            SystemExit: Exit code 2 if connector blocked in cloud mode
        """
        # Delegate to registry's validate_connector which handles mode restrictions
        # and prints error messages (avoids duplicate error messages)
        # Extract role from connector_def (should have 'roles' field)
        roles = connector_def.get("roles", ["source"])
        role = roles[0] if roles else "source"

        # This will check mode restriction and print error if needed, then exit
        self.registry.validate_connector(connector_type, role=role, mode=mode)

    def validate_incremental_strategy(
        self, job_config: JobConfig, connector_def: Dict[str, Any]
    ) -> None:
        """Validate incremental strategy configuration.

        Args:
            job_config: Job configuration
            connector_def: Connector definition from registry

        Raises:
            SystemExit: Exit code 2 if strategy is invalid
        """
        source_config = job_config.get_source()

        if not source_config.incremental:
            return  # No incremental config, skip validation

        strategy = source_config.incremental.get("strategy")
        if not strategy:
            print(
                f"ERROR: Incremental configuration missing 'strategy' field.\n"
                f"Connector: {source_config.type}\n"
                f"Config: {job_config.tenant_id}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Check if connector supports incremental
        if not connector_def.get("supports_incremental", False):
            print(
                f"ERROR: Connector '{source_config.type}' does not support incremental extraction.\n"
                f"Config: {job_config.tenant_id}",
                file=sys.stderr,
            )
            sys.exit(2)

        # Validate strategy matches default or is in allowed list
        default_strategy = connector_def.get("incremental_strategy_default")
        if strategy != default_strategy:
            # For file-based strategies, allow if it matches the connector type
            file_strategies = ["file_modified_time", "spreadsheet_modified_time"]
            if strategy not in file_strategies:
                print(
                    f"ERROR: Incremental strategy '{strategy}' does not match connector default '{default_strategy}'.\n"
                    f"Connector: {source_config.type}\n"
                    f"Config: {job_config.tenant_id}",
                    file=sys.stderr,
                )
                sys.exit(2)

        # Validate required fields based on strategy
        if strategy in ["updated_at", "created", "updated_after"]:
            if "cursor_field" not in source_config.incremental:
                print(
                    f"ERROR: Incremental strategy '{strategy}' requires 'cursor_field'.\n"
                    f"Connector: {source_config.type}\n"
                    f"Config: {job_config.tenant_id}",
                    file=sys.stderr,
                )
                sys.exit(2)

        elif strategy == "file_modified_time":
            if not source_config.files:
                print(
                    f"ERROR: Incremental strategy 'file_modified_time' requires 'files' configuration.\n"
                    f"Connector: {source_config.type}\n"
                    f"Config: {job_config.tenant_id}",
                    file=sys.stderr,
                )
                sys.exit(2)

        elif strategy == "spreadsheet_modified_time":
            if not source_config.sheets:
                print(
                    f"ERROR: Incremental strategy 'spreadsheet_modified_time' requires 'sheets' configuration.\n"
                    f"Connector: {source_config.type}\n"
                    f"Config: {job_config.tenant_id}",
                    file=sys.stderr,
                )
                sys.exit(2)

    def validate_image_security(
        self,
        connector_type: str,
        engine_type: str,
        docker_image: Optional[str] = None,
    ) -> None:
        """Validate docker image against security policies.

        Args:
            connector_type: Connector type
            engine_type: Engine type (airbyte, meltano, etc.)
            docker_image: Docker image to validate

        Raises:
            SystemExit: Exit code 2 if image is not allowed
        """
        # Only validate if engine uses docker images (Airbyte mostly)
        if engine_type not in ["airbyte", "meltano", "singer"]:
            return

        if not docker_image:
            return  # Skip if no image (will fail elsewhere if strict)

        # Check allowlist
        allow_custom = (
            os.getenv("DATIVO_ALLOW_CUSTOM_IMAGES", "false").lower() == "true"
        )
        if allow_custom:
            return

        allowed_prefixes = ["airbyte/", "meltano/", "singer/"]

        # Check if image starts with any allowed prefix
        is_allowed = any(docker_image.startswith(prefix) for prefix in allowed_prefixes)

        if not is_allowed:
            print(
                f"ERROR: Security violation for connector '{connector_type}'.\n"
                f"Docker image '{docker_image}' is not allowlisted.\n"
                f"Allowed prefixes: {', '.join(allowed_prefixes)}\n"
                f"To allow custom images, set DATIVO_ALLOW_CUSTOM_IMAGES=true",
                file=sys.stderr,
            )
            sys.exit(2)

    def validate_job(self, job_config: JobConfig, mode: str = "self_hosted") -> None:
        """Validate complete job configuration.

        Args:
            job_config: Job configuration to validate
            mode: Execution mode (self_hosted or cloud)

        Raises:
            SystemExit: Exit code 2 on validation failure
        """
        source_config = job_config.get_source()
        target_config = job_config.get_target()

        # Validate source connector type and role
        source_connector_def = self.validate_connector_type(
            source_config.type, role="source"
        )

        # Validate target connector type and role
        target_connector_def = self.validate_connector_type(
            target_config.type, role="target"
        )

        # Validate mode restrictions for source
        self.validate_mode_restriction(source_config.type, mode, source_connector_def)

        # Validate incremental strategy
        self.validate_incremental_strategy(job_config, source_connector_def)

        # Validate image security (source)
        # Skip validation if custom_reader is used (bypasses engine framework)
        if source_config.custom_reader:
            return

        source_engine = source_config.engine or {}
        engine_type = source_engine.get(
            "type", source_connector_def.get("default_engine")
        )

        # Only validate docker_image/version for engines that require Docker images
        # Meltano uses Python packages, not Docker images, so it doesn't need docker_image/version
        if engine_type in ["airbyte", "singer"]:
            job_overrides = {}
            if (
                source_engine.get("options", {})
                .get(engine_type, {})
                .get("docker_image")
            ):
                job_overrides["docker_image"] = (
                    source_engine.get("options", {})
                    .get(engine_type, {})
                    .get("docker_image")
                )

            # Resolve with strict mode to ensure metadata exists (Requirement C3)
            try:
                resolved = self.registry.resolve_connector(
                    source_config.type,
                    engine=engine_type,
                    job_overrides=job_overrides,
                    strict_mode=True,
                )

                if resolved and resolved.docker_image:
                    self.validate_image_security(
                        source_config.type, engine_type, resolved.docker_image
                    )
            except ValueError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(2)
        elif engine_type == "meltano":
            # Meltano uses Python packages, not Docker images
            # Strict mode is safe for meltano - it validates connector exists but doesn't require docker_image/version
            try:
                resolved = self.registry.resolve_connector(
                    source_config.type,
                    engine=engine_type,
                    job_overrides={},
                    strict_mode=True,  # Safe for meltano - strict validation excludes Docker requirements for meltano
                )
                if not resolved:
                    print(
                        f"ERROR: Connector '{source_config.type}' not found in registry",
                        file=sys.stderr,
                    )
                    sys.exit(2)
            except ValueError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(2)


class IncrementalStateManager:
    """Manages incremental state for file and sheet sources."""

    @staticmethod
    def read_state(state_path: Path) -> Dict[str, Any]:
        """Read incremental state from JSON file.

        Args:
            state_path: Path to state file

        Returns:
            State dictionary (empty dict if file doesn't exist)
        """
        if not state_path.exists():
            return {}

        try:
            with open(state_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    @staticmethod
    def write_state(state_path: Path, state: Dict[str, Any]) -> None:
        """Write incremental state to JSON file.

        Args:
            state_path: Path to state file
            state: State dictionary to write
        """
        # Ensure parent directory exists
        state_path.parent.mkdir(parents=True, exist_ok=True)

        with open(state_path, "w") as f:
            json.dump(state, f, indent=2)

    @staticmethod
    def should_skip_file(
        file_id: str,
        current_modified_time: str,
        state_path: Path,
        lookback_days: int = 0,
    ) -> bool:
        """Check if file should be skipped based on modified time.

        Args:
            file_id: Google Drive file ID
            current_modified_time: Current file modified timestamp (ISO format)
            state_path: Path to state file
            lookback_days: Number of days to look back (0 = only if unchanged)

        Returns:
            True if file should be skipped (not modified)
        """
        state = IncrementalStateManager.read_state(state_path)

        # Check if we have state for this file
        file_key = f"file_{file_id}"
        if file_key not in state:
            return False  # No state, process file

        last_modified = state[file_key].get("last_modified")
        if not last_modified:
            return False  # Invalid state, process file

        # Compare timestamps
        # For simplicity, string comparison works for ISO timestamps
        # If current time is less than or equal to last modified, file hasn't changed
        if current_modified_time <= last_modified:
            # File hasn't been modified since last run
            if lookback_days == 0:
                return True  # Skip if no lookback
            # If lookback_days > 0, we still process files within the lookback window
            # This is handled by the caller, so we return False here
            return False

        return False  # Process file (file has been modified)

    @staticmethod
    def update_file_state(
        file_id: str,
        modified_time: str,
        state_path: Path,
    ) -> None:
        """Update state with file modified time.

        Args:
            file_id: Google Drive file ID
            modified_time: File modified timestamp (ISO format)
            state_path: Path to state file
        """
        state = IncrementalStateManager.read_state(state_path)
        file_key = f"file_{file_id}"
        state[file_key] = {"last_modified": modified_time, "file_id": file_id}
        IncrementalStateManager.write_state(state_path, state)

    @staticmethod
    def should_skip_spreadsheet(
        spreadsheet_id: str,
        current_modified_time: str,
        state_path: Path,
        lookback_days: int = 0,
    ) -> bool:
        """Check if spreadsheet should be skipped based on modified time.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            current_modified_time: Current spreadsheet modified timestamp (ISO format)
            state_path: Path to state file
            lookback_days: Number of days to look back (0 = only if unchanged)

        Returns:
            True if spreadsheet should be skipped (not modified)
        """
        state = IncrementalStateManager.read_state(state_path)

        # Check if we have state for this spreadsheet
        sheet_key = f"spreadsheet_{spreadsheet_id}"
        if sheet_key not in state:
            return False  # No state, process spreadsheet

        last_modified = state[sheet_key].get("last_modified")
        if not last_modified:
            return False  # Invalid state, process spreadsheet

        # Compare timestamps
        if current_modified_time <= last_modified:
            # Spreadsheet hasn't been modified since last run
            if lookback_days == 0:
                return True  # Skip if no lookback

        return False  # Process spreadsheet

    @staticmethod
    def update_spreadsheet_state(
        spreadsheet_id: str,
        modified_time: str,
        state_path: Path,
    ) -> None:
        """Update state with spreadsheet modified time.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            modified_time: Spreadsheet modified timestamp (ISO format)
            state_path: Path to state file
        """
        state = IncrementalStateManager.read_state(state_path)
        sheet_key = f"spreadsheet_{spreadsheet_id}"
        state[sheet_key] = {
            "last_modified": modified_time,
            "spreadsheet_id": spreadsheet_id,
        }
        IncrementalStateManager.write_state(state_path, state)


def initialize_state_directory(job_config: JobConfig) -> None:
    """Initialize state directory for incremental sync tracking.

    Creates the parent directory for the state file if it doesn't exist
    and validates that it's writable.

    Args:
        job_config: Job configuration

    Raises:
        PermissionError: If the state directory is not writable
    """
    source_config = job_config.get_source()
    if source_config.incremental:
        state_path_str = source_config.incremental.get("state_path", "")
        if state_path_str:
            state_path = Path(state_path_str)
            # Create parent directories if they don't exist
            state_path.parent.mkdir(parents=True, exist_ok=True)
            # Validate directory is writable
            if not os.access(state_path.parent, os.W_OK):
                raise PermissionError(
                    f"State directory is not writable: {state_path.parent}"
                )
