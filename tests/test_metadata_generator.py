"""Tests for the LLM metadata generator."""

import sys
from pathlib import Path

import pytest
import yaml

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import (  # noqa: E402
    AssetDefinition,
    LLMConfig,
    MetadataGenerationConfig,
    SourceConfig,
)
from dativo_ingest.metadata_generator import MetadataGenerator  # noqa: E402


@pytest.fixture
def api_definition_file(tmp_path):
    """Create a temporary API definition file."""
    api_spec = {
        "openapi": "3.0.0",
        "info": {"title": "Stripe API", "version": "1.0.0"},
        "paths": {
            "/customers": {
                "get": {
                    "summary": "Retrieve customers",
                    "responses": {"200": {"description": "Successful response"}},
                }
            }
        },
    }
    spec_path = tmp_path / "api.yaml"
    spec_path.write_text(yaml.safe_dump(api_spec))
    return spec_path


def test_metadata_generator_parses_llm_response(api_definition_file, monkeypatch):
    """Ensure generator returns structured metadata from mocked LLM response."""
    asset = AssetDefinition(
        name="stripe_customers",
        version="1.0",
        source_type="stripe",
        object="customers",
        schema=[{"name": "id", "type": "string"}],
        team={"owner": "owner@example.com"},
    )
    source_config = SourceConfig(type="stripe", objects=["customers"])
    metadata_config = MetadataGenerationConfig(
        enabled=True,
        source_api_definition_path=str(api_definition_file),
        llm=LLMConfig(api_key="test-key", model="gpt-4o-mini"),
    )

    generator = MetadataGenerator(metadata_config, asset, source_config)

    mock_response = """
    {
        "summary": "Stripe customers API with billing metadata.",
        "recommended_tags": ["payments", "customers"],
        "field_insights": [{"field": "email", "description": "Primary customer email"}],
        "data_quality_notes": "Ensure email is unique."
    }
    """

    monkeypatch.setattr(
        MetadataGenerator,
        "_invoke_llm",
        lambda self, prompt: mock_response,
    )

    metadata = generator.generate()
    assert metadata["summary"].startswith("Stripe customers")
    assert "customers" in metadata["recommended_tags"]
    assert metadata["source_type"] == "stripe"
