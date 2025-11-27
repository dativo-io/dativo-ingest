"""Comprehensive tests for custom plugin system.

Tests cover:
1. Plugin loading (Python and Rust)
2. Base class functionality
3. Default readers and writers
4. Custom Python plugins
5. Custom Rust plugins (when available)
6. Integration with ETL pipeline
7. Error handling and edge cases
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

import pytest

from dativo_ingest.config import SourceConfig, TargetConfig
from dativo_ingest.plugins import (
    BaseReader,
    BaseWriter,
    ConnectionTestResult,
    DiscoveryResult,
    PluginLoader,
)
from dativo_ingest.validator import IncrementalStateManager


class TestPluginLoader:
    """Test plugin loading functionality."""

    def test_load_reader_from_path(self, tmp_path):
        """Test loading a custom reader from file path."""
        # Create a test reader plugin
        plugin_code = """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1, "name": "test"}]
"""

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
        plugin_code = """
from dativo_ingest.plugins import BaseWriter

class TestWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        return [{"path": "test.dat", "size_bytes": 100}]
"""

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

    def test_load_reader_from_cloud_uri(self, tmp_path, monkeypatch):
        """Test loading a Python reader from cloud storage URI."""
        plugin_code = """
from dativo_ingest.plugins import BaseReader

class CloudReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 42}]
"""

        cached_path = tmp_path / "cache" / "cloud_reader.py"
        cached_path.parent.mkdir(parents=True, exist_ok=True)
        cached_path.write_text(plugin_code)

        monkeypatch.setattr(
            "dativo_ingest.plugins.resolve_plugin_path",
            lambda path: cached_path,
        )

        reader_class = PluginLoader.load_reader(
            "s3://plugins/cloud_reader.py:CloudReader"
        )
        assert reader_class.__name__ == "CloudReader"
        records = list(reader_class(SourceConfig(type="test")).extract())
        assert records[0][0]["id"] == 42

    def test_load_rust_reader_from_cloud_uri(self, tmp_path, monkeypatch):
        """Test loading a Rust reader from cloud storage without touching ctypes."""
        lib_path = tmp_path / "libcloud_reader.so"
        lib_path.write_bytes(b"fake")

        monkeypatch.setattr(
            "dativo_ingest.plugins.resolve_plugin_path",
            lambda path: lib_path,
        )

        import sys
        import types

        fake_bridge = types.ModuleType("dativo_ingest.rust_plugin_bridge")

        def fake_reader_wrapper(_lib_path, _func_name):
            class DummyReader(BaseReader):
                def extract(self, state_manager=None):
                    yield [{"source": "rust"}]

            return DummyReader

        def fake_writer_wrapper(_asset, _target, _output_base):
            class DummyWriter(BaseWriter):
                def write_batch(self, records, file_counter):
                    return [{"path": "dummy", "records": len(records)}]

            return DummyWriter

        fake_bridge.create_rust_reader_wrapper = fake_reader_wrapper
        fake_bridge.create_rust_writer_wrapper = fake_writer_wrapper
        monkeypatch.setitem(
            sys.modules, "dativo_ingest.rust_plugin_bridge", fake_bridge
        )

        reader_class = PluginLoader.load_reader(
            "gs://plugins/libcloud_reader.so:create_reader"
        )
        reader = reader_class(SourceConfig(type="test"))
        batches = list(reader.extract())
        assert batches[0][0]["source"] == "rust"

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
        plugin_code = """
class WrongClassName:
    pass
"""

        plugin_file = tmp_path / "test.py"
        plugin_file.write_text(plugin_code)

        with pytest.raises(ValueError, match="not found in module"):
            PluginLoader.load_reader(f"{plugin_file}:TestReader")

    def test_wrong_base_class(self, tmp_path):
        """Test error handling for class not inheriting from BaseReader."""
        plugin_code = """
class TestReader:
    pass
"""

        plugin_file = tmp_path / "test.py"
        plugin_file.write_text(plugin_code)

        from dativo_ingest.exceptions import PluginError

        with pytest.raises(PluginError, match="must inherit from"):
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
                return [
                    {
                        "path": f"{self.output_base}/test.dat",
                        "asset_name": self.asset_definition.name,
                    }
                ]

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


class TestDefaultReaders:
    """Tests for default/built-in readers."""

    def test_csv_extractor(self, tmp_path):
        """Test CSV extractor (default reader)."""
        from dativo_ingest.connectors.csv_extractor import CSVExtractor

        # Create test CSV file
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("id,name,value\n1,Alice,100\n2,Bob,200\n")

        # Configure source
        source_config = SourceConfig(
            type="csv",
            files=[{"path": str(csv_file)}],
            engine={"options": {"batch_size": 100}},
        )

        # Create extractor
        extractor = CSVExtractor(source_config)

        # Extract data
        batches = list(extractor.extract())
        assert len(batches) == 1
        assert len(batches[0]) == 2
        assert batches[0][0]["name"] == "Alice"
        assert batches[0][1]["name"] == "Bob"

    def test_csv_extractor_large_file(self, tmp_path):
        """Test CSV extractor with batching."""
        from dativo_ingest.connectors.csv_extractor import CSVExtractor

        # Create larger CSV file
        csv_file = tmp_path / "large.csv"
        with open(csv_file, "w") as f:
            f.write("id,name\n")
            for i in range(250):
                f.write(f"{i},user_{i}\n")

        # Configure with small batch size
        source_config = SourceConfig(
            type="csv",
            files=[{"path": str(csv_file)}],
            engine={"options": {"batch_size": 100}},
        )

        extractor = CSVExtractor(source_config)

        # Extract in batches
        batches = list(extractor.extract())
        assert len(batches) == 3  # 100, 100, 50
        assert len(batches[0]) == 100
        assert len(batches[1]) == 100
        assert len(batches[2]) == 50


class TestDefaultWriters:
    """Tests for default/built-in writers."""

    def test_parquet_writer_basic(self, tmp_path):
        """Test ParquetWriter (default writer)."""
        from dativo_ingest.parquet_writer import ParquetWriter

        # Mock asset definition
        class MockAsset:
            name = "test_table"
            domain = "test"
            dataProduct = "test_product"
            schema = [
                {"name": "id", "type": "integer"},
                {"name": "name", "type": "string"},
            ]

        # Configure target
        target_config = TargetConfig(
            type="parquet",
            connection={},
            file_format="parquet",
        )

        output_base = str(tmp_path / "output")

        # Create writer
        writer = ParquetWriter(MockAsset(), target_config, output_base)

        # Write batch
        records = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]

        metadata = writer.write_batch(records, 0)
        assert len(metadata) == 1
        assert "path" in metadata[0]
        assert metadata[0]["record_count"] == 2


class TestPythonPluginEndToEnd:
    """End-to-end tests for Python plugins."""

    def test_python_reader_writer_pipeline(self, tmp_path):
        """Test complete pipeline with Python plugins."""
        # Create custom reader
        reader_code = """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        # Generate test data
        records = [
            {"id": i, "name": f"user_{i}", "value": i * 10}
            for i in range(1, 6)
        ]
        yield records
"""

        reader_file = tmp_path / "test_reader.py"
        reader_file.write_text(reader_code)

        # Create custom writer
        writer_code = """
import json
from dativo_ingest.plugins import BaseWriter

class TestWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        # Write to JSON file
        output_file = f"{self.output_base}/part-{file_counter:05d}.json"
        import os
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, "w") as f:
            json.dump(records, f)
        
        return [{"path": output_file, "size_bytes": 100, "record_count": len(records)}]
"""

        writer_file = tmp_path / "test_writer.py"
        writer_file.write_text(writer_code)

        # Load reader
        reader_class = PluginLoader.load_reader(f"{reader_file}:TestReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        # Load writer
        writer_class = PluginLoader.load_writer(f"{writer_file}:TestWriter")

        class MockAsset:
            name = "test"
            schema = []

        target_config = TargetConfig(type="test")
        output_base = str(tmp_path / "output")
        writer = writer_class(MockAsset(), target_config, output_base)

        # Run pipeline
        all_metadata = []
        for batch_idx, batch in enumerate(reader.extract()):
            metadata = writer.write_batch(batch, batch_idx)
            all_metadata.extend(metadata)

        # Verify results
        assert len(all_metadata) == 1
        assert all_metadata[0]["record_count"] == 5

        # Verify file was written
        output_file = Path(all_metadata[0]["path"])
        assert output_file.exists()

        # Verify content
        with open(output_file) as f:
            data = json.load(f)
        assert len(data) == 5
        assert data[0]["name"] == "user_1"


class TestRustPluginDetection:
    """Tests for Rust plugin detection and loading."""

    def test_plugin_type_detection_python(self):
        """Test detection of Python plugin."""
        plugin_type = PluginLoader._detect_plugin_type("/path/to/plugin.py:ClassName")
        assert plugin_type == "python"

    def test_plugin_type_detection_rust_so(self):
        """Test detection of Rust plugin (.so)."""
        plugin_type = PluginLoader._detect_plugin_type(
            "/path/to/libplugin.so:create_reader"
        )
        assert plugin_type == "rust"

    def test_plugin_type_detection_rust_dylib(self):
        """Test detection of Rust plugin (.dylib)."""
        plugin_type = PluginLoader._detect_plugin_type(
            "/path/to/libplugin.dylib:create_reader"
        )
        assert plugin_type == "rust"

    def test_plugin_type_detection_rust_dll(self):
        """Test detection of Rust plugin (.dll)."""
        plugin_type = PluginLoader._detect_plugin_type(
            "/path/to/plugin.dll:create_reader"
        )
        assert plugin_type == "rust"

    def test_rust_plugin_loading_without_library(self):
        """Test Rust plugin loading fails gracefully without library."""
        with pytest.raises(ValueError, match="not found"):
            PluginLoader.load_reader("/nonexistent/libplugin.so:create_reader")


class TestRustPluginBridge:
    """Tests for Rust plugin bridge functionality."""

    def test_rust_bridge_import(self):
        """Test that rust_plugin_bridge can be imported."""
        try:
            from dativo_ingest.rust_plugin_bridge import (
                RustReaderWrapper,
                RustWriterWrapper,
                create_rust_reader_wrapper,
                create_rust_writer_wrapper,
            )

            # If import succeeds, classes exist
            assert RustReaderWrapper is not None
            assert RustWriterWrapper is not None
        except ImportError as e:
            pytest.skip(f"Rust bridge not available: {e}")

    def test_rust_wrapper_serialization(self):
        """Test JSON serialization for Rust bridge."""
        from dativo_ingest.rust_plugin_bridge import RustReaderWrapper

        # Mock the library and functions
        class MockLib:
            pass

        # Create source config
        source_config = SourceConfig(
            type="test",
            connection={"endpoint": "http://test"},
            credentials={"api_key": "test"},
            objects=["table1"],
        )

        # Test serialization (without actually loading library)
        wrapper = object.__new__(RustReaderWrapper)
        wrapper.source_config = source_config

        config_json = wrapper._serialize_config()
        config_dict = json.loads(config_json)

        assert config_dict["type"] == "test"
        assert config_dict["connection"]["endpoint"] == "http://test"
        assert config_dict["credentials"]["api_key"] == "test"
        assert "table1" in config_dict["objects"]


class TestPluginErrorHandling:
    """Tests for error handling in plugin system."""

    def test_reader_error_propagation(self, tmp_path):
        """Test that reader errors are properly propagated."""
        reader_code = """
from dativo_ingest.plugins import BaseReader

class ErrorReader(BaseReader):
    def extract(self, state_manager=None):
        raise ValueError("Simulated extraction error")
"""

        reader_file = tmp_path / "error_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:ErrorReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        with pytest.raises(ValueError, match="Simulated extraction error"):
            list(reader.extract())

    def test_writer_error_propagation(self, tmp_path):
        """Test that writer errors are properly propagated."""
        writer_code = """
from dativo_ingest.plugins import BaseWriter

class ErrorWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        raise IOError("Simulated write error")
"""

        writer_file = tmp_path / "error_writer.py"
        writer_file.write_text(writer_code)

        writer_class = PluginLoader.load_writer(f"{writer_file}:ErrorWriter")

        class MockAsset:
            name = "test"
            schema = []

        target_config = TargetConfig(type="test")
        writer = writer_class(MockAsset(), target_config, "/tmp")

        with pytest.raises(IOError, match="Simulated write error"):
            writer.write_batch([{"id": 1}], 0)

    def test_invalid_plugin_path_format(self):
        """Test error for invalid plugin path format."""
        with pytest.raises(ValueError, match="must be in format"):
            PluginLoader.load_reader("invalid_path_without_colon.py")

    def test_missing_plugin_file(self):
        """Test error for missing plugin file."""
        with pytest.raises(ValueError, match="not found"):
            PluginLoader.load_reader("/nonexistent/path.py:ClassName")


class TestPluginConfiguration:
    """Tests for plugin configuration handling."""

    def test_reader_accesses_all_config(self, tmp_path):
        """Test that reader can access all configuration fields."""
        reader_code = """
from dativo_ingest.plugins import BaseReader

class ConfigReader(BaseReader):
    def extract(self, state_manager=None):
        config_summary = {
            "type": self.source_config.type,
            "has_connection": self.source_config.connection is not None,
            "has_credentials": self.source_config.credentials is not None,
            "has_engine": self.source_config.engine is not None,
        }
        yield [config_summary]
"""

        reader_file = tmp_path / "config_reader.py"
        reader_file.write_text(reader_code)

        source_config = SourceConfig(
            type="test",
            connection={"url": "http://test"},
            credentials={"token": "secret"},
            engine={"options": {"batch_size": 1000}},
        )

        reader_class = PluginLoader.load_reader(f"{reader_file}:ConfigReader")
        reader = reader_class(source_config)

        batches = list(reader.extract())
        assert len(batches) == 1
        config = batches[0][0]

        assert config["type"] == "test"
        assert config["has_connection"] is True
        assert config["has_credentials"] is True
        assert config["has_engine"] is True

    def test_writer_accesses_all_config(self, tmp_path):
        """Test that writer can access all configuration fields."""
        writer_code = """
from dativo_ingest.plugins import BaseWriter

class ConfigWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        config_summary = {
            "asset_name": self.asset_definition.name,
            "output_base": self.output_base,
            "target_type": self.target_config.type,
            "has_connection": self.target_config.connection is not None,
        }
        return [config_summary]
"""

        writer_file = tmp_path / "config_writer.py"
        writer_file.write_text(writer_code)

        class MockAsset:
            name = "test_table"
            schema = []

        target_config = TargetConfig(
            type="test",
            connection={"bucket": "test-bucket"},
        )

        writer_class = PluginLoader.load_writer(f"{writer_file}:ConfigWriter")
        writer = writer_class(MockAsset(), target_config, "/tmp/output")

        metadata = writer.write_batch([], 0)
        assert len(metadata) == 1

        config = metadata[0]
        assert config["asset_name"] == "test_table"
        assert config["output_base"] == "/tmp/output"
        assert config["target_type"] == "test"
        assert config["has_connection"] is True


class TestPluginPerformance:
    """Tests for plugin performance characteristics."""

    def test_streaming_reader(self, tmp_path):
        """Test that reader properly streams data in batches."""
        reader_code = """
from dativo_ingest.plugins import BaseReader

class StreamingReader(BaseReader):
    def extract(self, state_manager=None):
        # Yield multiple batches
        for batch_num in range(3):
            records = [
                {"batch": batch_num, "record": i}
                for i in range(100)
            ]
            yield records
"""

        reader_file = tmp_path / "streaming_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:StreamingReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        batches = list(reader.extract())
        assert len(batches) == 3
        assert all(len(batch) == 100 for batch in batches)

        # Verify batch ordering
        assert batches[0][0]["batch"] == 0
        assert batches[1][0]["batch"] == 1
        assert batches[2][0]["batch"] == 2


# ============================================================================
# Custom Reader Plugin Source Tag Extraction Tests
# ============================================================================


class TestCustomReaderSourceTagExtraction:
    """Tests for custom reader plugins implementing source tag extraction."""

    def test_custom_reader_with_extract_metadata(self, tmp_path):
        """Test custom reader implementing extract_metadata()."""
        reader_code = """
from dativo_ingest.plugins import BaseReader

class MetadataReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1, "email": "test@example.com"}]
    
    def extract_metadata(self):
        return {
            "tags": {
                "email": "PII",
                "id": "PUBLIC"
            }
        }
"""

        reader_file = tmp_path / "metadata_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:MetadataReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        # Test extract_metadata method
        metadata = reader.extract_metadata()
        assert "tags" in metadata
        assert metadata["tags"]["email"] == "PII"
        assert metadata["tags"]["id"] == "PUBLIC"

        # Verify extract still works
        batches = list(reader.extract())
        assert len(batches) == 1

    def test_custom_reader_with_get_source_tags(self, tmp_path):
        """Test custom reader implementing get_source_tags() (alternative method)."""
        reader_code = """
from dativo_ingest.plugins import BaseReader

class SourceTagsReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1, "phone": "555-1234"}]
    
    def get_source_tags(self):
        return {
            "phone": "SENSITIVE",
            "id": "PUBLIC"
        }
"""

        reader_file = tmp_path / "source_tags_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:SourceTagsReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        # Test get_source_tags method
        source_tags = reader.get_source_tags()
        assert source_tags["phone"] == "SENSITIVE"
        assert source_tags["id"] == "PUBLIC"

        # Verify extract still works
        batches = list(reader.extract())
        assert len(batches) == 1

    def test_custom_reader_source_tags_propagated(self, tmp_path):
        """Test that source tags from custom reader flow through to IcebergCommitter."""
        from dativo_ingest.config import AssetDefinition, TargetConfig
        from dativo_ingest.iceberg_committer import IcebergCommitter

        reader_code = """
from dativo_ingest.plugins import BaseReader

class TaggedReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1, "email": "test@example.com"}]
    
    def extract_metadata(self):
        return {
            "tags": {
                "email": "PII"
            }
        }
"""

        reader_file = tmp_path / "tagged_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:TaggedReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        # Extract source tags
        metadata = reader.extract_metadata()
        source_tags = metadata.get("tags", {})

        # Create asset and committer with source tags
        asset = AssetDefinition(
            name="test_asset",
            version="1.0",
            source_type="test",
            object="test_object",
            schema=[
                {"name": "id", "type": "integer"},
                {"name": "email", "type": "string"},
            ],
            team={"owner": "test@company.com"},
        )

        target_config = TargetConfig(
            type="iceberg",
            catalog="nessie",
            branch="main",
            warehouse="s3://test-bucket/",
            connection={
                "nessie": {"uri": "http://localhost:19120/api/v1"},
                "s3": {
                    "endpoint": "http://localhost:9000",
                    "bucket": "test-bucket",
                    "access_key_id": "test-key",
                    "secret_access_key": "test-secret",
                },
            },
        )

        committer = IcebergCommitter(
            asset_definition=asset,
            target_config=target_config,
            source_tags=source_tags,
        )

        # Verify source tags are stored
        assert committer.source_tags == source_tags

        # Derive properties (should include source tag classification)
        properties = committer._derive_table_properties()
        assert "classification.fields.email" in properties
        assert properties["classification.fields.email"] == "pii"

    def test_custom_reader_source_tags_override_hierarchy(self, tmp_path):
        """Test three-level hierarchy works with custom readers."""
        from dativo_ingest.config import AssetDefinition
        from dativo_ingest.tag_derivation import derive_tags_from_asset

        reader_code = """
from dativo_ingest.plugins import BaseReader

class HierarchyReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1, "email": "test@example.com"}]
    
    def extract_metadata(self):
        return {
            "tags": {
                "email": "PII"  # Level 3: Source (lowest priority)
            }
        }
"""

        reader_file = tmp_path / "hierarchy_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:HierarchyReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        # Extract source tags
        metadata = reader.extract_metadata()
        source_tags = metadata.get("tags", {})

        # Create asset with explicit classification (Level 2: Asset)
        asset = AssetDefinition(
            name="test_asset",
            version="1.0",
            source_type="test",
            object="test_object",
            schema=[
                {
                    "name": "email",
                    "type": "string",
                    "classification": "SENSITIVE_PII",  # Level 2: Asset (overrides source)
                },
            ],
            team={"owner": "test@company.com"},
        )

        # Job overrides (Level 1: Job - highest priority)
        classification_overrides = {
            "email": "HIGH_PII",  # Level 1: Job (overrides all)
        }

        # Derive tags with all three levels
        tags = derive_tags_from_asset(
            asset_definition=asset,
            classification_overrides=classification_overrides,
            source_tags=source_tags,
        )

        # Verify hierarchy: job > asset > source
        assert "classification.fields.email" in tags
        assert tags["classification.fields.email"] == "high_pii"  # Job wins

    def test_custom_reader_no_source_tags_method(self, tmp_path):
        """Test custom reader without source tag methods (should work normally)."""
        reader_code = """
from dativo_ingest.plugins import BaseReader

class SimpleReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1, "name": "test"}]
"""

        reader_file = tmp_path / "simple_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:SimpleReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        # Reader should work normally without source tag methods
        batches = list(reader.extract())
        assert len(batches) == 1

        # extract_metadata should not exist
        assert not hasattr(reader, "extract_metadata")
        assert not hasattr(reader, "get_source_tags")


class TestPluginConnectionAndDiscovery:
    """Tests for check_connection() and discover() methods."""

    def test_reader_check_connection_default(self):
        """Test default check_connection implementation."""
        source_config = SourceConfig(type="test", connection={})

        class TestReader(BaseReader):
            def extract(self, state_manager=None):
                yield []

        reader = TestReader(source_config)
        result = reader.check_connection()

        assert isinstance(result, ConnectionTestResult)
        assert result.success is True
        assert (
            "connection" in result.message.lower()
            or "success" in result.message.lower()
        )

    def test_reader_check_connection_custom(self, tmp_path):
        """Test custom check_connection implementation."""
        reader_code = """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(
            success=True,
            message="Custom connection check",
            details={"custom": "data"}
        )
    
    def extract(self, state_manager=None):
        yield []
"""

        reader_file = tmp_path / "test_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:TestReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        result = reader.check_connection()
        assert isinstance(result, ConnectionTestResult)
        assert result.success is True
        assert result.message == "Custom connection check"
        assert result.details["custom"] == "data"

    def test_writer_check_connection_default(self):
        """Test default check_connection implementation for writer."""

        class MockAsset:
            name = "test"
            schema = []

        target_config = TargetConfig(type="test")

        class TestWriter(BaseWriter):
            def write_batch(self, records, file_counter):
                return []

        writer = TestWriter(MockAsset(), target_config, "/tmp")
        result = writer.check_connection()

        assert isinstance(result, ConnectionTestResult)
        assert result.success is True

    def test_writer_check_connection_custom(self, tmp_path):
        """Test custom check_connection implementation for writer."""
        writer_code = """
from dativo_ingest.plugins import BaseWriter, ConnectionTestResult

class TestWriter(BaseWriter):
    def check_connection(self):
        return ConnectionTestResult(
            success=False,
            message="Connection failed",
            error_code="CONNECTION_ERROR"
        )
    
    def write_batch(self, records, file_counter):
        return []
"""

        writer_file = tmp_path / "test_writer.py"
        writer_file.write_text(writer_code)

        writer_class = PluginLoader.load_writer(f"{writer_file}:TestWriter")

        class MockAsset:
            name = "test"
            schema = []

        target_config = TargetConfig(type="test")
        writer = writer_class(MockAsset(), target_config, "/tmp")

        result = writer.check_connection()
        assert isinstance(result, ConnectionTestResult)
        assert result.success is False
        assert result.error_code == "CONNECTION_ERROR"

    def test_reader_discover_default(self):
        """Test default discover implementation."""
        source_config = SourceConfig(type="test", connection={})

        class TestReader(BaseReader):
            def extract(self, state_manager=None):
                yield []

        reader = TestReader(source_config)
        result = reader.discover()

        assert isinstance(result, DiscoveryResult)
        assert result.objects == []
        assert isinstance(result.metadata, dict)

    def test_reader_discover_custom(self, tmp_path):
        """Test custom discover implementation."""
        reader_code = """
from dativo_ingest.plugins import BaseReader, DiscoveryResult

class TestReader(BaseReader):
    def discover(self):
        return DiscoveryResult(
            objects=[
                {"name": "table1", "type": "table"},
                {"name": "table2", "type": "table"}
            ],
            metadata={"database": "test_db"}
        )
    
    def extract(self, state_manager=None):
        yield []
"""

        reader_file = tmp_path / "test_reader.py"
        reader_file.write_text(reader_code)

        reader_class = PluginLoader.load_reader(f"{reader_file}:TestReader")
        source_config = SourceConfig(type="test")
        reader = reader_class(source_config)

        result = reader.discover()
        assert isinstance(result, DiscoveryResult)
        assert len(result.objects) == 2
        assert result.objects[0]["name"] == "table1"
        assert result.metadata["database"] == "test_db"


class TestPluginSandboxExecution:
    """Tests for plugin execution through sandbox (cloud mode)."""

    def test_plugin_check_connection_via_sandbox(self, tmp_path):
        """Test check_connection through sandbox with mocked Docker."""
        import sys
        from unittest.mock import Mock, patch

        # Mock docker module if not already mocked
        if "docker" not in sys.modules or not hasattr(
            sys.modules.get("docker"), "from_env"
        ):
            mock_docker = Mock()
            mock_docker.from_env = Mock()
            mock_docker_errors = Mock()
            mock_docker_errors.DockerException = Exception
            sys.modules["docker"] = mock_docker
            sys.modules["docker.errors"] = mock_docker_errors

        reader_code = """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(
            success=True,
            message="Connection successful",
            details={"test": "data"}
        )
    
    def extract(self, state_manager=None):
        yield []
"""

        reader_file = tmp_path / "test_reader.py"
        reader_file.write_text(reader_code)

        with patch("dativo_ingest.sandbox.docker.from_env") as mock_docker:
            from dativo_ingest.sandbox import PluginSandbox

            # Mock Docker client
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_docker.return_value = mock_client

            # Mock container
            mock_container = Mock()
            mock_container.wait.return_value = {"StatusCode": 0}
            mock_container.logs.return_value = b'{"status": "success", "result": {"success": true, "message": "Connection successful", "details": {"test": "data"}}}'
            mock_client.containers.create.return_value = mock_container

            # Create sandbox and execute
            sandbox = PluginSandbox(str(reader_file))
            result = sandbox.execute(
                "check_connection", {"type": "test", "connection": {}}
            )

            # Verify Docker was called
            mock_client.containers.create.assert_called_once()
            mock_container.start.assert_called_once()
            mock_container.wait.assert_called_once()

            # Verify result
            assert isinstance(result, dict)
            assert result.get("success") is True or result.get("status") == "success"

    def test_plugin_discover_via_sandbox(self, tmp_path):
        """Test discover through sandbox with mocked Docker."""
        import sys
        from unittest.mock import Mock, patch

        # Mock docker module if not already mocked
        if "docker" not in sys.modules or not hasattr(
            sys.modules.get("docker"), "from_env"
        ):
            mock_docker = Mock()
            mock_docker.from_env = Mock()
            mock_docker_errors = Mock()
            mock_docker_errors.DockerException = Exception
            sys.modules["docker"] = mock_docker
            sys.modules["docker.errors"] = mock_docker_errors

        reader_code = """
from dativo_ingest.plugins import BaseReader, DiscoveryResult

class TestReader(BaseReader):
    def discover(self):
        return DiscoveryResult(
            objects=[{"name": "stream1", "type": "stream"}],
            metadata={"source": "test"}
        )
    
    def extract(self, state_manager=None):
        yield []
"""

        reader_file = tmp_path / "test_reader.py"
        reader_file.write_text(reader_code)

        with patch("dativo_ingest.sandbox.docker.from_env") as mock_docker:
            from dativo_ingest.sandbox import PluginSandbox

            # Mock Docker client
            mock_client = Mock()
            mock_client.ping.return_value = True
            mock_docker.return_value = mock_client

            # Mock container
            mock_container = Mock()
            mock_container.wait.return_value = {"StatusCode": 0}
            mock_container.logs.return_value = b'{"status": "success", "result": {"objects": [{"name": "stream1", "type": "stream"}], "metadata": {"source": "test"}}}'
            mock_client.containers.create.return_value = mock_container

            # Create sandbox and execute
            sandbox = PluginSandbox(str(reader_file))
            result = sandbox.execute("discover", {"type": "test", "connection": {}})

            # Verify Docker was called
            mock_client.containers.create.assert_called_once()
            mock_container.start.assert_called_once()

            # Verify result
            assert isinstance(result, dict)
            assert "objects" in result or result.get("status") == "success"


class TestConnectionTestResult:
    """Tests for ConnectionTestResult class."""

    def test_connection_result_success(self):
        """Test successful connection result."""
        result = ConnectionTestResult(
            success=True,
            message="Connected",
            details={"host": "localhost", "port": 5432},
        )

        assert result.success is True
        assert result.message == "Connected"
        assert result.details["host"] == "localhost"
        assert result.details["port"] == 5432
        assert result.error_code is None

        # Test to_dict
        result_dict = result.to_dict()
        assert result_dict["success"] is True
        assert result_dict["message"] == "Connected"
        assert result_dict["details"]["host"] == "localhost"
        assert "error_code" not in result_dict or result_dict["error_code"] is None

    def test_connection_result_failure(self):
        """Test failed connection result."""
        result = ConnectionTestResult(
            success=False,
            message="Connection failed",
            error_code="CONNECTION_ERROR",
            details={"error": "timeout"},
        )

        assert result.success is False
        assert result.message == "Connection failed"
        assert result.error_code == "CONNECTION_ERROR"
        assert result.details["error"] == "timeout"

        # Test to_dict
        result_dict = result.to_dict()
        assert result_dict["success"] is False
        assert result_dict["message"] == "Connection failed"
        assert result_dict["error_code"] == "CONNECTION_ERROR"
        assert result_dict["details"]["error"] == "timeout"


class TestDiscoveryResult:
    """Tests for DiscoveryResult class."""

    def test_discovery_result_with_objects(self):
        """Test discovery result with objects."""
        objects = [
            {"name": "users", "type": "table", "schema": {"id": "integer"}},
            {"name": "orders", "type": "table", "schema": {"order_id": "integer"}},
        ]
        metadata = {"database": "test_db", "version": "1.0"}

        result = DiscoveryResult(objects=objects, metadata=metadata)

        assert len(result.objects) == 2
        assert result.objects[0]["name"] == "users"
        assert result.objects[1]["name"] == "orders"
        assert result.metadata["database"] == "test_db"
        assert result.metadata["version"] == "1.0"

        # Test to_dict
        result_dict = result.to_dict()
        assert len(result_dict["objects"]) == 2
        assert result_dict["objects"][0]["name"] == "users"
        assert result_dict["metadata"]["database"] == "test_db"

    def test_discovery_result_empty(self):
        """Test discovery result with no objects."""
        result = DiscoveryResult(objects=[], metadata={})

        assert len(result.objects) == 0
        assert isinstance(result.metadata, dict)
        assert len(result.metadata) == 0

        # Test to_dict
        result_dict = result.to_dict()
        assert len(result_dict["objects"]) == 0
        assert isinstance(result_dict["metadata"], dict)


class TestPluginVersioning:
    """Tests for plugin versioning functionality."""

    def test_reader_version_attribute(self):
        """Test that reader can have version attribute."""
        source_config = SourceConfig(type="test")

        class VersionedReader(BaseReader):
            __version__ = "1.0.0"

            def extract(self, state_manager=None):
                yield []

        reader = VersionedReader(source_config)
        assert reader.__version__ == "1.0.0"

    def test_writer_version_attribute(self):
        """Test that writer can have version attribute."""

        class MockAsset:
            name = "test"
            schema = []

        target_config = TargetConfig(type="test")

        class VersionedWriter(BaseWriter):
            __version__ = "2.0.0"

            def write_batch(self, records, file_counter):
                return []

        writer = VersionedWriter(MockAsset(), target_config, "/tmp")
        assert writer.__version__ == "2.0.0"

    def test_reader_default_version(self):
        """Test that reader has default version from base class."""
        source_config = SourceConfig(type="test")

        class UnversionedReader(BaseReader):
            def extract(self, state_manager=None):
                yield []

        reader = UnversionedReader(source_config)
        # BaseReader should have a default version
        assert hasattr(reader, "__version__")
        assert reader.__version__ is not None

    def test_writer_default_version(self):
        """Test that writer has default version from base class."""

        class MockAsset:
            name = "test"
            schema = []

        target_config = TargetConfig(type="test")

        class UnversionedWriter(BaseWriter):
            def write_batch(self, records, file_counter):
                return []

        writer = UnversionedWriter(MockAsset(), target_config, "/tmp")
        # BaseWriter should have a default version
        assert hasattr(writer, "__version__")
        assert writer.__version__ is not None


class TestModuleExports:
    """Tests for module exports and imports."""

    def test_plugin_classes_importable(self):
        """Test that all plugin classes can be imported from main module."""
        from dativo_ingest import (
            BaseReader,
            BaseWriter,
            ConnectionTestResult,
            DiscoveryResult,
            PluginLoader,
        )

        assert BaseReader is not None
        assert BaseWriter is not None
        assert ConnectionTestResult is not None
        assert DiscoveryResult is not None
        assert PluginLoader is not None

    def test_error_classes_importable(self):
        """Test that all error classes can be imported from main module."""
        from dativo_ingest import (
            AuthenticationError,
            ConfigurationError,
            ConnectionError,
            DativoError,
            PluginError,
            PluginVersionError,
            RateLimitError,
            SandboxError,
            TransientError,
            ValidationError,
            get_error_code,
            is_retryable_error,
            wrap_exception,
        )

        # Verify all classes exist
        assert DativoError is not None
        assert ConnectionError is not None
        assert AuthenticationError is not None
        assert ValidationError is not None
        assert ConfigurationError is not None
        assert TransientError is not None
        assert RateLimitError is not None
        assert PluginError is not None
        assert PluginVersionError is not None
        assert SandboxError is not None
        assert callable(is_retryable_error)
        assert callable(get_error_code)
        assert callable(wrap_exception)

    def test_version_importable(self):
        """Test that __version__ can be imported from main module."""
        from dativo_ingest import __version__

        assert __version__ is not None
        assert isinstance(__version__, str)
        assert len(__version__) > 0
