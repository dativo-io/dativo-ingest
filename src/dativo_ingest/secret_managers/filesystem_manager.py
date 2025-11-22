"""Filesystem-based secret manager (backward compatibility)."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from .base import SecretManager

logger = logging.getLogger(__name__)


class FilesystemSecretManager(SecretManager):
    """Secret manager that reads credentials from filesystem storage.
    
    This is the original/legacy secret manager, preserved for backward compatibility.
    It loads secrets from files in a directory structure: {secrets_dir}/{tenant}/
    
    Supported file formats:
    - .json: JSON files with structured credentials
    - .env: Environment-style key=value files
    - .txt/.key: Plain text files
    
    Configuration options:
        - secrets_dir: Base directory for secrets (default: /secrets)
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize filesystem secret manager.
        
        Args:
            config: Configuration with optional secrets_dir
        """
        super().__init__(config)
        secrets_dir = self.config.get("secrets_dir", "/secrets")
        self.secrets_dir = Path(secrets_dir)

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from filesystem for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of loaded secrets, keyed by secret file name
            
        Raises:
            ValueError: If secrets directory doesn't exist
        """
        tenant_secrets_dir = self.secrets_dir / tenant_id
        
        if not tenant_secrets_dir.exists():
            raise ValueError(f"Secrets directory not found: {tenant_secrets_dir}")

        secrets = {}

        # Load all secret files
        for secret_file in tenant_secrets_dir.iterdir():
            if secret_file.is_file() and not secret_file.name.startswith("."):
                secret_name = secret_file.stem  # filename without extension
                try:
                    if secret_file.suffix == ".json":
                        secrets[secret_name] = self._load_json_file(secret_file)
                    elif secret_file.suffix == ".env":
                        secrets[secret_name] = self._load_env_file(secret_file)
                    else:
                        secrets[secret_name] = self._load_text_file(secret_file)
                except Exception as e:
                    logger.warning(
                        f"Failed to load secret file {secret_file}: {e}",
                        extra={"secret_file": str(secret_file), "error": str(e)},
                    )

        return secrets

    def _load_json_file(self, file_path: Path) -> Dict[str, Any]:
        """Load and parse a JSON secret file.
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            Parsed JSON content with environment variables expanded
        """
        with open(file_path, "r") as f:
            content = json.load(f)
            return self.expand_env_vars(content)

    def _load_env_file(self, file_path: Path) -> Dict[str, Any]:
        """Load and parse a .env file.
        
        Args:
            file_path: Path to .env file
            
        Returns:
            Dictionary of key-value pairs
        """
        env_vars = {}
        with open(file_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    if "=" in line:
                        key, value = line.split("=", 1)
                        key = key.strip()
                        value = value.strip().strip('"').strip("'")
                        # Expand environment variables
                        value = os.path.expandvars(value)
                        env_vars[key] = value
        return env_vars

    def _load_text_file(self, file_path: Path) -> str:
        """Load a plain text secret file.
        
        Args:
            file_path: Path to text file
            
        Returns:
            File contents with environment variables expanded
        """
        with open(file_path, "r") as f:
            content = f.read().strip()
            return os.path.expandvars(content)

    def resolve_secret_path(self, file_template: str, tenant_id: str) -> Path:
        """Resolve secret file path from template.
        
        Args:
            file_template: Template path with {tenant} placeholder
            tenant_id: Tenant identifier
            
        Returns:
            Resolved Path object
        """
        resolved_path = file_template.format(tenant=tenant_id)
        resolved_path = os.path.expandvars(resolved_path)
        return Path(resolved_path)
