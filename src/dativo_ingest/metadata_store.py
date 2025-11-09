"""Lightweight metadata store for persisting contract runtime context for AI APIs."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .config import AssetDefinition

DEFAULT_METADATA_DIR = Path(os.getenv("METADATA_STATE_DIR", ".local/metadata")).expanduser()


def _ensure_serializable(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure payload elements are JSON serializable."""

    def _convert(value: Any) -> Any:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.isoformat()
        if isinstance(value, dict):
            return {k: _convert(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_convert(item) for item in value]
        return value

    return _convert(payload)


def update_asset_metadata(
    asset: AssetDefinition,
    *,
    metadata: Dict[str, Any],
    metadata_dir: Optional[Path] = None,
) -> Path:
    """Persist metadata for the given asset to disk."""

    metadata_dir = metadata_dir or DEFAULT_METADATA_DIR
    metadata_dir.mkdir(parents=True, exist_ok=True)

    asset_payload = asset.model_dump(mode="json", by_alias=True, exclude_none=True)

    record = {
        "asset": asset_payload,
        "metrics": _ensure_serializable(
            {
                **metadata,
                "timestamp": metadata.get("timestamp")
                or datetime.now(tz=timezone.utc).isoformat(),
            }
        ),
    }

    path = metadata_dir / f"{asset.name}.json"
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(record, handle, indent=2)
    return path


def load_asset_metadata(asset_name: str, metadata_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Load persisted metadata for an asset."""

    metadata_dir = metadata_dir or DEFAULT_METADATA_DIR
    path = metadata_dir / f"{asset_name}.json"
    if not path.exists():
        raise FileNotFoundError(f"Metadata for asset '{asset_name}' not found at {path}")
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


__all__ = ["update_asset_metadata", "load_asset_metadata", "DEFAULT_METADATA_DIR"]
