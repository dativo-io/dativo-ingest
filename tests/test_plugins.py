"""Tests for custom plugin system."""

import pytest
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from dativo_ingest.plugins import BaseReader, BaseWriter, PluginLoader
from dativo_ingest.config import SourceConfig, TargetConfig
from dativo_ingest.validator import IncrementalStateManager


class TestPluginLoader:
    """Test plugin loading functionality."""
    
    def test_load_reader_from_path(self, tmp_path):
        """Test loading a custom reader from file path."""
        # Create a test reader plugin
        plugin_code = '''
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1, "name": "test"}]
'''
        
        plugin_file = tmp_path / "test_reader.py"
        plugin_file.write_text(plugin_code)
        
        # Load the reader class
        reader_class = PluginLoader.load_reader(f"{plugin_file}:TestReader")
        
        # Verify it's the correct class
        assert reader_class.__name__ == "TestReader"
        assert issubclass(reader_class, BaseReader)
        
        # Instantiate and test
        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)
        
        batches = list(reader.extract())
        assert len(batches) == 1
        assert batches[0] == [{"id": 1, "name": "test"}]
    
    def test_load_writer_from_path(self, tmp_path):
        """Test loading a custom writer from file path."""
        # Create a test writer plugin
        plugin_code = '''
from dativo_ingest.plugins import BaseWriter

class TestWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        return [{"path": "test.dat", "size_bytes": 100}]
'''
        
        plugin_file = tmp_path / "test_writer.py"
        plugin_file.write_text(plugin_code)
        
        # Load the writer class
        writer_class = PluginLoader.load_writer(f"{plugin_file}:TestWriter")
        
        # Verify it's the correct class
        assert writer_class.__name__ == "TestWriter"
        assert issubclass(writer_class, BaseWriter)
        
        # Instantiate and test
        class MockAsset:
            name = "test"
            schema = []
        
        target_config = TargetConfig(type="test")
        writer = writer_class(MockAsset(), target_config, "/tmp/output")
        
        metadata = writer.write_batch([{"id": 1}], 0)
        assert len(metadata) == 1
        assert metadata[0]["path"] == "test.dat"
    
    def test_invalid_path_format(self):
        """Test error handling for invalid path format."""
        with pytest.raises(ValueError, match="must be in format"):
            PluginLoader.load_reader("invalid_path")
    
    def test_missing_file(self):
        """Test error handling for missing plugin file."""
        with pytest.raises(ValueError, match="not found"):
            PluginLoader.load_reader("/nonexistent/path.py:TestReader")
    
    def test_missing_class(self, tmp_path):
        """Test error handling for missing class in module."""
        plugin_code = '''
class WrongClassName:
    pass
'''
        
        plugin_file = tmp_path / "test.py"
        plugin_file.write_text(plugin_code)
        
        with pytest.raises(ValueError, match="not found in module"):
            PluginLoader.load_reader(f"{plugin_file}:TestReader")
    
    def test_wrong_base_class(self, tmp_path):
        """Test error handling for class not inheriting from BaseReader."""
        plugin_code = '''
class TestReader:
    pass
'''
        
        plugin_file = tmp_path / "test.py"
        plugin_file.write_text(plugin_code)
        
        with pytest.raises(ValueError, match="must inherit from"):
            PluginLoader.load_reader(f"{plugin_file}:TestReader")


class TestBaseReader:
    """Test BaseReader base class."""
    
    def test_reader_has_source_config(self):
        """Test that reader receives source config."""
        source_config = SourceConfig(
            type="test",
            connection={"endpoint": "https://api.example.com"},
            credentials={"api_key": "test-key"},
        )
        
        class TestReader(BaseReader):
            def extract(self, state_manager=None):
                yield [{"config_type": self.source_config.type}]
        
        reader = TestReader(source_config)
        assert reader.source_config.type == "test"
        assert reader.source_config.connection["endpoint"] == "https://api.example.com"
        
        batches = list(reader.extract())
        assert batches[0][0]["config_type"] == "test"
    
    def test_reader_default_record_estimate(self):
        """Test default record estimate returns None."""
        source_config = SourceConfig(type="test")
        
        class TestReader(BaseReader):
            def extract(self, state_manager=None):
                yield []
        
        reader = TestReader(source_config)
        assert reader.get_total_records_estimate() is None


class TestBaseWriter:
    """Test BaseWriter base class."""
    
    def test_writer_has_config(self):
        """Test that writer receives target config and asset definition."""
        class MockAsset:
            name = "test_table"
            schema = [{"name": "id", "type": "integer"}]
        
        target_config = TargetConfig(
            type="test",
            connection={"bucket": "test-bucket"},
        )
        
        class TestWriter(BaseWriter):
            def write_batch(self, records, file_counter):
                return [{
                    "path": f"{self.output_base}/test.dat",
                    "asset_name": self.asset_definition.name,
                }]
        
        writer = TestWriter(MockAsset(), target_config, "s3://test-bucket/data")
        assert writer.target_config.type == "test"
        assert writer.asset_definition.name == "test_table"
        assert writer.output_base == "s3://test-bucket/data"
        
        metadata = writer.write_batch([], 0)
        assert metadata[0]["asset_name"] == "test_table"
    
    def test_writer_default_commit(self):
        """Test default commit_files implementation."""
        class MockAsset:
            name = "test"
            schema = []
        
        target_config = TargetConfig(type="test")
        
        class TestWriter(BaseWriter):
            def write_batch(self, records, file_counter):
                return [{"path": "test.dat"}]
        
        writer = TestWriter(MockAsset(), target_config, "/tmp")
        
        # Test default commit implementation
        result = writer.commit_files([{"path": "file1"}, {"path": "file2"}])
        assert result["status"] == "success"
        assert result["files_added"] == 2


class TestCustomReaderIntegration:
    """Integration tests for custom readers."""
    
    def test_reader_with_state_manager(self):
        """Test custom reader with state manager for incremental syncs."""
        source_config = SourceConfig(
            type="test",
            incremental={
                "strategy": "cursor",
                "cursor_field": "updated_at",
            },
        )
        
        class IncrementalReader(BaseReader):
            def extract(self, state_manager=None):
                # Simulate incremental extraction
                records = [
                    {"id": 1, "updated_at": "2024-01-01"},
                    {"id": 2, "updated_at": "2024-01-02"},
                ]
                yield records
        
        reader = IncrementalReader(source_config)
        
        # Extract with state manager
        state_manager = IncrementalStateManager()
        batches = list(reader.extract(state_manager=state_manager))
        
        assert len(batches) == 1
        assert len(batches[0]) == 2


class TestCustomWriterIntegration:
    """Integration tests for custom writers."""
    
    def test_writer_with_schema_validation(self):
        """Test custom writer accessing schema from asset definition."""
        class MockAsset:
            name = "users"
            schema = [
                {"name": "id", "type": "integer"},
                {"name": "email", "type": "string"},
            ]
        
        target_config = TargetConfig(type="test")
        
        class SchemaAwareWriter(BaseWriter):
            def write_batch(self, records, file_counter):
                # Validate records against schema
                schema_fields = {f["name"] for f in self.asset_definition.schema}
                
                for record in records:
                    for key in record.keys():
                        assert key in schema_fields, f"Field {key} not in schema"
                
                return [{"path": "test.dat", "size_bytes": 100}]
        
        writer = SchemaAwareWriter(MockAsset(), target_config, "/tmp")
        
        # Write valid records
        valid_records = [
            {"id": 1, "email": "user@example.com"},
            {"id": 2, "email": "admin@example.com"},
        ]
        metadata = writer.write_batch(valid_records, 0)
        assert len(metadata) == 1
        
        # Write invalid records (should raise assertion)
        invalid_records = [
            {"id": 1, "invalid_field": "value"},
        ]
        with pytest.raises(AssertionError, match="not in schema"):
            writer.write_batch(invalid_records, 0)
