"""Secret managers for loading credentials from various sources."""

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _expand_env_vars_in_dict(data: Any) -> Any:
    """Recursively expand environment variables in dictionary values.

    This is a helper function shared by secret managers.
    """
    if isinstance(data, dict):
        return {k: _expand_env_vars_in_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [_expand_env_vars_in_dict(item) for item in data]
    elif isinstance(data, str):
        return os.path.expandvars(data)
    else:
        return data


class SecretManager(ABC):
    """Abstract base class for secret managers."""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    @abstractmethod
    def get_secret(self, secret_name: str) -> Optional[Any]:
        """Retrieve a specific secret by name.

        Args:
            secret_name: Name of the secret to retrieve

        Returns:
            Secret value (usually a dict) or None if not found
        """
        pass

    @abstractmethod
    def list_secrets(self) -> Dict[str, Any]:
        """Retrieve all available secrets for the tenant.

        Returns:
            Dictionary of secrets keyed by name
        """
        pass


class FilesystemSecretManager(SecretManager):
    """Loads secrets from filesystem (JSON/ENV files)."""

    def __init__(self, tenant_id: str, secrets_dir: Path = Path("/secrets")):
        super().__init__(tenant_id)
        self.secrets_dir = secrets_dir

    def get_secret(self, secret_name: str) -> Optional[Any]:
        # This manager is optimized for bulk loading as files are small
        # but we can implement single fetch
        secrets = self.list_secrets()
        return secrets.get(secret_name)

    def list_secrets(self) -> Dict[str, Any]:
        tenant_secrets_dir = self.secrets_dir / self.tenant_id
        if not tenant_secrets_dir.exists():
            logger.warning(f"Secrets directory not found: {tenant_secrets_dir}")
            return {}

        secrets = {}
        for secret_file in tenant_secrets_dir.iterdir():
            if secret_file.is_file() and not secret_file.name.startswith("."):
                secret_name = secret_file.stem
                try:
                    if secret_file.suffix == ".json":
                        with open(secret_file, "r") as f:
                            content = json.load(f)
                            secrets[secret_name] = _expand_env_vars_in_dict(content)
                    elif secret_file.suffix == ".env":
                        env_vars = {}
                        with open(secret_file, "r") as f:
                            for line in f:
                                line = line.strip()
                                if line and not line.startswith("#"):
                                    if "=" in line:
                                        key, value = line.split("=", 1)
                                        key = key.strip()
                                        value = value.strip().strip('"').strip("'")
                                        value = os.path.expandvars(value)
                                        env_vars[key] = value
                        secrets[secret_name] = env_vars
                    else:
                        with open(secret_file, "r") as f:
                            content = f.read().strip()
                            content = os.path.expandvars(content)
                            secrets[secret_name] = content
                except Exception as e:
                    logger.warning(
                        f"Failed to load secret file {secret_file}: {e}",
                        extra={"secret_file": str(secret_file), "error": str(e)},
                    )
        return secrets


class EnvSecretManager(SecretManager):
    """Loads secrets from environment variables.

    Looks for environment variables with prefix DATIVO_SECRET_{secret_name}.
    Value is expected to be a JSON string for complex secrets.
    """

    PREFIX = "DATIVO_SECRET_"

    def get_secret(self, secret_name: str) -> Optional[Any]:
        env_key = f"{self.PREFIX}{secret_name.upper()}"
        val = os.getenv(env_key)
        if val:
            try:
                parsed = json.loads(val)
            except json.JSONDecodeError:
                parsed = val
            return _expand_env_vars_in_dict(parsed)
        return None

    def list_secrets(self) -> Dict[str, Any]:
        secrets = {}
        for key, val in os.environ.items():
            if key.startswith(self.PREFIX):
                secret_name = key[len(self.PREFIX) :].lower()
                try:
                    parsed = json.loads(val)
                except json.JSONDecodeError:
                    parsed = val
                secrets[secret_name] = _expand_env_vars_in_dict(parsed)
        return secrets


class AWSSecretManager(SecretManager):
    """Loads secrets from AWS Secrets Manager."""

    def __init__(self, tenant_id: str, prefix: str = ""):
        super().__init__(tenant_id)
        self.prefix = prefix.rstrip("/")
        try:
            import boto3

            self.client = boto3.client("secretsmanager")
        except ImportError:
            raise ImportError("boto3 is required for AWSSecretManager")

    def _get_secret_id(self, secret_name: str) -> str:
        if self.prefix:
            return f"{self.prefix}/{self.tenant_id}/{secret_name}"
        return f"{self.tenant_id}/{secret_name}"

    def get_secret(self, secret_name: str) -> Optional[Any]:
        secret_id = self._get_secret_id(secret_name)
        try:
            response = self.client.get_secret_value(SecretId=secret_id)
            if "SecretString" in response:
                secret_str = response["SecretString"]
                try:
                    parsed = json.loads(secret_str)
                except json.JSONDecodeError:
                    parsed = secret_str
                return _expand_env_vars_in_dict(parsed)
            return None
        except self.client.exceptions.ResourceNotFoundException:
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch AWS secret {secret_id}: {e}")
            return None

    def list_secrets(self) -> Dict[str, Any]:
        # Note: AWS Secrets Manager list_secrets returns metadata, not values.
        # Fetching all values might be expensive/throttled.
        # This implementation tries to list and fetch.
        secrets = {}
        path_prefix = (
            f"{self.prefix}/{self.tenant_id}/" if self.prefix else f"{self.tenant_id}/"
        )

        try:
            paginator = self.client.get_paginator("list_secrets")
            for page in paginator.paginate(
                Filters=[{"Key": "name", "Values": [path_prefix]}]
            ):
                for secret in page["SecretList"]:
                    name = secret["Name"]
                    # Extract secret_name from full path
                    if name.startswith(path_prefix):
                        secret_name = name[len(path_prefix) :]
                        # Fetch value
                        val = self.get_secret(secret_name)
                        if val is not None:
                            secrets[secret_name] = val
        except Exception as e:
            logger.error(f"Failed to list AWS secrets: {e}")

        return secrets


class GCPSecretManager(SecretManager):
    """Loads secrets from Google Secret Manager."""

    def __init__(self, tenant_id: str, project_id: str, prefix: str = "dativo"):
        super().__init__(tenant_id)
        self.project_id = project_id
        self.prefix = prefix
        try:
            from google.cloud import secretmanager

            self.client = secretmanager.SecretManagerServiceClient()
        except ImportError:
            raise ImportError(
                "google-cloud-secret-manager is required for GCPSecretManager"
            )

    def _get_secret_id(self, secret_name: str) -> str:
        # GCP Secret names must be unique in project and follow [a-zA-Z_0-9]+
        # Construct name: {prefix}-{tenant}-{name}
        safe_tenant = re.sub(r"[^a-zA-Z0-9]", "-", self.tenant_id)
        safe_name = re.sub(r"[^a-zA-Z0-9]", "-", secret_name)
        return f"{self.prefix}-{safe_tenant}-{safe_name}"

    def get_secret(self, secret_name: str) -> Optional[Any]:
        name = self.client.secret_version_path(
            self.project_id, self._get_secret_id(secret_name), "latest"
        )
        try:
            response = self.client.access_secret_version(request={"name": name})
            payload = response.payload.data.decode("UTF-8")
            try:
                parsed = json.loads(payload)
            except json.JSONDecodeError:
                parsed = payload
            return _expand_env_vars_in_dict(parsed)
        except Exception as e:
            logger.debug(f"GCP secret {name} not found or inaccessible: {e}")
            return None

    def list_secrets(self) -> Dict[str, Any]:
        secrets = {}
        parent = f"projects/{self.project_id}"
        prefix_filter = (
            f"{self.prefix}-{re.sub(r'[^a-zA-Z0-9]', '-', self.tenant_id)}-"
        )

        try:
            for secret in self.client.list_secrets(request={"parent": parent}):
                secret_name_full = secret.name.split("/")[-1]
                if secret_name_full.startswith(prefix_filter):
                    simple_name = secret_name_full[len(prefix_filter) :]
                    val = self.get_secret(simple_name)
                    if val is not None:
                        secrets[simple_name] = val
        except Exception as e:
            logger.error(f"Failed to list GCP secrets: {e}")

        return secrets


class VaultSecretManager(SecretManager):
    """Loads secrets from HashiCorp Vault."""

    def __init__(
        self,
        tenant_id: str,
        url: str,
        token: Optional[str] = None,
        mount_point: str = "secret",
    ):
        super().__init__(tenant_id)
        self.mount_point = mount_point
        try:
            import hvac

            self.client = hvac.Client(url=url, token=token)
            if not self.client.is_authenticated():
                logger.warning("Vault client is not authenticated")
        except ImportError:
            raise ImportError("hvac is required for VaultSecretManager")

    def get_secret(self, secret_name: str) -> Optional[Any]:
        path = f"{self.tenant_id}/{secret_name}"
        try:
            response = self.client.secrets.kv.v2.read_secret_version(
                path=path, mount_point=self.mount_point
            )
            val = response["data"]["data"]
            return _expand_env_vars_in_dict(val)
        except Exception as e:
            logger.debug(f"Vault secret {path} not found: {e}")
            return None

    def list_secrets(self) -> Dict[str, Any]:
        secrets = {}
        path = f"{self.tenant_id}/"
        try:
            # List keys
            list_response = self.client.secrets.kv.v2.list_secrets(
                path=path, mount_point=self.mount_point
            )
            keys = list_response["data"]["keys"]
            for key in keys:
                # keys can be subdirs (ending in /) or secrets
                if not key.endswith("/"):
                    val = self.get_secret(key)
                    if val:
                        secrets[key] = val
        except Exception as e:
            logger.debug(f"Failed to list Vault secrets at {path}: {e}")

        return secrets


class CompositeSecretManager(SecretManager):
    """Chains multiple secret managers."""

    def __init__(self, managers: List[SecretManager]):
        # tenant_id is not really used here as managers are already initialized
        super().__init__("composite")
        self.managers = managers

    def get_secret(self, secret_name: str) -> Optional[Any]:
        for manager in self.managers:
            val = manager.get_secret(secret_name)
            if val:
                return val
        return None

    def list_secrets(self) -> Dict[str, Any]:
        secrets = {}
        # Iterate in reverse so earlier managers override later ones
        for manager in reversed(self.managers):
            try:
                secrets.update(manager.list_secrets())
            except Exception as e:
                logger.warning(
                    f"Failed to list secrets from {manager.__class__.__name__}: {e}"
                )
        return secrets


def get_secret_manager(
    tenant_id: str, secrets_dir: Path = Path("/secrets")
) -> SecretManager:
    """Factory to get the configured secret manager."""
    manager_type = os.getenv("DATIVO_SECRET_MANAGER", "env").lower()

    if manager_type == "filesystem":
        return FilesystemSecretManager(tenant_id, secrets_dir)

    elif manager_type == "env":
        # For backward compatibility or hybrid, we might want to check FS too?
        # But the requirement says "making environment variables the new default".
        # We could return a CompositeSecretManager if we wanted to support both.
        return EnvSecretManager(tenant_id)

    elif manager_type == "aws":
        prefix = os.getenv("DATIVO_AWS_SECRET_PREFIX", "")
        return AWSSecretManager(tenant_id, prefix=prefix)

    elif manager_type == "gcp":
        project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        if not project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT env var required for GCP Secret Manager"
            )
        prefix = os.getenv("DATIVO_GCP_SECRET_PREFIX", "dativo")
        return GCPSecretManager(tenant_id, project_id, prefix)

    elif manager_type == "vault":
        url = os.getenv("VAULT_ADDR")
        token = os.getenv("VAULT_TOKEN")
        mount = os.getenv("DATIVO_VAULT_MOUNT", "secret")
        if not url:
            raise ValueError("VAULT_ADDR env var required for Vault")
        return VaultSecretManager(tenant_id, url, token, mount)

    else:
        logger.warning(
            f"Unknown secret manager type '{manager_type}', falling back to Env"
        )
        return EnvSecretManager(tenant_id)
