"""Engine framework for Airbyte/Meltano/Singer connectors."""

import json
import os
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None  # type: ignore

from ..config import ConnectorRecipe, SourceConfig
from ..logging import get_logger
from ..validator import IncrementalStateManager
from .engine_config import EngineConfigParser


def _get_temp_dir() -> Path:
    """Get temporary directory for Airbyte config files.

    Uses .local/tmp in the project root (consistent with .local/state pattern).
    This keeps temp files out of the project root and ensures they're gitignored.

    Returns:
        Path to temporary directory (created if it doesn't exist)
    """
    # Use .local/tmp in the current working directory (project root)
    # Can be overridden with TEMP_DIR env var for custom locations
    temp_dir = Path(os.getenv("TEMP_DIR", ".local/tmp"))
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir


class BaseEngineExtractor(ABC):
    """Abstract base class for all engine extractors."""

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: ConnectorRecipe,
        tenant_id: Optional[str] = None,
    ):
        """Initialize engine extractor.

        Args:
            source_config: Source configuration from job
            connector_recipe: Connector recipe with engine configuration
            tenant_id: Optional tenant ID for credential path resolution
        """
        self.source_config = source_config
        self.connector_recipe = connector_recipe
        self.tenant_id = tenant_id
        self.config_parser = EngineConfigParser(
            source_config, connector_recipe, tenant_id
        )
        self.logger = get_logger()

    @abstractmethod
    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data using the engine.

        Args:
            state_manager: Optional incremental state manager

        Yields:
            Batches of records as dictionaries
        """
        pass

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract metadata for Dagster asset tags.

        Returns:
            Dictionary with 'tags' key containing metadata
        """
        return {
            "tags": {
                "connector_type": self.source_config.type,
                "engine_type": self.config_parser.engine_type,
            }
        }


class AirbyteExtractor(BaseEngineExtractor):
    """Extractor for Airbyte connectors using Docker containers."""

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: ConnectorRecipe,
        tenant_id: Optional[str] = None,
    ):
        """Initialize Airbyte extractor.

        Args:
            source_config: Source configuration from job
            connector_recipe: Connector recipe with engine configuration
            tenant_id: Optional tenant ID for credential path resolution
        """
        super().__init__(source_config, connector_recipe, tenant_id)
        self.docker_image = self.config_parser.get_docker_image()
        if not self.docker_image:
            raise ValueError(
                f"Airbyte connector requires docker_image in engine options. "
                f"Connector: {connector_recipe.name}"
            )

        self.logger.info(
            f"Initialized Airbyte extractor with image: {self.docker_image}",
            extra={
                "connector_type": source_config.type,
                "docker_image": self.docker_image,
                "event_type": "extractor_initialized",
            },
        )

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data using Airbyte Docker container.

        Args:
            state_manager: Optional incremental state manager

        Yields:
            Batches of records as dictionaries
        """
        try:
            # Build Airbyte configuration
            config = self.config_parser.build_airbyte_config()

            # Get incremental configuration
            incremental_config = self.config_parser.get_incremental_config()

            # Run Airbyte container
            records = self._run_airbyte_container(
                config, incremental_config, state_manager
            )

            # Yield records in batches
            batch = []
            batch_size = 1000  # Default batch size

            for record in records:
                batch.append(record)
                if len(batch) >= batch_size:
                    yield batch
                    batch = []

            # Yield remaining records
            if batch:
                yield batch

        except Exception as e:
            self.logger.error(
                f"Airbyte extraction failed: {e}",
                extra={
                    "connector_type": self.source_config.type,
                    "event_type": "extractor_error",
                    "error": str(e),
                },
            )
            raise

    def _get_airbyte_catalog(
        self,
        config: Dict[str, Any],
        requested_streams: List[str],
        incremental_config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Get Airbyte catalog for specified streams.

        Args:
            config: Airbyte configuration
            requested_streams: List of stream names to include in catalog
            incremental_config: Incremental sync configuration

        Returns:
            Airbyte catalog dictionary
        """
        # Call discover to get full catalog
        discover_result = self.discover()
        if discover_result.get("error"):
            raise RuntimeError(
                f"Failed to discover streams: {discover_result.get('error')}"
            )

        # We need the full catalog structure, not just stream names
        # Re-run discover to get the full catalog JSON
        import tempfile

        config_json = json.dumps(config)
        temp_dir = _get_temp_dir()

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, dir=str(temp_dir)
        ) as tmp_file:
            tmp_file.write(config_json)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
            tmp_config_path = Path(tmp_file.name).absolute()

        try:
            process = subprocess.Popen(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-v",
                    f"{tmp_config_path}:/airbyte_config.json:ro",
                    self.docker_image,
                    "discover",
                    "--config",
                    "/airbyte_config.json",
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            stdout, stderr = process.communicate(timeout=60)

            if process.returncode != 0:
                raise RuntimeError(f"Discover failed: {stderr or stdout}")

            # Parse catalog from discover output
            catalog = None
            for line in stdout.split("\n"):
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    if msg.get("type") == "CATALOG":
                        catalog = msg.get("catalog", {})
                        break
                except json.JSONDecodeError:
                    continue

            if not catalog:
                raise RuntimeError("No catalog found in discover output")

            # Filter catalog to only include requested streams
            streams = catalog.get("streams", [])
            if requested_streams:
                streams = [
                    stream
                    for stream in streams
                    if stream.get("name") in requested_streams
                ]

            # Convert to ConfiguredAirbyteCatalog format
            # Each stream needs to be wrapped with sync mode configuration
            configured_streams = []
            for stream in streams:
                configured_stream = {
                    "stream": stream,  # The stream definition from discover
                    "sync_mode": (
                        "incremental"
                        if incremental_config.get("enabled")
                        else "full_refresh"
                    ),
                    "destination_sync_mode": "append",
                }

                # Add cursor field for incremental sync
                if incremental_config.get("enabled"):
                    cursor_field = incremental_config.get("cursor_field")
                    if cursor_field:
                        # Check if cursor field exists in stream schema
                        stream_schema = stream.get("json_schema", {}).get(
                            "properties", {}
                        )
                        if cursor_field in stream_schema:
                            configured_stream["cursor_field"] = [cursor_field]

                configured_streams.append(configured_stream)

            # Return ConfiguredAirbyteCatalog format
            return {"streams": configured_streams}
        finally:
            try:
                tmp_config_path.unlink(missing_ok=True)
            except Exception:
                pass

    def _run_airbyte_container(
        self,
        config: Dict[str, Any],
        incremental_config: Dict[str, Any],
        state_manager: Optional[IncrementalStateManager] = None,
    ) -> Iterator[Dict[str, Any]]:
        """Run Airbyte Docker container and stream records.

        Args:
            config: Airbyte configuration
            incremental_config: Incremental sync configuration
            state_manager: Optional incremental state manager

        Yields:
            Individual records as dictionaries
        """
        if not DOCKER_AVAILABLE:
            raise RuntimeError(
                "Docker Python library is not installed. "
                "Install it with: pip install docker"
            )

        try:
            # Try to auto-detect Colima socket if DOCKER_HOST is not set
            import os

            docker_host = os.getenv("DOCKER_HOST")
            if not docker_host:
                # Check for Colima socket (common on macOS)
                colima_socket = Path.home() / ".colima" / "default" / "docker.sock"
                if colima_socket.exists():
                    os.environ["DOCKER_HOST"] = f"unix://{colima_socket}"

            client = docker.from_env()
        except Exception as e:
            raise RuntimeError(
                f"Failed to connect to Docker daemon: {e}. "
                "Ensure Docker is running and accessible. "
                "If using Colima, set DOCKER_HOST=unix://$HOME/.colima/default/docker.sock"
            ) from e

        # Check if image exists, pull if needed
        try:
            client.images.get(self.docker_image)
        except docker.errors.ImageNotFound:
            self.logger.info(
                f"Pulling Airbyte image: {self.docker_image}",
                extra={
                    "docker_image": self.docker_image,
                    "event_type": "docker_image_pull",
                },
            )
            try:
                client.images.pull(self.docker_image)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to pull Docker image {self.docker_image}: {e}"
                ) from e

        # Get requested streams from source_config or engine options (not from config)
        # Streams should not be in the config passed to Airbyte (they belong in the catalog)
        if self.source_config.objects:
            requested_streams = self.source_config.objects
        else:
            airbyte_opts = self.config_parser.engine_options.get("airbyte", {})
            requested_streams = airbyte_opts.get("streams_default", [])

        # Get catalog for requested streams
        self.logger.info(
            f"Generating Airbyte catalog for streams: {requested_streams}",
            extra={"event_type": "catalog_generation", "streams": requested_streams},
        )
        catalog = self._get_airbyte_catalog(
            config, requested_streams, incremental_config
        )
        catalog_json = json.dumps(catalog)

        # Build config JSON
        config_json = json.dumps(config)

        # Run container with read command
        # Airbyte protocol: requires both config and catalog
        try:
            # Use temporary files for config and catalog
            import tempfile

            temp_dir = _get_temp_dir()
            tmp_config_path = None
            tmp_catalog_path = None

            try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir=str(temp_dir)
            ) as tmp_config_file:
                tmp_config_file.write(config_json)
                tmp_config_file.flush()
                os.fsync(tmp_config_file.fileno())
                tmp_config_path = Path(tmp_config_file.name).absolute()

            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir=str(temp_dir)
            ) as tmp_catalog_file:
                tmp_catalog_file.write(catalog_json)
                tmp_catalog_file.flush()
                os.fsync(tmp_catalog_file.fileno())
                tmp_catalog_path = Path(tmp_catalog_file.name).absolute()

                # Use subprocess with mounted files
                process = subprocess.Popen(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{tmp_config_path}:/airbyte_config.json:ro",
                        "-v",
                        f"{tmp_catalog_path}:/airbyte_catalog.json:ro",
                        self.docker_image,
                        "read",
                        "--config",
                        "/airbyte_config.json",
                        "--catalog",
                        "/airbyte_catalog.json",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,  # Line buffered
                )

                stderr_lines = []

                # Read output line by line
                try:
                    for line in iter(process.stdout.readline, ""):
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            record = json.loads(line)
                            # Airbyte format: {"type": "RECORD", "record": {"stream": "...", "data": {...}, "emitted_at": ...}}
                            if record.get("type") == "RECORD":
                                record_obj = record.get("record", {})
                                # Extract the actual data from the 'data' field
                                # Airbyte wraps the actual record in a 'data' field along with metadata
                                actual_data = record_obj.get("data", record_obj)
                                yield actual_data
                            elif record.get("type") == "STATE":
                                # Handle state updates
                                state = record.get("state", {})
                                if state_manager and state:
                                    self._update_state(state_manager, state)
                        except json.JSONDecodeError:
                            # Skip invalid JSON lines (may be logs)
                            continue
                finally:
                    # Read any remaining stderr
                    if process.stderr:
                        for line in iter(process.stderr.readline, ""):
                            stderr_lines.append(line)

                process.wait()

                if process.returncode != 0:
                    stderr_output = (
                        "".join(stderr_lines) if stderr_lines else "Unknown error"
                    )
                    raise RuntimeError(
                        f"Airbyte container failed with exit code {process.returncode}: {stderr_output}"
                    )
            finally:
                # Clean up temp files - ensure cleanup even if file creation fails
                try:
                    if tmp_config_path is not None:
                    tmp_config_path.unlink(missing_ok=True)
                except Exception:
                    pass
                try:
                    if tmp_catalog_path is not None:
                    tmp_catalog_path.unlink(missing_ok=True)
                except Exception:
                    pass

        except Exception as e:
            # Check if it's a docker error (only if docker is available and errors module exists)
            if (
                DOCKER_AVAILABLE
                and docker
                and hasattr(docker, "errors")
                and hasattr(docker.errors, "ContainerError")
            ):
                try:
                    if isinstance(e, docker.errors.ContainerError):
                        error_msg = (
                            e.stderr.decode("utf-8")
                            if hasattr(e, "stderr") and e.stderr
                            else str(e)
                        )
                        raise RuntimeError(
                            f"Airbyte container failed: {error_msg}"
                        ) from e
                except (TypeError, AttributeError):
                    # docker.errors.ContainerError might not be a valid type when mocked
                    pass
            raise RuntimeError(f"Failed to run Airbyte container: {e}") from e

    def _update_state(
        self, state_manager: IncrementalStateManager, state: Dict[str, Any]
    ) -> None:
        """Update incremental state from Airbyte state message.

        Args:
            state_manager: Incremental state manager
            state: State data from Airbyte
        """
        incremental_config = self.config_parser.get_incremental_config()
        state_path_str = incremental_config.get("state_path", "")

        if state_path_str:
            state_path = Path(state_path_str)
            # Update state with Airbyte state data
            current_state = IncrementalStateManager.read_state(state_path)
            current_state.update(state)
            IncrementalStateManager.write_state(state_path, current_state)

    def check_connection(self) -> Dict[str, Any]:
        """Check connection using Airbyte's check command.

        Returns:
            Dictionary with status, message, and error_code if failed
        """
        if not DOCKER_AVAILABLE:
            return {
                "status": "error",
                "message": "Docker Python library is not installed",
                "error_code": "MISSING_DEPENDENCY",
            }

        try:
            # Try to auto-detect Colima socket if DOCKER_HOST is not set
            import os

            docker_host = os.getenv("DOCKER_HOST")
            if not docker_host:
                colima_socket = Path.home() / ".colima" / "default" / "docker.sock"
                if colima_socket.exists():
                    os.environ["DOCKER_HOST"] = f"unix://{colima_socket}"

            # Build Airbyte configuration
            config = self.config_parser.build_airbyte_config()
            config_json = json.dumps(config)

            # Ensure config_json is not empty
            if not config_json or config_json.strip() == "{}":
                return {
                    "status": "error",
                    "message": "Airbyte configuration is empty",
                    "error_code": "INVALID_CONFIG",
                }

            # Use temporary file (stdin doesn't work reliably with docker run)
            import tempfile

            temp_dir = _get_temp_dir()
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir=str(temp_dir)
            ) as tmp_file:
                tmp_file.write(config_json)
                tmp_config_path = Path(tmp_file.name).absolute()

            try:
                # Mount file into container
                process = subprocess.Popen(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{tmp_config_path}:/airbyte_config.json:ro",
                        self.docker_image,
                        "check",
                        "--config",
                        "/airbyte_config.json",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                stdout, stderr = process.communicate(timeout=30)
            finally:
                # Clean up temp file
                try:
                    tmp_config_path.unlink(missing_ok=True)
                except Exception:
                    pass

            if process.returncode == 0:
                # Parse Airbyte check response (JSONL format)
                # Look for CONNECTION_STATUS message
                for line in stdout.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "CONNECTION_STATUS":
                            status = msg.get("connectionStatus", {}).get("status")
                            if status == "SUCCEEDED":
                                return {
                                    "status": "success",
                                    "message": "Airbyte connection check successful",
                                }
                            else:
                                return {
                                    "status": "failed",
                                    "message": f"Connection check failed: {status}",
                                    "error_code": "AUTH_FAILED",
                                }
                    except json.JSONDecodeError:
                        continue

                # If no CONNECTION_STATUS found but exit code is 0, assume success
                return {
                    "status": "success",
                    "message": "Airbyte connection check successful",
                }
            else:
                # Parse error from stderr or stdout
                # Airbyte outputs JSONL format, so we need to parse line by line
                error_messages = []
                for line in stdout.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "LOG" and msg.get("log", {}).get(
                            "level"
                        ) in ["ERROR", "FATAL"]:
                            error_messages.append(msg.get("log", {}).get("message", ""))
                        elif (
                            msg.get("type") == "TRACE"
                            and msg.get("trace", {}).get("type") == "ERROR"
                        ):
                            error_info = msg.get("trace", {}).get("error", {})
                            error_messages.append(
                                error_info.get("message", "")
                                or error_info.get("internal_message", "")
                            )
                    except json.JSONDecodeError:
                        continue

                # Also check stderr
                if stderr.strip():
                    error_messages.append(stderr.strip())

                error_msg = (
                    " | ".join(error_messages)
                    if error_messages
                    else "Connection check failed"
                )

                # Determine error code based on error message
                error_code = "AUTH_FAILED"
                if "account_id" in error_msg.lower() or "required" in error_msg.lower():
                    error_code = "MISSING_CONFIG"
                elif "timeout" in error_msg.lower():
                    error_code = "TIMEOUT_ERROR"
                elif (
                    "connection" in error_msg.lower() or "network" in error_msg.lower()
                ):
                    error_code = "CONNECTION_ERROR"

                return {
                    "status": "failed",
                    "message": error_msg,
                    "error_code": error_code,
                }

        except subprocess.TimeoutExpired:
            return {
                "status": "failed",
                "message": "Airbyte connection check timeout",
                "error_code": "TIMEOUT_ERROR",
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Airbyte connection check error: {e}",
                "error_code": "CHECK_ERROR",
            }

    def discover(self) -> Dict[str, Any]:
        """Discover available streams using Airbyte's discover command.

        Returns:
            Dictionary with streams list and metadata
        """
        if not DOCKER_AVAILABLE:
            return {
                "streams": [],
                "metadata": {},
                "error": "Docker Python library is not installed",
            }

        try:
            # Try to auto-detect Colima socket if DOCKER_HOST is not set
            import os

            docker_host = os.getenv("DOCKER_HOST")
            if not docker_host:
                colima_socket = Path.home() / ".colima" / "default" / "docker.sock"
                if colima_socket.exists():
                    os.environ["DOCKER_HOST"] = f"unix://{colima_socket}"

            # Build Airbyte configuration
            config = self.config_parser.build_airbyte_config()
            config_json = json.dumps(config)

            # Log config for debugging (without secrets)
            config_debug = {
                k: "***" if "secret" in k.lower() or "key" in k.lower() else v
                for k, v in config.items()
            }
            self.logger.debug(
                f"Airbyte discover config: {json.dumps(config_debug, indent=2)}",
                extra={"event_type": "discover_config_debug"},
            )

            # Use temporary file (stdin doesn't work reliably with docker run)
            import tempfile

            temp_dir = _get_temp_dir()
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False, dir=str(temp_dir)
            ) as tmp_file:
                tmp_file.write(config_json)
                tmp_file.flush()  # Ensure data is written
                os.fsync(tmp_file.fileno())  # Force write to disk
                tmp_config_path = Path(tmp_file.name).absolute()

                # Verify file was written correctly
                if not tmp_config_path.exists() or tmp_config_path.stat().st_size == 0:
                    return {
                        "streams": [],
                        "metadata": {},
                        "error": "Failed to write config file",
                    }

            try:
                # Mount file into container
                process = subprocess.Popen(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "-v",
                        f"{tmp_config_path}:/airbyte_config.json:ro",
                        self.docker_image,
                        "discover",
                        "--config",
                        "/airbyte_config.json",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )

                stdout, stderr = process.communicate(timeout=60)
            finally:
                # Clean up temp file
                try:
                    tmp_config_path.unlink(missing_ok=True)
                except Exception:
                    pass

            if process.returncode == 0:
                # Parse Airbyte discover response (JSONL format)
                # Look for CATALOG message
                catalog = None
                for line in stdout.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "CATALOG":
                            catalog = msg.get("catalog", {})
                            break
                    except json.JSONDecodeError:
                        continue

                if catalog:
                    streams = []
                    if "streams" in catalog:
                        for stream in catalog["streams"]:
                            streams.append(
                                {
                                    "name": stream.get("name"),
                                    "type": "stream",
                                    "schema": stream.get("json_schema", {}).get(
                                        "properties", {}
                                    ),
                                }
                            )
                    return {"streams": streams, "metadata": {}}
                else:
                    # Check for errors in output even if returncode is 0
                    error_messages = []
                    for line in stdout.split("\n"):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            msg = json.loads(line)
                            if msg.get("type") == "LOG" and msg.get("log", {}).get(
                                "level"
                            ) in ["ERROR", "FATAL"]:
                                error_messages.append(
                                    msg.get("log", {}).get("message", "")
                                )
                            elif (
                                msg.get("type") == "TRACE"
                                and msg.get("trace", {}).get("type") == "ERROR"
                            ):
                                error_info = msg.get("trace", {}).get("error", {})
                                error_messages.append(
                                    error_info.get("message", "")
                                    or error_info.get("internal_message", "")
                                )
                        except json.JSONDecodeError:
                            continue

                    error_msg = (
                        " | ".join(error_messages)
                        if error_messages
                        else "No CATALOG message found in discover output"
                    )
                    return {
                        "streams": [],
                        "metadata": {},
                        "error": error_msg,
                    }
            else:
                # Parse error from stderr or stdout
                error_messages = []
                for line in stdout.split("\n"):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        msg = json.loads(line)
                        if msg.get("type") == "LOG" and msg.get("log", {}).get(
                            "level"
                        ) in ["ERROR", "FATAL"]:
                            error_messages.append(msg.get("log", {}).get("message", ""))
                        elif (
                            msg.get("type") == "TRACE"
                            and msg.get("trace", {}).get("type") == "ERROR"
                        ):
                            error_info = msg.get("trace", {}).get("error", {})
                            error_messages.append(
                                error_info.get("message", "")
                                or error_info.get("internal_message", "")
                            )
                    except json.JSONDecodeError:
                        continue

                if stderr.strip():
                    error_messages.append(stderr.strip())

                error_msg = (
                    " | ".join(error_messages)
                    if error_messages
                    else (stderr.strip() or stdout.strip() or "Discover failed")
                )
                return {
                    "streams": [],
                    "metadata": {},
                    "error": error_msg,
                }

        except subprocess.TimeoutExpired:
            return {
                "streams": [],
                "metadata": {},
                "error": "Airbyte discover command timeout",
            }
        except Exception as e:
            return {
                "streams": [],
                "metadata": {},
                "error": f"Airbyte discover error: {e}",
            }


class MeltanoExtractor(BaseEngineExtractor):
    """Extractor for Meltano taps/targets."""

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: ConnectorRecipe,
        tenant_id: Optional[str] = None,
    ):
        """Initialize Meltano extractor.

        Args:
            source_config: Source configuration from job
            connector_recipe: Connector recipe with engine configuration
            tenant_id: Optional tenant ID for credential path resolution
        """
        super().__init__(source_config, connector_recipe, tenant_id)
        self.logger.info(
            "Initialized Meltano extractor",
            extra={
                "connector_type": source_config.type,
                "event_type": "extractor_initialized",
            },
        )

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data using Meltano tap.

        Args:
            state_manager: Optional incremental state manager

        Yields:
            Batches of records as dictionaries
        """
        # TODO: Implement Meltano extraction
        # This would involve:
        # 1. Setting up Meltano project
        # 2. Running meltano invoke tap-<name>
        # 3. Parsing Singer-compatible output
        raise NotImplementedError("Meltano extractor not yet implemented")


class SingerExtractor(BaseEngineExtractor):
    """Extractor for Singer taps."""

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: ConnectorRecipe,
        tenant_id: Optional[str] = None,
    ):
        """Initialize Singer extractor.

        Args:
            source_config: Source configuration from job
            connector_recipe: Connector recipe with engine configuration
            tenant_id: Optional tenant ID for credential path resolution
        """
        super().__init__(source_config, connector_recipe, tenant_id)
        self.logger.info(
            "Initialized Singer extractor",
            extra={
                "connector_type": source_config.type,
                "event_type": "extractor_initialized",
            },
        )

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data using Singer tap.

        Args:
            state_manager: Optional incremental state manager

        Yields:
            Batches of records as dictionaries
        """
        # TODO: Implement Singer extraction
        # This would involve:
        # 1. Finding Singer tap executable
        # 2. Running tap with config
        # 3. Parsing JSONL output
        raise NotImplementedError("Singer extractor not yet implemented")
