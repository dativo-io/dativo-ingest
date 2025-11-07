"""Smoke tests for CSV to Iceberg E2E ingestion.

Users can select datasets using pytest markers:
  - pytest tests/test_smoke_csv_to_iceberg.py -m adventureworks
  - pytest tests/test_smoke_csv_to_iceberg.py -m music_listening
  - pytest tests/test_smoke_csv_to_iceberg.py -m employee
  - pytest tests/test_smoke_csv_to_iceberg.py  # runs all datasets

Or use the --dataset flag:
  - pytest tests/test_smoke_csv_to_iceberg.py --dataset=adventureworks
  - pytest tests/test_smoke_csv_to_iceberg.py --dataset=music_listening
"""

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

import pytest
import yaml

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import AssetDefinition, JobConfig
from dativo_ingest.validator import ConnectorValidator


# Dataset registry
DATASETS_YAML = Path(__file__).parent / "fixtures" / "datasets.yaml"


def load_datasets() -> Dict:
    """Load available datasets from registry."""
    with open(DATASETS_YAML) as f:
        return yaml.safe_load(f)


def get_available_datasets() -> List[str]:
    """Get list of available dataset names."""
    datasets = load_datasets()
    return list(datasets.get("datasets", {}).keys())


def get_dataset_info(dataset_name: str) -> Dict:
    """Get information about a specific dataset."""
    datasets = load_datasets()
    return datasets.get("datasets", {}).get(dataset_name, {})


@pytest.fixture
def selected_dataset(request) -> Optional[str]:
    """Get selected dataset from command line or marker."""
    # Check for --dataset command line argument
    dataset_arg = request.config.getoption("--dataset", default=None)
    if dataset_arg:
        return dataset_arg
    
    # Check for pytest marker
    markers = [m.name for m in request.node.iter_markers()]
    for marker in markers:
        if marker in get_available_datasets():
            return marker
    
    # Default: return None to run all datasets
    return None


@pytest.fixture
def temp_test_dir():
    """Create a temporary directory for test execution."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def test_registry(temp_test_dir):
    """Create a test registry file."""
    registry_path = temp_test_dir / "registry" / "connectors.yaml"
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Copy the actual registry
    actual_registry = Path(__file__).parent.parent / "registry" / "connectors.yaml"
    shutil.copy(actual_registry, registry_path)
    
    return registry_path


@pytest.fixture
def csv_connector_recipe(temp_test_dir):
    """Create CSV connector recipe."""
    connector_dir = temp_test_dir / "connectors" / "sources"
    connector_dir.mkdir(parents=True, exist_ok=True)
    connector_path = connector_dir / "csv.yaml"
    
    actual_connector = Path(__file__).parent.parent / "connectors" / "sources" / "csv.yaml"
    shutil.copy(actual_connector, connector_path)
    
    return connector_path


@pytest.fixture
def iceberg_connector_recipe(temp_test_dir):
    """Create Iceberg connector recipe."""
    connector_dir = temp_test_dir / "connectors" / "targets"
    connector_dir.mkdir(parents=True, exist_ok=True)
    connector_path = connector_dir / "iceberg.yaml"
    
    actual_connector = Path(__file__).parent.parent / "connectors" / "targets" / "iceberg.yaml"
    shutil.copy(actual_connector, connector_path)
    
    return connector_path


@pytest.fixture
def asset_definitions(temp_test_dir):
    """Create asset definition files from tests/assets."""
    assets_dir = temp_test_dir / "assets" / "csv" / "v1.0"
    assets_dir.mkdir(parents=True, exist_ok=True)
    
    # Use test-specific asset definitions from tests/assets
    test_assets = Path(__file__).parent / "assets" / "csv" / "v1.0"
    for asset_file in test_assets.glob("*.yaml"):
        shutil.copy(asset_file, assets_dir / asset_file.name)
    
    return assets_dir


@pytest.fixture
def dataset_fixtures(selected_dataset, temp_test_dir):
    """Load dataset fixtures based on selection."""
    fixtures_base = Path(__file__).parent / "fixtures" / "seeds"
    
    if selected_dataset:
        # Load specific dataset
        dataset_info = get_dataset_info(selected_dataset)
        if not dataset_info:
            pytest.skip(f"Dataset '{selected_dataset}' not found")
        
        fixtures_dir = fixtures_base / dataset_info["fixtures_dir"]
        data_dir = temp_test_dir / "data" / dataset_info["fixtures_dir"]
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy CSV files
        for csv_file in fixtures_dir.glob("*.csv"):
            shutil.copy(csv_file, data_dir / csv_file.name)
        
        return {
            "dataset_name": selected_dataset,
            "dataset_info": dataset_info,
            "fixtures_dir": fixtures_dir,
            "data_dir": data_dir,
        }
    else:
        # Load all datasets
        datasets = {}
        for dataset_name in get_available_datasets():
            dataset_info = get_dataset_info(dataset_name)
            fixtures_dir = fixtures_base / dataset_info["fixtures_dir"]
            data_dir = temp_test_dir / "data" / dataset_info["fixtures_dir"]
            data_dir.mkdir(parents=True, exist_ok=True)
            
            # Copy CSV files
            for csv_file in fixtures_dir.glob("*.csv"):
                shutil.copy(csv_file, data_dir / csv_file.name)
            
            datasets[dataset_name] = {
                "dataset_name": dataset_name,
                "dataset_info": dataset_info,
                "fixtures_dir": fixtures_dir,
                "data_dir": data_dir,
            }
        
        return datasets


@pytest.fixture
def job_config_factory(temp_test_dir, csv_connector_recipe, iceberg_connector_recipe, asset_definitions):
    """Factory to create job configs for any dataset asset - jobs stored in tests/jobs/smoke."""
    def _create_job_config(dataset_name: str, asset_name: str, csv_file: Path, object_name: str):
        """Create a job config for a specific dataset asset - stored in tests/jobs/smoke."""
        # Store job configs in tests/jobs/smoke directory
        test_jobs_dir = Path(__file__).parent / "jobs" / "smoke"
        test_jobs_dir.mkdir(parents=True, exist_ok=True)
        
        # Also create in temp dir for test execution
        job_dir = temp_test_dir / "jobs" / dataset_name
        job_dir.mkdir(parents=True, exist_ok=True)
        job_path = job_dir / f"{asset_name}_to_iceberg.yaml"
        
        # Find asset file - try multiple naming conventions
        asset_file = None
        for pattern in [f"{asset_name}.yaml", f"csv_{asset_name}.yaml"]:
            candidate = asset_definitions / pattern
            if candidate.exists():
                asset_file = candidate
                break
        
        if not asset_file or not asset_file.exists():
            pytest.skip(f"Asset file not found for {asset_name} (tried {asset_name}.yaml, csv_{asset_name}.yaml)")
        
        # Read asset name from asset file
        asset_def = AssetDefinition.from_yaml(asset_file)
        actual_asset_name = asset_def.name
        
        job_data = {
            "tenant_id": "test_tenant",
            "environment": "test",
            "source_connector": "csv",
            "source_connector_path": str(csv_connector_recipe),
            "target_connector": "iceberg",
            "target_connector_path": str(iceberg_connector_recipe),
            "asset": actual_asset_name,
            "asset_path": str(asset_file),
            "source_overrides": {
                "files": [
                    {
                        "file_path": str(csv_file),
                        "object": object_name
                    }
                ]
            },
            "target_overrides": {
                "branch": "test_tenant",
                "warehouse": f"s3://test-lake/{temp_test_dir.name}/",
                "connection": {
                    "nessie": {
                        "uri": "http://localhost:19120/api/v1"
                    },
                    "s3": {
                        "endpoint": "http://localhost:9000",
                        "bucket": "test-bucket",
                        "access_key_id": "minioadmin",
                        "secret_access_key": "minioadmin",
                        "region": "us-east-1",
                        "path_style_access": True
                    }
                }
            },
            "logging": {
                "redaction": False,
                "level": "DEBUG"
            }
        }
        
        # Write to temp dir for test execution
        with open(job_path, "w") as f:
            yaml.dump(job_data, f)
        
        # Also save a copy to tests/jobs/smoke for reference
        test_job_path = test_jobs_dir / f"{dataset_name}_{asset_name}_to_iceberg.yaml"
        with open(test_job_path, "w") as f:
            yaml.dump(job_data, f)
        
        return job_path
    
    return _create_job_config


class TestCSVToIcebergSmoke:
    """Smoke tests for CSV to Iceberg E2E ingestion."""
    
    @pytest.mark.parametrize("dataset_name", get_available_datasets())
    def test_dataset_files_exist(self, dataset_fixtures, dataset_name):
        """Test that CSV files exist for each dataset."""
        if isinstance(dataset_fixtures, dict) and "dataset_name" in dataset_fixtures:
            # Single dataset selected
            if dataset_fixtures["dataset_name"] != dataset_name:
                pytest.skip(f"Dataset {dataset_name} not selected")
            fixtures = dataset_fixtures
        else:
            # All datasets loaded
            if dataset_name not in dataset_fixtures:
                pytest.skip(f"Dataset {dataset_name} not found")
            fixtures = dataset_fixtures[dataset_name]
        
        data_dir = fixtures["data_dir"]
        dataset_info = fixtures["dataset_info"]
        
        # Check that CSV files exist
        for asset in dataset_info.get("assets", []):
            csv_file = data_dir / asset["csv_file"]
            assert csv_file.exists(), f"CSV file {asset['csv_file']} not found for dataset {dataset_name}"
            assert csv_file.stat().st_size > 0, f"CSV file {asset['csv_file']} is empty"
    
    @pytest.mark.parametrize("dataset_name", get_available_datasets())
    def test_asset_definitions_exist(self, asset_definitions, dataset_fixtures, dataset_name):
        """Test that asset definitions exist for each dataset."""
        if isinstance(dataset_fixtures, dict) and "dataset_name" in dataset_fixtures:
            if dataset_fixtures["dataset_name"] != dataset_name:
                pytest.skip(f"Dataset {dataset_name} not selected")
            fixtures = dataset_fixtures
        else:
            if dataset_name not in dataset_fixtures:
                pytest.skip(f"Dataset {dataset_name} not found")
            fixtures = dataset_fixtures[dataset_name]
        
        dataset_info = fixtures["dataset_info"]
        
        # Check that asset definitions exist
        for asset in dataset_info.get("assets", []):
            asset_file = asset_definitions / asset["asset_file"]
            assert asset_file.exists(), f"Asset file {asset['asset_file']} not found"
            
            # Verify it can be loaded
            asset_def_obj = AssetDefinition.from_yaml(asset_file)
            assert asset_def_obj.name is not None
            assert len(asset_def_obj.schema) > 0
    
    @pytest.mark.parametrize("dataset_name", get_available_datasets())
    def test_job_config_validation(
        self, 
        dataset_fixtures, 
        job_config_factory, 
        test_registry, 
        dataset_name
    ):
        """Test job config validation for each dataset asset."""
        if isinstance(dataset_fixtures, dict) and "dataset_name" in dataset_fixtures:
            if dataset_fixtures["dataset_name"] != dataset_name:
                pytest.skip(f"Dataset {dataset_name} not selected")
            fixtures = dataset_fixtures
        else:
            if dataset_name not in dataset_fixtures:
                pytest.skip(f"Dataset {dataset_name} not found")
            fixtures = dataset_fixtures[dataset_name]
        
        dataset_info = fixtures["dataset_info"]
        data_dir = fixtures["data_dir"]
        
        # Test each asset in the dataset
        for asset in dataset_info.get("assets", []):
            csv_file = data_dir / asset["csv_file"]
            if not csv_file.exists():
                pytest.skip(f"CSV file {asset['csv_file']} not found")
            
            # Create job config
            job_config_path = job_config_factory(
                dataset_name=dataset_name,
                asset_name=asset["name"],
                csv_file=csv_file,
                object_name=asset["object"]
            )
            
            # Load and validate
            job_config = JobConfig.from_yaml(job_config_path)
            
            assert job_config.tenant_id == "test_tenant"
            assert job_config.source_connector_path is not None
            assert job_config.target_connector_path is not None
            assert job_config.asset_path is not None
            
            # Verify source config
            source_config = job_config.get_source()
            assert source_config.type == "csv"
            assert source_config.files is not None
            assert len(source_config.files) == 1
            assert source_config.files[0]["object"] == asset["object"]
            
            # Verify target config
            target_config = job_config.get_target()
            assert target_config.type == "iceberg"
            
            # Validate schema presence
            job_config.validate_schema_presence()
            
            # Validate connector
            validator = ConnectorValidator(registry_path=test_registry)
            validator.validate_job(job_config, mode="self_hosted")
    
    @pytest.mark.parametrize("dataset_name", get_available_datasets())
    @pytest.mark.integration
    def test_csv_to_iceberg_e2e_validation(
        self,
        dataset_fixtures,
        job_config_factory,
        test_registry,
        dataset_name
    ):
        """E2E smoke test: Validate complete CSV to Iceberg job configuration for each dataset."""
        if isinstance(dataset_fixtures, dict) and "dataset_name" in dataset_fixtures:
            if dataset_fixtures["dataset_name"] != dataset_name:
                pytest.skip(f"Dataset {dataset_name} not selected")
            fixtures = dataset_fixtures
        else:
            if dataset_name not in dataset_fixtures:
                pytest.skip(f"Dataset {dataset_name} not found")
            fixtures = dataset_fixtures[dataset_name]
        
        dataset_info = fixtures["dataset_info"]
        data_dir = fixtures["data_dir"]
        
        # Test first asset as representative
        if not dataset_info.get("assets"):
            pytest.skip(f"No assets defined for dataset {dataset_name}")
        
        asset = dataset_info["assets"][0]
        csv_file = data_dir / asset["csv_file"]
        if not csv_file.exists():
            pytest.skip(f"CSV file {asset['csv_file']} not found")
        
        # Create job config
        job_config_path = job_config_factory(
            dataset_name=dataset_name,
            asset_name=asset["name"],
            csv_file=csv_file,
            object_name=asset["object"]
        )
        
        # Load and validate
        job_config = JobConfig.from_yaml(job_config_path)
        
        # Validate all components
        job_config.validate_schema_presence()
        
        validator = ConnectorValidator(registry_path=test_registry)
        validator.validate_job(job_config, mode="self_hosted")
        
        # Verify resolved configs
        source_config = job_config.get_source()
        target_config = job_config.get_target()
        
        assert source_config.type == "csv"
        assert target_config.type == "iceberg"
        assert source_config.files[0]["file_path"] is not None
        assert Path(source_config.files[0]["file_path"]).exists()
        
        # Verify asset definition
        asset_path = job_config.get_asset_path()
        asset_def = AssetDefinition.from_yaml(asset_path)
        assert asset_def.schema is not None
        assert len(asset_def.schema) > 0
    
    def test_csv_connector_recipe_loads(self, csv_connector_recipe):
        """Test that CSV connector recipe loads correctly."""
        from dativo_ingest.config import SourceConnectorRecipe
        
        recipe = SourceConnectorRecipe.from_yaml(csv_connector_recipe)
        
        assert recipe.name == "csv"
        assert recipe.type == "csv"
        assert recipe.default_engine is not None
        assert recipe.default_engine["type"] == "native"
        assert recipe.credentials["type"] == "none"
        assert recipe.incremental is not None
        assert recipe.incremental["strategy"] == "file_modified_time"
    
    def test_csv_connector_registry_entry(self, test_registry):
        """Test that CSV connector is registered correctly."""
        validator = ConnectorValidator(registry_path=test_registry)
        
        connector_def = validator.validate_connector_type("csv")
        
        assert connector_def["category"] == "files"
        assert connector_def["default_engine"] == "native"
        assert connector_def["allowed_in_cloud"] is True
        assert connector_def["supports_incremental"] is True
        assert connector_def["incremental_strategy_default"] == "file_modified_time"


def pytest_addoption(parser):
    """Add custom command line options."""
    parser.addoption(
        "--dataset",
        action="store",
        default=None,
        help="Select specific dataset to test (adventureworks, music_listening, employee)"
    )


def pytest_configure(config):
    """Register custom markers."""
    for dataset_name in get_available_datasets():
        config.addinivalue_line("markers", f"{dataset_name}: mark test to run with {dataset_name} dataset")
