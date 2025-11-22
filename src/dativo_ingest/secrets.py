"""Secrets management with pluggable backends (env, filesystem, Vault, AWS, GCP)."""

import base64
import json
import os
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence


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


class SecretManager(ABC):
    """Abstract base class for tenant-scoped secret managers."""

    type_name: str = "base"

    def __init__(self, **config: Any) -> None:
        self.config = config

    @abstractmethod
    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets for the given tenant."""


class EnvironmentSecretManager(SecretManager):
    """Load secrets from environment variables with structured naming."""

    type_name = "env"
    _FORMAT_HINTS = {"json", "env", "text", "raw"}

    def __init__(
        self,
        prefix: str = "DATIVO_SECRET",
        delimiter: str = "__",
        allow_global_scope: bool = True,
        **config: Any,
    ) -> None:
        super().__init__(
            prefix=prefix, delimiter=delimiter, allow_global_scope=allow_global_scope, **config
        )
        self.prefix = prefix.upper()
        self.delimiter = delimiter
        self.allow_global_scope = allow_global_scope

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        tenant_upper = tenant_id.upper()
        prefix = f"{self.prefix}{self.delimiter}"
        secrets: Dict[str, Any] = {}

        for env_key, value in os.environ.items():
            if not env_key.upper().startswith(prefix):
                continue

            parts = env_key.split(self.delimiter)
            if len(parts) < 3:
                continue

            _, scope_part, *name_parts = parts
            scope_upper = scope_part.upper()
            allowed_scopes = {tenant_upper}
            if self.allow_global_scope:
                allowed_scopes.update({"GLOBAL", "ALL"})
            if scope_upper not in allowed_scopes:
                continue
            if not name_parts:
                continue

            format_hint = None
            if name_parts[-1].lower() in self._FORMAT_HINTS:
                format_hint = name_parts.pop().lower()

            secret_name = self._sanitize_secret_name(name_parts)
            if not secret_name:
                continue

            secrets[secret_name] = _parse_secret_payload(value, format_hint=format_hint)

        return secrets

    @staticmethod
    def _sanitize_secret_name(parts: Sequence[str]) -> str:
        cleaned = [part for part in parts if part]
        return "_".join(cleaned).lower()


class FilesystemSecretManager(SecretManager):
    """Load secrets from tenant-specific directories on disk."""

    type_name = "filesystem"

    def __init__(self, secrets_dir: Path = Path("/secrets"), **config: Any) -> None:
        super().__init__(secrets_dir=secrets_dir, **config)
        self.secrets_dir = Path(secrets_dir)

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        tenant_secrets_dir = self.secrets_dir / tenant_id
        if not tenant_secrets_dir.exists():
            raise ValueError(f"Secrets directory not found: {tenant_secrets_dir}")

        secrets: Dict[str, Any] = {}
        for secret_file in tenant_secrets_dir.iterdir():
            if not secret_file.is_file() or secret_file.name.startswith("."):
                continue

            secret_name = secret_file.stem
            try:
                if secret_file.suffix == ".json":
                    with open(secret_file, "r", encoding="utf-8") as handle:
                        secrets[secret_name] = _expand_env_vars_in_dict(json.load(handle))
                elif secret_file.suffix == ".env":
                    with open(secret_file, "r", encoding="utf-8") as handle:
                        secrets[secret_name] = _parse_env_blob(handle.read())
                else:
                    with open(secret_file, "r", encoding="utf-8") as handle:
                        secrets[secret_name] = os.path.expandvars(handle.read().strip())
            except Exception as exc:  # pragma: no cover - defensive logging
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(
                    "Failed to load secret file %s: %s",
                    secret_file,
                    exc,
                    extra={"secret_file": str(secret_file), "error": str(exc)},
                )
        return secrets


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
        client = self._client_factory()
        data: Dict[str, Any] = {}

        for path_config in self.paths:
            mount_point = path_config.get("mount_point", self.mount_point)
            kv_version = path_config.get("kv_version", self.kv_version)
            rendered_path = path_config["path"].format(tenant=tenant_id)
            secrets = self._read_path(client, rendered_path, mount_point, kv_version)
            if secrets:
                data.update(_expand_env_vars_in_dict(secrets))

        return data

    def _normalize_paths(self, paths: Optional[List[Any]]) -> List[Dict[str, Any]]:
        if not paths:
            return [{"path": self.path_template, "mount_point": self.mount_point, "kv_version": self.kv_version}]

        normalized: List[Dict[str, Any]] = []
        for entry in paths:
            if isinstance(entry, str):
                normalized.append(
                    {"path": entry, "mount_point": self.mount_point, "kv_version": self.kv_version}
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
                raise ValueError("Each Vault path entry must be a string or dict with 'path'.")
        return normalized

    def _build_client(self) -> Any:
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
    def _read_path(client: Any, path: str, mount_point: str, kv_version: int) -> Dict[str, Any]:
        if kv_version == 1:
            response = client.secrets.kv.v1.read_secret(path=path, mount_point=mount_point)
            return response.get("data", {}) if response else {}
        response = client.secrets.kv.v2.read_secret_version(path=path, mount_point=mount_point)
        return response.get("data", {}).get("data", {}) if response else {}


@dataclass
class SecretDefinition:
    """Concrete secret to resolve from a remote manager."""

    name: str
    identifier: Optional[str] = None
    version_stage: Optional[str] = None
    version_id: Optional[str] = None
    format: Optional[str] = None

    def resolve_identifier(self, tenant_id: str, template: str) -> str:
        base = self.identifier or template
        return base.format(tenant=tenant_id, name=self.name)


def _build_secret_definitions(entries: Optional[Iterable[Any]]) -> List[SecretDefinition]:
    if not entries:
        return []
    definitions: List[SecretDefinition] = []
    for entry in entries:
        if isinstance(entry, str):
            definitions.append(SecretDefinition(name=entry))
        elif isinstance(entry, dict):
            if "name" not in entry:
                raise ValueError("Secret definition dictionaries must include 'name'.")
            definitions.append(
                SecretDefinition(
                    name=entry["name"],
                    identifier=entry.get("id") or entry.get("identifier"),
                    version_stage=entry.get("version_stage"),
                    version_id=entry.get("version_id"),
                    format=entry.get("format"),
                )
            )
        else:
            raise ValueError("Secret definitions must be strings or dictionaries.")
    return definitions


class AWSSecretsManager(SecretManager):
    """Load secrets from AWS Secrets Manager."""

    type_name = "aws"

    def __init__(
        self,
        region_name: Optional[str] = None,
        secret_id_template: str = "{tenant}/{name}",
        secrets: Optional[Iterable[Any]] = None,
        bundle_secret_id_template: Optional[str] = None,
        bundle_format: str = "json",
        profile_name: Optional[str] = None,
        session_kwargs: Optional[Dict[str, Any]] = None,
        client: Optional[Any] = None,
        **config: Any,
    ) -> None:
        super().__init__(
            region_name=region_name,
            secret_id_template=secret_id_template,
            bundle_secret_id_template=bundle_secret_id_template,
            profile_name=profile_name,
            **config,
        )
        self.region_name = region_name
        self.secret_id_template = secret_id_template
        self.bundle_secret_id_template = bundle_secret_id_template
        self.bundle_format = bundle_format
        self.profile_name = profile_name
        self.session_kwargs = session_kwargs or {}
        self.secret_definitions = _build_secret_definitions(secrets)
        self._client = client

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        client = self._client or self._build_client()

        if self.secret_definitions:
            result: Dict[str, Any] = {}
            for definition in self.secret_definitions:
                secret_id = definition.resolve_identifier(tenant_id, self.secret_id_template)
                payload = self._get_secret_value(
                    client,
                    secret_id,
                    version_id=definition.version_id,
                    version_stage=definition.version_stage,
                )
                result[definition.name] = _parse_secret_payload(
                    payload, format_hint=definition.format
                )
            return result

        if not self.bundle_secret_id_template:
            raise ValueError(
                "AWS Secrets Manager requires either 'secrets' definitions or 'bundle_secret_id_template'."
            )

        bundle_id = self.bundle_secret_id_template.format(tenant=tenant_id)
        payload = self._get_secret_value(client, bundle_id)
        parsed = _parse_secret_payload(payload, format_hint=self.bundle_format)
        if not isinstance(parsed, dict):
            raise ValueError("AWS bundle secret must deserialize into a dictionary.")
        return _expand_env_vars_in_dict(parsed)

    def _build_client(self) -> Any:
        try:
            import boto3
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "boto3 is required for AWS secret manager support. Install boto3 or add it to your dependencies."
            ) from exc

        session_kwargs = dict(self.session_kwargs)
        if self.profile_name:
            session_kwargs["profile_name"] = self.profile_name
        session = boto3.session.Session(**session_kwargs)
        return session.client("secretsmanager", region_name=self.region_name)

    @staticmethod
    def _get_secret_value(
        client: Any, secret_id: str, version_id: Optional[str] = None, version_stage: Optional[str] = None
    ) -> str:
        params = {"SecretId": secret_id}
        if version_id:
            params["VersionId"] = version_id
        if version_stage:
            params["VersionStage"] = version_stage

        response = client.get_secret_value(**params)
        if "SecretString" in response and response["SecretString"] is not None:
            return response["SecretString"]
        binary_secret = response.get("SecretBinary")
        if binary_secret is None:
            return ""
        if isinstance(binary_secret, bytes):
            binary_secret = binary_secret.decode("utf-8")
        return base64.b64decode(binary_secret).decode("utf-8")


class GCPSecretManager(SecretManager):
    """Load secrets from Google Cloud Secret Manager."""

    type_name = "gcp"

    def __init__(
        self,
        project_id: Optional[str] = None,
        secret_id_template: str = "{tenant}-{name}",
        secrets: Optional[Iterable[Any]] = None,
        bundle_secret_id_template: Optional[str] = None,
        bundle_format: str = "json",
        version: str = "latest",
        client_options: Optional[Dict[str, Any]] = None,
        client: Optional[Any] = None,
        **config: Any,
    ) -> None:
        super().__init__(
            project_id=project_id,
            secret_id_template=secret_id_template,
            bundle_secret_id_template=bundle_secret_id_template,
            version=version,
            **config,
        )
        self.project_id = project_id or os.getenv("GOOGLE_CLOUD_PROJECT")
        if not self.project_id:
            raise ValueError("project_id is required for GCP secret manager.")
        self.secret_id_template = secret_id_template
        self.bundle_secret_id_template = bundle_secret_id_template
        self.bundle_format = bundle_format
        self.version = version
        self.client_options = client_options
        self.secret_definitions = _build_secret_definitions(secrets)
        self._client = client

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        client = self._client or self._build_client()

        if self.secret_definitions:
            secrets: Dict[str, Any] = {}
            for definition in self.secret_definitions:
                secret_id = definition.resolve_identifier(tenant_id, self.secret_id_template)
                payload = self._access_secret(
                    client,
                    secret_id,
                    version=definition.version_id or self.version,
                )
                secrets[definition.name] = _parse_secret_payload(
                    payload, format_hint=definition.format
                )
            return secrets

        if not self.bundle_secret_id_template:
            raise ValueError(
                "GCP Secret Manager requires either 'secrets' definitions or 'bundle_secret_id_template'."
            )

        bundle_id = self.bundle_secret_id_template.format(tenant=tenant_id)
        payload = self._access_secret(client, bundle_id, version=self.version)
        parsed = _parse_secret_payload(payload, format_hint=self.bundle_format)
        if not isinstance(parsed, dict):
            raise ValueError("GCP bundle secret must deserialize into a dictionary.")
        return _expand_env_vars_in_dict(parsed)

    def _build_client(self) -> Any:
        try:
            from google.cloud import secretmanager
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "google-cloud-secret-manager is required for GCP secret manager support."
            ) from exc
        return secretmanager.SecretManagerServiceClient(client_options=self.client_options)

    def _access_secret(self, client: Any, secret_id: str, version: Optional[str]) -> str:
        resource_name = self._build_resource_name(secret_id, version or self.version)
        response = client.access_secret_version(name=resource_name)
        data = response.payload.data
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return str(data)

    def _build_resource_name(self, secret_id: str, version: str) -> str:
        if secret_id.startswith("projects/"):
            base = secret_id
        else:
            base = f"projects/{self.project_id}/secrets/{secret_id}"
        return f"{base}/versions/{version}"


SECRET_MANAGER_REGISTRY = {
    "env": EnvironmentSecretManager,
    "environment": EnvironmentSecretManager,
    "filesystem": FilesystemSecretManager,
    "fs": FilesystemSecretManager,
    "file": FilesystemSecretManager,
    "vault": HashicorpVaultSecretManager,
    "hashicorp": HashicorpVaultSecretManager,
    "hashicorp_vault": HashicorpVaultSecretManager,
    "aws": AWSSecretsManager,
    "aws_secrets_manager": AWSSecretsManager,
    "gcp": GCPSecretManager,
    "gcp_secret_manager": GCPSecretManager,
}


def create_secret_manager(
    manager_type: Optional[str],
    secrets_dir: Path = Path("/secrets"),
    config: Optional[Dict[str, Any]] = None,
) -> SecretManager:
    """Instantiate the requested secret manager."""

    normalized = (manager_type or "env").lower()
    manager_cls = SECRET_MANAGER_REGISTRY.get(normalized)
    if not manager_cls:
        raise ValueError(
            f"Unsupported secret manager '{manager_type}'. "
            f"Supported managers: {sorted(set(SECRET_MANAGER_REGISTRY))}"
        )

    config = config or {}
    if manager_cls is FilesystemSecretManager and "secrets_dir" not in config:
        config = {**config, "secrets_dir": secrets_dir}

    return manager_cls(**config)


def load_secrets(
    tenant_id: str,
    secrets_dir: Path = Path("/secrets"),
    manager_type: Optional[str] = None,
    manager_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Load secrets using the configured secret manager.

    Args:
        tenant_id: Tenant identifier
        secrets_dir: Base directory for filesystem manager fallback
        manager_type: Secret manager identifier (env, filesystem, vault, aws, gcp)
        manager_config: Optional configuration dictionary passed to the manager

    Returns:
        Dictionary of loaded secrets (may be empty if manager has nothing to return)
    """

    manager = create_secret_manager(
        manager_type=manager_type or "env",
        secrets_dir=secrets_dir,
        config=manager_config,
    )
    return manager.load_secrets(tenant_id)


def _parse_env_blob(blob: str) -> Dict[str, str]:
    env_vars: Dict[str, str] = {}
    for raw_line in blob.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_vars[key.strip()] = os.path.expandvars(value.strip().strip('"').strip("'"))
    return env_vars


def _parse_secret_payload(payload: Any, format_hint: Optional[str] = None) -> Any:
    if isinstance(payload, (dict, list)):
        return _expand_env_vars_in_dict(payload)

    if payload is None:
        return payload

    if not isinstance(payload, str):
        return payload

    text = payload.strip()
    hint = (format_hint or "auto").lower()

    if hint == "json" or (hint == "auto" and text.startswith(("{", "["))):
        try:
            return _expand_env_vars_in_dict(json.loads(text))
        except json.JSONDecodeError:
            if hint == "json":
                raise
    if hint == "env" or (hint == "auto" and "\n" in text and "=" in text):
        return _parse_env_blob(text)
    if hint == "text" or hint == "raw":
        return os.path.expandvars(text)

    # auto fallback
    return os.path.expandvars(text)


def _expand_env_vars_in_dict(data: Any) -> Any:
    """Recursively expand environment variables in dictionary values."""
    if isinstance(data, dict):
        return {k: _expand_env_vars_in_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_expand_env_vars_in_dict(item) for item in data]
    if isinstance(data, str):
        return os.path.expandvars(data)
    return data


def validate_secrets_for_connector(
    secrets: Dict[str, Any], connector_type: str, credentials_config: Dict[str, Any]
) -> bool:
    """Validate that required secrets are present for a connector."""
    required_secrets: List[str] = []

    # Check credentials configuration
    cred_type = credentials_config.get("type", "none")
    if cred_type == "none":
        return True  # No credentials needed

    # Check for file_template
    if "file_template" in credentials_config:
        file_template = credentials_config["file_template"]
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

