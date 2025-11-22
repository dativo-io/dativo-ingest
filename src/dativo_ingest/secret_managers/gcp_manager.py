"""Google Cloud Secret Manager integration."""

import json
import logging
from typing import Any, Dict, Optional

try:
    from google.cloud import secretmanager
    from google.api_core import exceptions as gcp_exceptions
    GCP_AVAILABLE = True
except ImportError:
    GCP_AVAILABLE = False

from .base import SecretManager

logger = logging.getLogger(__name__)


class GCPSecretManager(SecretManager):
    """Secret manager that integrates with Google Cloud Secret Manager.
    
    Uses google-cloud-secretmanager for authentication. Supports standard GCP credential providers:
    - Application Default Credentials (ADC)
    - Service account key file (GOOGLE_APPLICATION_CREDENTIALS env var)
    - Workload Identity (for GKE)
    - Compute Engine service account
    
    Configuration options:
        - project_id: GCP project ID (required, or GOOGLE_CLOUD_PROJECT env var)
        - secret_name_template: Secret name template (default: {tenant}-secrets)
        - credentials_file: Path to service account key file (optional)
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize Google Cloud Secret Manager.
        
        Args:
            config: GCP Secret Manager configuration
            
        Raises:
            ImportError: If google-cloud-secretmanager library is not installed
        """
        if not GCP_AVAILABLE:
            raise ImportError(
                "google-cloud-secretmanager library is required for GCP Secret Manager support. "
                "Install it with: pip install google-cloud-secretmanager"
            )
        
        super().__init__(config)
        
        import os
        
        # Get project ID
        self.project_id = self.config.get("project_id") or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            raise ValueError(
                "GCP project ID must be provided via config or GOOGLE_CLOUD_PROJECT environment variable"
            )
        
        # Configuration
        self.secret_name_template = self.config.get("secret_name_template", "{tenant}-secrets")
        
        # Initialize Secret Manager client
        client_kwargs = {}
        if self.config.get("credentials_file"):
            # Use explicit credentials file
            from google.oauth2 import service_account
            credentials = service_account.Credentials.from_service_account_file(
                self.config["credentials_file"]
            )
            client_kwargs["credentials"] = credentials
        
        self.client = secretmanager.SecretManagerServiceClient(**client_kwargs)
        
        logger.info(f"Initialized GCP Secret Manager client for project {self.project_id}")

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from GCP Secret Manager for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of secrets
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        secret_name = self.secret_name_template.format(tenant=tenant_id)
        resource_name = f"projects/{self.project_id}/secrets/{secret_name}/versions/latest"
        
        try:
            response = self.client.access_secret_version(request={"name": resource_name})
            secret_data = response.payload.data.decode("UTF-8")
            
            # Try to parse as JSON
            try:
                secrets = json.loads(secret_data)
            except json.JSONDecodeError:
                # If not JSON, return as single secret
                secrets = {"secret": secret_data}
            
            # Expand environment variables in values
            secrets = self.expand_env_vars(secrets)
            
            logger.info(
                f"Loaded {len(secrets)} secrets from GCP Secret Manager for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "secret_name": secret_name},
            )
            
            return secrets
            
        except gcp_exceptions.NotFound:
            raise ValueError(f"Secret not found in GCP Secret Manager: {secret_name}")
        except gcp_exceptions.PermissionDenied:
            raise ValueError(f"Permission denied to access secret in GCP Secret Manager: {secret_name}")
        except Exception as e:
            raise ValueError(f"Failed to load secrets from GCP Secret Manager: {e}")

    def get_secret(self, tenant_id: str, secret_name: str) -> Optional[Any]:
        """Retrieve a specific secret from GCP Secret Manager.
        
        This implementation supports two modes:
        1. Single secret per tenant (all fields in one GCP secret)
        2. Multiple secrets per tenant (separate GCP secrets)
        
        Args:
            tenant_id: Tenant identifier
            secret_name: Name of the secret to retrieve
            
        Returns:
            Secret value or None if not found
        """
        # First try to get from the tenant's main secret bundle
        secrets = self.load_secrets(tenant_id)
        if secret_name in secrets:
            return secrets[secret_name]
        
        # If not found, try as a separate GCP secret
        gcp_secret_name = f"{tenant_id}-{secret_name}"
        resource_name = f"projects/{self.project_id}/secrets/{gcp_secret_name}/versions/latest"
        
        try:
            response = self.client.access_secret_version(request={"name": resource_name})
            secret_data = response.payload.data.decode("UTF-8")
            
            try:
                return json.loads(secret_data)
            except json.JSONDecodeError:
                return secret_data
                
        except gcp_exceptions.NotFound:
            return None
        except Exception:
            return None
