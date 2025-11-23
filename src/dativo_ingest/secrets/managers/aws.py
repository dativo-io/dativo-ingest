"""AWS Secrets Manager implementation."""

from typing import Any, Dict, Iterable, Optional

from ..base import SecretManager, build_secret_definitions
from ..parsers import expand_env_vars_in_dict, parse_secret_payload


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
        self.secret_definitions = build_secret_definitions(secrets)
        self._client = client

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from AWS Secrets Manager.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary of loaded secrets

        Raises:
            ValueError: If neither secrets definitions nor bundle template is provided
        """
        client = self._client or self._build_client()

        if self.secret_definitions:
            result: Dict[str, Any] = {}
            for definition in self.secret_definitions:
                secret_id = definition.resolve_identifier(
                    tenant_id, self.secret_id_template
                )
                payload = self._get_secret_value(
                    client,
                    secret_id,
                    version_id=definition.version_id,
                    version_stage=definition.version_stage,
                )
                result[definition.name] = parse_secret_payload(
                    payload, format_hint=definition.format
                )
            return result

        if not self.bundle_secret_id_template:
            raise ValueError(
                "AWS Secrets Manager requires either 'secrets' definitions or 'bundle_secret_id_template'."
            )

        bundle_id = self.bundle_secret_id_template.format(tenant=tenant_id)
        payload = self._get_secret_value(client, bundle_id)
        parsed = parse_secret_payload(payload, format_hint=self.bundle_format)
        if not isinstance(parsed, dict):
            raise ValueError("AWS bundle secret must deserialize into a dictionary.")
        return expand_env_vars_in_dict(parsed)

    def _build_client(self) -> Any:
        """Build AWS Secrets Manager client.

        Returns:
            boto3 Secrets Manager client

        Raises:
            ImportError: If boto3 is not installed
        """
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
        client: Any,
        secret_id: str,
        version_id: Optional[str] = None,
        version_stage: Optional[str] = None,
    ) -> str:
        """Retrieve secret value from AWS Secrets Manager.

        Args:
            client: boto3 Secrets Manager client
            secret_id: Secret identifier
            version_id: Optional version ID
            version_stage: Optional version stage

        Returns:
            Secret value as string
        """
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
        # boto3 already base64-decodes SecretBinary from the API response, so we just decode bytes to UTF-8
        if isinstance(binary_secret, bytes):
            return binary_secret.decode("utf-8")
        # Fallback for non-bytes (shouldn't happen, but handle gracefully)
        return str(binary_secret)
