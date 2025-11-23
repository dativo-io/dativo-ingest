"""Environment variable-based secret manager."""

import os
from typing import Any, Dict, Sequence

from ..base import SecretManager
from ..parsers import parse_secret_payload


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
            prefix=prefix,
            delimiter=delimiter,
            allow_global_scope=allow_global_scope,
            **config,
        )
        self.prefix = prefix.upper()
        self.delimiter = delimiter
        self.allow_global_scope = allow_global_scope

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from environment variables.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary of loaded secrets
        """
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

            secrets[secret_name] = parse_secret_payload(value, format_hint=format_hint)

        return secrets

    @staticmethod
    def _sanitize_secret_name(parts: Sequence[str]) -> str:
        """Sanitize secret name parts into a single identifier.

        Args:
            parts: Sequence of name parts

        Returns:
            Sanitized secret name
        """
        cleaned = [part for part in parts if part]
        return "_".join(cleaned).lower()
