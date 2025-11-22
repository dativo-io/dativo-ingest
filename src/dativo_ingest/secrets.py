"""Secrets management for loading and validating credentials from filesystem storage and other managers."""

import os
import re
from pathlib import Path
from typing import Any, Dict

from .secret_managers import (
    CompositeSecretManager,
    EnvSecretManager,
    FilesystemSecretManager,
    get_secret_manager,
)


def resolve_secret_path(file_template: str, tenant_id: str) -> Path:
    """Resolve secret file path from template.

    Args:
        file_template: Template path with {tenant} placeholder (e.g., "/secrets/{tenant}/gsheets.json")
        tenant_id: Tenant identifier

    Returns:
        Resolved Path object
    """
    resolved_path = file_template.format(tenant=tenant_id)
    # Expand environment variables in path
    resolved_path = os.path.expandvars(resolved_path)
    return Path(resolved_path)


def load_secrets(
    tenant_id: str, secrets_dir: Path = Path("/secrets")
) -> Dict[str, Any]:
    """Load secrets for a tenant from secrets storage.

    Args:
        tenant_id: Tenant identifier
        secrets_dir: Base directory for secrets (default: /secrets)

    Returns:
        Dictionary of loaded secrets, keyed by secret file name (without extension)

    Raises:
        ValueError: If secrets directory doesn't exist (only for filesystem manager)
    """
    manager_type = os.getenv("DATIVO_SECRET_MANAGER")
    
    if manager_type:
        # User explicitly selected a manager
        manager = get_secret_manager(tenant_id, secrets_dir)
    else:
        # Default behavior: Env + Filesystem (Env overrides Filesystem)
        env_manager = EnvSecretManager(tenant_id)
        fs_manager = FilesystemSecretManager(tenant_id, secrets_dir)
        manager = CompositeSecretManager([env_manager, fs_manager])

    return manager.list_secrets()


def validate_secrets_for_connector(
    secrets: Dict[str, Any], connector_type: str, credentials_config: Dict[str, Any]
) -> bool:
    """Validate that required secrets are present for a connector.

    Args:
        secrets: Dictionary of loaded secrets
        connector_type: Type of connector (e.g., "stripe", "postgres", "iceberg")
        credentials_config: Credentials configuration from connector recipe

    Returns:
        True if all required secrets are present

    Raises:
        ValueError: If required secrets are missing
    """
    required_secrets = []

    # Check credentials configuration
    cred_type = credentials_config.get("type", "none")
    if cred_type == "none":
        return True  # No credentials needed

    # Check for file_template
    if "file_template" in credentials_config:
        file_template = credentials_config["file_template"]
        # Extract secret name from template (e.g., "/secrets/{tenant}/gsheets.json" -> "gsheets")
        match = re.search(r"/([^/]+)\.(json|env|txt|key)$", file_template)
        if match:
            secret_name = match.group(1)
            required_secrets.append(secret_name)

    # Connector-specific requirements
    if connector_type == "stripe":
        if "stripe_api_key" not in secrets and "api_key" not in secrets:
            required_secrets.append("stripe_api_key")
    elif connector_type == "hubspot":
        if "hubspot_api_key" not in secrets and "api_key" not in secrets:
            required_secrets.append("hubspot_api_key")
    elif connector_type in ["postgres", "mysql"]:
        # Database connectors need connection info in .env file
        db_name = connector_type
        if db_name not in secrets:
            required_secrets.append(f"{db_name}.env")
    elif connector_type == "iceberg":
        # Iceberg needs Nessie URI and S3 credentials
        if "iceberg" not in secrets and "nessie" not in secrets:
            # Check if individual env vars are set
            if not os.getenv("NESSIE_URI"):
                required_secrets.append("iceberg.env or NESSIE_URI env var")

    # Validate all required secrets are present
    missing_secrets = []
    for secret_name in required_secrets:
        # Check if secret exists (handle .env suffix)
        found = False
        for key in secrets.keys():
            if key == secret_name or key.startswith(secret_name):
                found = True
                break
        if not found:
            missing_secrets.append(secret_name)

    if missing_secrets:
        raise ValueError(
            f"Missing required secrets for connector '{connector_type}': {', '.join(missing_secrets)}"
        )

    return True
