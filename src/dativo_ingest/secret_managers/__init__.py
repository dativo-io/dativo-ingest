"""Pluggable secret management system supporting multiple backends.

This module provides a flexible secret management architecture that supports:
- Environment variables (default)
- Filesystem-based storage (backward compatibility)
- HashiCorp Vault
- AWS Secrets Manager
- GCP Secret Manager

The appropriate backend is selected based on configuration, allowing users
to choose their preferred secure credential storage.
"""

from .base import SecretManager
from .env_manager import EnvSecretManager
from .filesystem_manager import FilesystemSecretManager
from .factory import create_secret_manager

__all__ = [
    "SecretManager",
    "EnvSecretManager",
    "FilesystemSecretManager",
    "create_secret_manager",
]

# Optional imports for cloud providers
try:
    from .vault_manager import HashiCorpVaultSecretManager
    __all__.append("HashiCorpVaultSecretManager")
except ImportError:
    pass

try:
    from .aws_manager import AWSSecretManager
    __all__.append("AWSSecretManager")
except ImportError:
    pass

try:
    from .gcp_manager import GCPSecretManager
    __all__.append("GCPSecretManager")
except ImportError:
    pass
