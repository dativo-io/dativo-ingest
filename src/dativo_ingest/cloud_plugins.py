"""Utilities for resolving custom plugin files stored in cloud object storage.

This module provides a thin abstraction for fetching Python/Rust plugin
artifacts from AWS S3 and Google Cloud Storage. Files are materialized into a
local cache directory so the rest of the plugin loader can treat them like any
other on-disk module/shared library.
"""

from __future__ import annotations

import logging
import os
import shutil
import tempfile
from pathlib import Path
from typing import Callable, Dict, IO, Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

CACHE_ENV_VAR = "DATIVO_PLUGIN_CACHE_DIR"
REFRESH_ENV_VAR = "DATIVO_PLUGIN_REFRESH"
SUPPORTED_SCHEMES = ("s3", "gs")

try:
    import boto3  # type: ignore
except ImportError:  # pragma: no cover - boto3 is part of base deps but guard anyway
    boto3 = None  # type: ignore

try:
    from google.cloud import storage  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    storage = None  # type: ignore


def is_cloud_uri(path: str) -> bool:
    """Return True if the provided path points to a supported cloud URI."""
    if not path:
        return False
    parsed = urlparse(os.path.expandvars(path))
    return parsed.scheme.lower() in SUPPORTED_SCHEMES


def _should_refresh() -> bool:
    """Check whether downloads should be refreshed regardless of cache state."""
    value = os.getenv(REFRESH_ENV_VAR, "")
    return value.lower() in {"1", "true", "yes", "on"}


class CloudPluginResolver:
    """Resolve plugin files that live in cloud object storage."""

    def __init__(self, cache_dir: Optional[str] = None):
        base_cache = cache_dir or os.getenv(CACHE_ENV_VAR)
        if base_cache:
            self.cache_dir = Path(base_cache).expanduser()
        else:
            self.cache_dir = Path(tempfile.gettempdir()) / "dativo_plugins"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._resolved: Dict[str, Path] = {}

    def resolve(self, path: str) -> Path:
        """Resolve a plugin path, downloading it if it points to cloud storage."""
        candidate = os.path.expandvars(path)
        if not is_cloud_uri(candidate):
            return Path(candidate).expanduser()

        normalized = self._normalize(candidate)
        cached = self._resolved.get(normalized)
        if cached and cached.exists() and not _should_refresh():
            return cached

        parsed = urlparse(candidate)
        scheme = parsed.scheme.lower()
        if scheme == "s3":
            resolved = self._download_from_s3(parsed)
        elif scheme == "gs":
            resolved = self._download_from_gcs(parsed)
        else:  # pragma: no cover - guarded by is_cloud_uri
            raise ValueError(f"Unsupported plugin scheme: {scheme}")

        self._resolved[normalized] = resolved
        return resolved

    def _normalize(self, path: str) -> str:
        """Produce a stable cache key for a remote path."""
        parsed = urlparse(path)
        return f"{parsed.scheme.lower()}://{parsed.netloc}{parsed.path}"

    def _download_from_s3(self, parsed) -> Path:
        """Download a plugin artifact from AWS S3."""
        if boto3 is None:  # pragma: no cover - boto3 is part of base deps
            raise ImportError(
                "boto3 is required to load plugins from s3:// URIs. "
                "Install the 'boto3' package or add it to your dependencies."
            )

        bucket = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket or not key:
            raise ValueError("s3:// URIs must include both bucket and key")

        dest = self._destination_path("s3", bucket, key)
        if dest.exists() and not _should_refresh():
            return dest

        s3_client = boto3.client("s3")
        return self._write_stream(
            dest,
            lambda fh: s3_client.download_fileobj(bucket, key, fh),
            f"s3://{bucket}/{key}",
        )

    def _download_from_gcs(self, parsed) -> Path:
        """Download a plugin artifact from Google Cloud Storage."""
        if storage is None:
            raise ImportError(
                "google-cloud-storage is required to load plugins from gs:// URIs. "
                "Install it with: pip install google-cloud-storage"
            )

        bucket_name = parsed.netloc
        key = parsed.path.lstrip("/")
        if not bucket_name or not key:
            raise ValueError("gs:// URIs must include both bucket and object path")

        dest = self._destination_path("gcs", bucket_name, key)
        if dest.exists() and not _should_refresh():
            return dest

        client = storage.Client()
        bucket = client.bucket(bucket_name)
        blob = bucket.blob(key)

        return self._write_stream(
            dest,
            lambda fh: blob.download_to_file(fh),
            f"gs://{bucket_name}/{key}",
        )

    def _destination_path(self, provider: str, bucket: str, key: str) -> Path:
        """Build a safe cache path for a remote object."""
        safe_parts = [part for part in key.split("/") if part and part not in (".", "..")]
        if not safe_parts:
            raise ValueError("Remote plugin key must reference a file")
        return self.cache_dir / provider / bucket / Path(*safe_parts)

    def _write_stream(
        self, dest: Path, writer: Callable[[IO[bytes]], None], identifier: str
    ) -> Path:
        """Write downloaded bytes into the destination atomically."""
        dest.parent.mkdir(parents=True, exist_ok=True)

        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=str(dest.parent),
            suffix=dest.suffix or ".bin",
        )
        try:
            with os.fdopen(tmp_fd, "wb") as handle:
                writer(handle)
            shutil.move(tmp_path, dest)
            logger.info("Materialized plugin '%s' at %s", identifier, dest)
        except Exception:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

        return dest


DEFAULT_RESOLVER = CloudPluginResolver()


def resolve_plugin_path(path: str) -> Path:
    """Public helper that resolves a plugin path using the default resolver."""
    return DEFAULT_RESOLVER.resolve(path)

