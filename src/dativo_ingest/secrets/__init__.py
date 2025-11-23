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

from pathlib import Path
from typing import Any, Dict, Optional

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


# Re-export for backwards compatibility
from .base import resolve_secret_path
from .validation import validate_secrets_for_connector
