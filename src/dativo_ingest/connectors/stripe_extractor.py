"""Stripe connector using Airbyte."""

from typing import Any, Dict, Iterator, List, Optional

from ..config import ConnectorRecipe, SourceConfig
from ..validator import IncrementalStateManager
from .engine_framework import AirbyteExtractor


class StripeExtractor(AirbyteExtractor):
    """Extracts data from Stripe using Airbyte connector.

    Replaces the previous native Python implementation with Airbyte wrapper
    for better connector ecosystem support and maintenance.
    """

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: ConnectorRecipe,
        tenant_id: Optional[str] = None,
    ):
        """Initialize Stripe extractor.

        Args:
            source_config: Source configuration with objects and credentials
            connector_recipe: Stripe connector recipe
            tenant_id: Optional tenant ID for credential path resolution
        """
        super().__init__(source_config, connector_recipe, tenant_id)

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Stripe.

        Args:
            state_manager: Optional incremental state manager

        Yields:
            Batches of records as dictionaries
        """
        # Use parent AirbyteExtractor's extract method
        yield from super().extract(state_manager)

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract metadata for Dagster asset tags.

        Returns:
            Dictionary with 'tags' key containing metadata
        """
        base_metadata = super().extract_metadata()
        base_metadata["tags"].update(
            {
                "connector": "stripe",
                "category": "payments",
            }
        )
        return base_metadata
