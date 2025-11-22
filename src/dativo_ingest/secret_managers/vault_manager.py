"""HashiCorp Vault secret manager."""

import logging
from typing import Any, Dict, Optional

try:
    import hvac
    HVAC_AVAILABLE = True
except ImportError:
    HVAC_AVAILABLE = False

from .base import SecretManager

logger = logging.getLogger(__name__)


class HashiCorpVaultSecretManager(SecretManager):
    """Secret manager that integrates with HashiCorp Vault.
    
    Supports multiple authentication methods:
    - Token authentication (VAULT_TOKEN)
    - AppRole authentication
    - Kubernetes authentication
    - AWS IAM authentication
    
    Configuration options:
        - url: Vault server URL (required, or VAULT_ADDR env var)
        - token: Vault token (optional, or VAULT_TOKEN env var)
        - auth_method: Authentication method (token, approle, kubernetes, aws)
        - mount_point: KV secrets engine mount point (default: secret)
        - kv_version: KV secrets engine version, 1 or 2 (default: 2)
        - path_template: Secret path template (default: {tenant})
        - namespace: Vault namespace (optional, Enterprise feature)
        
    AppRole specific:
        - role_id: AppRole role ID (or VAULT_ROLE_ID env var)
        - secret_id: AppRole secret ID (or VAULT_SECRET_ID env var)
        
    Kubernetes specific:
        - k8s_role: Kubernetes authentication role
        - k8s_token_path: Path to service account token (default: /var/run/secrets/kubernetes.io/serviceaccount/token)
        
    AWS specific:
        - aws_role: AWS IAM role name for Vault authentication
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize HashiCorp Vault secret manager.
        
        Args:
            config: Vault configuration
            
        Raises:
            ImportError: If hvac library is not installed
        """
        if not HVAC_AVAILABLE:
            raise ImportError(
                "hvac library is required for HashiCorp Vault support. "
                "Install it with: pip install hvac"
            )
        
        super().__init__(config)
        
        import os
        
        # Get Vault URL
        self.url = self.config.get("url") or os.getenv("VAULT_ADDR")
        if not self.url:
            raise ValueError("Vault URL must be provided via config or VAULT_ADDR environment variable")
        
        # Configuration
        self.mount_point = self.config.get("mount_point", "secret")
        self.kv_version = self.config.get("kv_version", 2)
        self.path_template = self.config.get("path_template", "{tenant}")
        self.namespace = self.config.get("namespace")
        self.auth_method = self.config.get("auth_method", "token")
        
        # Initialize Vault client
        self.client = hvac.Client(url=self.url, namespace=self.namespace)
        
        # Authenticate
        self._authenticate()

    def _authenticate(self):
        """Authenticate with Vault using configured method."""
        import os
        
        if self.auth_method == "token":
            token = self.config.get("token") or os.getenv("VAULT_TOKEN")
            if not token:
                raise ValueError("Vault token must be provided via config or VAULT_TOKEN environment variable")
            self.client.token = token
            
        elif self.auth_method == "approle":
            role_id = self.config.get("role_id") or os.getenv("VAULT_ROLE_ID")
            secret_id = self.config.get("secret_id") or os.getenv("VAULT_SECRET_ID")
            if not role_id or not secret_id:
                raise ValueError("AppRole authentication requires role_id and secret_id")
            
            auth_response = self.client.auth.approle.login(
                role_id=role_id,
                secret_id=secret_id,
            )
            self.client.token = auth_response["auth"]["client_token"]
            
        elif self.auth_method == "kubernetes":
            k8s_role = self.config.get("k8s_role")
            if not k8s_role:
                raise ValueError("Kubernetes authentication requires k8s_role")
            
            k8s_token_path = self.config.get("k8s_token_path", "/var/run/secrets/kubernetes.io/serviceaccount/token")
            try:
                with open(k8s_token_path, "r") as f:
                    jwt = f.read().strip()
            except IOError as e:
                raise ValueError(f"Failed to read Kubernetes service account token: {e}")
            
            auth_response = self.client.auth.kubernetes.login(
                role=k8s_role,
                jwt=jwt,
            )
            self.client.token = auth_response["auth"]["client_token"]
            
        elif self.auth_method == "aws":
            aws_role = self.config.get("aws_role")
            if not aws_role:
                raise ValueError("AWS authentication requires aws_role")
            
            auth_response = self.client.auth.aws.iam_login(
                role=aws_role,
            )
            self.client.token = auth_response["auth"]["client_token"]
            
        else:
            raise ValueError(f"Unsupported authentication method: {self.auth_method}")
        
        # Verify authentication
        if not self.client.is_authenticated():
            raise ValueError("Failed to authenticate with Vault")
        
        logger.info(f"Successfully authenticated with Vault using {self.auth_method} method")

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from Vault for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of secrets
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        path = self.path_template.format(tenant=tenant_id)
        
        try:
            if self.kv_version == 2:
                # KV v2 API
                response = self.client.secrets.kv.v2.read_secret_version(
                    path=path,
                    mount_point=self.mount_point,
                )
                secrets = response["data"]["data"]
            else:
                # KV v1 API
                response = self.client.secrets.kv.v1.read_secret(
                    path=path,
                    mount_point=self.mount_point,
                )
                secrets = response["data"]
            
            # Expand environment variables in values
            secrets = self.expand_env_vars(secrets)
            
            logger.info(
                f"Loaded {len(secrets)} secrets from Vault for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "path": path},
            )
            
            return secrets
            
        except hvac.exceptions.InvalidPath:
            raise ValueError(f"No secrets found in Vault at path: {path}")
        except Exception as e:
            raise ValueError(f"Failed to load secrets from Vault: {e}")

    def get_secret(self, tenant_id: str, secret_name: str) -> Optional[Any]:
        """Retrieve a specific secret from Vault.
        
        Args:
            tenant_id: Tenant identifier
            secret_name: Name of the secret to retrieve
            
        Returns:
            Secret value or None if not found
        """
        secrets = self.load_secrets(tenant_id)
        return secrets.get(secret_name)
