"""HubSpot connector using Airbyte."""

import os
from typing import Any, Dict, Iterator, List, Optional

from ..config import ConnectorRecipe, SourceConfig
from ..validator import IncrementalStateManager
from .engine_config import EngineConfigParser
from .engine_framework import AirbyteExtractor


class HubSpotConfigParser(EngineConfigParser):
    """HubSpot-specific configuration parser that handles HubSpot API requirements."""

    def _get_credentials(self) -> Dict[str, Any]:
        """
        HubSpot-specific: Maps credentials to nested 'credentials' structure (Airbyte HubSpot requirement).

        Airbyte HubSpot 0.2.0 requires OAuth credentials with client_id and client_secret.
        For private app tokens, we can use client_id as empty and client_secret as the access token.

        Returns:
            Dictionary with credentials nested under 'credentials' key
        """
        credentials = {}

        # Get credentials from connector recipe
        recipe_creds = self.connector_recipe.credentials or {}
        cred_type = recipe_creds.get("type", "")

        if cred_type in ["api_key", "oauth"]:
            # HubSpot authentication - supports both OAuth and Private App
            # Airbyte HubSpot 6.0.15+ supports both methods:
            # - OAuth: requires client_id, client_secret, refresh_token
            # - Private App: requires access_token (pat-*)

            # Get access token (for Private App)
            access_token = os.getenv("HUBSPOT_API_KEY") or os.getenv(
                "HUBSPOT_ACCESS_TOKEN"
            )

            # For OAuth flow
            oauth_client_id = os.getenv("HUBSPOT_CLIENT_ID")
            oauth_client_secret = os.getenv("HUBSPOT_OAUTH_CLIENT_SECRET")
            oauth_refresh_token = os.getenv("HUBSPOT_REFRESH_TOKEN")

            # Fallback: try from_env in recipe
            if not access_token:
                env_var = recipe_creds.get("from_env", "")
                if env_var:
                    access_token = os.getenv(env_var)

            # Determine authentication method
            if oauth_client_id and oauth_client_secret and oauth_refresh_token:
                # Full OAuth flow (for Airbyte HubSpot 6.0.15+)
                # credentials_title must be exactly "OAuth" (per schema)
                credentials["credentials"] = {
                    "credentials_title": "OAuth",
                    "client_id": oauth_client_id,
                    "client_secret": oauth_client_secret,
                    "refresh_token": oauth_refresh_token,
                }
            elif access_token:
                # Private App authentication (supported in Airbyte HubSpot 6.0.15+)
                # credentials_title must be exactly "Private App Credentials" (per schema)
                credentials["credentials"] = {
                    "credentials_title": "Private App Credentials",
                    "access_token": access_token,
                }
            else:
                # Missing credentials
                raise ValueError(
                    "HubSpot connector requires either:\n"
                    "  - Private App: HUBSPOT_API_KEY or HUBSPOT_ACCESS_TOKEN\n"
                    "  - OAuth: HUBSPOT_CLIENT_ID, HUBSPOT_OAUTH_CLIENT_SECRET, and HUBSPOT_REFRESH_TOKEN"
                )

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
                        creds_data = json.load(f)
                        credentials["credentials"] = creds_data

        # Override with source config credentials if provided
        # Only use if it contains actual credential values (client_id, client_secret, access_token, etc.)
        # Not if it's just metadata (type, from_env, etc.)
        if self.source_config.credentials:
            if isinstance(self.source_config.credentials, dict):
                # Check if it contains actual credential values (not just metadata)
                has_credential_values = any(
                    key in self.source_config.credentials
                    for key in [
                        "client_id",
                        "client_secret",
                        "access_token",
                        "api_key",
                        "credentials",
                    ]
                )
                if has_credential_values:
                    # If credentials already has nested structure, use it
                    if "credentials" in self.source_config.credentials:
                        credentials["credentials"] = self.source_config.credentials[
                            "credentials"
                        ]
                    else:
                        # Otherwise, wrap in credentials object
                        credentials["credentials"] = self.source_config.credentials

        return credentials

    def build_airbyte_config(self) -> Dict[str, Any]:
        """Build Airbyte configuration with HubSpot-specific credential structure."""
        # Build base config without calling parent (to avoid credential overwrite)
        config = {}

        # Get Airbyte-specific options
        airbyte_opts = self.engine_options.get("airbyte", {})

        # Add credentials using our custom _get_credentials method
        credentials = self._get_credentials()
        if credentials:
            config.update(credentials)

        # Add start date if configured (with ISO 8601 format conversion)
        start_date = airbyte_opts.get("start_date_default")
        if start_date:
            if (
                isinstance(start_date, str)
                and len(start_date) == 10
                and start_date.count("-") == 2
            ):
                # Date format: YYYY-MM-DD -> convert to YYYY-MM-DDTHH:MM:SSZ
                config["start_date"] = f"{start_date}T00:00:00Z"
            else:
                config["start_date"] = start_date

        # Add streams if configured
        streams = airbyte_opts.get("streams_default", [])
        if streams:
            config["streams"] = streams

        # Override with job-level source config
        if self.source_config.object:
            config["streams"] = [self.source_config.object]

        # Add incremental configuration
        if self.source_config.incremental:
            incremental = self.source_config.incremental
            cursor_field = incremental.get("cursor_field")
            if cursor_field:
                config["cursor_field"] = cursor_field

        # Merge any additional config from source_config
        if hasattr(self.source_config, "connection") and self.source_config.connection:
            config.update(self.source_config.connection)

        # Filter out metadata fields
        metadata_fields = ["type", "from_env", "file_template", "streams"]
        for field in metadata_fields:
            config.pop(field, None)

        return config


class HubSpotExtractor(AirbyteExtractor):
    """Extracts data from HubSpot using Airbyte connector."""

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: ConnectorRecipe,
        tenant_id: Optional[str] = None,
    ):
        """Initialize HubSpot extractor.

        Args:
            source_config: Source configuration with objects and credentials
            connector_recipe: HubSpot connector recipe
            tenant_id: Optional tenant ID for credential path resolution
        """
        # Initialize parent but replace config_parser with HubSpot-specific one
        super().__init__(source_config, connector_recipe, tenant_id)
        # Replace the generic config parser with HubSpot-specific one
        self.config_parser = HubSpotConfigParser(
            source_config, connector_recipe, tenant_id
        )

    def extract(
        self,
        state_manager: Optional[IncrementalStateManager] = None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from HubSpot.

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
                "connector": "hubspot",
                "category": "crm",
            }
        )
        return base_metadata
