"""Base abstract class for secret managers."""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class SecretManager(ABC):
    """Abstract base class for secret management backends.
    
    All secret managers must implement methods to:
    - Load secrets for a given tenant
    - Retrieve individual secret values
    - Check if a secret exists
    - Validate required secrets for connectors
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """Initialize the secret manager with optional configuration.
        
        Args:
            config: Backend-specific configuration options
        """
        self.config = config or {}

    @abstractmethod
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load all secrets for a given tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of secrets keyed by secret name
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        pass

    def get_secret(self, tenant_id: str, secret_name: str) -> Optional[Any]:
        """Retrieve a specific secret value.
        
        Args:
            tenant_id: Tenant identifier
            secret_name: Name of the secret to retrieve
            
        Returns:
            Secret value or None if not found
        """
        secrets = self.load_secrets(tenant_id)
        return secrets.get(secret_name)

    def has_secret(self, tenant_id: str, secret_name: str) -> bool:
        """Check if a secret exists.
        
        Args:
            tenant_id: Tenant identifier
            secret_name: Name of the secret to check
            
        Returns:
            True if the secret exists, False otherwise
        """
        try:
            return self.get_secret(tenant_id, secret_name) is not None
        except Exception:
            return False

    @staticmethod
    def expand_env_vars(value: Any) -> Any:
        """Recursively expand environment variables in values.
        
        Args:
            value: String, dict, list, or other value to process
            
        Returns:
            Value with environment variables expanded
        """
        if isinstance(value, dict):
            return {k: SecretManager.expand_env_vars(v) for k, v in value.items()}
        elif isinstance(value, list):
            return [SecretManager.expand_env_vars(item) for item in value]
        elif isinstance(value, str):
            return os.path.expandvars(value)
        else:
            return value

    def validate_secrets_for_connector(
        self,
        tenant_id: str,
        connector_type: str,
        credentials_config: Dict[str, Any],
    ) -> bool:
        """Validate that required secrets are present for a connector.
        
        Args:
            tenant_id: Tenant identifier
            connector_type: Type of connector (e.g., "stripe", "postgres")
            credentials_config: Credentials configuration from connector recipe
            
        Returns:
            True if all required secrets are present
            
        Raises:
            ValueError: If required secrets are missing
        """
        import re

        required_secrets = []
        secrets = self.load_secrets(tenant_id)

        # Check credentials configuration
        cred_type = credentials_config.get("type", "none")
        if cred_type == "none":
            return True  # No credentials needed

        # Check for file_template (legacy filesystem approach)
        if "file_template" in credentials_config:
            file_template = credentials_config["file_template"]
            # Extract secret name from template
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

        # Validate all required secrets are present
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
