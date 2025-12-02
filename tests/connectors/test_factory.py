"""Tests for ExtractorFactory."""

import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dativo_ingest.config import JobConfig, SourceConfig
from dativo_ingest.connectors.factory import ExtractorFactory


class TestExtractorFactory:
    """Test ExtractorFactory."""

    def test_create_csv_extractor(self):
        """Test creating CSV extractor."""
        source_config = SourceConfig(type="csv", files=[{"path": "test.csv"}])
        job_config = Mock(spec=JobConfig)
        job_config.source_connector_path = None

        extractor, source_tags = ExtractorFactory.create(
            source_config, job_config, tenant_id="test_tenant"
        )

        assert extractor is not None
        assert hasattr(extractor, "extract")
        assert source_tags is None

    def test_create_postgres_extractor(self):
        """Test creating Postgres extractor."""
        source_config = SourceConfig(
            type="postgres",
            connection={"host": "localhost", "database": "test"},
        )
        job_config = Mock(spec=JobConfig)
        job_config.source_connector_path = None

        extractor, source_tags = ExtractorFactory.create(
            source_config, job_config, tenant_id="test_tenant"
        )

        assert extractor is not None
        assert hasattr(extractor, "extract")
        assert source_tags is None

    def test_create_mysql_extractor(self):
        """Test creating MySQL extractor."""
        source_config = SourceConfig(
            type="mysql",
            connection={"host": "localhost", "database": "test"},
        )
        job_config = Mock(spec=JobConfig)
        job_config.source_connector_path = None

        extractor, source_tags = ExtractorFactory.create(
            source_config, job_config, tenant_id="test_tenant"
        )

        assert extractor is not None
        assert hasattr(extractor, "extract")
        assert source_tags is None

    def test_create_custom_reader(self):
        """Test creating custom reader."""
        source_config = SourceConfig(
            type="custom",
            custom_reader="tests/fixtures/plugins/csv_employee_reader.py:CSVEmployeeReader",
        )
        job_config = Mock(spec=JobConfig)
        job_config.plugins = None

        extractor, source_tags = ExtractorFactory.create(
            source_config, job_config, tenant_id="test_tenant"
        )

        assert extractor is not None
        assert hasattr(extractor, "extract")
        assert source_tags is None

    def test_create_unsupported_type(self):
        """Test that unsupported types raise ValueError."""
        source_config = SourceConfig(type="unsupported_type")
        job_config = Mock(spec=JobConfig)
        job_config.source_connector_path = None

        with pytest.raises(ValueError, match="Unsupported source type"):
            ExtractorFactory.create(source_config, job_config, tenant_id="test_tenant")

    def test_create_stripe_without_recipe(self):
        """Test that Stripe requires connector recipe."""
        source_config = SourceConfig(type="stripe", objects=["customers"])
        job_config = Mock(spec=JobConfig)
        job_config.source_connector_path = None

        with pytest.raises(
            ValueError, match="Stripe connector requires connector_recipe"
        ):
            ExtractorFactory.create(source_config, job_config, tenant_id="test_tenant")

    def test_create_hubspot_without_recipe(self):
        """Test that HubSpot requires connector recipe."""
        source_config = SourceConfig(type="hubspot", objects=["contacts"])
        job_config = Mock(spec=JobConfig)
        job_config.source_connector_path = None

        with pytest.raises(
            ValueError, match="HubSpot connector requires connector_recipe"
        ):
            ExtractorFactory.create(source_config, job_config, tenant_id="test_tenant")

    @patch("dativo_ingest.connectors.factory.ConnectorRecipe")
    @patch("dativo_ingest.connectors.engine_framework.AirbyteExtractor")
    def test_create_airbyte_extractor(
        self, mock_airbyte_extractor, mock_connector_recipe_class
    ):
        """Test creating Airbyte extractor."""
        # Mock connector recipe
        mock_recipe = Mock()
        mock_recipe.default_engine = "airbyte"
        mock_recipe.name = "test_connector"
        mock_connector_recipe_class.from_yaml.return_value = mock_recipe

        # Mock AirbyteExtractor to avoid initialization issues
        mock_extractor = Mock()
        mock_airbyte_extractor.return_value = mock_extractor

        source_config = SourceConfig(type="custom_airbyte", objects=["stream1"])
        job_config = Mock(spec=JobConfig)
        job_config.source_connector_path = "connectors/test.yaml"

        extractor, source_tags = ExtractorFactory.create(
            source_config, job_config, tenant_id="test_tenant"
        )

        assert extractor is not None
        assert hasattr(extractor, "extract")

    @patch("dativo_ingest.connectors.csv_extractor.CSVExtractor")
    def test_extract_source_tags_from_metadata(self, mock_csv_extractor_class):
        """Test extracting source tags from extractor metadata."""
        source_config = SourceConfig(type="csv", files=[{"path": "test.csv"}])
        job_config = Mock(spec=JobConfig)
        job_config.source_connector_path = None

        # Mock extractor with extract_metadata method
        mock_extractor = Mock()
        mock_extractor.extract_metadata.return_value = {
            "tags": {"connector": "csv", "category": "file"}
        }
        mock_csv_extractor_class.return_value = mock_extractor

        extractor, source_tags = ExtractorFactory.create(
            source_config, job_config, tenant_id="test_tenant"
        )

        assert extractor is not None
        assert source_tags == {"connector": "csv", "category": "file"}
