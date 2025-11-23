"""Validation utilities for secrets."""

import os
import re
from typing import Any, Dict, List


def validate_secrets_for_connector(
    secrets: Dict[str, Any], connector_type: str, credentials_config: Dict[str, Any]
) -> bool:
    """Validate that required secrets are present for a connector.

    Args:
        secrets: Dictionary of loaded secrets
        connector_type: Type of connector (e.g., "postgres", "stripe")
        credentials_config: Connector credentials configuration

    Returns:
        True if validation passes

    Raises:
        ValueError: If required secrets are missing
    """
    required_secrets: List[str] = []

    # Check credentials configuration
    cred_type = credentials_config.get("type", "none")
    if cred_type == "none":
        return True  # No credentials needed

    # Check for file_template
    if "file_template" in credentials_config:
        file_template = credentials_config["file_template"]
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
        db_name = connector_type
        if db_name not in secrets:
            required_secrets.append(f"{db_name}.env")
    elif connector_type == "iceberg":
        if "iceberg" not in secrets and "nessie" not in secrets:
            if not os.getenv("NESSIE_URI"):
                required_secrets.append("iceberg.env or NESSIE_URI env var")

    missing_secrets = []
    for secret_name in required_secrets:
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
