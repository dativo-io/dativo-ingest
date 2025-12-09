"""Factory for creating extractor instances."""

from typing import Any, Dict, Optional, Tuple

from ..config import ConnectorRecipe, JobConfig, SourceConfig
from ..logging import get_logger
from ..plugins import PluginLoader, extract_sandbox_config


class ExtractorFactory:
    """Factory for creating extractor instances based on source type and configuration."""

    @staticmethod
    def create(
        source_config: SourceConfig,
        job_config: JobConfig,
        tenant_id: Optional[str] = None,
        mode: str = "self_hosted",
        asset_definition: Optional[Any] = None,
    ) -> Tuple[Any, Optional[Dict[str, Any]]]:
        """Create extractor instance based on source configuration.

        Args:
            source_config: Source configuration
            job_config: Job configuration
            tenant_id: Optional tenant ID
            mode: Execution mode (default: self_hosted)
            asset_definition: Optional asset definition (required for mimesis connector)

        Returns:
            Tuple of (extractor, source_tags). source_tags may be None.

        Raises:
            ValueError: If extractor type is not supported or initialization fails
        """
        logger = get_logger()
        source_tags = None

        # Handle custom readers
        if source_config.custom_reader:
            logger.info(
                f"Loading custom reader from: {source_config.custom_reader}",
                extra={
                    "custom_reader": source_config.custom_reader,
                    "event_type": "custom_reader_loading",
                },
            )

            sandbox_config, plugin_config = extract_sandbox_config(job_config)

            reader_class = PluginLoader.load_reader(
                source_config.custom_reader,
                mode=mode,
                sandbox_config=sandbox_config,
                plugin_config=plugin_config,
            )
            extractor = reader_class(source_config)

            logger.info(
                "Custom reader initialized",
                extra={
                    "custom_reader": source_config.custom_reader,
                    "event_type": "custom_reader_initialized",
                },
            )
            return extractor, source_tags

        # Load connector recipe to determine engine type
        connector_recipe = None
        if (
            hasattr(job_config, "source_connector_path")
            and job_config.source_connector_path
        ):
            try:
                connector_recipe = ConnectorRecipe.from_yaml(
                    job_config.source_connector_path
                )
            except Exception as e:
                logger.warning(
                    f"Failed to load connector recipe: {e}. Using default engine selection.",
                    extra={"event_type": "connector_recipe_warning"},
                )

        # Check engine type if connector recipe is available
        engine_type = None
        if connector_recipe:
            default_engine = connector_recipe.default_engine
            if isinstance(default_engine, dict):
                engine_type = default_engine.get("type")
            elif default_engine:
                engine_type = str(default_engine)

        # Route to connector-specific extractors first (to preserve custom metadata),
        # then fall back to engine framework or native extractors
        if source_config.type == "stripe":
            if connector_recipe:
                from .stripe_extractor import StripeExtractor

                extractor = StripeExtractor(source_config, connector_recipe, tenant_id)
            else:
                raise ValueError(
                    "Stripe connector requires connector_recipe for Airbyte engine"
                )
        elif source_config.type == "hubspot":
            if connector_recipe:
                from .hubspot_extractor import HubSpotExtractor

                extractor = HubSpotExtractor(source_config, connector_recipe, tenant_id)
            else:
                raise ValueError(
                    "HubSpot connector requires connector_recipe for Airbyte engine"
                )
        elif source_config.type in ("mimesis", "synthetic"):
            # Handle both "mimesis" (canonical) and "synthetic" (deprecated alias)
            if source_config.type == "synthetic":
                logger.warning(
                    "Connector type 'synthetic' is deprecated. Use 'mimesis' instead.",
                    extra={
                        "event_type": "deprecated_connector_type",
                        "old_type": "synthetic",
                        "new_type": "mimesis",
                    },
                )

            from .mimesis_extractor import MimesisExtractor
            from ..config import AssetDefinition

            # Validate asset_definition is present and correct type
            if asset_definition is None:
                raise ValueError(
                    "Mimesis connector requires asset_definition. "
                    "Ensure asset is loaded before initializing extractor."
                )
            if not isinstance(asset_definition, AssetDefinition):
                raise ValueError(
                    f"asset_definition must be AssetDefinition instance, got {type(asset_definition)}"
                )

            extractor = MimesisExtractor(source_config, asset_definition)
        elif source_config.type == "csv":
            from .csv_extractor import CSVExtractor

            extractor = CSVExtractor(source_config)
        elif source_config.type == "postgres":
            from .postgres_extractor import PostgresExtractor

            extractor = PostgresExtractor(source_config)
        elif source_config.type == "mysql":
            from .mysql_extractor import MySQLExtractor

            extractor = MySQLExtractor(source_config)
        elif engine_type == "airbyte":
            from .engine_framework import AirbyteExtractor

            extractor = AirbyteExtractor(source_config, connector_recipe, tenant_id)
            logger.info(
                f"Using Airbyte engine for {source_config.type}",
                extra={
                    "connector_type": source_config.type,
                    "engine_type": "airbyte",
                    "event_type": "extractor_initialized",
                },
            )
        elif engine_type == "meltano":
            from .engine_framework import MeltanoExtractor

            extractor = MeltanoExtractor(source_config, connector_recipe, tenant_id)
            logger.info(
                f"Using Meltano engine for {source_config.type}",
                extra={
                    "connector_type": source_config.type,
                    "engine_type": "meltano",
                    "event_type": "extractor_initialized",
                },
            )
        elif engine_type == "singer":
            from .engine_framework import SingerExtractor

            extractor = SingerExtractor(source_config, connector_recipe, tenant_id)
            logger.info(
                f"Using Singer engine for {source_config.type}",
                extra={
                    "connector_type": source_config.type,
                    "engine_type": "singer",
                    "event_type": "extractor_initialized",
                },
            )
        elif source_config.type == "gdrive_csv":
            from .gdrive_csv_extractor import GDriveCSVExtractor

            extractor = GDriveCSVExtractor(source_config, connector_recipe, tenant_id)
        elif source_config.type == "google_sheets":
            from .google_sheets_extractor import GoogleSheetsExtractor

            extractor = GoogleSheetsExtractor(
                source_config, connector_recipe, tenant_id
            )
        else:
            raise ValueError(
                f"Unsupported source type: {source_config.type}. "
                "Either use a supported type or specify a custom_reader in the source configuration."
            )

        # Extract source tags from extractor if available (for three-level tag hierarchy)
        if hasattr(extractor, "extract_metadata"):
            try:
                metadata = extractor.extract_metadata()
                if metadata and isinstance(metadata, dict):
                    source_tags = metadata.get("tags") or metadata.get("source_tags")
                    if source_tags:
                        logger.info(
                            "Source tags extracted from connector",
                            extra={
                                "source_tags_count": len(source_tags),
                                "event_type": "source_tags_extracted",
                            },
                        )
            except Exception as e:
                logger.debug(
                    f"Failed to extract source tags from connector (non-critical): {e}",
                    extra={"event_type": "source_tags_extraction_failed"},
                )
        elif hasattr(extractor, "get_source_tags"):
            try:
                source_tags = extractor.get_source_tags()
                if source_tags:
                    logger.info(
                        "Source tags extracted from connector",
                        extra={
                            "source_tags_count": len(source_tags),
                            "event_type": "source_tags_extracted",
                        },
                    )
            except Exception as e:
                logger.debug(
                    f"Failed to extract source tags from connector (non-critical): {e}",
                    extra={"event_type": "source_tags_extraction_failed"},
                )

        if not source_config.custom_reader:
            logger.info(
                "Extractor initialized",
                extra={
                    "source_type": source_config.type,
                    "event_type": "extractor_initialized",
                },
            )

        return extractor, source_tags
