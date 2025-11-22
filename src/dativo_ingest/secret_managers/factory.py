"""Factory for creating secret manager instances."""

import logging
import os
from typing import Any, Dict, Optional

from .base import SecretManager
from .env_manager import EnvSecretManager
from .filesystem_manager import FilesystemSecretManager

logger = logging.getLogger(__name__)


def create_secret_manager(
    manager_type: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
) -> SecretManager:
    """Create a secret manager instance based on type and configuration.
    
    The manager type is determined by (in order of precedence):
    1. Explicit manager_type parameter
    2. SECRET_MANAGER_TYPE environment variable
    3. Detection based on available configuration/environment
    4. Default to 'env' (environment variables)
    
    Supported manager types:
    - 'env': Environment variables (default)
    - 'filesystem': Filesystem-based storage (backward compatibility)
    - 'vault': HashiCorp Vault
    - 'aws': AWS Secrets Manager
    - 'gcp': Google Cloud Secret Manager
    
    Args:
        manager_type: Type of secret manager to create (optional)
        config: Configuration for the secret manager (optional)
        
    Returns:
        Initialized SecretManager instance
        
    Raises:
        ValueError: If manager type is invalid or required config is missing
        ImportError: If required library for cloud provider is not installed
    """
    config = config or {}
    
    # Determine manager type
    if manager_type is None:
        manager_type = os.getenv("SECRET_MANAGER_TYPE")
    
    if manager_type is None:
        # Auto-detect based on configuration/environment
        manager_type = _auto_detect_manager_type(config)
    
    manager_type = manager_type.lower()
    
    logger.info(f"Creating secret manager of type: {manager_type}")
    
    # Create appropriate manager
    if manager_type == "env":
        return EnvSecretManager(config)
    
    elif manager_type == "filesystem":
        return FilesystemSecretManager(config)
    
    elif manager_type == "vault":
        try:
            from .vault_manager import HashiCorpVaultSecretManager
            return HashiCorpVaultSecretManager(config)
        except ImportError as e:
            raise ImportError(
                f"Failed to load HashiCorp Vault manager: {e}. "
                "Install required dependencies with: pip install hvac"
            )
    
    elif manager_type == "aws":
        try:
            from .aws_manager import AWSSecretManager
            return AWSSecretManager(config)
        except ImportError as e:
            raise ImportError(
                f"Failed to load AWS Secrets Manager: {e}. "
                "Install required dependencies with: pip install boto3"
            )
    
    elif manager_type == "gcp":
        try:
            from .gcp_manager import GCPSecretManager
            return GCPSecretManager(config)
        except ImportError as e:
            raise ImportError(
                f"Failed to load GCP Secret Manager: {e}. "
                "Install required dependencies with: pip install google-cloud-secretmanager"
            )
    
    else:
        raise ValueError(
            f"Unknown secret manager type: {manager_type}. "
            f"Supported types: env, filesystem, vault, aws, gcp"
        )


def _auto_detect_manager_type(config: Dict[str, Any]) -> str:
    """Auto-detect the appropriate secret manager type.
    
    Detection logic:
    1. If VAULT_ADDR or vault URL in config -> vault
    2. If AWS_SECRETS_MANAGER or aws config present -> aws
    3. If GOOGLE_CLOUD_PROJECT or gcp config present -> gcp
    4. If /secrets directory exists -> filesystem (backward compatibility)
    5. Default to env
    
    Args:
        config: Configuration dictionary
        
    Returns:
        Detected manager type
    """
    # Check for Vault
    if os.getenv("VAULT_ADDR") or config.get("vault", {}).get("url"):
        logger.info("Auto-detected Vault configuration")
        return "vault"
    
    # Check for AWS Secrets Manager
    if os.getenv("AWS_SECRETS_MANAGER") or config.get("aws"):
        logger.info("Auto-detected AWS Secrets Manager configuration")
        return "aws"
    
    # Check for GCP Secret Manager
    if os.getenv("GOOGLE_CLOUD_PROJECT") or config.get("gcp"):
        logger.info("Auto-detected GCP Secret Manager configuration")
        return "gcp"
    
    # Check for filesystem secrets directory (backward compatibility)
    secrets_dir = config.get("secrets_dir", "/secrets")
    if os.path.exists(secrets_dir) and os.path.isdir(secrets_dir):
        logger.info(f"Auto-detected filesystem secrets directory: {secrets_dir}")
        return "filesystem"
    
    # Default to environment variables
    logger.info("No specific secret manager detected, defaulting to environment variables")
    return "env"


def create_secret_manager_from_env() -> SecretManager:
    """Create a secret manager using only environment variables for configuration.
    
    This is a convenience function for simple setups where all configuration
    comes from environment variables.
    
    Supported environment variables:
    - SECRET_MANAGER_TYPE: Type of secret manager (env, filesystem, vault, aws, gcp)
    - SECRET_MANAGER_CONFIG: JSON string with additional configuration
    
    Returns:
        Initialized SecretManager instance
    """
    import json
    
    manager_type = os.getenv("SECRET_MANAGER_TYPE")
    config_str = os.getenv("SECRET_MANAGER_CONFIG")
    
    config = {}
    if config_str:
        try:
            config = json.loads(config_str)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse SECRET_MANAGER_CONFIG: {e}")
    
    return create_secret_manager(manager_type=manager_type, config=config)
