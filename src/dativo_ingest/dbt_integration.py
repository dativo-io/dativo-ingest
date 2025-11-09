"""DBT integration for generating dbt-compatible YAML from ODCS contracts."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .config import AssetDefinition
from .logging import get_logger


class DBTGenerator:
    """Generates dbt-compatible YAML from ODCS asset definitions."""

    def __init__(self, output_dir: Optional[Path] = None):
        """Initialize DBT generator.

        Args:
            output_dir: Output directory for dbt YAML files (default: /dbt)
        """
        self.output_dir = output_dir or Path("/dbt")
        self.logger = get_logger()

    def _map_odcs_type_to_dbt(self, odcs_type: str) -> str:
        """Map ODCS type to dbt column type.

        Args:
            odcs_type: ODCS type string

        Returns:
            DBT-compatible type string
        """
        type_mapping = {
            "string": "string",
            "integer": "integer",
            "float": "float",
            "double": "float",
            "boolean": "boolean",
            "date": "date",
            "timestamp": "timestamp",
            "datetime": "timestamp",
        }
        return type_mapping.get(odcs_type, "string")

    def generate_source_yaml(
        self, asset: AssetDefinition, catalog_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate dbt source YAML from asset definition.

        Args:
            asset: Asset definition
            catalog_name: Optional catalog name override

        Returns:
            DBT source configuration dictionary
        """
        # Build column definitions
        columns = []
        for field in asset.schema:
            column = {
                "name": field.get("name"),
                "description": field.get("description", ""),
                "data_type": self._map_odcs_type_to_dbt(field.get("type", "string")),
            }
            
            # Add data tests based on field properties
            tests = []
            if field.get("required", False):
                tests.append("not_null")
            if field.get("unique", False):
                tests.append("unique")
            
            if tests:
                column["tests"] = tests
            
            # Add classification tags
            tags = []
            if field.get("classification"):
                tags.append(field["classification"].lower())
            if tags:
                column["tags"] = tags
            
            columns.append(column)
        
        # Build source configuration
        source_config = {
            "name": asset.object,
            "description": (
                asset.description.purpose
                if asset.description and asset.description.purpose
                else f"Source table for {asset.object}"
            ),
            "tables": [
                {
                    "name": asset.object,
                    "description": (
                        asset.description.usage
                        if asset.description and asset.description.usage
                        else ""
                    ),
                    "columns": columns,
                }
            ],
        }
        
        # Add metadata
        meta = {
            "owner": asset.team.owner if asset.team else "unknown",
            "contract_version": asset.version,
            "odcs_version": asset.apiVersion,
        }
        
        # Add governance metadata
        if asset.compliance:
            if asset.compliance.classification:
                meta["classification"] = asset.compliance.classification
            if asset.compliance.retention_days:
                meta["retention_days"] = asset.compliance.retention_days
            if asset.compliance.regulations:
                meta["regulations"] = asset.compliance.regulations
        
        source_config["tables"][0]["meta"] = meta
        
        # Add tags at table level
        tags = asset.tags or []
        if asset.compliance and asset.compliance.classification:
            tags.extend([c.lower() for c in asset.compliance.classification])
        if tags:
            source_config["tables"][0]["tags"] = list(set(tags))
        
        return {
            "version": 2,
            "sources": [
                {
                    "name": catalog_name or asset.source_type,
                    "description": f"{asset.source_type} data source",
                    "tables": [source_config],
                }
            ],
        }

    def generate_model_yaml(
        self, asset: AssetDefinition, model_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """Generate dbt model YAML from asset definition.

        Args:
            asset: Asset definition
            model_name: Optional model name override

        Returns:
            DBT model configuration dictionary
        """
        model_name = model_name or f"stg_{asset.object}"
        
        # Build column definitions
        columns = []
        for field in asset.schema:
            column = {
                "name": field.get("name"),
                "description": field.get("description", ""),
                "data_type": self._map_odcs_type_to_dbt(field.get("type", "string")),
            }
            
            # Add data tests
            tests = []
            if field.get("required", False):
                tests.append("not_null")
            if field.get("unique", False):
                tests.append("unique")
            
            # Add dbt-specific tests from data_quality
            if asset.data_quality and asset.data_quality.expectations:
                for expectation in asset.data_quality.expectations:
                    if expectation.get("column") == field.get("name"):
                        test_type = expectation.get("type")
                        if test_type == "accepted_values":
                            tests.append(
                                {
                                    "accepted_values": {
                                        "values": expectation.get("values", [])
                                    }
                                }
                            )
                        elif test_type == "relationships":
                            tests.append(
                                {
                                    "relationships": {
                                        "to": expectation.get("to"),
                                        "field": expectation.get("field"),
                                    }
                                }
                            )
            
            if tests:
                column["tests"] = tests
            
            # Add classification tags
            tags = []
            if field.get("classification"):
                tags.append(field["classification"].lower())
            if tags:
                column["tags"] = tags
            
            columns.append(column)
        
        # Build model metadata
        meta = {
            "owner": asset.team.owner if asset.team else "unknown",
            "contract_version": asset.version,
            "contract_id": asset.id,
        }
        
        if asset.compliance:
            if asset.compliance.classification:
                meta["classification"] = asset.compliance.classification
            if asset.compliance.retention_days:
                meta["retention_days"] = asset.compliance.retention_days
        
        # Add data quality monitoring config
        if asset.data_quality and asset.data_quality.monitoring:
            meta["monitoring"] = {
                "enabled": asset.data_quality.monitoring.enabled,
            }
            if asset.data_quality.monitoring.oncall_rotation:
                meta["monitoring"]["oncall"] = (
                    asset.data_quality.monitoring.oncall_rotation
                )
        
        # Build model config
        model_config = {
            "name": model_name,
            "description": (
                asset.description.purpose
                if asset.description and asset.description.purpose
                else f"Staging model for {asset.object}"
            ),
            "columns": columns,
            "meta": meta,
        }
        
        # Add tags
        tags = asset.tags or []
        if asset.compliance and asset.compliance.classification:
            tags.extend([c.lower() for c in asset.compliance.classification])
        if tags:
            model_config["tags"] = list(set(tags))
        
        return {
            "version": 2,
            "models": [model_config],
        }

    def generate_exposure_yaml(
        self,
        asset: AssetDefinition,
        exposure_name: str,
        exposure_type: str = "dashboard",
        depends_on: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate dbt exposure YAML from asset definition.

        Args:
            asset: Asset definition
            exposure_name: Name of the exposure
            exposure_type: Type of exposure (dashboard, notebook, ml, etc.)
            depends_on: List of model dependencies

        Returns:
            DBT exposure configuration dictionary
        """
        exposure_config = {
            "name": exposure_name,
            "type": exposure_type,
            "description": (
                asset.description.usage
                if asset.description and asset.description.usage
                else f"Exposure for {asset.object}"
            ),
            "owner": {
                "name": asset.team.owner if asset.team else "unknown",
                "email": asset.team.owner if asset.team else "unknown@example.com",
            },
        }
        
        # Add dependencies
        if depends_on:
            exposure_config["depends_on"] = [
                f"ref('{model}')" for model in depends_on
            ]
        
        # Add metadata
        meta = {
            "contract_version": asset.version,
            "contract_id": asset.id,
        }
        
        if asset.compliance:
            if asset.compliance.classification:
                meta["classification"] = asset.compliance.classification
        
        exposure_config["meta"] = meta
        
        # Add tags
        tags = asset.tags or []
        if tags:
            exposure_config["tags"] = tags
        
        return {
            "version": 2,
            "exposures": [exposure_config],
        }

    def save_dbt_yaml(
        self,
        asset: AssetDefinition,
        yaml_type: str = "source",
        catalog_name: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> Path:
        """Save dbt YAML file for asset.

        Args:
            asset: Asset definition
            yaml_type: Type of YAML ('source', 'model', 'exposure')
            catalog_name: Optional catalog name for sources
            model_name: Optional model name for models

        Returns:
            Path to saved YAML file

        Raises:
            ValueError: If yaml_type is invalid
        """
        # Generate YAML based on type
        if yaml_type == "source":
            yaml_content = self.generate_source_yaml(asset, catalog_name)
            subdir = "models/staging"
            filename = f"{asset.source_type}__{asset.object}.yml"
        elif yaml_type == "model":
            yaml_content = self.generate_model_yaml(asset, model_name)
            subdir = "models/staging"
            filename = f"stg_{asset.object}.yml"
        elif yaml_type == "exposure":
            yaml_content = self.generate_exposure_yaml(
                asset, f"{asset.object}_dashboard"
            )
            subdir = "models/marts"
            filename = f"{asset.object}_exposure.yml"
        else:
            raise ValueError(
                f"Invalid yaml_type: {yaml_type}. Expected 'source', 'model', or 'exposure'"
            )
        
        # Create output directory
        output_path = self.output_dir / subdir
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Save YAML file
        file_path = output_path / filename
        with open(file_path, "w") as f:
            yaml.dump(yaml_content, f, default_flow_style=False, sort_keys=False)
        
        self.logger.info(
            f"DBT YAML saved: {file_path}",
            extra={
                "event_type": "dbt_yaml_saved",
                "yaml_type": yaml_type,
                "asset": asset.name,
            },
        )
        
        return file_path

    def generate_dbt_project_yml(
        self, project_name: str, profile_name: str = "default"
    ) -> Dict[str, Any]:
        """Generate dbt_project.yml configuration.

        Args:
            project_name: Name of the dbt project
            profile_name: Name of the dbt profile

        Returns:
            DBT project configuration dictionary
        """
        return {
            "name": project_name,
            "version": "1.0.0",
            "config-version": 2,
            "profile": profile_name,
            "model-paths": ["models"],
            "analysis-paths": ["analyses"],
            "test-paths": ["tests"],
            "seed-paths": ["seeds"],
            "macro-paths": ["macros"],
            "snapshot-paths": ["snapshots"],
            "target-path": "target",
            "clean-targets": ["target", "dbt_packages"],
            "models": {
                project_name: {
                    "staging": {
                        "+materialized": "view",
                        "+tags": ["staging"],
                    },
                    "marts": {
                        "+materialized": "table",
                        "+tags": ["marts"],
                    },
                }
            },
        }

    def generate_schema_test(
        self, asset: AssetDefinition
    ) -> str:
        """Generate dbt schema test SQL.

        Args:
            asset: Asset definition

        Returns:
            SQL test string
        """
        tests = []
        
        # Generate tests for each field
        for field in asset.schema:
            field_name = field.get("name")
            
            # Required field test
            if field.get("required", False):
                tests.append(
                    f"-- Test: {field_name} should not be null\n"
                    f"select count(*) as failures\n"
                    f"from {{{{ ref('stg_{asset.object}') }}}}\n"
                    f"where {field_name} is null"
                )
            
            # Unique field test
            if field.get("unique", False):
                tests.append(
                    f"-- Test: {field_name} should be unique\n"
                    f"select {field_name}, count(*) as n_records\n"
                    f"from {{{{ ref('stg_{asset.object}') }}}}\n"
                    f"group by {field_name}\n"
                    f"having count(*) > 1"
                )
        
        return "\n\n".join(tests)
