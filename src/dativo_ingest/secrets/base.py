"""Base classes and common utilities for secret managers."""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence


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
        pass


@dataclass
class SecretDefinition:
    """Concrete secret to resolve from a remote manager."""

    name: str
    identifier: Optional[str] = None
    version_stage: Optional[str] = None
    version_id: Optional[str] = None
    format: Optional[str] = None

    def resolve_identifier(self, tenant_id: str, template: str) -> str:
        """Resolve the secret identifier using tenant ID and template.

        Args:
            tenant_id: Tenant identifier
            template: Template string with {tenant} and {name} placeholders

        Returns:
            Resolved secret identifier
        """
        base = self.identifier or template
        return base.format(tenant=tenant_id, name=self.name)


def build_secret_definitions(
    entries: Optional[Iterable[Any]],
) -> List[SecretDefinition]:
    """Build SecretDefinition objects from configuration entries.

    Args:
        entries: Iterable of secret definitions (strings or dicts)

    Returns:
        List of SecretDefinition objects

    Raises:
        ValueError: If entry format is invalid
    """
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
