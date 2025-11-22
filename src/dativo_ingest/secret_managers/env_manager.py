"""Environment variable-based secret manager (new default)."""

import json
import os
from typing import Any, Dict

from .base import SecretManager


class EnvSecretManager(SecretManager):
    """Secret manager that reads credentials from environment variables.
    
    This is the new default secret manager. It supports several naming conventions:
    
    1. Tenant-specific secrets: {TENANT}_{SECRET_NAME}
       Example: ACME_STRIPE_API_KEY
    
    2. Generic secrets (shared across tenants): {SECRET_NAME}
       Example: STRIPE_API_KEY
    
    3. Structured JSON secrets: {TENANT}_{SECRET_NAME}_JSON
       Example: ACME_GSHEETS_JSON='{"type":"service_account",...}'
    
    Configuration options:
        - prefix: Optional prefix for all environment variables (default: none)
        - uppercase: Convert secret names to uppercase (default: True)
        - allow_generic: Allow non-tenant-specific secrets as fallback (default: True)
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize environment variable secret manager.
        
        Args:
            config: Configuration options
        """
        super().__init__(config)
        self.prefix = self.config.get("prefix", "")
        self.uppercase = self.config.get("uppercase", True)
        self.allow_generic = self.config.get("allow_generic", True)

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from environment variables for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of secrets loaded from environment variables
        """
        secrets = {}
        tenant_prefix = self._normalize_name(tenant_id)

        # Scan environment variables for tenant-specific and generic secrets
        for key, value in os.environ.items():
            # Skip if doesn't match our prefix
            if self.prefix and not key.startswith(self.prefix):
                continue

            # Remove global prefix if present
            working_key = key[len(self.prefix):] if self.prefix else key

            # Check for tenant-specific secret
            if working_key.startswith(f"{tenant_prefix}_"):
                secret_name = working_key[len(tenant_prefix) + 1:]
                secrets[self._denormalize_name(secret_name)] = self._parse_value(value)
            
            # Check for generic secret (if allowed)
            elif self.allow_generic and not working_key.startswith("_"):
                # Don't override tenant-specific secrets
                denorm_name = self._denormalize_name(working_key)
                if denorm_name not in secrets:
                    secrets[denorm_name] = self._parse_value(value)

        # Also check for commonly-used secret patterns
        secrets = self._load_common_patterns(tenant_id, secrets)
        
        return secrets

    def _load_common_patterns(self, tenant_id: str, secrets: Dict[str, Any]) -> Dict[str, Any]:
        """Load commonly-used secret naming patterns.
        
        Args:
            tenant_id: Tenant identifier
            secrets: Existing secrets dictionary to augment
            
        Returns:
            Updated secrets dictionary
        """
        tenant_prefix = self._normalize_name(tenant_id)
        
        # Common database patterns
        db_patterns = {
            "postgres": ["PGHOST", "PGPORT", "PGDATABASE", "PGUSER", "PGPASSWORD"],
            "mysql": ["MYSQL_HOST", "MYSQL_PORT", "MYSQL_DATABASE", "MYSQL_USER", "MYSQL_PASSWORD"],
        }
        
        for db_type, env_vars in db_patterns.items():
            db_config = {}
            for env_var in env_vars:
                # Check tenant-specific first
                tenant_var = f"{tenant_prefix}_{env_var}"
                value = os.getenv(tenant_var)
                
                # Fall back to generic if allowed
                if value is None and self.allow_generic:
                    value = os.getenv(env_var)
                
                if value is not None:
                    db_config[env_var] = value
            
            # Store as structured config if we found any values
            if db_config and db_type not in secrets:
                secrets[db_type] = db_config
        
        # Common API key patterns
        api_patterns = [
            "STRIPE_API_KEY",
            "HUBSPOT_API_KEY",
            "NESSIE_URI",
            "AWS_ACCESS_KEY_ID",
            "AWS_SECRET_ACCESS_KEY",
            "MINIO_ACCESS_KEY",
            "MINIO_SECRET_KEY",
        ]
        
        for pattern in api_patterns:
            key_name = self._denormalize_name(pattern)
            if key_name not in secrets:
                # Check tenant-specific
                tenant_var = f"{tenant_prefix}_{pattern}"
                value = os.getenv(tenant_var)
                
                # Fall back to generic if allowed
                if value is None and self.allow_generic:
                    value = os.getenv(pattern)
                
                if value is not None:
                    secrets[key_name] = value
        
        return secrets

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for use in environment variable lookup.
        
        Args:
            name: Name to normalize
            
        Returns:
            Normalized name
        """
        if self.uppercase:
            return name.upper().replace("-", "_").replace(".", "_")
        return name.replace("-", "_").replace(".", "_")

    def _denormalize_name(self, name: str) -> str:
        """Convert environment variable name back to secret name.
        
        Args:
            name: Environment variable name
            
        Returns:
            Denormalized secret name (lowercase with underscores)
        """
        # Remove _JSON suffix if present
        if name.endswith("_JSON"):
            name = name[:-5]
        
        return name.lower()

    def _parse_value(self, value: str) -> Any:
        """Parse environment variable value, handling JSON if present.
        
        Args:
            value: Raw environment variable value
            
        Returns:
            Parsed value (dict if JSON, string otherwise)
        """
        # Try to parse as JSON
        value = value.strip()
        if (value.startswith("{") and value.endswith("}")) or \
           (value.startswith("[") and value.endswith("]")):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                pass
        
        # Return as-is, expanding any nested environment variables
        return self.expand_env_vars(value)
