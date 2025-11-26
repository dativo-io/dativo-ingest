"""Engine framework for Airbyte/Meltano/Singer connectors."""

import json
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
            client = docker.from_env()
        except Exception as e:
            raise RuntimeError(
                f"Failed to connect to Docker daemon: {e}. "
                "Ensure Docker is running and accessible."
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

        # Prepare Airbyte commands
        # Airbyte uses: spec, check, discover, read
        # We'll use 'read' command to extract data

        # Build config JSON
        config_json = json.dumps(config)

        # Run container with read command
        # Airbyte protocol: stdin receives config JSON, stdout emits messages
        try:
            # Use subprocess for better control over stdin/stdout
            process = subprocess.Popen(
                [
                    "docker",
                    "run",
                    "--rm",
                    "-i",  # Interactive mode for stdin
                    self.docker_image,
                    "read",
                    "--config",
                    "/dev/stdin",
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Send config and close stdin
            stdout, stderr = process.communicate(input=config_json)

            if process.returncode != 0:
                raise RuntimeError(
                    f"Airbyte container failed with exit code {process.returncode}: {stderr}"
                )

            # Parse output (Airbyte outputs JSONL format)
            output_lines = stdout.split("\n")

            for line in output_lines:
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)
                    # Airbyte format: {"type": "RECORD", "record": {...}}
                    if record.get("type") == "RECORD":
                        yield record.get("record", {})
                    elif record.get("type") == "STATE":
                        # Handle state updates
                        state = record.get("state", {})
                        if state_manager and state:
                            self._update_state(state_manager, state)
                except json.JSONDecodeError:
                    # Skip invalid JSON lines (may be logs)
                    continue

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


class MeltanoExtractor(BaseEngineExtractor):
    """Extractor for Meltano taps/targets."""

    def __init__(self, source_config: SourceConfig, connector_recipe: ConnectorRecipe):
        """Initialize Meltano extractor.

        Args:
            source_config: Source configuration from job
            connector_recipe: Connector recipe with engine configuration
        """
        super().__init__(source_config, connector_recipe)
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
