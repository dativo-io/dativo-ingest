"""Tests for cloud plugin executor."""

import json
import pytest
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path

from src.dativo_ingest.cloud_plugin_executor import (
    CloudExecutionConfig,
    CloudReaderWrapper,
    CloudWriterWrapper,
    create_cloud_executor,
    AWSLambdaExecutor,
    GCPCloudFunctionsExecutor,
)
from src.dativo_ingest.plugins import ConnectionTestResult, DiscoveryResult
from src.dativo_ingest.config import SourceConfig, TargetConfig


class TestCloudExecutionConfig:
    """Tests for CloudExecutionConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = CloudExecutionConfig()
        
        assert config.enabled is False
        assert config.provider == "aws"
        assert config.runtime == "python3.11"
        assert config.memory_mb == 512
        assert config.timeout_seconds == 300

    def test_from_dict(self):
        """Test creating config from dictionary."""
        config_dict = {
            "enabled": True,
            "provider": "gcp",
            "runtime": "python311",
            "memory_mb": 1024,
            "timeout_seconds": 600,
            "gcp": {
                "project_id": "my-project",
                "region": "us-central1"
            },
            "environment_variables": {
                "LOG_LEVEL": "INFO"
            }
        }
        
        config = CloudExecutionConfig.from_dict(config_dict)
        
        assert config.enabled is True
        assert config.provider == "gcp"
        assert config.runtime == "python311"
        assert config.memory_mb == 1024
        assert config.timeout_seconds == 600
        assert config.gcp_config["project_id"] == "my-project"
        assert config.environment_variables["LOG_LEVEL"] == "INFO"


class TestAWSLambdaExecutor:
    """Tests for AWSLambdaExecutor."""

    def test_init_without_boto3(self):
        """Test initialization fails without boto3."""
        config = CloudExecutionConfig(provider="aws")
        
        with patch.dict("sys.modules", {"boto3": None}):
            with pytest.raises(ImportError, match="boto3"):
                AWSLambdaExecutor(config)

    @patch("src.dativo_ingest.cloud_plugin_executor.boto3")
    def test_init_with_boto3(self, mock_boto3):
        """Test initialization with boto3."""
        config = CloudExecutionConfig(provider="aws")
        mock_boto3.client.return_value = Mock()
        
        executor = AWSLambdaExecutor(config)
        
        assert executor.config == config
        assert mock_boto3.client.call_count >= 1

    @patch("src.dativo_ingest.cloud_plugin_executor.boto3")
    def test_package_python_plugin(self, mock_boto3):
        """Test packaging Python plugin."""
        config = CloudExecutionConfig(provider="aws")
        mock_boto3.client.return_value = Mock()
        
        executor = AWSLambdaExecutor(config)
        
        # Create temporary plugin file
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write('class TestPlugin:\n    pass\n')
            plugin_path = f.name
        
        try:
            # Package plugin
            zip_bytes = executor._package_python_plugin(plugin_path)
            
            # Verify it's a valid ZIP
            import zipfile
            import io
            with zipfile.ZipFile(io.BytesIO(zip_bytes), 'r') as zipf:
                files = zipf.namelist()
                assert 'handler.py' in files
                assert any(Path(plugin_path).name in f for f in files)
        finally:
            Path(plugin_path).unlink()


class TestGCPCloudFunctionsExecutor:
    """Tests for GCPCloudFunctionsExecutor."""

    def test_init_without_google_cloud(self):
        """Test initialization fails without google-cloud packages."""
        config = CloudExecutionConfig(
            provider="gcp",
            gcp_config={"project_id": "test-project"}
        )
        
        with patch.dict("sys.modules", {"google.cloud.functions_v2": None}):
            with pytest.raises(ImportError, match="google-cloud-functions"):
                GCPCloudFunctionsExecutor(config)

    def test_init_without_project_id(self):
        """Test initialization fails without project_id."""
        config = CloudExecutionConfig(provider="gcp")
        
        with pytest.raises(ValueError, match="project_id"):
            GCPCloudFunctionsExecutor(config)


class TestCloudReaderWrapper:
    """Tests for CloudReaderWrapper."""

    def test_init(self):
        """Test initialization."""
        source_config = SourceConfig(
            type="custom",
            connection={"base_url": "https://api.example.com"}
        )
        
        mock_executor = Mock()
        plugin_path = "/path/to/plugin.py"
        
        wrapper = CloudReaderWrapper(
            source_config,
            plugin_path,
            "python",
            mock_executor
        )
        
        assert wrapper.plugin_path == plugin_path
        assert wrapper.plugin_type == "python"
        assert wrapper.executor == mock_executor
        assert wrapper._deployed is False

    def test_check_connection(self):
        """Test check_connection method."""
        source_config = SourceConfig(
            type="custom",
            connection={"base_url": "https://api.example.com"}
        )
        
        mock_executor = Mock()
        mock_executor.deploy_plugin.return_value = "function-arn"
        mock_executor.invoke_plugin.return_value = {
            "statusCode": 200,
            "body": json.dumps({
                "success": True,
                "message": "Connection successful"
            })
        }
        
        wrapper = CloudReaderWrapper(
            source_config,
            "/path/to/plugin.py",
            "python",
            mock_executor
        )
        
        result = wrapper.check_connection()
        
        assert isinstance(result, ConnectionTestResult)
        assert result.success is True
        assert mock_executor.deploy_plugin.called
        assert mock_executor.invoke_plugin.called

    def test_discover(self):
        """Test discover method."""
        source_config = SourceConfig(
            type="custom",
            connection={"base_url": "https://api.example.com"},
            objects=["users", "orders"]
        )
        
        mock_executor = Mock()
        mock_executor.deploy_plugin.return_value = "function-arn"
        mock_executor.invoke_plugin.return_value = {
            "statusCode": 200,
            "body": json.dumps({
                "objects": [
                    {"name": "users", "type": "table"},
                    {"name": "orders", "type": "table"}
                ],
                "metadata": {}
            })
        }
        
        wrapper = CloudReaderWrapper(
            source_config,
            "/path/to/plugin.py",
            "python",
            mock_executor
        )
        
        result = wrapper.discover()
        
        assert isinstance(result, DiscoveryResult)
        assert len(result.objects) == 2

    def test_extract(self):
        """Test extract method."""
        source_config = SourceConfig(
            type="custom",
            connection={"base_url": "https://api.example.com"},
            objects=["users"]
        )
        
        mock_executor = Mock()
        mock_executor.deploy_plugin.return_value = "function-arn"
        
        # Simulate two batches
        responses = [
            {
                "statusCode": 200,
                "body": json.dumps({
                    "batch": [{"id": 1}, {"id": 2}],
                    "has_more": True
                })
            },
            {
                "statusCode": 200,
                "body": json.dumps({
                    "batch": [{"id": 3}],
                    "has_more": False
                })
            }
        ]
        mock_executor.invoke_plugin.side_effect = responses
        
        wrapper = CloudReaderWrapper(
            source_config,
            "/path/to/plugin.py",
            "python",
            mock_executor
        )
        
        batches = list(wrapper.extract())
        
        assert len(batches) == 2
        assert len(batches[0]) == 2
        assert len(batches[1]) == 1


class TestCloudWriterWrapper:
    """Tests for CloudWriterWrapper."""

    def test_init(self):
        """Test initialization."""
        from src.dativo_ingest.config import AssetDefinition
        
        asset_definition = Mock()
        asset_definition.name = "test_asset"
        
        target_config = TargetConfig(
            type="parquet",
            file_format="parquet"
        )
        
        mock_executor = Mock()
        plugin_path = "/path/to/plugin.py"
        
        wrapper = CloudWriterWrapper(
            asset_definition,
            target_config,
            "/output",
            plugin_path,
            "python",
            mock_executor
        )
        
        assert wrapper.plugin_path == plugin_path
        assert wrapper.plugin_type == "python"
        assert wrapper.executor == mock_executor
        assert wrapper._deployed is False

    def test_write_batch(self):
        """Test write_batch method."""
        asset_definition = Mock()
        asset_definition.name = "test_asset"
        asset_definition.schema = []
        
        target_config = TargetConfig(
            type="parquet",
            file_format="parquet"
        )
        
        mock_executor = Mock()
        mock_executor.deploy_plugin.return_value = "function-arn"
        mock_executor.invoke_plugin.return_value = {
            "statusCode": 200,
            "body": json.dumps({
                "metadata": [{
                    "path": "/output/file_000001.parquet",
                    "size_bytes": 1024
                }]
            })
        }
        
        wrapper = CloudWriterWrapper(
            asset_definition,
            target_config,
            "/output",
            "/path/to/plugin.py",
            "python",
            mock_executor
        )
        
        records = [{"id": 1, "name": "Test"}]
        metadata = wrapper.write_batch(records, 1)
        
        assert len(metadata) == 1
        assert metadata[0]["path"] == "/output/file_000001.parquet"
        assert mock_executor.deploy_plugin.called
        assert mock_executor.invoke_plugin.called


class TestCreateCloudExecutor:
    """Tests for create_cloud_executor function."""

    @patch("src.dativo_ingest.cloud_plugin_executor.boto3")
    def test_create_aws_executor(self, mock_boto3):
        """Test creating AWS executor."""
        mock_boto3.client.return_value = Mock()
        
        config = CloudExecutionConfig(provider="aws")
        executor = create_cloud_executor(config)
        
        assert isinstance(executor, AWSLambdaExecutor)

    def test_create_gcp_executor_without_project(self):
        """Test creating GCP executor without project_id fails."""
        config = CloudExecutionConfig(provider="gcp")
        
        with pytest.raises(ValueError, match="project_id"):
            create_cloud_executor(config)

    def test_unsupported_provider(self):
        """Test unsupported provider raises error."""
        config = CloudExecutionConfig(provider="azure")
        
        with pytest.raises(ValueError, match="Unsupported cloud provider"):
            create_cloud_executor(config)


class TestPluginLoaderIntegration:
    """Integration tests with PluginLoader."""

    @patch("src.dativo_ingest.cloud_plugin_executor.boto3")
    def test_load_reader_with_cloud_config(self, mock_boto3):
        """Test loading reader with cloud execution config."""
        from src.dativo_ingest.plugins import PluginLoader
        
        mock_boto3.client.return_value = Mock()
        
        plugin_path = "examples/plugins/json_api_reader.py:JSONAPIReader"
        cloud_config = {
            "enabled": True,
            "provider": "aws",
            "runtime": "python3.11"
        }
        
        reader_class = PluginLoader.load_reader(plugin_path, cloud_config)
        
        # Check that we got a cloud wrapper class
        assert reader_class.__name__ == "DynamicCloudReader"

    def test_load_reader_without_cloud_config(self):
        """Test loading reader without cloud execution."""
        from src.dativo_ingest.plugins import PluginLoader
        
        plugin_path = "examples/plugins/json_api_reader.py:JSONAPIReader"
        
        reader_class = PluginLoader.load_reader(plugin_path)
        
        # Check that we got the original class
        assert reader_class.__name__ == "JSONAPIReader"

    @patch("src.dativo_ingest.cloud_plugin_executor.boto3")
    def test_load_writer_with_cloud_config(self, mock_boto3):
        """Test loading writer with cloud execution config."""
        from src.dativo_ingest.plugins import PluginLoader
        
        mock_boto3.client.return_value = Mock()
        
        plugin_path = "examples/plugins/json_file_writer.py:JSONFileWriter"
        cloud_config = {
            "enabled": True,
            "provider": "aws",
            "runtime": "python3.11"
        }
        
        writer_class = PluginLoader.load_writer(plugin_path, cloud_config)
        
        # Check that we got a cloud wrapper class
        assert writer_class.__name__ == "DynamicCloudWriter"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
