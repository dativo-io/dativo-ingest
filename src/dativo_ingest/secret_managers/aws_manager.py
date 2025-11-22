"""AWS Secrets Manager integration."""

import json
import logging
from typing import Any, Dict, Optional

try:
    import boto3
    from botocore.exceptions import ClientError
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False

from .base import SecretManager

logger = logging.getLogger(__name__)


class AWSSecretManager(SecretManager):
    """Secret manager that integrates with AWS Secrets Manager.
    
    Uses boto3 for AWS authentication. Supports standard AWS credential providers:
    - Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
    - AWS credentials file (~/.aws/credentials)
    - IAM roles (for EC2, ECS, Lambda)
    - AWS SSO
    
    Configuration options:
        - region_name: AWS region (default: us-east-1, or AWS_DEFAULT_REGION env var)
        - secret_name_template: Secret name template (default: {tenant}/secrets)
        - aws_access_key_id: AWS access key (optional)
        - aws_secret_access_key: AWS secret key (optional)
        - aws_session_token: AWS session token (optional)
        - endpoint_url: Custom endpoint URL (for testing with LocalStack)
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize AWS Secrets Manager.
        
        Args:
            config: AWS Secrets Manager configuration
            
        Raises:
            ImportError: If boto3 library is not installed
        """
        if not BOTO3_AVAILABLE:
            raise ImportError(
                "boto3 library is required for AWS Secrets Manager support. "
                "Install it with: pip install boto3"
            )
        
        super().__init__(config)
        
        import os
        
        # Configuration
        self.region_name = self.config.get("region_name") or os.getenv("AWS_DEFAULT_REGION", "us-east-1")
        self.secret_name_template = self.config.get("secret_name_template", "{tenant}/secrets")
        
        # Initialize AWS Secrets Manager client
        client_kwargs = {
            "region_name": self.region_name,
        }
        
        # Optional authentication parameters
        if self.config.get("aws_access_key_id"):
            client_kwargs["aws_access_key_id"] = self.config["aws_access_key_id"]
        if self.config.get("aws_secret_access_key"):
            client_kwargs["aws_secret_access_key"] = self.config["aws_secret_access_key"]
        if self.config.get("aws_session_token"):
            client_kwargs["aws_session_token"] = self.config["aws_session_token"]
        if self.config.get("endpoint_url"):
            client_kwargs["endpoint_url"] = self.config["endpoint_url"]
        
        self.client = boto3.client("secretsmanager", **client_kwargs)
        
        logger.info(f"Initialized AWS Secrets Manager client in region {self.region_name}")

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from AWS Secrets Manager for a tenant.
        
        Args:
            tenant_id: Tenant identifier
            
        Returns:
            Dictionary of secrets
            
        Raises:
            ValueError: If secrets cannot be loaded
        """
        secret_name = self.secret_name_template.format(tenant=tenant_id)
        
        try:
            response = self.client.get_secret_value(SecretId=secret_name)
            
            # Parse secret string
            if "SecretString" in response:
                secret_data = response["SecretString"]
                try:
                    # Try to parse as JSON
                    secrets = json.loads(secret_data)
                except json.JSONDecodeError:
                    # If not JSON, return as single secret
                    secrets = {"secret": secret_data}
            else:
                # Binary secret (uncommon)
                secrets = {"secret": response["SecretBinary"]}
            
            # Expand environment variables in values
            secrets = self.expand_env_vars(secrets)
            
            logger.info(
                f"Loaded {len(secrets)} secrets from AWS Secrets Manager for tenant {tenant_id}",
                extra={"tenant_id": tenant_id, "secret_name": secret_name},
            )
            
            return secrets
            
        except ClientError as e:
            error_code = e.response["Error"]["Code"]
            if error_code == "ResourceNotFoundException":
                raise ValueError(f"Secret not found in AWS Secrets Manager: {secret_name}")
            elif error_code == "AccessDeniedException":
                raise ValueError(f"Access denied to secret in AWS Secrets Manager: {secret_name}")
            else:
                raise ValueError(f"Failed to load secret from AWS Secrets Manager: {e}")
        except Exception as e:
            raise ValueError(f"Failed to load secrets from AWS Secrets Manager: {e}")

    def get_secret(self, tenant_id: str, secret_name: str) -> Optional[Any]:
        """Retrieve a specific secret from AWS Secrets Manager.
        
        This implementation supports two modes:
        1. Single secret per tenant (all fields in one AWS secret)
        2. Multiple secrets per tenant (separate AWS secrets)
        
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
        
        # If not found, try as a separate AWS secret
        aws_secret_name = f"{tenant_id}/{secret_name}"
        try:
            response = self.client.get_secret_value(SecretId=aws_secret_name)
            if "SecretString" in response:
                secret_data = response["SecretString"]
                try:
                    return json.loads(secret_data)
                except json.JSONDecodeError:
                    return secret_data
            else:
                return response["SecretBinary"]
        except ClientError:
            return None
