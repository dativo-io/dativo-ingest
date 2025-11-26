"""Tests for infrastructure integration module."""

import json
import pytest
from pathlib import Path

from dativo_ingest.infrastructure import (
    InfrastructureConfig,
    InfrastructureRuntime,
    InfrastructureNetworking,
    InfrastructureStorage,
    InfrastructureTags,
    InfrastructureTerraform,
    InfrastructureMonitoring,
    load_infrastructure_config,
)


class MockJobConfig:
    """Mock job configuration for testing."""
    
    def __init__(self, tenant_id="test_tenant", environment="prod", asset="test_asset"):
        self.tenant_id = tenant_id
        self.environment = environment
        self.asset = asset
        self.source_connector = "test_source"


def test_infrastructure_runtime_validation():
    """Test runtime type validation."""
    # Valid runtime types
    valid_types = ["dagster", "airflow", "kubernetes", "ecs", "cloud_run", "cloud_functions"]
    for runtime_type in valid_types:
        runtime = InfrastructureRuntime(type=runtime_type)
        assert runtime.type == runtime_type
    
    # Invalid runtime type
    with pytest.raises(ValueError, match="Invalid runtime type"):
        InfrastructureRuntime(type="invalid")


def test_infrastructure_tags_to_flat_dict():
    """Test tag conversion to flat dictionary."""
    tags = InfrastructureTags(
        cost_center="FIN-001",
        business_unit="Finance",
        project="data-platform",
        environment="prod",
        owner="data-team@acme.com",
        compliance=["GDPR", "SOC2"],
        data_classification="Confidential",
        custom={"department": "payments", "team": "data-engineering"}
    )
    
    flat_tags = tags.to_flat_dict()
    
    assert flat_tags["CostCenter"] == "FIN-001"
    assert flat_tags["BusinessUnit"] == "Finance"
    assert flat_tags["Project"] == "data-platform"
    assert flat_tags["Environment"] == "prod"
    assert flat_tags["Owner"] == "data-team@acme.com"
    assert flat_tags["Compliance"] == "GDPR,SOC2"
    assert flat_tags["DataClassification"] == "Confidential"
    assert flat_tags["Custom_department"] == "payments"
    assert flat_tags["Custom_team"] == "data-engineering"


def test_infrastructure_config_provider_validation():
    """Test provider validation."""
    runtime = InfrastructureRuntime(type="ecs")
    
    # Valid providers
    valid_providers = ["aws", "gcp", "azure"]
    for provider in valid_providers:
        config = InfrastructureConfig(provider=provider, runtime=runtime)
        assert config.provider == provider
    
    # Invalid provider
    with pytest.raises(ValueError, match="Invalid provider"):
        InfrastructureConfig(provider="invalid", runtime=runtime)


def test_infrastructure_config_from_dict():
    """Test creating infrastructure config from dictionary."""
    config_dict = {
        "provider": "aws",
        "runtime": {
            "type": "ecs",
            "compute": {
                "cpu": "2048",
                "memory": "4096"
            },
            "timeout_seconds": 3600
        },
        "networking": {
            "vpc_id": "vpc-12345678",
            "subnet_ids": ["subnet-12345678", "subnet-87654321"],
            "private_access": True
        },
        "storage": {
            "state_bucket": "dativo-state",
            "data_bucket": "dativo-data",
            "encryption": {
                "enabled": True,
                "kms_key_id": "arn:aws:kms:us-east-1:123456789012:key/12345678"
            }
        },
        "tags": {
            "cost_center": "FIN-001",
            "owner": "data-team@acme.com"
        },
        "monitoring": {
            "enabled": True,
            "log_group": "/dativo/jobs/test"
        }
    }
    
    config = InfrastructureConfig.from_dict(config_dict)
    
    assert config.provider == "aws"
    assert config.runtime.type == "ecs"
    assert config.runtime.compute["cpu"] == "2048"
    assert config.networking.vpc_id == "vpc-12345678"
    assert len(config.networking.subnet_ids) == 2
    assert config.storage.state_bucket == "dativo-state"
    assert config.tags.cost_center == "FIN-001"
    assert config.monitoring.enabled is True


def test_infrastructure_config_to_dict():
    """Test converting infrastructure config to dictionary."""
    runtime = InfrastructureRuntime(
        type="ecs",
        compute={"cpu": "2048", "memory": "4096"},
        timeout_seconds=3600
    )
    tags = InfrastructureTags(
        cost_center="FIN-001",
        owner="data-team@acme.com"
    )
    
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        tags=tags
    )
    
    config_dict = config.to_dict()
    
    assert config_dict["provider"] == "aws"
    assert config_dict["runtime"]["type"] == "ecs"
    assert config_dict["runtime"]["compute"]["cpu"] == "2048"
    assert config_dict["tags"]["cost_center"] == "FIN-001"


def test_generate_terraform_vars_basic():
    """Test generating Terraform variables without asset tags."""
    runtime = InfrastructureRuntime(
        type="ecs",
        compute={"cpu": "2048", "memory": "4096"},
        timeout_seconds=3600
    )
    tags = InfrastructureTags(
        cost_center="FIN-001",
        business_unit="Finance",
        environment="prod"
    )
    
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        tags=tags
    )
    
    job_config = MockJobConfig()
    tf_vars = config.generate_terraform_vars(job_config)
    
    assert tf_vars["provider"] == "aws"
    assert tf_vars["runtime_type"] == "ecs"
    assert tf_vars["compute"]["cpu"] == "2048"
    assert tf_vars["timeout_seconds"] == 3600
    
    # Check tags
    assert tf_vars["tags"]["CostCenter"] == "FIN-001"
    assert tf_vars["tags"]["BusinessUnit"] == "Finance"
    assert tf_vars["tags"]["Environment"] == "prod"
    assert tf_vars["tags"]["TenantId"] == "test_tenant"
    assert tf_vars["tags"]["Asset"] == "test_asset"
    assert tf_vars["tags"]["ManagedBy"] == "dativo"


def test_generate_terraform_vars_with_asset_tags():
    """Test generating Terraform variables with asset tags."""
    runtime = InfrastructureRuntime(type="ecs")
    tags = InfrastructureTags(cost_center="FIN-001")
    
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        tags=tags
    )
    
    job_config = MockJobConfig()
    
    # Mock asset tags from tag_derivation
    asset_tags = {
        "classification.default": "pii",
        "classification.fields.email": "pii",
        "governance.retention_days": "365",
        "finops.cost_center": "FIN-001"
    }
    
    tf_vars = config.generate_terraform_vars(job_config, asset_tags)
    
    # Check asset tags are propagated
    assert tf_vars["tags"]["Classification_default"] == "pii"
    assert tf_vars["tags"]["Classification_fields_email"] == "pii"
    assert tf_vars["tags"]["Governance_retention_days"] == "365"
    assert tf_vars["tags"]["FinOps_cost_center"] == "FIN-001"


def test_export_terraform_vars_json(tmp_path):
    """Test exporting Terraform variables to JSON file."""
    runtime = InfrastructureRuntime(type="ecs")
    tags = InfrastructureTags(cost_center="FIN-001")
    
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        tags=tags
    )
    
    job_config = MockJobConfig()
    output_path = tmp_path / "terraform.tfvars.json"
    
    config.export_terraform_vars(
        output_path=output_path,
        job_config=job_config,
        format="json"
    )
    
    assert output_path.exists()
    
    with open(output_path) as f:
        data = json.load(f)
    
    assert data["provider"] == "aws"
    assert data["runtime_type"] == "ecs"
    assert data["tags"]["CostCenter"] == "FIN-001"


def test_export_terraform_vars_tfvars(tmp_path):
    """Test exporting Terraform variables to tfvars file."""
    runtime = InfrastructureRuntime(type="ecs")
    tags = InfrastructureTags(cost_center="FIN-001")
    
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        tags=tags
    )
    
    job_config = MockJobConfig()
    output_path = tmp_path / "terraform.tfvars"
    
    config.export_terraform_vars(
        output_path=output_path,
        job_config=job_config,
        format="tfvars"
    )
    
    assert output_path.exists()
    
    content = output_path.read_text()
    assert 'provider = "aws"' in content
    assert 'runtime_type = "ecs"' in content


def test_validate_infrastructure_config():
    """Test infrastructure configuration validation."""
    runtime = InfrastructureRuntime(type="ecs")
    
    # Config without tags
    config = InfrastructureConfig(provider="aws", runtime=runtime)
    warnings = config.validate_infrastructure_config()
    assert any("No tags specified" in w for w in warnings)
    
    # Config with incomplete tags
    tags = InfrastructureTags(cost_center="FIN-001")
    config = InfrastructureConfig(provider="aws", runtime=runtime, tags=tags)
    warnings = config.validate_infrastructure_config()
    assert any("No owner tag specified" in w for w in warnings)
    assert any("No environment tag specified" in w for w in warnings)
    
    # Config with complete tags
    tags = InfrastructureTags(
        cost_center="FIN-001",
        owner="data-team@acme.com",
        environment="prod"
    )
    config = InfrastructureConfig(provider="aws", runtime=runtime, tags=tags)
    warnings = config.validate_infrastructure_config()
    assert len(warnings) == 0


def test_load_infrastructure_config_none():
    """Test loading infrastructure config when None is provided."""
    result = load_infrastructure_config(None)
    assert result is None


def test_load_infrastructure_config_valid():
    """Test loading valid infrastructure config."""
    config_dict = {
        "provider": "aws",
        "runtime": {
            "type": "ecs"
        }
    }
    
    config = load_infrastructure_config(config_dict)
    assert config is not None
    assert config.provider == "aws"
    assert config.runtime.type == "ecs"


def test_load_infrastructure_config_invalid():
    """Test loading invalid infrastructure config."""
    config_dict = {
        "provider": "invalid_provider",
        "runtime": {
            "type": "ecs"
        }
    }
    
    with pytest.raises(ValueError, match="Invalid infrastructure configuration"):
        load_infrastructure_config(config_dict)


def test_terraform_backend_configuration():
    """Test Terraform backend configuration."""
    terraform = InfrastructureTerraform(
        module_source="git::https://github.com/acme/terraform-dativo-job.git",
        module_version="v1.0.0",
        backend={
            "type": "s3",
            "config": {
                "bucket": "terraform-state",
                "key": "dativo/jobs/test.tfstate",
                "region": "us-east-1"
            }
        }
    )
    
    assert terraform.module_source == "git::https://github.com/acme/terraform-dativo-job.git"
    assert terraform.backend["type"] == "s3"
    assert terraform.backend["config"]["bucket"] == "terraform-state"


def test_custom_terraform_variables():
    """Test custom Terraform variables are included."""
    runtime = InfrastructureRuntime(type="ecs")
    terraform = InfrastructureTerraform(
        variables={
            "enable_vpc_endpoints": True,
            "enable_container_insights": True
        }
    )
    
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        terraform=terraform
    )
    
    job_config = MockJobConfig()
    tf_vars = config.generate_terraform_vars(job_config)
    
    assert tf_vars["enable_vpc_endpoints"] is True
    assert tf_vars["enable_container_insights"] is True


def test_networking_validation():
    """Test networking configuration validation."""
    runtime = InfrastructureRuntime(type="ecs")
    
    # VPC ID without subnets
    networking = InfrastructureNetworking(
        vpc_id="vpc-12345678",
        subnet_ids=None
    )
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        networking=networking
    )
    warnings = config.validate_infrastructure_config()
    assert any("VPC ID specified but no subnet IDs" in w for w in warnings)
    
    # Subnets without VPC ID
    networking = InfrastructureNetworking(
        vpc_id=None,
        subnet_ids=["subnet-12345678"]
    )
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        networking=networking
    )
    warnings = config.validate_infrastructure_config()
    assert any("Subnet IDs specified but no VPC ID" in w for w in warnings)


def test_storage_encryption_validation():
    """Test storage encryption configuration validation."""
    runtime = InfrastructureRuntime(type="ecs")
    
    # Encryption enabled without KMS key
    storage = InfrastructureStorage(
        state_bucket="state-bucket",
        data_bucket="data-bucket",
        encryption={"enabled": True, "kms_key_id": None}
    )
    config = InfrastructureConfig(
        provider="aws",
        runtime=runtime,
        storage=storage
    )
    warnings = config.validate_infrastructure_config()
    assert any("Encryption enabled but no KMS key ID" in w for w in warnings)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
