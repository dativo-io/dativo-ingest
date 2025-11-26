"""Factory for creating catalog instances."""

from typing import TYPE_CHECKING

from ..config import AssetDefinition, CatalogConfig, JobConfig

if TYPE_CHECKING:
    from .base import BaseCatalog

from .base import BaseCatalog


class CatalogFactory:
    """Factory for creating catalog instances based on type."""

    @staticmethod
    def create(
        catalog_config: CatalogConfig,
        asset_definition: AssetDefinition,
        job_config: JobConfig,
    ) -> BaseCatalog:
        """Create catalog instance based on type.

        Args:
            catalog_config: Catalog configuration
            asset_definition: Asset definition
            job_config: Job configuration

        Returns:
            Catalog instance

        Raises:
            ValueError: If catalog type is not supported
        """
        catalog_type = catalog_config.type.lower()

        if catalog_type == "aws_glue":
            from .aws_glue import AWSGlueCatalog

            return AWSGlueCatalog(catalog_config, asset_definition, job_config)
        elif catalog_type == "databricks_unity":
            from .databricks_unity import DatabricksUnityCatalog

            return DatabricksUnityCatalog(catalog_config, asset_definition, job_config)
        elif catalog_type == "nessie":
            from .nessie import NessieCatalog

            return NessieCatalog(catalog_config, asset_definition, job_config)
        elif catalog_type == "openmetadata":
            from .openmetadata import OpenMetadataCatalog

            return OpenMetadataCatalog(catalog_config, asset_definition, job_config)
        else:
            raise ValueError(
                f"Unsupported catalog type: {catalog_type}. "
                "Supported types: aws_glue, databricks_unity, nessie, openmetadata"
            )
