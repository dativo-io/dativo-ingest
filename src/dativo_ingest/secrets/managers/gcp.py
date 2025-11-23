"""Google Cloud Secret Manager implementation."""

import os
from typing import Any, Dict, Iterable, Optional

from ..base import SecretManager, build_secret_definitions
from ..parsers import expand_env_vars_in_dict, parse_secret_payload


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
        self.secret_definitions = build_secret_definitions(secrets)
        self._client = client

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from GCP Secret Manager.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary of loaded secrets

        Raises:
            ValueError: If neither secrets definitions nor bundle template is provided
        """
        client = self._client or self._build_client()

        if self.secret_definitions:
            secrets: Dict[str, Any] = {}
            for definition in self.secret_definitions:
                secret_id = definition.resolve_identifier(
                    tenant_id, self.secret_id_template
                )
                payload = self._access_secret(
                    client,
                    secret_id,
                    version=definition.version_id or self.version,
                )
                secrets[definition.name] = parse_secret_payload(
                    payload, format_hint=definition.format
                )
            return secrets

        if not self.bundle_secret_id_template:
            raise ValueError(
                "GCP Secret Manager requires either 'secrets' definitions or 'bundle_secret_id_template'."
            )

        bundle_id = self.bundle_secret_id_template.format(tenant=tenant_id)
        payload = self._access_secret(client, bundle_id, version=self.version)
        parsed = parse_secret_payload(payload, format_hint=self.bundle_format)
        if not isinstance(parsed, dict):
            raise ValueError("GCP bundle secret must deserialize into a dictionary.")
        return expand_env_vars_in_dict(parsed)

    def _build_client(self) -> Any:
        """Build GCP Secret Manager client.

        Returns:
            GCP Secret Manager client

        Raises:
            ImportError: If google-cloud-secret-manager is not installed
        """
        try:
            from google.cloud import secretmanager
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise ImportError(
                "google-cloud-secret-manager is required for GCP secret manager support."
            ) from exc
        return secretmanager.SecretManagerServiceClient(
            client_options=self.client_options
        )

    def _access_secret(
        self, client: Any, secret_id: str, version: Optional[str]
    ) -> str:
        """Access a secret version from GCP Secret Manager.

        Args:
            client: GCP Secret Manager client
            secret_id: Secret identifier
            version: Secret version (defaults to self.version)

        Returns:
            Secret payload as string
        """
        resource_name = self._build_resource_name(secret_id, version or self.version)
        response = client.access_secret_version(name=resource_name)
        data = response.payload.data
        if isinstance(data, bytes):
            return data.decode("utf-8")
        return str(data)

    def _build_resource_name(self, secret_id: str, version: str) -> str:
        """Build GCP secret resource name.

        Args:
            secret_id: Secret identifier
            version: Secret version

        Returns:
            Full resource name path
        """
        if secret_id.startswith("projects/"):
            base = secret_id
        else:
            base = f"projects/{self.project_id}/secrets/{secret_id}"
        return f"{base}/versions/{version}"
