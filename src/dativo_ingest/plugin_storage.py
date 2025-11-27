"""Utilities for resolving custom plugin paths from local or cloud storage."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

from .exceptions import PluginError

REMOTE_SCHEMES = ("s3://", "gs://")
DEFAULT_CACHE_ENV = "DATIVO_PLUGIN_CACHE_DIR"
DEFAULT_CACHE_DIR = ".local/plugins"


def is_remote_plugin_uri(path: str) -> bool:
    """Return True when the plugin path references a supported remote scheme."""
    if not path:
        return False
    return path.startswith(REMOTE_SCHEMES)


def resolve_plugin_path(plugin_identifier: str) -> str:
    """Resolve a plugin identifier to a local filesystem path.

    Args:
        plugin_identifier: Full plugin identifier (e.g. path.py:ClassName).

    Returns:
        Updated identifier that points to a local file.
    """
    module_path, suffix = _split_plugin_identifier(plugin_identifier)
    resolved_module_path = ensure_local_plugin_file(module_path)

    if suffix:
        return f"{resolved_module_path}:{suffix}"
    return resolved_module_path


def ensure_local_plugin_file(path: str) -> str:
    """Ensure the provided plugin path exists locally, downloading if required."""
    expanded = os.path.expandvars(os.path.expanduser(path))
    if is_remote_plugin_uri(expanded):
        local_path = _download_remote_plugin(expanded)
    else:
        local_path = Path(expanded)
        if not local_path.is_absolute():
            local_path = local_path.resolve()
    return str(local_path)


def _split_plugin_identifier(identifier: str) -> Tuple[str, Optional[str]]:
    if ":" not in identifier:
        return identifier, None
    module_path, suffix = identifier.rsplit(":", 1)
    return module_path, suffix


def _download_remote_plugin(uri: str) -> Path:
    cache_dir = _get_cache_dir()
    parsed = urlparse(uri)
    extension = Path(parsed.path).suffix or ".plugin"
    digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()
    cache_path = cache_dir / f"{digest}{extension}"

    if cache_path.exists():
        return cache_path

    tmp_path = cache_path.with_suffix(cache_path.suffix + ".tmp")

    try:
        if uri.startswith("s3://"):
            _download_s3_uri(uri, tmp_path)
        elif uri.startswith("gs://"):
            _download_gcs_uri(uri, tmp_path)
        else:
            raise PluginError(
                f"Unsupported remote plugin URI: {uri}",
                details={"uri": uri},
            )
        tmp_path.replace(cache_path)
        return cache_path
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


def _get_cache_dir() -> Path:
    cache_dir = Path(os.getenv(DEFAULT_CACHE_ENV, DEFAULT_CACHE_DIR)).expanduser()
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _parse_bucket_and_key(uri: str) -> Tuple[str, str]:
    parsed = urlparse(uri)
    bucket = parsed.netloc
    key = parsed.path.lstrip("/")
    if not bucket or not key:
        raise PluginError(
            f"Invalid remote plugin URI: {uri}",
            details={"uri": uri},
        )
    return bucket, key


def _download_s3_uri(uri: str, destination: Path) -> None:
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError
    except ImportError as exc:
        raise PluginError(
            "boto3 is required for downloading plugins from S3.",
            details={"uri": uri},
        ) from exc

    bucket, key = _parse_bucket_and_key(uri)
    client = boto3.client("s3")
    try:
        client.download_file(bucket, key, str(destination))
    except (ClientError, BotoCoreError, OSError) as exc:
        raise PluginError(
            f"Failed to download plugin from {uri}",
            details={"uri": uri, "bucket": bucket, "key": key},
            retryable=True,
        ) from exc


def _download_gcs_uri(uri: str, destination: Path) -> None:
    try:
        from google.cloud import storage
        from google.cloud.exceptions import GoogleCloudError
    except ImportError as exc:
        raise PluginError(
            "google-cloud-storage is required for downloading plugins from GCS.",
            details={"uri": uri},
        ) from exc

    bucket_name, blob_name = _parse_bucket_and_key(uri)
    client = storage.Client()
    bucket = client.bucket(bucket_name)
    blob = bucket.blob(blob_name)
    try:
        blob.download_to_filename(str(destination))
    except (GoogleCloudError, OSError) as exc:
        raise PluginError(
            f"Failed to download plugin from {uri}",
            details={"uri": uri, "bucket": bucket_name, "object": blob_name},
            retryable=True,
        ) from exc


__all__ = [
    "ensure_local_plugin_file",
    "is_remote_plugin_uri",
    "resolve_plugin_path",
]
