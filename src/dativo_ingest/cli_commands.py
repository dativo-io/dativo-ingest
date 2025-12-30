"""CLI command implementations for check and discover operations."""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import ConnectorRecipe, JobConfig, SourceConfig, TargetConfig
from .connectors.factory import ExtractorFactory
from .exceptions import AuthenticationError, ConnectionError
from .logging import get_logger, setup_logging
from .plugins import PluginLoader, extract_sandbox_config
from .utils import expand_env_variable
from .validator import ConnectorValidator


class ConnectionChecker:
    """Handles connection checking for source and target systems."""

    def __init__(
        self,
        job_config: JobConfig,
        mode: str = "self_hosted",
        logger=None,
    ):
        """Initialize connection checker.

        Args:
            job_config: Job configuration
            mode: Execution mode
            logger: Optional logger instance
        """
        self.job_config = job_config
        self.mode = mode
        self.logger = logger or get_logger()

    def check_source(self) -> Dict[str, Any]:
        """Check source connection.

        Returns:
            Dictionary with status information
        """
        source_config = self.job_config.get_source()
        source_status = None

        try:
            if source_config.custom_reader:
                source_status = self._check_custom_reader(source_config)
            else:
                source_status = self._check_builtin_connector(source_config)

        except AuthenticationError as e:
            self.logger.error(
                f"Source authentication failed: {e}",
                extra={
                    "event_type": "source_auth_failed",
                    "error_code": e.error_code,
                },
            )
            source_status = {
                "status": "failed",
                "message": str(e),
                "error_code": e.error_code,
                "retryable": False,
            }
        except ConnectionError as e:
            self.logger.error(
                f"Source connection failed: {e}",
                extra={
                    "event_type": "source_check_failed",
                    "error_code": e.error_code,
                    "retryable": e.retryable,
                },
            )
            source_status = {
                "status": "failed",
                "message": str(e),
                "error_code": e.error_code,
                "retryable": e.retryable,
            }
        except Exception as e:
            self.logger.error(
                f"Source check error: {e}",
                extra={"event_type": "source_check_error"},
                exc_info=True,
            )
            source_status = {
                "status": "error",
                "message": str(e),
            }

        return source_status

    def check_target(self) -> Dict[str, Any]:
        """Check target connection.

        Returns:
            Dictionary with status information
        """
        target_config = self.job_config.get_target()
        target_status = None

        try:
            if target_config.custom_writer:
                target_status = self._check_custom_writer(target_config)
            else:
                target_status = self._check_s3_connection(target_config)

        except AuthenticationError as e:
            self.logger.error(
                f"Target authentication failed: {e}",
                extra={
                    "event_type": "target_auth_failed",
                    "error_code": e.error_code,
                },
            )
            target_status = {
                "status": "failed",
                "message": str(e),
                "error_code": e.error_code,
                "retryable": False,
            }
        except ConnectionError as e:
            self.logger.error(
                f"Target connection failed: {e}",
                extra={
                    "event_type": "target_check_failed",
                    "error_code": e.error_code,
                    "retryable": e.retryable,
                },
            )
            target_status = {
                "status": "failed",
                "message": str(e),
                "error_code": e.error_code,
                "retryable": e.retryable,
            }
        except Exception as e:
            self.logger.error(
                f"Target check error: {e}",
                extra={"event_type": "target_check_error"},
                exc_info=True,
            )
            target_status = {
                "status": "error",
                "message": str(e),
            }

        return target_status

    def _check_custom_reader(self, source_config: SourceConfig) -> Dict[str, Any]:
        """Check custom reader connection.

        Args:
            source_config: Source configuration

        Returns:
            Status dictionary
        """
        sandbox_config, plugin_config = extract_sandbox_config(self.job_config)

        reader_class = PluginLoader.load_reader(
            source_config.custom_reader,
            mode=self.mode,
            sandbox_config=sandbox_config,
            plugin_config=plugin_config,
        )
        reader = reader_class(source_config)

        source_result = reader.check_connection()

        if hasattr(source_result, "to_dict"):
            source_status = source_result.to_dict()
            source_status["status"] = "success" if source_result.success else "failed"
        else:
            source_status = (
                source_result
                if isinstance(source_result, dict)
                else {"status": "unknown", "message": str(source_result)}
            )

        self.logger.info(
            f"Source connection check: {source_status.get('status')}",
            extra={
                "event_type": "source_check_complete",
                "status": source_status.get("status"),
                "check_message": source_status.get("message"),
            },
        )

        return source_status

    def _check_builtin_connector(self, source_config: SourceConfig) -> Dict[str, Any]:
        """Check built-in connector connection.

        Args:
            source_config: Source configuration

        Returns:
            Status dictionary
        """
        # Use ExtractorFactory to create extractor, then call check_connection
        # For connector-specific extractors (stripe, hubspot), use them directly
        # For generic Airbyte connectors, use AirbyteExtractor

        connector_recipe = None
        if (
            hasattr(self.job_config, "source_connector_path")
            and self.job_config.source_connector_path
        ):
            try:
                connector_recipe = ConnectorRecipe.from_yaml(
                    self.job_config.source_connector_path
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to load connector recipe: {e}",
                    extra={"event_type": "connector_recipe_warning"},
                )

        if source_config.type == "stripe":
            return self._check_stripe_connector(source_config, connector_recipe)
        elif source_config.type == "hubspot":
            return self._check_hubspot_connector(source_config, connector_recipe)
        else:
            return self._check_generic_connector(source_config, connector_recipe)

    def _check_stripe_connector(
        self, source_config: SourceConfig, connector_recipe: Optional[ConnectorRecipe]
    ) -> Dict[str, Any]:
        """Check Stripe connector connection.

        Args:
            source_config: Source configuration
            connector_recipe: Optional connector recipe

        Returns:
            Status dictionary
        """
        if not connector_recipe:
            return {
                "status": "error",
                "message": "Connector recipe not available for Airbyte check",
            }

        try:
            from .connectors.stripe_extractor import StripeExtractor

            extractor = StripeExtractor(
                source_config, connector_recipe, self.job_config.tenant_id
            )
            check_result = extractor.check_connection()

            self.logger.info(
                f"Source connection check: {check_result.get('status')}",
                extra={
                    "event_type": "source_check_complete",
                    "status": check_result.get("status"),
                    "check_message": check_result.get("message"),
                },
            )

            return check_result
        except Exception as e:
            return {
                "status": "error",
                "message": f"Stripe Airbyte connection check error: {e}",
            }

    def _check_hubspot_connector(
        self, source_config: SourceConfig, connector_recipe: Optional[ConnectorRecipe]
    ) -> Dict[str, Any]:
        """Check HubSpot connector connection.

        Args:
            source_config: Source configuration
            connector_recipe: Optional connector recipe

        Returns:
            Status dictionary
        """
        if not connector_recipe:
            return {
                "status": "error",
                "message": "Connector recipe not available for Airbyte check",
            }

        try:
            from .connectors.hubspot_extractor import HubSpotExtractor

            extractor = HubSpotExtractor(
                source_config, connector_recipe, self.job_config.tenant_id
            )
            check_result = extractor.check_connection()

            self.logger.info(
                f"Source connection check: {check_result.get('status')}",
                extra={
                    "event_type": "source_check_complete",
                    "status": check_result.get("status"),
                    "check_message": check_result.get("message"),
                },
            )

            return check_result
        except Exception as e:
            return {
                "status": "error",
                "message": f"HubSpot Airbyte connection check error: {e}",
            }

    def _check_generic_connector(
        self, source_config: SourceConfig, connector_recipe: Optional[ConnectorRecipe]
    ) -> Dict[str, Any]:
        """Check generic connector connection.

        Args:
            source_config: Source configuration
            connector_recipe: Optional connector recipe

        Returns:
            Status dictionary
        """
        if not connector_recipe:
            return {
                "status": "skipped",
                "message": f"Connection check not implemented for built-in connector: {source_config.type}",
            }

        engine_type = None
        default_engine = connector_recipe.default_engine
        if isinstance(default_engine, dict):
            engine_type = default_engine.get("type")
        elif default_engine:
            engine_type = str(default_engine)

        if engine_type == "airbyte":
            try:
                from .connectors.engine_framework import AirbyteExtractor

                extractor = AirbyteExtractor(
                    source_config, connector_recipe, self.job_config.tenant_id
                )
                check_result = extractor.check_connection()

                self.logger.info(
                    f"Source connection check: {check_result.get('status')}",
                    extra={
                        "event_type": "source_check_complete",
                        "status": check_result.get("status"),
                        "check_message": check_result.get("message"),
                    },
                )

                return check_result
            except Exception as e:
                return {
                    "status": "error",
                    "message": f"Airbyte connection check error: {e}",
                }
        else:
            self.logger.info(
                "Source connection check not available for built-in connectors",
                extra={
                    "event_type": "source_check_skipped",
                    "connector_type": source_config.type,
                },
            )
            return {
                "status": "skipped",
                "message": f"Connection check not implemented for built-in connector: {source_config.type}",
            }

    def _check_custom_writer(self, target_config: TargetConfig) -> Dict[str, Any]:
        """Check custom writer connection.

        Args:
            target_config: Target configuration

        Returns:
            Status dictionary
        """
        asset_definition = self.job_config._resolve_asset()
        output_base = "s3://test"  # Dummy output base for check

        sandbox_config, plugin_config = extract_sandbox_config(self.job_config)

        writer_class = PluginLoader.load_writer(
            target_config.custom_writer,
            mode=self.mode,
            sandbox_config=sandbox_config,
            plugin_config=plugin_config,
        )
        writer = writer_class(asset_definition, target_config, output_base)

        target_result = writer.check_connection()

        if hasattr(target_result, "to_dict"):
            target_status = target_result.to_dict()
            target_status["status"] = "success" if target_result.success else "failed"
        else:
            target_status = (
                target_result
                if isinstance(target_result, dict)
                else {"status": "unknown", "message": str(target_result)}
            )

        self.logger.info(
            f"Target connection check: {target_status.get('status')}",
            extra={
                "event_type": "target_check_complete",
                "status": target_status.get("status"),
                "message": target_status.get("message"),
            },
        )

        return target_status

    def _check_s3_connection(self, target_config: TargetConfig) -> Dict[str, Any]:
        """Check S3 connection.

        Args:
            target_config: Target configuration

        Returns:
            Status dictionary
        """
        connection = target_config.connection or {}
        s3_config = connection.get("s3") or connection.get("minio", {})
        bucket_raw = s3_config.get("bucket") or connection.get("bucket")
        bucket = (
            expand_env_variable(bucket_raw)
            or os.getenv("S3_BUCKET")
            or os.getenv("MINIO_BUCKET")
        )

        if not bucket:
            return {
                "status": "skipped",
                "message": "S3 bucket not configured",
            }

        try:
            import boto3
            from botocore.exceptions import ClientError

            endpoint = (
                s3_config.get("endpoint")
                or connection.get("endpoint")
                or os.getenv("S3_ENDPOINT")
                or os.getenv("MINIO_ENDPOINT")
                or None
            )
            access_key_id = (
                s3_config.get("access_key_id")
                or connection.get("access_key_id")
                or os.getenv("AWS_ACCESS_KEY_ID")
                or os.getenv("MINIO_ACCESS_KEY")
                or None
            )
            secret_access_key = (
                s3_config.get("secret_access_key")
                or connection.get("secret_access_key")
                or os.getenv("AWS_SECRET_ACCESS_KEY")
                or os.getenv("MINIO_SECRET_KEY")
                or None
            )
            region = (
                s3_config.get("region")
                or connection.get("region")
                or os.getenv("AWS_REGION")
                or None
            )

            s3_client_kwargs = {}
            if region:
                s3_client_kwargs["region_name"] = region
            if access_key_id:
                s3_client_kwargs["aws_access_key_id"] = access_key_id
            if secret_access_key:
                s3_client_kwargs["aws_secret_access_key"] = secret_access_key
            if endpoint and endpoint != "s3.amazonaws.com":
                s3_client_kwargs["endpoint_url"] = endpoint

            s3_client = boto3.client("s3", **s3_client_kwargs)
            s3_client.head_bucket(Bucket=bucket)

            self.logger.info(
                "Target connection check: success",
                extra={
                    "event_type": "target_check_complete",
                    "bucket": bucket,
                },
            )

            return {
                "status": "success",
                "message": f"S3 bucket '{bucket}' is accessible",
            }
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "403":
                raise AuthenticationError(
                    f"Access denied to S3 bucket '{bucket}'",
                    details={"bucket": bucket, "error_code": error_code},
                ) from e
            else:
                raise ConnectionError(
                    f"Failed to access S3 bucket '{bucket}': {error_code}",
                    details={"bucket": bucket, "error_code": error_code},
                ) from e


class DiscoveryService:
    """Handles discovery of available tables/streams from source connectors."""

    def __init__(
        self,
        source_config: SourceConfig,
        job_config: Optional[JobConfig] = None,
        tenant_id: Optional[str] = None,
        mode: str = "self_hosted",
        logger=None,
    ):
        """Initialize discovery service.

        Args:
            source_config: Source configuration
            job_config: Optional job configuration
            tenant_id: Optional tenant ID
            mode: Execution mode
            logger: Optional logger instance
        """
        self.source_config = source_config
        self.job_config = job_config
        self.tenant_id = tenant_id
        self.mode = mode
        self.logger = logger or get_logger()

    def discover(self) -> Dict[str, Any]:
        """Discover available streams/objects.

        Returns:
            Dictionary with streams and metadata
        """
        streams = []
        discovery_metadata = {}

        try:
            if self.source_config.custom_reader:
                streams, discovery_metadata = self._discover_custom_reader()
            else:
                streams, discovery_metadata = self._discover_builtin_connector()

        except Exception as e:
            self.logger.error(
                f"Discovery failed: {e}",
                extra={"event_type": "discover_error"},
                exc_info=True,
            )
            raise

        return {
            "objects": streams,
            "metadata": discovery_metadata,
            "count": len(streams),
        }

    def _discover_custom_reader(self) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Discover using custom reader.

        Returns:
            Tuple of (streams list, metadata dict)
        """
        sandbox_config, plugin_config = extract_sandbox_config(self.job_config)

        reader_class = PluginLoader.load_reader(
            self.source_config.custom_reader,
            mode=self.mode,
            sandbox_config=sandbox_config,
            plugin_config=plugin_config,
        )
        reader = reader_class(self.source_config)

        discovery_result = reader.discover()

        if hasattr(discovery_result, "to_dict"):
            result_dict = discovery_result.to_dict()
            streams = result_dict.get("objects", [])
            discovery_metadata = result_dict.get("metadata", {})
        elif isinstance(discovery_result, dict):
            streams = discovery_result.get("objects", [])
            discovery_metadata = discovery_result.get("metadata", {})
        else:
            streams = discovery_result if isinstance(discovery_result, list) else []
            discovery_metadata = {}

        self.logger.info(
            f"Discovered {len(streams)} streams from custom reader",
            extra={
                "event_type": "discover_complete",
                "stream_count": len(streams),
            },
        )

        return streams, discovery_metadata

    def _discover_builtin_connector(
        self,
    ) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Discover using built-in connector.

        Returns:
            Tuple of (streams list, metadata dict)
        """
        connector_type = self.source_config.type

        if connector_type == "postgres":
            from .connectors.postgres_extractor import PostgresExtractor

            extractor = PostgresExtractor(self.source_config)
            streams = [
                {
                    "name": "tables",
                    "type": "table",
                    "message": "Use PostgresExtractor to list tables",
                }
            ]
            return streams, {}

        elif connector_type == "mysql":
            from .connectors.mysql_extractor import MySQLExtractor

            extractor = MySQLExtractor(self.source_config)
            streams = [
                {
                    "name": "tables",
                    "type": "table",
                    "message": "Use MySQLExtractor to list tables",
                }
            ]
            return streams, {}

        elif connector_type == "stripe":
            return self._discover_stripe()

        elif connector_type == "hubspot":
            streams = [
                {"name": "contacts", "type": "object"},
                {"name": "companies", "type": "object"},
                {"name": "deals", "type": "object"},
            ]
            return streams, {}

        else:
            self.logger.warning(
                f"Discovery not implemented for connector: {connector_type}",
                extra={
                    "event_type": "discover_not_implemented",
                    "connector_type": connector_type,
                },
            )
            streams = [
                {
                    "name": "unknown",
                    "type": "unknown",
                    "message": f"Discovery not implemented for {connector_type}",
                }
            ]
            return streams, {}

    def _discover_stripe(self) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Discover Stripe streams.

        Returns:
            Tuple of (streams list, metadata dict)
        """
        connector_recipe = None
        if (
            self.job_config
            and hasattr(self.job_config, "source_connector_path")
            and self.job_config.source_connector_path
        ):
            try:
                connector_recipe = ConnectorRecipe.from_yaml(
                    self.job_config.source_connector_path
                )
            except Exception as e:
                self.logger.warning(
                    f"Failed to load connector recipe: {e}",
                    extra={"event_type": "connector_recipe_warning"},
                )

        if connector_recipe:
            try:
                from .connectors.stripe_extractor import StripeExtractor

                extractor = StripeExtractor(
                    self.source_config, connector_recipe, self.tenant_id
                )
                discover_result = extractor.discover()
                streams = discover_result.get("streams", [])
                discovery_metadata = discover_result.get("metadata", {})

                if discover_result.get("error"):
                    self.logger.warning(
                        f"Airbyte discover had issues: {discover_result.get('error')}",
                        extra={"event_type": "discover_warning"},
                    )

                return streams, discovery_metadata
            except Exception as e:
                self.logger.error(
                    f"Stripe Airbyte discover failed: {e}",
                    extra={"event_type": "discover_error"},
                    exc_info=True,
                )
                # Fallback to hardcoded list
                return [
                    {"name": "customers", "type": "stream"},
                    {"name": "charges", "type": "stream"},
                    {"name": "invoices", "type": "stream"},
                    {"name": "subscriptions", "type": "stream"},
                ], {}
        else:
            self.logger.warning(
                "Connector recipe not available, using hardcoded Stripe streams",
                extra={"event_type": "discover_fallback"},
            )
            return [
                {"name": "customers", "type": "stream"},
                {"name": "charges", "type": "stream"},
                {"name": "invoices", "type": "stream"},
                {"name": "subscriptions", "type": "stream"},
            ], {}


def format_check_output(
    source_status: Dict[str, Any],
    target_status: Dict[str, Any],
    json_output: bool = False,
    verbose: bool = False,
) -> None:
    """Format and print connection check results.

    Args:
        source_status: Source connection status
        target_status: Target connection status
        json_output: Whether to output JSON
        verbose: Whether to include verbose details
    """
    output_data = {
        "source": source_status,
        "target": target_status,
    }

    if json_output:
        print(json.dumps(output_data, indent=2))
    else:
        print("\n" + "=" * 60)
        print("Connection Check Results")
        print("=" * 60)
        print(f"\nSource: {source_status.get('status', 'unknown')}")
        print(f"  {source_status.get('message', 'No message')}")
        if source_status.get("error_code"):
            print(f"  Error Code: {source_status.get('error_code')}")
            print(f"  Retryable: {source_status.get('retryable', False)}")
        if verbose and source_status.get("details"):
            print(f"  Details: {json.dumps(source_status.get('details'), indent=4)}")

        print(f"\nTarget: {target_status.get('status', 'unknown')}")
        print(f"  {target_status.get('message', 'No message')}")
        if target_status.get("error_code"):
            print(f"  Error Code: {target_status.get('error_code')}")
            print(f"  Retryable: {target_status.get('retryable', False)}")
        if verbose and target_status.get("details"):
            print(f"  Details: {json.dumps(target_status.get('details'), indent=4)}")

        print("\n" + "=" * 60)


def format_discovery_output(
    discovery_result: Dict[str, Any],
    json_output: bool = False,
    verbose: bool = False,
) -> None:
    """Format and print discovery results.

    Args:
        discovery_result: Discovery result dictionary
        json_output: Whether to output JSON
        verbose: Whether to include verbose details
    """
    streams = discovery_result.get("objects", [])
    discovery_metadata = discovery_result.get("metadata", {})

    if json_output:
        print(json.dumps(discovery_result, indent=2))
    else:
        print("\n" + "=" * 60)
        print("Discovery Results")
        print("=" * 60)
        if verbose and discovery_metadata:
            print(f"\nMetadata: {json.dumps(discovery_metadata, indent=2)}")
        print(f"\nFound {len(streams)} stream(s):\n")

        for idx, stream in enumerate(streams, 1):
            print(f"{idx}. {stream.get('name', 'unknown')}")
            print(f"   Type: {stream.get('type', 'unknown')}")
            if stream.get("schema"):
                if verbose:
                    print(f"   Schema: {json.dumps(stream.get('schema'), indent=6)}")
                else:
                    print(f"   Schema: {stream.get('schema')}")
            if stream.get("metadata"):
                if verbose:
                    print(
                        f"   Metadata: {json.dumps(stream.get('metadata'), indent=6)}"
                    )
                else:
                    print(f"   Metadata: {stream.get('metadata')}")
            if stream.get("message"):
                print(f"   Note: {stream.get('message')}")
            if verbose:
                for key, value in stream.items():
                    if key not in ["name", "type", "schema", "metadata", "message"]:
                        print(f"   {key}: {value}")
            print()

        print("=" * 60)
