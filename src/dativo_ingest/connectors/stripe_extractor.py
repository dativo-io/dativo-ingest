"""Stripe connector using Airbyte."""

import os
from typing import Any, Dict, Iterator, List, Optional

from ..config import ConnectorRecipe, SourceConfig
from ..validator import IncrementalStateManager
from .engine_config import EngineConfigParser
from .engine_framework import AirbyteExtractor


class StripeConfigParser(EngineConfigParser):
    """Stripe-specific configuration parser that handles Stripe API requirements."""

    def _get_credentials(self) -> Dict[str, Any]:
        """Extract and map Stripe credentials.

        Stripe-specific: Maps API key to 'client_secret' (Airbyte Stripe requirement).

        Returns:
            Dictionary of credentials with client_secret and account_id
        """
        credentials = {}

        # Get credentials from connector recipe
        recipe_creds = self.connector_recipe.credentials or {}
        cred_type = recipe_creds.get("type", "")

        if cred_type == "api_key":
            # API key from environment variable
            env_var = recipe_creds.get("from_env", "")
            if env_var:
                api_key = os.getenv(env_var)
                if api_key:
                    # Airbyte Stripe uses "client_secret" for the API key
                    credentials["client_secret"] = api_key
                    # Account ID is required by Airbyte Stripe - try to get from env
                    account_id = os.getenv("STRIPE_ACCOUNT_ID") or os.getenv(
                        "STRIPE_ACCOUNT"
                    )
                    if account_id:
                        credentials["account_id"] = account_id

        elif cred_type == "service_account":
            # Service account file
            import json
            from pathlib import Path

            file_template = recipe_creds.get("file_template", "")
            if file_template:
                # Use tenant_id from parser or default
                tenant_id = self.tenant_id or "default"
                # Replace {tenant} placeholder
                creds_path = file_template.replace("{tenant}", tenant_id)
                if Path(creds_path).exists():
                    with open(creds_path, "r") as f:
                        credentials = json.load(f)

        # Override with source config credentials if provided
        if self.source_config.credentials:
            if isinstance(self.source_config.credentials, dict):
                credentials.update(self.source_config.credentials)

        return credentials

    def build_airbyte_config(self) -> Dict[str, Any]:
        """Build Airbyte Stripe connector configuration.

        Stripe-specific: Handles account_id auto-fetching and ISO 8601 date format.

        Returns:
            Airbyte Stripe configuration dictionary
        """
        # Get base config from parent
        config = super().build_airbyte_config()

        # Stripe-specific: Ensure account_id is present
        # If not provided, try to fetch it from Stripe API
        if "account_id" not in config and "client_secret" in config:
            # Try to get account_id from environment first
            account_id = os.getenv("STRIPE_ACCOUNT_ID") or os.getenv("STRIPE_ACCOUNT")
            if not account_id:
                # Auto-fetch from Stripe API
                try:
                    import requests

                    api_key = config.get("client_secret")
                    if api_key:
                        response = requests.get(
                            "https://api.stripe.com/v1/account",
                            auth=(api_key, ""),
                            timeout=5,
                        )
                        if response.status_code == 200:
                            account_data = response.json()
                            account_id = account_data.get("id")
                            if account_id:
                                config["account_id"] = account_id
                except Exception:
                    # Silently fail - account_id will be missing and Airbyte will error with clear message
                    pass
            else:
                config["account_id"] = account_id

        # Stripe-specific: Ensure start_date is in ISO 8601 format (YYYY-MM-DDTHH:MM:SSZ)
        if "start_date" in config:
            start_date = config["start_date"]
            if (
                isinstance(start_date, str)
                and len(start_date) == 10
                and start_date.count("-") == 2
            ):
                # Date format: YYYY-MM-DD -> convert to YYYY-MM-DDTHH:MM:SSZ
                config["start_date"] = f"{start_date}T00:00:00Z"

        return config


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
        # Initialize parent but replace config_parser with Stripe-specific one
        super().__init__(source_config, connector_recipe, tenant_id)
        # Replace the generic config parser with Stripe-specific one
        self.config_parser = StripeConfigParser(
            source_config, connector_recipe, tenant_id
        )

    def extract(
        self,
        state_manager: Optional[IncrementalStateManager] = None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Stripe.

        Args:
            state_manager: Optional incremental state manager
            checkpoint_context: Optional checkpoint context for WAL resume

        Yields:
            Batches of records as dictionaries
        """
        # Use parent AirbyteExtractor's extract method
        yield from super().extract(state_manager, checkpoint_context=checkpoint_context)

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
