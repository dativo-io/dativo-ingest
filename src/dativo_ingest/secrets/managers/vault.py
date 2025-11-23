"""HashiCorp Vault secret manager."""

import os
from typing import Any, Callable, Dict, List, Optional

from ..base import SecretManager
from ..parsers import expand_env_vars_in_dict


class HashicorpVaultSecretManager(SecretManager):
    """Load secrets from HashiCorp Vault KV secrets engine."""

    type_name = "vault"

    def __init__(
        self,
        address: Optional[str] = None,
        mount_point: str = "secret",
        path_template: str = "{tenant}",
        kv_version: int = 2,
        namespace: Optional[str] = None,
        auth_method: str = "token",
        token: Optional[str] = None,
        role_id: Optional[str] = None,
        secret_id: Optional[str] = None,
        verify: bool = True,
        timeout: Optional[float] = None,
        paths: Optional[List[Any]] = None,
        client_factory: Optional[Callable[[], Any]] = None,
        **config: Any,
    ) -> None:
        super().__init__(
            address=address,
            mount_point=mount_point,
            path_template=path_template,
            kv_version=kv_version,
            namespace=namespace,
            auth_method=auth_method,
            verify=verify,
            timeout=timeout,
            **config,
        )
        self.address = address or os.getenv("VAULT_ADDR")
        if not self.address:
            raise ValueError("Vault address is required (set 'address' or VAULT_ADDR).")
        self.mount_point = mount_point
        self.path_template = path_template
        self.kv_version = kv_version
        self.namespace = namespace or os.getenv("VAULT_NAMESPACE")
        self.auth_method = auth_method
        self.token = token or os.getenv("VAULT_TOKEN")
        self.role_id = role_id or os.getenv("VAULT_ROLE_ID")
        self.secret_id = secret_id or os.getenv("VAULT_SECRET_ID")
        self.verify = verify
        self.timeout = timeout
        self._client_factory = client_factory or self._build_client
        self.paths = self._normalize_paths(paths)

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from Vault.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary of loaded secrets
        """
        client = self._client_factory()
        data: Dict[str, Any] = {}

        for path_config in self.paths:
            mount_point = path_config.get("mount_point", self.mount_point)
            kv_version = path_config.get("kv_version", self.kv_version)
            rendered_path = path_config["path"].format(tenant=tenant_id)
            secrets = self._read_path(client, rendered_path, mount_point, kv_version)
            if secrets:
                data.update(expand_env_vars_in_dict(secrets))

        return data

    def _normalize_paths(self, paths: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """Normalize path configurations into a consistent format.

        Args:
            paths: Optional list of path configurations (strings or dicts)

        Returns:
            List of normalized path dictionaries

        Raises:
            ValueError: If path format is invalid
        """
        if not paths:
            return [
                {
                    "path": self.path_template,
                    "mount_point": self.mount_point,
                    "kv_version": self.kv_version,
                }
            ]

        normalized: List[Dict[str, Any]] = []
        for entry in paths:
            if isinstance(entry, str):
                normalized.append(
                    {
                        "path": entry,
                        "mount_point": self.mount_point,
                        "kv_version": self.kv_version,
                    }
                )
            elif isinstance(entry, dict) and "path" in entry:
                normalized.append(
                    {
                        "path": entry["path"],
                        "mount_point": entry.get("mount_point", self.mount_point),
                        "kv_version": entry.get("kv_version", self.kv_version),
                    }
                )
            else:
                raise ValueError(
                    "Each Vault path entry must be a string or dict with 'path'."
                )
        return normalized

    def _build_client(self) -> Any:
        """Build and authenticate Vault client.

        Returns:
            Authenticated Vault client

        Raises:
            ImportError: If hvac is not installed
            ValueError: If authentication fails
        """
        try:
            import hvac
        except ImportError as exc:  # pragma: no cover - import guard
            raise ImportError(
                "hvac is required for HashiCorp Vault secret manager. Install hvac or "
                "add it to your dependencies."
            ) from exc

        client = hvac.Client(
            url=self.address,
            namespace=self.namespace,
            verify=self.verify,
            timeout=self.timeout,
        )

        if self.auth_method == "token":
            if not self.token:
                raise ValueError("Vault token is required for token authentication.")
            client.token = self.token
        elif self.auth_method == "approle":
            if not self.role_id or not self.secret_id:
                raise ValueError("role_id and secret_id are required for approle auth.")
            client.auth.approle.login(role_id=self.role_id, secret_id=self.secret_id)
        else:
            raise ValueError(f"Unsupported Vault auth_method: {self.auth_method}")

        if not client.is_authenticated():
            raise ValueError("Vault authentication failed.")
        return client

    @staticmethod
    def _read_path(
        client: Any, path: str, mount_point: str, kv_version: int
    ) -> Dict[str, Any]:
        """Read secrets from a Vault path.

        Args:
            client: Vault client instance
            path: Secret path
            mount_point: KV mount point
            kv_version: KV version (1 or 2)

        Returns:
            Dictionary of secrets from the path
        """
        if kv_version == 1:
            response = client.secrets.kv.v1.read_secret(
                path=path, mount_point=mount_point
            )
            return response.get("data", {}) if response else {}
        response = client.secrets.kv.v2.read_secret_version(
            path=path, mount_point=mount_point
        )
        return response.get("data", {}).get("data", {}) if response else {}
