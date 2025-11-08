"""Secrets management for loading and validating credentials from multiple secret managers."""

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SecretManager(ABC):
    """Base class for secret managers."""
    
    @abstractmethod
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of loaded secrets, keyed by secret name
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        pass


class EnvironmentSecretManager(SecretManager):
    """Load secrets from environment variables.
    
    This is the default secret manager. It reads secrets from environment variables
    with the pattern: {TENANT_ID}_{SECRET_NAME} or just {SECRET_NAME}.
    """
    
    def __init__(self, prefix: Optional[str] = None):
        """Initialize environment secret manager.
        
        Args:
            prefix: Optional prefix for environment variables (e.g., "DATIVO_")
        """
        self.prefix = prefix or ""
    
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from environment variables.
        
        Looks for environment variables in the following order:
        1. {PREFIX}{TENANT_ID}_{SECRET_NAME}
        2. {PREFIX}{SECRET_NAME}
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of loaded secrets
        """
        secrets = {}
        tenant_prefix = f"{self.prefix}{tenant_id.upper()}_"
        
        # Scan all environment variables
        for key, value in os.environ.items():
            # Check if it matches tenant-specific pattern
            if key.startswith(tenant_prefix):
                secret_name = key[len(tenant_prefix):].lower()
                secrets[secret_name] = value
            # Check if it matches general pattern with prefix
            elif self.prefix and key.startswith(self.prefix):
                secret_name = key[len(self.prefix):].lower()
                if secret_name not in secrets:  # Don't override tenant-specific
                    secrets[secret_name] = value
        
        logger.info(
            f"Loaded {len(secrets)} secrets from environment variables for tenant {tenant_id}",
            extra={"tenant_id": tenant_id, "secret_count": len(secrets)}
        )
        
        return secrets


class FilesystemSecretManager(SecretManager):
    """Load secrets from filesystem storage (original implementation)."""
    
    def __init__(self, secrets_dir: Path = Path("/secrets")):
        """Initialize filesystem secret manager.
        
        Args:
            secrets_dir: Base directory for secrets (default: /secrets)
        """
        self.secrets_dir = secrets_dir
    
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets for a tenant from secrets storage.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of loaded secrets, keyed by secret file name (without extension)
            
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
                        # Load JSON file
                        with open(secret_file, "r") as f:
                            content = json.load(f)
                            # Expand environment variables in JSON values
                            secrets[secret_name] = _expand_env_vars_in_dict(content)
                    elif secret_file.suffix == ".env":
                        # Load .env file (key=value format)
                        env_vars = {}
                        with open(secret_file, "r") as f:
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
                        secrets[secret_name] = env_vars
                    else:
                        # Load plain text file
                        with open(secret_file, "r") as f:
                            content = f.read().strip()
                            # Expand environment variables
                            content = os.path.expandvars(content)
                            secrets[secret_name] = content
                except Exception as e:
                    # Log warning but continue loading other secrets
                    logger.warning(
                        f"Failed to load secret file {secret_file}: {e}",
                        extra={"secret_file": str(secret_file), "error": str(e)},
                    )
        
        return secrets


class HashiCorpVaultSecretManager(SecretManager):
    """Load secrets from HashiCorp Vault."""
    
    def __init__(
        self,
        url: str,
        token: Optional[str] = None,
        mount_point: str = "secret",
        namespace: Optional[str] = None,
        verify: bool = True
    ):
        """Initialize HashiCorp Vault secret manager.
        
        Args:
            url: Vault server URL (e.g., "https://vault.example.com:8200")
            token: Vault token (if None, reads from VAULT_TOKEN env var)
            mount_point: KV secrets engine mount point (default: "secret")
            namespace: Vault namespace (optional)
            verify: Whether to verify SSL certificates (default: True)
        """
        try:
            import hvac
        except ImportError:
            raise ImportError(
                "hvac library not installed. Install with: pip install hvac"
            )
        
        self.url = url
        self.token = token or os.getenv("VAULT_TOKEN")
        self.mount_point = mount_point
        self.namespace = namespace
        self.verify = verify
        
        if not self.token:
            raise ValueError("Vault token not provided. Set VAULT_TOKEN environment variable or pass token parameter.")
        
        self.client = hvac.Client(
            url=self.url,
            token=self.token,
            namespace=self.namespace,
            verify=self.verify
        )
        
        if not self.client.is_authenticated():
            raise ValueError(f"Failed to authenticate with Vault at {self.url}")
    
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from Vault KV store.
        
        Reads secrets from path: {mount_point}/data/{tenant_id}
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of loaded secrets
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        try:
            # For KV v2, path is: {mount_point}/data/{tenant_id}
            response = self.client.secrets.kv.v2.read_secret_version(
                path=tenant_id,
                mount_point=self.mount_point
            )
            
            secrets = response.get("data", {}).get("data", {})
            
            logger.info(
                f"Loaded {len(secrets)} secrets from Vault for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "secret_count": len(secrets)}
            )
            
            return secrets
        except Exception as e:
            raise ValueError(f"Failed to load secrets from Vault for tenant {tenant_id}: {e}")


class AWSSecretsManagerSecretManager(SecretManager):
    """Load secrets from AWS Secrets Manager."""
    
    def __init__(
        self,
        region_name: Optional[str] = None,
        prefix: Optional[str] = None
    ):
        """Initialize AWS Secrets Manager secret manager.
        
        Args:
            region_name: AWS region (if None, uses default from boto3 config)
            prefix: Optional prefix for secret names (e.g., "dativo/")
        """
        try:
            import boto3
        except ImportError:
            raise ImportError(
                "boto3 library not installed. Install with: pip install boto3"
            )
        
        self.region_name = region_name
        self.prefix = prefix or ""
        self.client = boto3.client('secretsmanager', region_name=region_name)
    
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from AWS Secrets Manager.
        
        Looks for secrets with the pattern: {prefix}{tenant_id}/{secret_name}
        or a single secret named: {prefix}{tenant_id}
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of loaded secrets
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        secrets = {}
        secret_name = f"{self.prefix}{tenant_id}"
        
        try:
            # Try to load a single secret for the tenant
            response = self.client.get_secret_value(SecretId=secret_name)
            
            # Parse the secret value
            if 'SecretString' in response:
                secret_value = response['SecretString']
                try:
                    # Try to parse as JSON
                    secrets = json.loads(secret_value)
                except json.JSONDecodeError:
                    # If not JSON, store as single value
                    secrets = {"value": secret_value}
            else:
                # Binary secret
                secrets = {"value": response['SecretBinary']}
            
            logger.info(
                f"Loaded secrets from AWS Secrets Manager for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "secret_count": len(secrets)}
            )
            
        except self.client.exceptions.ResourceNotFoundException:
            # Try to list secrets with tenant prefix
            try:
                paginator = self.client.get_paginator('list_secrets')
                for page in paginator.paginate(
                    Filters=[
                        {'Key': 'name', 'Values': [f"{secret_name}/"]}
                    ]
                ):
                    for secret in page['SecretList']:
                        # Extract secret name after tenant prefix
                        full_name = secret['Name']
                        if full_name.startswith(f"{secret_name}/"):
                            key = full_name[len(f"{secret_name}/"):]
                            
                            # Get secret value
                            response = self.client.get_secret_value(SecretId=full_name)
                            if 'SecretString' in response:
                                secrets[key] = response['SecretString']
                            else:
                                secrets[key] = response['SecretBinary']
                
                if not secrets:
                    logger.warning(
                        f"No secrets found in AWS Secrets Manager for tenant {tenant_id}",
                        extra={"tenant_id": tenant_id}
                    )
            except Exception as e:
                raise ValueError(f"Failed to load secrets from AWS Secrets Manager for tenant {tenant_id}: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load secrets from AWS Secrets Manager for tenant {tenant_id}: {e}")
        
        return secrets


class GCPSecretManagerSecretManager(SecretManager):
    """Load secrets from Google Cloud Secret Manager."""
    
    def __init__(
        self,
        project_id: Optional[str] = None,
        prefix: Optional[str] = None
    ):
        """Initialize GCP Secret Manager secret manager.
        
        Args:
            project_id: GCP project ID (if None, uses default from application credentials)
            prefix: Optional prefix for secret names (e.g., "dativo-")
        """
        try:
            from google.cloud import secretmanager
        except ImportError:
            raise ImportError(
                "google-cloud-secret-manager library not installed. "
                "Install with: pip install google-cloud-secret-manager"
            )
        
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        if not self.project_id:
            raise ValueError(
                "GCP project ID not provided. Set GCP_PROJECT_ID environment variable or pass project_id parameter."
            )
        
        self.prefix = prefix or ""
        self.client = secretmanager.SecretManagerServiceClient()
    
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from GCP Secret Manager.
        
        Looks for secrets with the pattern: {prefix}{tenant_id}-{secret_name}
        or a single secret named: {prefix}{tenant_id}
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of loaded secrets
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        secrets = {}
        secret_base_name = f"{self.prefix}{tenant_id}"
        
        try:
            # List all secrets in the project
            parent = f"projects/{self.project_id}"
            
            for secret in self.client.list_secrets(request={"parent": parent}):
                secret_name = secret.name.split("/")[-1]
                
                # Check if secret belongs to this tenant
                if secret_name == secret_base_name:
                    # Single secret for tenant
                    version_name = f"{secret.name}/versions/latest"
                    response = self.client.access_secret_version(request={"name": version_name})
                    payload = response.payload.data.decode("UTF-8")
                    
                    try:
                        # Try to parse as JSON
                        secrets = json.loads(payload)
                    except json.JSONDecodeError:
                        # If not JSON, store as single value
                        secrets = {"value": payload}
                    break
                elif secret_name.startswith(f"{secret_base_name}-"):
                    # Multiple secrets with tenant prefix
                    key = secret_name[len(f"{secret_base_name}-"):]
                    version_name = f"{secret.name}/versions/latest"
                    response = self.client.access_secret_version(request={"name": version_name})
                    secrets[key] = response.payload.data.decode("UTF-8")
            
            if not secrets:
                logger.warning(
                    f"No secrets found in GCP Secret Manager for tenant {tenant_id}",
                    extra={"tenant_id": tenant_id}
                )
            else:
                logger.info(
                    f"Loaded {len(secrets)} secrets from GCP Secret Manager for tenant {tenant_id}",
                    extra={"tenant_id": tenant_id, "secret_count": len(secrets)}
                )
            
        except Exception as e:
            raise ValueError(f"Failed to load secrets from GCP Secret Manager for tenant {tenant_id}: {e}")
        
        return secrets


class AzureKeyVaultSecretManager(SecretManager):
    """Load secrets from Azure Key Vault."""
    
    def __init__(
        self,
        vault_url: str,
        credential: Optional[Any] = None,
        prefix: Optional[str] = None
    ):
        """Initialize Azure Key Vault secret manager.
        
        Args:
            vault_url: Azure Key Vault URL (e.g., "https://myvault.vault.azure.net/")
            credential: Azure credential (if None, uses DefaultAzureCredential)
            prefix: Optional prefix for secret names (e.g., "dativo-")
        """
        try:
            from azure.keyvault.secrets import SecretClient
            from azure.identity import DefaultAzureCredential
        except ImportError:
            raise ImportError(
                "azure-keyvault-secrets and azure-identity libraries not installed. "
                "Install with: pip install azure-keyvault-secrets azure-identity"
            )
        
        self.vault_url = vault_url
        self.prefix = prefix or ""
        
        if credential is None:
            credential = DefaultAzureCredential()
        
        self.client = SecretClient(vault_url=vault_url, credential=credential)
    
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from Azure Key Vault.
        
        Looks for secrets with the pattern: {prefix}{tenant_id}-{secret_name}
        Note: Azure Key Vault secret names can only contain alphanumeric characters and hyphens.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of loaded secrets
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        secrets = {}
        secret_prefix = f"{self.prefix}{tenant_id}-"
        
        try:
            # List all secrets in the vault
            for secret_properties in self.client.list_properties_of_secrets():
                secret_name = secret_properties.name
                
                # Check if secret belongs to this tenant
                if secret_name.startswith(secret_prefix):
                    key = secret_name[len(secret_prefix):]
                    
                    # Get secret value
                    secret = self.client.get_secret(secret_name)
                    secrets[key] = secret.value
            
            if not secrets:
                logger.warning(
                    f"No secrets found in Azure Key Vault for tenant {tenant_id}",
                    extra={"tenant_id": tenant_id}
                )
            else:
                logger.info(
                    f"Loaded {len(secrets)} secrets from Azure Key Vault for tenant {tenant_id}",
                    extra={"tenant_id": tenant_id, "secret_count": len(secrets)}
                )
            
        except Exception as e:
            raise ValueError(f"Failed to load secrets from Azure Key Vault for tenant {tenant_id}: {e}")
        
        return secrets


def create_secret_manager(config: Optional[Dict[str, Any]] = None) -> SecretManager:
    """Create a secret manager based on configuration.
    
    Args:
        config: Secret manager configuration. If None, uses environment variables (default).
                Structure:
                {
                    "type": "env" | "filesystem" | "vault" | "aws" | "gcp" | "azure",
                    ... type-specific options ...
                }
    
    Returns:
        SecretManager instance
        
    Raises:
        ValueError: If configuration is invalid
    """
    if config is None:
        config = {"type": "env"}
    
    manager_type = config.get("type", "env").lower()
    
    if manager_type == "env" or manager_type == "environment":
        return EnvironmentSecretManager(
            prefix=config.get("prefix")
        )
    
    elif manager_type == "filesystem" or manager_type == "file":
        secrets_dir = config.get("secrets_dir", "/secrets")
        return FilesystemSecretManager(
            secrets_dir=Path(secrets_dir)
        )
    
    elif manager_type == "vault" or manager_type == "hashicorp":
        if "url" not in config:
            raise ValueError("Vault URL is required for HashiCorp Vault secret manager")
        return HashiCorpVaultSecretManager(
            url=config["url"],
            token=config.get("token"),
            mount_point=config.get("mount_point", "secret"),
            namespace=config.get("namespace"),
            verify=config.get("verify", True)
        )
    
    elif manager_type == "aws" or manager_type == "aws_secrets_manager":
        return AWSSecretsManagerSecretManager(
            region_name=config.get("region_name"),
            prefix=config.get("prefix")
        )
    
    elif manager_type == "gcp" or manager_type == "google":
        return GCPSecretManagerSecretManager(
            project_id=config.get("project_id"),
            prefix=config.get("prefix")
        )
    
    elif manager_type == "azure" or manager_type == "azure_keyvault":
        if "vault_url" not in config:
            raise ValueError("Vault URL is required for Azure Key Vault secret manager")
        return AzureKeyVaultSecretManager(
            vault_url=config["vault_url"],
            prefix=config.get("prefix")
        )
    
    else:
        raise ValueError(
            f"Unknown secret manager type: {manager_type}. "
            f"Supported types: env, filesystem, vault, aws, gcp, azure"
        )


# Backward compatibility functions
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
    tenant_id: str,
    secrets_dir: Path = Path("/secrets"),
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Load secrets for a tenant using configured secret manager.
    
    This function maintains backward compatibility with the filesystem-based approach
    while supporting new secret managers through the config parameter.

    Args:
        tenant_id: Tenant identifier
        secrets_dir: Base directory for secrets (default: /secrets) - used only for filesystem manager
        config: Secret manager configuration (if None, uses filesystem for backward compatibility)

    Returns:
        Dictionary of loaded secrets, keyed by secret name

    Raises:
        ValueError: If secrets cannot be loaded
    """
    # If config is provided, use the configured secret manager
    if config is not None:
        manager = create_secret_manager(config)
        return manager.load_secrets(tenant_id)
    
    # Otherwise, fall back to filesystem manager for backward compatibility
    manager = FilesystemSecretManager(secrets_dir=secrets_dir)
    return manager.load_secrets(tenant_id)


def _expand_env_vars_in_dict(data: Any) -> Any:
    """Recursively expand environment variables in dictionary values.

    Args:
        data: Dictionary, list, or string to process

    Returns:
        Data with environment variables expanded
    """
    if isinstance(data, dict):
        return {k: _expand_env_vars_in_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_expand_env_vars_in_dict(item) for item in data]
    elif isinstance(data, str):
        return os.path.expandvars(data)
    else:
        return data


def validate_secrets_for_connector(secrets: Dict[str, Any], connector_type: str, credentials_config: Dict[str, Any]) -> bool:
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
