import time
from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.dry_run import DryRunExecutor


@pytest.fixture
def mock_job_config():
    config = MagicMock()
    config.tenant_id = "test_tenant"
    config.schema_validation_mode = "strict"
    
    # Mock logging config to return strings, not Mocks
    config.logging.level = "INFO"
    config.logging.redaction = True
    
    source = MagicMock()
    source.type = "csv"
    source.object = "test_object"
    config.get_source.return_value = source
    
    target = MagicMock()
    target.type = "iceberg"
    config.get_target.return_value = target
    
    return config


class TestDryRunExecutor:
    @patch("dativo_ingest.dry_run.DiscoveryService")
    @patch("dativo_ingest.job_executor.update_logging_settings")
    def test_dry_run_success(self, mock_logging, mock_discovery_cls, mock_job_config):
        # Mock logger to avoid NoneType error
        mock_logger = MagicMock()
        mock_logging.return_value = mock_logger
        
        executor = DryRunExecutor(mock_job_config)
        
        # Mock initialization steps
        executor._validate_job = MagicMock(return_value=0)
        executor._load_asset = MagicMock(return_value=0)
        executor._initialize_extractor = MagicMock(return_value=0)
        executor._initialize_validator = MagicMock(return_value=0)
        
        # Mock asset definition
        asset_def = MagicMock()
        asset_def.name = "test_asset"
        asset_def.version = "1.0"
        asset_def.object = "test_object"
        asset_def.schema = [{"name": "col1", "type": "string"}]
        executor.asset_definition = asset_def
        
        # Mock discovery
        mock_discovery = MagicMock()
        mock_discovery_cls.return_value = mock_discovery
        mock_discovery.discover.return_value = {
            "objects": [{"name": "test_object", "type": "table"}],
            "metadata": {}
        }
        
        # Mock extractor data fetch
        executor.extractor = MagicMock()
        mock_records = [{"col1": "val1"}, {"col1": "val2"}]
        executor.extractor.extract.return_value = iter([mock_records])
        
        # Mock validator
        executor.validator = MagicMock()
        executor.validator.validate_batch.return_value = (mock_records, [])
        
        # Execute
        exit_code = executor.execute_dry_run()
        
        assert exit_code == 0
        assert executor.results["valid"] is True
        assert "configuration_validation" in executor.results["phases_completed"]
        assert "asset_loading" in executor.results["phases_completed"]
        assert "discovery" in executor.results["phases_completed"]
        assert "sample_fetch" in executor.results["phases_completed"]
        assert "sample_validation" in executor.results["phases_completed"]
        
        assert executor.results["sample_data"]["rows_fetched"] == 2
        assert executor.results["validation_results"]["data_contract_valid"] is True

    @patch("dativo_ingest.job_executor.update_logging_settings")
    def test_dry_run_validation_failed(self, mock_logging, mock_job_config):
        mock_logger = MagicMock()
        mock_logging.return_value = mock_logger
        
        executor = DryRunExecutor(mock_job_config)
        executor._validate_job = MagicMock(return_value=2)
        
        exit_code = executor.execute_dry_run()
        
        assert exit_code == 2
        assert "configuration_validation" not in executor.results["phases_completed"]
        assert "Configuration validation failed" in executor.results["errors"]

    @patch("dativo_ingest.job_executor.update_logging_settings")
    def test_dry_run_asset_load_failed(self, mock_logging, mock_job_config):
        mock_logger = MagicMock()
        mock_logging.return_value = mock_logger
        
        executor = DryRunExecutor(mock_job_config)
        executor._validate_job = MagicMock(return_value=0)
        executor._load_asset = MagicMock(return_value=2)
        
        exit_code = executor.execute_dry_run()
        
        assert exit_code == 2
        assert "configuration_validation" in executor.results["phases_completed"]
        assert "asset_loading" not in executor.results["phases_completed"]

    @patch("dativo_ingest.dry_run.DiscoveryService")
    @patch("dativo_ingest.job_executor.update_logging_settings")
    def test_dry_run_sample_validation_failed(self, mock_logging, mock_discovery_cls, mock_job_config):
        mock_logger = MagicMock()
        mock_logging.return_value = mock_logger
        
        executor = DryRunExecutor(mock_job_config)
        
        executor._validate_job = MagicMock(return_value=0)
        executor._load_asset = MagicMock(return_value=0)
        executor._initialize_extractor = MagicMock(return_value=0)
        executor._initialize_validator = MagicMock(return_value=0)
        
        asset_def = MagicMock()
        asset_def.name = "test_asset"
        asset_def.version = "1.0"
        asset_def.object = "test_object"
        asset_def.schema = [{"name": "col1", "type": "string"}]
        executor.asset_definition = asset_def
        
        mock_discovery = MagicMock()
        mock_discovery_cls.return_value = mock_discovery
        mock_discovery.discover.return_value = {"objects": []}
        
        executor.extractor = MagicMock()
        executor.extractor.extract.return_value = iter([ [{"col1": "val1"}] ])
        
        executor.validator = MagicMock()
        # Return empty valid records and some errors
        executor.validator.validate_batch.return_value = ([], ["error"])
        executor.validator.get_error_summary.return_value = {"total_errors": 1}
        
        exit_code = executor.execute_dry_run()
        
        assert exit_code == 2
        assert executor.results["valid"] is False
        assert executor.results["validation_results"]["data_contract_valid"] is False
        assert "Data contract validation failed on sample data" in executor.results["errors"]

    @patch("dativo_ingest.job_executor.update_logging_settings")
    def test_dry_run_timeout(self, mock_logging, mock_job_config):
        mock_logger = MagicMock()
        mock_logging.return_value = mock_logger
        
        # Set very short timeout
        executor = DryRunExecutor(mock_job_config, timeout=0)
        
        executor._validate_job = MagicMock(return_value=0)
        executor._load_asset = MagicMock(return_value=0)
        executor._initialize_extractor = MagicMock(return_value=0)
        
        # Mock asset definition to avoid AttributeError
        asset_def = MagicMock()
        asset_def.name = "test_asset"
        asset_def.version = "1.0"
        asset_def.object = "test_object"
        asset_def.schema = []
        executor.asset_definition = asset_def
        
        # Simulate time passing
        with patch("time.time", side_effect=[0, 100]):
            exit_code = executor.execute_dry_run()
            
        assert exit_code == 2
        assert "Timeout exceeded before discovery" in executor.results["errors"]
