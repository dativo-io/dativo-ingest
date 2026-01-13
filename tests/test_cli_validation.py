import argparse
import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest
import yaml

from dativo_ingest.cli_validation import validate_asset_command, validate_config_command
from dativo_ingest.config import AssetDefinition, JobConfig


@pytest.fixture
def mock_args():
    args = MagicMock()
    args.verbose = False
    args.json = False
    args.mode = "self_hosted"
    args.skip_schema = False
    return args


class TestValidateConfigCommand:
    @patch("dativo_ingest.cli_validation.Path")
    @patch("dativo_ingest.cli_validation.JobConfig")
    @patch("dativo_ingest.cli_validation.ConnectorValidator")
    def test_validate_config_success(self, mock_validator_cls, mock_job_config_cls, mock_path, mock_args):
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.__str__.return_value = "config.yaml"
        
        job_config = MagicMock()
        mock_job_config_cls.from_yaml.return_value = job_config
        
        mock_validator = MagicMock()
        mock_validator_cls.return_value = mock_validator
        
        mock_args.path = "config.yaml"
        
        exit_code = validate_config_command(mock_args)
        
        assert exit_code == 0
        mock_job_config_cls.from_yaml.assert_called_once()
        job_config.validate_schema_presence.assert_called_once()
        mock_validator.validate_job.assert_called_once_with(job_config, mode="self_hosted")

    @patch("dativo_ingest.cli_validation.Path")
    def test_validate_config_file_not_found(self, mock_path, mock_args):
        mock_path.return_value.exists.return_value = False
        mock_args.path = "nonexistent.yaml"
        
        exit_code = validate_config_command(mock_args)
        
        assert exit_code == 2

    @patch("dativo_ingest.cli_validation.Path")
    @patch("dativo_ingest.cli_validation.JobConfig")
    def test_validate_config_invalid_yaml(self, mock_job_config_cls, mock_path, mock_args):
        mock_path.return_value.exists.return_value = True
        mock_job_config_cls.from_yaml.side_effect = Exception("Invalid YAML")
        mock_args.path = "invalid.yaml"
        
        exit_code = validate_config_command(mock_args)
        
        assert exit_code == 2

    @patch("dativo_ingest.cli_validation.Path")
    @patch("dativo_ingest.cli_validation.JobConfig")
    def test_validate_config_missing_asset(self, mock_job_config_cls, mock_path, mock_args):
        mock_path.return_value.exists.return_value = True
        job_config = MagicMock()
        mock_job_config_cls.from_yaml.return_value = job_config
        job_config.validate_schema_presence.side_effect = SystemExit(2)
        mock_args.path = "config.yaml"
        
        exit_code = validate_config_command(mock_args)
        
        assert exit_code == 2


class TestValidateAssetCommand:
    @patch("dativo_ingest.cli_validation.Path")
    @patch("dativo_ingest.cli_validation.AssetDefinition")
    def test_validate_asset_success(self, mock_asset_def_cls, mock_path, mock_args):
        mock_path.return_value.exists.return_value = True
        mock_path.return_value.__str__.return_value = "asset.yaml"
        
        mock_args.path = "asset.yaml"
        
        exit_code = validate_asset_command(mock_args)
        
        assert exit_code == 0
        mock_asset_def_cls.from_yaml.assert_called_once_with(mock_path.return_value, validate_schema=True)

    @patch("dativo_ingest.cli_validation.Path")
    @patch("dativo_ingest.cli_validation.AssetDefinition")
    def test_validate_asset_skip_schema(self, mock_asset_def_cls, mock_path, mock_args):
        mock_path.return_value.exists.return_value = True
        
        mock_args.path = "asset.yaml"
        mock_args.skip_schema = True
        
        exit_code = validate_asset_command(mock_args)
        
        assert exit_code == 0
        mock_asset_def_cls.from_yaml.assert_called_once_with(mock_path.return_value, validate_schema=False)

    @patch("dativo_ingest.cli_validation.Path")
    @patch("dativo_ingest.cli_validation.AssetDefinition")
    def test_validate_asset_invalid(self, mock_asset_def_cls, mock_path, mock_args):
        mock_path.return_value.exists.return_value = True
        mock_asset_def_cls.from_yaml.side_effect = ValueError("Missing required field")
        
        mock_args.path = "asset.yaml"
        
        exit_code = validate_asset_command(mock_args)
        
        assert exit_code == 2

    @patch("dativo_ingest.cli_validation.Path")
    def test_validate_asset_file_not_found(self, mock_path, mock_args):
        mock_path.return_value.exists.return_value = False
        mock_args.path = "nonexistent.yaml"
        
        exit_code = validate_asset_command(mock_args)
        
        assert exit_code == 2
