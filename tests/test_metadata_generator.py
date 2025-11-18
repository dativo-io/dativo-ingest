"""Tests for the LLM-powered metadata generator."""

import json
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import AssetDefinition, LLMMetadataConfig, SourceConfig
from dativo_ingest.metadata_generator import SourceMetadataGenerator


def _sample_asset() -> AssetDefinition:
    return AssetDefinition(
        name="sample_asset",
        version="1.0",
        source_type="csv",
        object="Person",
        schema=[
            {"name": "id", "type": "integer", "required": True},
            {"name": "email", "type": "string", "required": False},
        ],
        team={"owner": "owner@example.com"},
        description={"purpose": "Sample dataset"},
    )


def _sample_source() -> SourceConfig:
    return SourceConfig(
        type="csv",
        description="CSV files",
        files=[{"path": "/tmp/person.csv", "object": "Person"}],
    )


def test_generate_metadata_persists_artifact(tmp_path, monkeypatch):
    """Generator should return metadata payload and write artifact."""
    config = LLMMetadataConfig(
        enabled=True,
        api_key="test-key",
        output_dir=str(tmp_path),
        persist_artifact=True,
    )
    generator = SourceMetadataGenerator(config)
    asset = _sample_asset()
    source = _sample_source()

    llm_payload = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "dataset_summary": "Contains customer contacts.",
                            "pii_risk_assessment": "medium",
                            "data_quality_recommendations": ["enforce unique id"],
                            "semantic_columns": [
                                {
                                    "name": "id",
                                    "description": "Primary key",
                                    "business_term": "customer_id",
                                }
                            ],
                        }
                    )
                }
            }
        ]
    }
    monkeypatch.setattr(generator, "_call_llm", lambda prompt: llm_payload)

    result = generator.generate(asset, source)
    assert result is not None
    assert result["metadata"]["dataset_summary"] == "Contains customer contacts."
    artifact_path = Path(result["artifact_path"])
    assert artifact_path.exists()
    artifact_data = json.loads(artifact_path.read_text())
    assert artifact_data["metadata"]["pii_risk_assessment"] == "medium"


def test_generate_metadata_handles_invalid_json(monkeypatch):
    """Generator should return None when LLM response is not JSON."""
    config = LLMMetadataConfig(enabled=True, api_key="test-key", persist_artifact=False)
    generator = SourceMetadataGenerator(config)
    asset = _sample_asset()
    source = _sample_source()

    invalid_payload = {
        "choices": [{"message": {"content": "not-json"}}],
    }
    monkeypatch.setattr(generator, "_call_llm", lambda prompt: invalid_payload)

    result = generator.generate(asset, source)
    assert result is None
