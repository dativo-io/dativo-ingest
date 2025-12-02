"""Tests for plugin utility functions."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import JobConfig, PluginConfig, PluginSandboxConfig
from dativo_ingest.plugins import extract_sandbox_config


class TestExtractSandboxConfig:
    """Test sandbox config extraction utility."""

    def test_extract_with_pydantic_model_dump(self):
        """Test extraction with Pydantic model that has model_dump method."""
        # Create actual Pydantic models
        sandbox_config = PluginSandboxConfig(
            enabled=True,
            memory_limit="512m",
            network_disabled=False,
        )
        plugin_config = PluginConfig(sandbox=sandbox_config)

        job_config = Mock(spec=JobConfig)
        job_config.plugins = plugin_config

        result_sandbox, result_plugin = extract_sandbox_config(job_config)

        assert result_sandbox is not None
        assert isinstance(result_sandbox, dict)
        assert result_sandbox["enabled"] is True
        assert result_sandbox["memory_limit"] == "512m"
        assert result_sandbox["network_disabled"] is False
        assert result_plugin is not None
        assert isinstance(result_plugin, dict)
        assert "sandbox" in result_plugin

    def test_extract_with_dict_method(self):
        """Test extraction with object that has dict() method."""
        sandbox_config = {"enabled": True, "seccomp_profile": "default"}

        # Create a simple object with dict() method
        class DictPluginConfig:
            def dict(self):
                return {"sandbox": sandbox_config}

            def __init__(self):
                self.sandbox = DictSandboxConfig()

        class DictSandboxConfig:
            def dict(self):
                return sandbox_config

        plugin_config = DictPluginConfig()
        job_config = Mock()
        job_config.plugins = plugin_config

        result_sandbox, result_plugin = extract_sandbox_config(job_config)

        assert result_sandbox == sandbox_config
        assert result_plugin is not None
        assert isinstance(result_plugin, dict)

    def test_extract_with_dict_attribute(self):
        """Test extraction with object that has __dict__ attribute."""
        sandbox_config = {"enabled": True}

        # Create a simple class with __dict__ attribute
        class DictSandbox:
            def __init__(self):
                self.__dict__ = sandbox_config.copy()

        class DictPlugin:
            def __init__(self):
                self.sandbox = DictSandbox()
                self.__dict__ = {"sandbox": self.sandbox}

        plugin_obj = DictPlugin()
        job_config = Mock()
        job_config.plugins = plugin_obj

        result_sandbox, result_plugin = extract_sandbox_config(job_config)

        assert result_sandbox == sandbox_config
        assert result_plugin is not None

    def test_extract_with_none_job_config(self):
        """Test extraction with None job_config."""
        result_sandbox, result_plugin = extract_sandbox_config(None)

        assert result_sandbox is None
        assert result_plugin is None

    def test_extract_with_no_plugins(self):
        """Test extraction with job_config that has no plugins."""
        job_config = Mock()
        job_config.plugins = None

        result_sandbox, result_plugin = extract_sandbox_config(job_config)

        assert result_sandbox is None
        assert result_plugin is None

    def test_extract_with_no_sandbox(self):
        """Test extraction with plugins but no sandbox config."""
        plugin_config = Mock()
        plugin_config.model_dump.return_value = {}
        plugin_config.sandbox = None

        job_config = Mock()
        job_config.plugins = plugin_config

        result_sandbox, result_plugin = extract_sandbox_config(job_config)

        assert result_sandbox is None
        assert result_plugin is not None
        assert isinstance(result_plugin, dict)

    def test_extract_with_empty_plugins(self):
        """Test extraction with empty plugins."""
        # Use SimpleNamespace to avoid Mock issues
        plugin_config = SimpleNamespace()
        plugin_config.model_dump = lambda: {}
        plugin_config.sandbox = None

        job_config = Mock()
        job_config.plugins = plugin_config

        result_sandbox, result_plugin = extract_sandbox_config(job_config)

        # Should handle gracefully
        assert result_sandbox is None
        assert result_plugin is not None
