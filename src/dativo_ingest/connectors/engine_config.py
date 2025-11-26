"""Engine configuration parser for Airbyte/Meltano/Singer connectors."""

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from ..config import ConnectorRecipe, SourceConfig


class EngineConfigParser:
    """Parses and builds engine-specific configurations from connector recipes."""

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: ConnectorRecipe,
        tenant_id: Optional[str] = None,
    ):
        """Initialize engine config parser.

        Args:
            source_config: Source configuration from job
            connector_recipe: Connector recipe with engine configuration
            tenant_id: Optional tenant ID for credential path resolution
        """
        self.source_config = source_config
        self.connector_recipe = connector_recipe
        self.tenant_id = tenant_id
        self.engine_type = self._get_engine_type()
        self.engine_options = self._get_engine_options()

    def _get_engine_type(self) -> str:
        """Extract engine type from connector recipe.

        Returns:
            Engine type (airbyte, meltano, singer, native)
        """
        default_engine = self.connector_recipe.default_engine
        if isinstance(default_engine, dict):
            return default_engine.get("type", "native")
        return str(default_engine) if default_engine else "native"

    def _get_engine_options(self) -> Dict[str, Any]:
        """Get engine-specific options from connector recipe.

        Returns:
            Dictionary of engine options
        """
        default_engine = self.connector_recipe.default_engine
        if isinstance(default_engine, dict):
            return default_engine.get("options", {})
        return {}

    def build_airbyte_config(self) -> Dict[str, Any]:
        """Build Airbyte connector configuration.

        Returns:
            Airbyte configuration dictionary
        """
        config = {}

        # Get Airbyte-specific options
        airbyte_opts = self.engine_options.get("airbyte", {})

        # Map credentials
        credentials = self._get_credentials()
        if credentials:
            config.update(credentials)

        # Add start date if configured
        start_date = airbyte_opts.get("start_date_default")
        if start_date:
            config["start_date"] = start_date

        # Add streams if configured
        streams = airbyte_opts.get("streams_default", [])
        if streams:
            config["streams"] = streams

        # Override with job-level source config
        if self.source_config.objects:
            config["streams"] = self.source_config.objects

        # Add incremental configuration
        if self.source_config.incremental:
            incremental = self.source_config.incremental
            cursor_field = incremental.get("cursor_field")
            if cursor_field:
                config["cursor_field"] = cursor_field

        # Merge any additional config from source_config
        if hasattr(self.source_config, "connection") and self.source_config.connection:
            config.update(self.source_config.connection)

        return config

    def build_meltano_config(self) -> Dict[str, Any]:
        """Build Meltano configuration.

        Returns:
            Meltano configuration dictionary
        """
        config = {}

        # Get Meltano-specific options
        meltano_opts = self.engine_options.get("meltano", {})

        # Map credentials
        credentials = self._get_credentials()
        if credentials:
            config.update(credentials)

        # Add tap-specific settings
        if meltano_opts:
            config.update(meltano_opts)

        # Merge connection config if available
        if hasattr(self.source_config, "connection") and self.source_config.connection:
            config.update(self.source_config.connection)

        return config

    def build_singer_config(self) -> Dict[str, Any]:
        """Build Singer tap configuration.

        Returns:
            Singer configuration dictionary
        """
        config = {}

        # Get Singer-specific options
        singer_opts = self.engine_options.get("singer", {})

        # Map credentials
        credentials = self._get_credentials()
        if credentials:
            config.update(credentials)

        # Add tap-specific settings
        if singer_opts:
            config.update(singer_opts)

        # Merge connection config if available
        if hasattr(self.source_config, "connection") and self.source_config.connection:
            config.update(self.source_config.connection)

        return config

    def _get_credentials(self) -> Dict[str, Any]:
        """Extract and map credentials from connector recipe and source config.

        Returns:
            Dictionary of credentials in engine format
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
                    # Map to engine-specific credential format
                    if self.engine_type == "airbyte":
                        credentials["api_key"] = api_key
                    elif self.engine_type in ["meltano", "singer"]:
                        credentials["api_key"] = api_key
                    else:
                        credentials["api_key"] = api_key

        elif cred_type == "service_account":
            # Service account file
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

    def get_docker_image(self) -> Optional[str]:
        """Get Docker image for Airbyte connector.

        Returns:
            Docker image name or None
        """
        if self.engine_type == "airbyte":
            airbyte_opts = self.engine_options.get("airbyte", {})
            return airbyte_opts.get("docker_image")
        return None

    def get_incremental_config(self) -> Dict[str, Any]:
        """Get incremental sync configuration.

        Returns:
            Incremental configuration dictionary
        """
        incremental = self.source_config.incremental or {}
        recipe_incremental = self.connector_recipe.incremental or {}

        # Merge recipe defaults with source config
        config = {
            "strategy": incremental.get(
                "strategy", recipe_incremental.get("strategy_default", "updated_after")
            ),
            "cursor_field": incremental.get(
                "cursor_field",
                recipe_incremental.get("cursor_field_default"),
            ),
            "lookback_days": incremental.get(
                "lookback_days",
                recipe_incremental.get("lookback_days_default", 0),
            ),
        }

        # Add state path if configured
        if incremental.get("state_path"):
            config["state_path"] = incremental["state_path"]

        return config
