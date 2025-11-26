"""Factory for creating catalog clients."""

import logging
from typing import Optional

from .base import BaseCatalogClient, CatalogConfig

logger = logging.getLogger(__name__)


class CatalogClientFactory:
    """Factory for creating data catalog clients."""

    @staticmethod
    def create_client(config: CatalogConfig) -> BaseCatalogClient:
        """Create a catalog client based on configuration.

        Args:
            config: Catalog configuration

        Returns:
            Catalog client instance

        Raises:
            ValueError: If catalog type is not supported
        """
        catalog_type = config.type.lower()

        if catalog_type == "openmetadata":
            from .openmetadata_client import OpenMetadataClient

            return OpenMetadataClient(config)
        elif catalog_type == "aws_glue":
            from .glue_client import GlueClient

            return GlueClient(config)
        elif catalog_type == "databricks_unity":
            from .unity_client import UnityClient

            return UnityClient(config)
        elif catalog_type == "nessie":
            from .nessie_client import NessieClient

            return NessieClient(config)
        else:
            raise ValueError(
                f"Unsupported catalog type: {catalog_type}. "
                f"Supported types: openmetadata, aws_glue, databricks_unity, nessie"
            )

    @staticmethod
    def create_from_job_config(job_config_dict: dict) -> Optional[BaseCatalogClient]:
        """Create catalog client from job configuration dictionary.

        Args:
            job_config_dict: Job configuration dictionary

        Returns:
            Catalog client instance or None if catalog not configured

        Raises:
            ValueError: If catalog configuration is invalid
        """
        catalog_dict = job_config_dict.get("catalog")
        if not catalog_dict:
            return None

        if not catalog_dict.get("enabled", True):
            logger.info("Catalog integration is disabled in job configuration")
            return None

        try:
            config = CatalogConfig(
                type=catalog_dict["type"],
                connection=catalog_dict["connection"],
                enabled=catalog_dict.get("enabled", True),
                push_lineage=catalog_dict.get("push_lineage", True),
                push_metadata=catalog_dict.get("push_metadata", True),
            )
            return CatalogClientFactory.create_client(config)
        except KeyError as e:
            raise ValueError(
                f"Invalid catalog configuration: missing required field {e}"
            ) from e
        except Exception as e:
            raise ValueError(f"Failed to create catalog client: {e}") from e
