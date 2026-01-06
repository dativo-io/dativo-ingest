import os
import json
import tempfile
import pytest
from pathlib import Path
from datetime import datetime
from unittest.mock import MagicMock, patch

from dativo_ingest.job_executor import JobExecutor
from dativo_ingest.config import JobConfig, SourceConfig, TargetConfig, AssetDefinition

class TestRunSummaryArtifact:
    
    @pytest.fixture
    def job_config(self):
        # Create a mock job config
        mock_config = MagicMock(spec=JobConfig)
        mock_config.tenant_id = "test_tenant"
        mock_config.asset = "test_job"
        mock_config.get_source.return_value = SourceConfig(
            type="csv", 
            object="test_object",
            incremental={"state_path": "state.json"} # Mock incremental config
        )
        mock_config.get_target.return_value = TargetConfig(type="parquet", connection={"bucket": "test_bucket"})
        mock_config._resolve_asset.return_value = AssetDefinition(
            name="test_asset",
            version="1.0.0",
            source_type="csv",
            object="test_object",
            schema=[{"name": "id", "type": "string"}],
            team={"owner": "test"},
            id="test-asset-id"
        )
        mock_config.validate_schema_presence.return_value = None
        mock_config.logging = None
        mock_config.metrics = None
        mock_config.schema_validation_mode = "strict"
        mock_config.classification_overrides = None
        mock_config.finops = None
        mock_config.governance_overrides = None
        mock_config.catalog = None
        mock_config.plugins = None # Add plugins
        
        return mock_config

    @patch("dativo_ingest.job_executor.ConnectorValidator")
    @patch("dativo_ingest.job_executor.ExtractorFactory")
    @patch("dativo_ingest.job_executor.SchemaValidator")
    @patch("dativo_ingest.parquet_writer.ParquetWriter")
    @patch("dativo_ingest.iceberg_committer.IcebergCommitter")
    @patch("dativo_ingest.job_executor.IncrementalStateManager")
    @patch("dativo_ingest.job_executor.WALManager")
    def test_run_summary_generated_on_success(
        self, mock_wal_manager, mock_state_manager, mock_committer, mock_writer, mock_validator, mock_extractor_factory, mock_connector_validator, job_config, tmp_path
    ):
        # Setup mocks
        mock_extractor = MagicMock()
        mock_extractor.extract.return_value = [[{"id": "1"}]]
        mock_extractor_factory.create.return_value = (mock_extractor, {})
        
        mock_validator_instance = MagicMock()
        mock_validator_instance.validate_batch.return_value = ([{"id": "1"}], [])
        mock_validator.return_value = mock_validator_instance
        
        mock_writer_instance = MagicMock()
        mock_writer_instance.write_batch.return_value = [{"path": "file1.parquet", "size_bytes": 100}]
        mock_writer.return_value = mock_writer_instance
        
        mock_wal_manager_instance = MagicMock()
        mock_wal_manager.return_value = mock_wal_manager_instance
        mock_wal_manager.find_latest_wal.return_value = None
        mock_wal_manager_instance.is_resuming.return_value = False

        # Override state directory
        with patch.dict(os.environ, {"STATE_DIR": str(tmp_path)}):
            executor = JobExecutor(job_config)
            
            # Execute
            exit_code = executor.execute()
            
            assert exit_code == 0
            
            # Check summary file
            expected_dir = tmp_path / "test_tenant" / "test_job" / "runs"
            assert expected_dir.exists()
            
            files = list(expected_dir.glob("run-*.json"))
            assert len(files) == 1
            
            with open(files[0], "r") as f:
                summary = json.load(f)
                
            assert summary["tenant_id"] == "test_tenant"
            assert summary["job_name"] == "test_job"
            assert summary["status"] == "success"
            assert summary["metrics"]["records_extracted"] == 1
            assert summary["metrics"]["records_written"] == 1
            assert summary["metrics"]["bytes_written"] == 100
            assert summary["asset"]["id"] == "test-asset-id"

    @patch("dativo_ingest.job_executor.ConnectorValidator")
    @patch("dativo_ingest.job_executor.ExtractorFactory")
    @patch("dativo_ingest.job_executor.SchemaValidator")
    @patch("dativo_ingest.parquet_writer.ParquetWriter")
    def test_run_summary_generated_on_failure(
        self, mock_writer, mock_validator, mock_extractor_factory, mock_connector_validator, job_config, tmp_path
    ):
         # Setup mocks to fail at extractor initialization
        mock_extractor_factory.create.side_effect = Exception("Extractor init failed")
        
        with patch.dict(os.environ, {"STATE_DIR": str(tmp_path)}):
            executor = JobExecutor(job_config)
            
            exit_code = executor.execute()
            
            assert exit_code == 2
            
            expected_dir = tmp_path / "test_tenant" / "test_job" / "runs"
            assert expected_dir.exists()
            
            files = list(expected_dir.glob("run-*.json"))
            assert len(files) == 1
            
            with open(files[0], "r") as f:
                summary = json.load(f)
                
            assert summary["status"] == "failure"
            assert summary["error"]["has_errors"] is True
            assert "Extractor init failed" in summary["error"]["error_message"]
