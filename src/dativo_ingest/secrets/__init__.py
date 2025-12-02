"""Pluggable secret management system with multiple backend support.

This package provides a unified interface for loading secrets from various sources:
- Environment variables
- Filesystem directories
- HashiCorp Vault
- AWS Secrets Manager
- Google Cloud Secret Manager

The main entry point is the `load_secrets()` function, which automatically
instantiates and uses the appropriate secret manager based on configuration.
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .base import SecretManager
from .managers import (
    AWSSecretsManager,
    EnvironmentSecretManager,
    FilesystemSecretManager,
    GCPSecretManager,
    HashicorpVaultSecretManager,
)

# Public API
__all__ = [
    "load_secrets",
    "load_secrets_and_set_env",
    "load_secret_manager_config",
    "create_secret_manager",
    "SecretManager",
    "EnvironmentSecretManager",
    "FilesystemSecretManager",
    "HashiCorpVaultSecretManager",
    "AWSSecretsManager",
    "GCPSecretManager",
    "validate_secrets_for_connector",
    "resolve_secret_path",
]

# Registry mapping manager type names to their classes
_SECRET_MANAGER_REGISTRY: Dict[str, type[SecretManager]] = {
    "env": EnvironmentSecretManager,
    "environment": EnvironmentSecretManager,
    "filesystem": FilesystemSecretManager,
    "fs": FilesystemSecretManager,
    "file": FilesystemSecretManager,
    "vault": HashicorpVaultSecretManager,
    "hashicorp": HashicorpVaultSecretManager,
    "hashicorp_vault": HashicorpVaultSecretManager,
    "aws": AWSSecretsManager,
    "aws_secrets_manager": AWSSecretsManager,
    "gcp": GCPSecretManager,
    "gcp_secret_manager": GCPSecretManager,
}


def create_secret_manager(
    manager_type: Optional[str],
    secrets_dir: Path = Path("/secrets"),
    config: Optional[Dict[str, Any]] = None,
) -> SecretManager:
    """Instantiate the requested secret manager.

    Args:
        manager_type: Type identifier for the secret manager (e.g., "env", "vault")
        secrets_dir: Base directory for filesystem manager (default: /secrets)
        config: Optional configuration dictionary passed to the manager

    Returns:
        Instantiated SecretManager

    Raises:
        ValueError: If manager_type is not supported
    """
    normalized = (manager_type or "env").lower()
    manager_cls = _SECRET_MANAGER_REGISTRY.get(normalized)
    if not manager_cls:
        supported_types = sorted(set(_SECRET_MANAGER_REGISTRY.keys()))
        raise ValueError(
            f"Unsupported secret manager '{manager_type}'. "
            f"Supported managers: {supported_types}"
        )

    config = config or {}
    if manager_cls is FilesystemSecretManager and "secrets_dir" not in config:
        config = {**config, "secrets_dir": secrets_dir}

    return manager_cls(**config)


def load_secrets(
    tenant_id: str,
    secrets_dir: Path = Path("/secrets"),
    manager_type: Optional[str] = None,
    manager_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load secrets using the configured secret manager.

    This is the main entry point for loading secrets. It automatically
    instantiates the appropriate secret manager and loads secrets for
    the given tenant.

    Args:
        tenant_id: Tenant identifier
        secrets_dir: Base directory for filesystem manager fallback
        manager_type: Secret manager identifier (env, filesystem, vault, aws, gcp)
        manager_config: Optional configuration dictionary passed to the manager

    Returns:
        Dictionary of loaded secrets (may be empty if manager has nothing to return)
    """
    manager = create_secret_manager(
        manager_type=manager_type or "env",
        secrets_dir=secrets_dir,
        config=manager_config,
    )
    return manager.load_secrets(tenant_id)


def load_secret_manager_config(
    config_arg: Optional[str],
) -> Optional[Dict[str, Any]]:
    """Load secret manager configuration from path or inline JSON.

    Args:
        config_arg: Path to YAML/JSON file, inline JSON string, or None.
                    Falls back to DATIVO_SECRET_MANAGER_CONFIG env var if None.

    Returns:
        Configuration dictionary or None if not provided

    Raises:
        ValueError: If config file format is invalid or JSON is malformed
    """
    candidate = config_arg or os.getenv("DATIVO_SECRET_MANAGER_CONFIG")
    if not candidate:
        return None

    candidate_path = Path(candidate)
    if candidate_path.exists():
        with open(candidate_path, "r", encoding="utf-8") as handle:
            content = handle.read()
        suffix = candidate_path.suffix.lower()
        if suffix in {".yaml", ".yml"}:
            return yaml.safe_load(content) or {}
        if suffix == ".json":
            return json.loads(content or "{}")
        # Fall back to JSON parsing for arbitrary extensions
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Secret manager config file '{candidate_path}' must be YAML or JSON."
            ) from exc

    # Treat argument as inline JSON
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        raise ValueError(
            "Secret manager config must be a path to a YAML/JSON file or a JSON string."
        ) from exc


def load_secrets_and_set_env(
    tenant_id: str,
    secrets_dir: Path,
    manager_type: str = "env",
    manager_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load secrets and set them as environment variables.

    This function loads secrets using the configured secret manager and
    automatically sets them as environment variables for use by connectors.
    Secrets from .env files are flattened into individual environment variables.

    Args:
        tenant_id: Tenant identifier
        secrets_dir: Base directory for filesystem manager
        manager_type: Secret manager identifier (env, filesystem, vault, aws, gcp)
        manager_config: Optional configuration dictionary passed to the manager

    Returns:
        Dictionary of loaded secrets (may be empty if loading fails)

    Note:
        Existing environment variables are not overwritten.
    """
    secrets = {}
    try:
        secrets = load_secrets(
            tenant_id=tenant_id,
            secrets_dir=secrets_dir,
            manager_type=manager_type,
            manager_config=manager_config,
        )

        # Set environment variables from loaded secrets
        # Secrets from .env files are parsed as dictionaries, so we need to flatten them
        for secret_name, secret_value in secrets.items():
            if isinstance(secret_value, dict):
                # For .env files, secret_value is a dict of KEY=VALUE pairs
                for key, value in secret_value.items():
                    if key not in os.environ:
                        os.environ[key] = str(value)
            elif isinstance(secret_value, (str, int, float, bool)):
                # For simple values, use the secret name as the env var name
                if secret_name.upper() not in os.environ:
                    os.environ[secret_name.upper()] = str(secret_value)

        # For filesystem manager, set environment variables from loaded secrets
        # This allows config values like ${VAR} to be expanded
        if manager_type == "filesystem":
            for secret_name, secret_value in secrets.items():
                if isinstance(secret_value, dict):
                    # For .env files, secret_value is a dict of KEY=VALUE pairs
                    for key, value in secret_value.items():
                        if isinstance(value, str) and key not in os.environ:
                            os.environ[key] = value
    except ValueError:
        # Secret loading failures are handled gracefully
        # Return empty dict to allow execution to continue
        pass

    return secrets


# Re-export for backwards compatibility
from .base import resolve_secret_path
from .validation import validate_secrets_for_connector
