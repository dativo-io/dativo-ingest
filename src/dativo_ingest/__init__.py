"""Dativo ingestion runner - core framework for config-driven data ingestion."""

import re
from pathlib import Path

# Try to get version from installed package first
try:
    from importlib.metadata import version, PackageNotFoundError
    try:
        __version__ = version("dativo-ingest")
    except PackageNotFoundError:
        raise
except (ImportError, PackageNotFoundError):
    # Package not installed, read from pyproject.toml
    pyproject_path = Path(__file__).parent.parent.parent / "pyproject.toml"
    if pyproject_path.exists():
        with open(pyproject_path, "r", encoding="utf-8") as f:
            content = f.read()
            # Simple regex to extract version from pyproject.toml
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                __version__ = match.group(1)
            else:
                __version__ = "1.1.0"  # Fallback
    else:
        __version__ = "1.1.0"  # Fallback

