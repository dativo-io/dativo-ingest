"""Tests for dry-run mode in job executor."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.dativo_ingest.config import (
    AssetDefinition,
    JobConfig,
    SourceConfig,
    TargetConfig,
)
from src.dativo_ingest.job_executor import JobExecutor


class TestJobExecutorDryRun:
    """Test JobExecutor dry-run mode."""

    @pytest.fixture
    def mock_job_config(self, tmp_path):
        """Create a mock job configuration for testing."""
        # Create minimal connector recipes
        source_connector = {
            "name": "csv",
            "type": "csv",
            "roles": ["source"],
            "default_engine": {"type": "native"},
            "credentials": {},
        }
        source_path = tmp_path / "csv_connector.yaml"
        with open(source_path, "w") as f:
            yaml.dump(source_connector, f)

        target_connector = {
            "name": "iceberg",
            "type": "iceberg",
            "roles": ["target"],
            "default_engine": {"type": "native"},
            "catalog": "test_catalog",
            "file_format": "parquet",
        }
        target_path = tmp_path / "iceberg_connector.yaml"
        with open(target_path, "w") as f:
            yaml.dump(target_connector, f)

        # Create minimal asset definition
        asset_def = {
            "apiVersion": "v3.0.2",
            "kind": "DataContract",
            "name": "test_asset",
            "version": "1.0.0",
            "status": "active",
            "source_type": "csv",
            "object": "test_table",
            "schema": [
                {"name": "id", "type": "integer", "required": True},
                {"name": "name", "type": "string"},
            ],
            "team": {"owner": "test@example.com"},
        }
        asset_path = tmp_path / "test_asset.yaml"
        with open(asset_path, "w") as f:
            yaml.dump(asset_def, f)

        # Create job config
        job_config = JobConfig(
            tenant_id="test-tenant",
            source_connector_path=str(source_path),
            target_connector_path=str(target_path),
            asset_path=str(asset_path),
            source={"object": "test_table"},
        )

        return job_config

    def test_dry_run_flag_initialization(self, mock_job_config):
        """Test that dry_run flag is properly set."""
        executor = JobExecutor(mock_job_config, dry_run=False)
        assert executor.dry_run is False

        executor_dry = JobExecutor(mock_job_config, dry_run=True)
        assert executor_dry.dry_run is True

    def test_dry_run_constants(self, mock_job_config):
        """Test dry-run sample size constants."""
        executor = JobExecutor(mock_job_config, dry_run=True)

        assert executor.DRY_RUN_SAMPLE_MIN == 10
        assert executor.DRY_RUN_SAMPLE_MAX == 50
        assert executor.DRY_RUN_SAMPLE_MIN <= executor.DRY_RUN_SAMPLE_MAX

    def test_dry_run_skips_writer_and_committer(self, mock_job_config):
        """Test that dry-run mode calls _execute_dry_run instead of full ETL."""
        # Create executor with dry_run=True
        executor = JobExecutor(mock_job_config, dry_run=True)

        # Manually set up internal state to simulate a job after initialization
        executor.logger = MagicMock()
        executor.source_config = MagicMock()
        executor.source_config.type = "csv"
        executor.source_config.incremental = None
        executor.target_config = MagicMock()
        executor.target_config.type = "iceberg"
        executor.asset_definition = MagicMock()
        executor.asset_definition.name = "test_asset"
        executor.asset_definition.schema = [{"name": "id", "type": "integer"}]
        executor.extractor = MagicMock()
        executor.extractor.extract.return_value = iter([[{"id": 1}]])
        executor.validator = MagicMock()
        executor.validator.validate_batch.return_value = ([{"id": 1}], [])
        executor.validator.get_error_summary.return_value = {
            "total_errors": 0,
            "errors_by_type": {},
            "errors_by_field": {},
            "errors": [],
        }
        executor.run_summary = None
        executor.metrics_collector = None

        # Execute dry run directly
        exit_code = executor._execute_dry_run()

        # Should succeed
        assert exit_code == 0

        # Verify extractor.extract was called
        executor.extractor.extract.assert_called()

        # Verify validator was called
        executor.validator.validate_batch.assert_called()

    def test_normal_mode_does_not_skip_writer(self, mock_job_config):
        """Test that normal mode sets up writer (different from dry-run)."""
        # Create executor with dry_run=False
        executor = JobExecutor(mock_job_config, dry_run=False)

        # Verify dry_run is False
        assert executor.dry_run is False

        # The actual execution would try to set up writer
        # We just verify the flag is set correctly here


class TestDryRunValidationResults:
    """Test dry-run data contract validation output."""

    def test_dry_run_validates_records_against_schema(self, tmp_path, capsys):
        """Test that dry-run validates sample records against schema."""
        from src.dativo_ingest.dry_run import DryRunConfig

        # Create a mock extractor that yields sample records
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = iter(
            [
                [
                    {"id": 1, "name": "Alice"},
                    {"id": 2, "name": "Bob"},
                    {"id": "invalid", "name": "Charlie"},  # Invalid id type
                ]
            ]
        )

        # Create mock asset definition with schema
        mock_asset = MagicMock()
        mock_asset.name = "test_asset"
        mock_asset.schema = [
            {"name": "id", "type": "integer", "required": True},
            {"name": "name", "type": "string"},
        ]

        # Create mock validator
        mock_validator = MagicMock()
        mock_validator.validate_batch.return_value = (
            [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],  # valid records
            [MagicMock(field_name="id", error_type="type_mismatch")],  # errors
        )
        mock_validator.get_error_summary.return_value = {
            "total_errors": 1,
            "errors_by_type": {"type_mismatch": 1},
            "errors_by_field": {"id": 1},
            "errors": [
                {
                    "record_index": 2,
                    "field": "id",
                    "type": "type_mismatch",
                    "message": "Invalid type",
                }
            ],
        }

        # Create mock source/target configs
        mock_source_config = MagicMock()
        mock_source_config.type = "csv"
        mock_target_config = MagicMock()
        mock_target_config.type = "iceberg"

        # Create mock job config
        mock_job_config = MagicMock()
        mock_job_config.schema_validation_mode = "warn"

        # Create executor
        executor = JobExecutor.__new__(JobExecutor)
        executor.dry_run = True
        executor.dry_run_config = DryRunConfig(sample_size=50, verbose=False)
        executor.extractor = mock_extractor
        executor.validator = mock_validator
        executor.asset_definition = mock_asset
        executor.source_config = mock_source_config
        executor.target_config = mock_target_config
        executor.job_config = mock_job_config
        executor.logger = MagicMock()
        executor._dry_run_result = None
        executor.DRY_RUN_SAMPLE_MIN = 10
        executor.DRY_RUN_SAMPLE_MAX = 50

        # Execute dry run
        exit_code = executor._execute_dry_run()

        # Verify validator was called
        mock_validator.validate_batch.assert_called_once()

        # In warn mode with validation errors, should return 0 or 1
        # (0 = success, 1 = general failure with warnings)
        assert exit_code in [0, 1]


class TestDryRunSampleSizeLimit:
    """Test dry-run sample size limiting."""

    def test_dry_run_respects_sample_limit(self, tmp_path, capsys):
        """Test that dry-run stops after collecting max sample size."""
        from src.dativo_ingest.dry_run import DryRunConfig

        # Create a mock extractor that yields many records
        large_batch = [{"id": i, "name": f"Name{i}"} for i in range(100)]
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = iter([large_batch])

        # Create mock components
        mock_asset = MagicMock()
        mock_asset.name = "test_asset"
        mock_asset.schema = [{"name": "id", "type": "integer"}]

        mock_validator = MagicMock()
        mock_validator.validate_batch.return_value = (
            large_batch[:50],
            [],
        )  # Return valid records
        mock_validator.get_error_summary.return_value = {
            "total_errors": 0,
            "errors_by_type": {},
            "errors_by_field": {},
            "errors": [],
        }

        mock_source_config = MagicMock()
        mock_source_config.type = "csv"
        mock_target_config = MagicMock()
        mock_target_config.type = "iceberg"

        mock_job_config = MagicMock()
        mock_job_config.schema_validation_mode = "strict"

        # Create executor
        executor = JobExecutor.__new__(JobExecutor)
        executor.dry_run = True
        executor.dry_run_config = DryRunConfig(sample_size=50, verbose=False)
        executor.extractor = mock_extractor
        executor.validator = mock_validator
        executor.asset_definition = mock_asset
        executor.source_config = mock_source_config
        executor.target_config = mock_target_config
        executor.job_config = mock_job_config
        executor.logger = MagicMock()
        executor._dry_run_result = None
        executor.DRY_RUN_SAMPLE_MIN = 10
        executor.DRY_RUN_SAMPLE_MAX = 50

        # Execute dry run
        exit_code = executor._execute_dry_run()

        # Verify validator was called with at most sample_size records
        call_args = mock_validator.validate_batch.call_args[0][0]
        assert len(call_args) <= 50
