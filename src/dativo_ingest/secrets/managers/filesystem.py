"""Filesystem-based secret manager."""

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict

from ..base import SecretManager
from ..parsers import expand_env_vars_in_dict, parse_env_blob


class FilesystemSecretManager(SecretManager):
    """Load secrets from tenant-specific directories on disk."""

    type_name = "filesystem"

    def __init__(self, secrets_dir: Path = Path("/secrets"), **config: Any) -> None:
        super().__init__(secrets_dir=secrets_dir, **config)
        self.secrets_dir = Path(secrets_dir)

    def load_secrets(self, tenant_id: str) -> Dict[str, Any]:
        """Load secrets from filesystem directory.

        Args:
            tenant_id: Tenant identifier

        Returns:
            Dictionary of loaded secrets

        Raises:
            ValueError: If tenant secrets directory does not exist
        """
        tenant_secrets_dir = self.secrets_dir / tenant_id
        if not tenant_secrets_dir.exists():
            raise ValueError(f"Secrets directory not found: {tenant_secrets_dir}")

        secrets: Dict[str, Any] = {}
        logger = logging.getLogger(__name__)

        for secret_file in tenant_secrets_dir.iterdir():
            if not secret_file.is_file() or secret_file.name.startswith("."):
                continue

            secret_name = secret_file.stem
            try:
                if secret_file.suffix == ".json":
                    with open(secret_file, "r", encoding="utf-8") as handle:
                        secrets[secret_name] = expand_env_vars_in_dict(
                            json.load(handle)
                        )
                elif secret_file.suffix == ".env":
                    with open(secret_file, "r", encoding="utf-8") as handle:
                        secrets[secret_name] = parse_env_blob(handle.read())
                else:
                    with open(secret_file, "r", encoding="utf-8") as handle:
                        secrets[secret_name] = os.path.expandvars(handle.read().strip())
            except Exception as exc:  # pragma: no cover - defensive logging
                logger.warning(
                    "Failed to load secret file %s: %s",
                    secret_file,
                    exc,
                    extra={"secret_file": str(secret_file), "error": str(exc)},
                )
        return secrets
