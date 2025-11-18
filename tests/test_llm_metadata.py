"""Tests for LLM metadata generation configuration and validation."""

import pytest
from src.dativo_ingest.config import LLMConfig, JobConfig


class TestLLMConfig:
    """Test LLM configuration model."""

    def test_llm_config_disabled_by_default(self):
        """Test that LLM is disabled by default."""
        config = LLMConfig()
        assert config.enabled is False

    def test_llm_config_minimal_disabled(self):
        """Test minimal disabled configuration."""
        config = LLMConfig(enabled=False)
        assert config.enabled is False
        assert config.provider is None
        assert config.model is None

    def test_llm_config_enabled_requires_provider(self):
        """Test that enabled LLM requires provider."""
        with pytest.raises(ValueError, match="LLM provider is required"):
            LLMConfig(enabled=True, model="gpt-4")

    def test_llm_config_enabled_requires_model(self):
        """Test that enabled LLM requires model."""
        with pytest.raises(ValueError, match="LLM model is required"):
            LLMConfig(enabled=True, provider="openai")

    def test_llm_config_invalid_provider(self):
        """Test that invalid provider is rejected."""
        with pytest.raises(ValueError, match="Unsupported LLM provider"):
            LLMConfig(enabled=True, provider="invalid", model="test")

    def test_llm_config_valid_providers(self):
        """Test all valid LLM providers."""
        valid_providers = ["openai", "anthropic", "bedrock", "azure"]
        
        for provider in valid_providers:
            config = LLMConfig(
                enabled=True,
                provider=provider,
                model="test-model",
                api_key="test-key"
            )
            assert config.enabled is True
            assert config.provider == provider
            assert config.model == "test-model"

    def test_llm_config_defaults(self):
        """Test default values for optional fields."""
        config = LLMConfig(
            enabled=True,
            provider="openai",
            model="gpt-4",
            api_key="test-key"
        )
        
        assert config.temperature == 0.3
        assert config.max_tokens == 2000
        assert config.sample_records_count == 3
        assert config.endpoint is None

    def test_llm_config_custom_values(self):
        """Test custom values for optional fields."""
        config = LLMConfig(
            enabled=True,
            provider="azure",
            model="gpt-4",
            api_key="test-key",
            endpoint="https://custom.api",
            temperature=0.5,
            max_tokens=3000,
            sample_records_count=5
        )
        
        assert config.endpoint == "https://custom.api"
        assert config.temperature == 0.5
        assert config.max_tokens == 3000
        assert config.sample_records_count == 5


class TestJobConfigWithLLM:
    """Test JobConfig integration with LLM configuration."""

    def test_job_config_without_llm(self):
        """Test job config without LLM section."""
        config_data = {
            "tenant_id": "test",
            "source_connector_path": "/test/source.yaml",
            "target_connector_path": "/test/target.yaml",
            "asset_path": "/test/asset.yaml",
        }
        
        config = JobConfig(**config_data)
        assert config.llm is None

    def test_job_config_with_llm_disabled(self):
        """Test job config with LLM explicitly disabled."""
        config_data = {
            "tenant_id": "test",
            "source_connector_path": "/test/source.yaml",
            "target_connector_path": "/test/target.yaml",
            "asset_path": "/test/asset.yaml",
            "llm": {
                "enabled": False
            }
        }
        
        config = JobConfig(**config_data)
        assert config.llm is not None
        assert config.llm.enabled is False

    def test_job_config_with_llm_enabled(self):
        """Test job config with LLM enabled."""
        config_data = {
            "tenant_id": "test",
            "source_connector_path": "/test/source.yaml",
            "target_connector_path": "/test/target.yaml",
            "asset_path": "/test/asset.yaml",
            "llm": {
                "enabled": True,
                "provider": "openai",
                "model": "gpt-4",
                "api_key": "${OPENAI_API_KEY}",
                "temperature": 0.3,
                "sample_records_count": 5
            }
        }
        
        config = JobConfig(**config_data)
        assert config.llm is not None
        assert config.llm.enabled is True
        assert config.llm.provider == "openai"
        assert config.llm.model == "gpt-4"
        assert config.llm.api_key == "${OPENAI_API_KEY}"
        assert config.llm.temperature == 0.3
        assert config.llm.sample_records_count == 5

    def test_job_config_llm_validation_fails(self):
        """Test that job config fails with invalid LLM config."""
        config_data = {
            "tenant_id": "test",
            "source_connector_path": "/test/source.yaml",
            "target_connector_path": "/test/target.yaml",
            "asset_path": "/test/asset.yaml",
            "llm": {
                "enabled": True,
                "provider": "invalid",
                "model": "test"
            }
        }
        
        with pytest.raises(ValueError):
            JobConfig(**config_data)
