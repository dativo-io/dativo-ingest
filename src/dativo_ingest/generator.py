"""Interactive generator for jobs and asset definitions."""

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any
import yaml


class ConnectorRegistry:
    """Load and query the connector registry."""
    
    def __init__(self, registry_path: str = "/workspace/registry/connectors.yaml"):
        """Initialize registry from YAML file."""
        with open(registry_path) as f:
            data = yaml.safe_load(f)
            self.connectors = data.get("connectors", {})
    
    def get_connector(self, name: str) -> Optional[Dict]:
        """Get connector metadata by name."""
        return self.connectors.get(name)
    
    def list_source_connectors(self) -> List[str]:
        """List all connectors that can be used as sources."""
        return [
            name for name, config in self.connectors.items()
            if "source" in config.get("roles", [])
        ]
    
    def list_target_connectors(self) -> List[str]:
        """List all connectors that can be used as targets."""
        return [
            name for name, config in self.connectors.items()
            if "target" in config.get("roles", [])
        ]
    
    def get_connector_details(self, name: str) -> str:
        """Get formatted connector details for display."""
        connector = self.get_connector(name)
        if not connector:
            return f"Unknown connector: {name}"
        
        details = [f"\n{name.upper()} Connector:"]
        details.append(f"  Category: {connector.get('category', 'N/A')}")
        details.append(f"  Roles: {', '.join(connector.get('roles', []))}")
        details.append(f"  Default Engine: {connector.get('default_engine', 'N/A')}")
        details.append(f"  Cloud Allowed: {connector.get('allowed_in_cloud', 'N/A')}")
        details.append(f"  Incremental Support: {connector.get('supports_incremental', False)}")
        
        if connector.get('supports_incremental'):
            details.append(f"  Incremental Strategy: {connector.get('incremental_strategy_default', 'N/A')}")
        
        if connector.get('objects_supported'):
            details.append(f"  Objects Supported: {', '.join(connector.get('objects_supported', []))}")
        
        if connector.get('requires_tables'):
            details.append(f"  Requires Tables: {connector.get('requires_tables')}")
        
        if connector.get('supports_queries'):
            details.append(f"  Supports Queries: {connector.get('supports_queries')}")
        
        return "\n".join(details)


class ConnectorRecipeLoader:
    """Load connector recipe (full configuration) from connectors directory."""
    
    def __init__(self, connectors_dir: str = "/workspace/connectors"):
        self.connectors_dir = Path(connectors_dir)
    
    def load_recipe(self, connector_name: str) -> Optional[Dict]:
        """Load full connector recipe YAML."""
        recipe_path = self.connectors_dir / f"{connector_name}.yaml"
        if recipe_path.exists():
            with open(recipe_path) as f:
                return yaml.safe_load(f)
        return None
    
    def get_credentials_info(self, connector_name: str) -> Dict:
        """Get credentials information from recipe."""
        recipe = self.load_recipe(connector_name)
        if recipe and "credentials" in recipe:
            return recipe["credentials"]
        return {}
    
    def get_connection_template(self, connector_name: str) -> Dict:
        """Get connection template from recipe."""
        recipe = self.load_recipe(connector_name)
        if recipe and "connection_template" in recipe:
            return recipe["connection_template"]
        return {}
    
    def get_default_engine_options(self, connector_name: str) -> Dict:
        """Get default engine options from recipe."""
        recipe = self.load_recipe(connector_name)
        if recipe and "default_engine" in recipe:
            return recipe["default_engine"].get("options", {})
        return {}


class InteractiveGenerator:
    """Interactive generator for jobs and assets."""
    
    def __init__(self):
        self.registry = ConnectorRegistry()
        self.recipe_loader = ConnectorRecipeLoader()
    
    def prompt(self, message: str, default: Optional[str] = None) -> str:
        """Prompt user for input with optional default."""
        if default:
            message = f"{message} [{default}]"
        response = input(f"{message}: ").strip()
        return response if response else (default or "")
    
    def prompt_choice(self, message: str, choices: List[str], default: Optional[str] = None) -> str:
        """Prompt user to select from a list of choices."""
        print(f"\n{message}")
        for i, choice in enumerate(choices, 1):
            marker = "*" if choice == default else " "
            print(f"  {marker} {i}. {choice}")
        
        while True:
            response = input(f"\nEnter number (1-{len(choices)})" + (f" [{choices.index(default) + 1}]" if default else "") + ": ").strip()
            
            if not response and default:
                return default
            
            try:
                idx = int(response) - 1
                if 0 <= idx < len(choices):
                    return choices[idx]
            except ValueError:
                pass
            
            print(f"Invalid choice. Please enter a number between 1 and {len(choices)}.")
    
    def prompt_yes_no(self, message: str, default: bool = False) -> bool:
        """Prompt user for yes/no question."""
        default_str = "Y/n" if default else "y/N"
        response = input(f"{message} [{default_str}]: ").strip().lower()
        
        if not response:
            return default
        
        return response in ["y", "yes"]
    
    def generate_asset(self, source_connector: str, tenant_id: str) -> Dict:
        """Generate asset definition interactively."""
        print("\n" + "=" * 80)
        print("ASSET DEFINITION GENERATION")
        print("=" * 80)
        
        connector_info = self.registry.get_connector(source_connector)
        print(self.registry.get_connector_details(source_connector))
        
        # Basic asset information
        print("\n--- Basic Information ---")
        asset_name = self.prompt("Asset name (e.g., stripe_customers, postgres_orders)")
        
        # Suggest object based on connector's supported objects
        object_name = None
        if connector_info and connector_info.get("objects_supported"):
            objects = connector_info["objects_supported"]
            if len(objects) == 1:
                object_name = self.prompt("Object/table name", default=objects[0])
            else:
                print(f"\nSupported objects for {source_connector}: {', '.join(objects)}")
                object_name = self.prompt("Object/table name")
        else:
            object_name = self.prompt("Object/table/file name")
        
        version = self.prompt("Version", default="1.0")
        
        # Schema definition
        print("\n--- Schema Definition ---")
        print("Define the schema fields for this asset.")
        print("Common field types: string, integer, bigint, double, boolean, date, timestamp")
        
        schema_fields = []
        
        # Suggest common fields based on connector type
        if source_connector in ["stripe", "hubspot"]:
            # API connectors typically have id, created, updated fields
            print("\nSuggested starter fields (you can customize):")
            if self.prompt_yes_no("Add 'id' field (string, required)?", default=True):
                schema_fields.append({
                    "name": "id",
                    "type": "string",
                    "required": True
                })
        
        if source_connector in ["postgres", "mysql"]:
            # Database connectors typically have primary key and timestamps
            print("\nSuggested starter fields:")
            if self.prompt_yes_no("Add 'id' field (bigint, required)?", default=True):
                schema_fields.append({
                    "name": "id",
                    "type": "bigint",
                    "required": True
                })
            
            # Check if incremental is supported
            if connector_info and connector_info.get("supports_incremental"):
                cursor_field = connector_info.get("incremental_strategy_default", "updated_at")
                if self.prompt_yes_no(f"Add '{cursor_field}' field for incremental sync (timestamp)?", default=True):
                    schema_fields.append({
                        "name": cursor_field,
                        "type": "timestamp",
                        "required": True
                    })
        
        # Add custom fields
        print("\nAdd additional fields (press Enter with empty name to finish):")
        while True:
            field_name = self.prompt("\nField name").strip()
            if not field_name:
                break
            
            field_type = self.prompt_choice(
                "Field type",
                ["string", "integer", "bigint", "double", "boolean", "date", "timestamp"],
                default="string"
            )
            
            required = self.prompt_yes_no("Required?", default=False)
            
            field = {
                "name": field_name,
                "type": field_type,
                "required": required
            }
            
            # Ask about classification for potentially sensitive fields
            if any(keyword in field_name.lower() for keyword in ["email", "phone", "name", "address", "ssn"]):
                if self.prompt_yes_no("Mark as PII?", default=True):
                    field["classification"] = "PII"
            elif any(keyword in field_name.lower() for keyword in ["salary", "income", "credit", "balance"]):
                if self.prompt_yes_no("Mark as SENSITIVE?", default=True):
                    field["classification"] = "SENSITIVE"
            
            schema_fields.append(field)
        
        # Governance
        print("\n--- Governance ---")
        owner = self.prompt("Owner email", default=f"data-team@{tenant_id}.com")
        tags_str = self.prompt("Tags (comma-separated)", default=f"{source_connector}, {object_name}")
        tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
        
        # Check if any fields have classifications
        classifications = set()
        for field in schema_fields:
            if "classification" in field:
                classifications.add(field["classification"])
        
        retention_days = int(self.prompt("Retention days", default="90"))
        
        # Target configuration
        print("\n--- Target Configuration ---")
        file_format = self.prompt_choice(
            "File format",
            ["parquet"],
            default="parquet"
        )
        
        partitioning_str = self.prompt("Partitioning columns (comma-separated)", default="ingest_date")
        partitioning = [p.strip() for p in partitioning_str.split(",") if p.strip()]
        
        mode = self.prompt_choice(
            "Schema evolution mode",
            ["strict", "merge", "relaxed"],
            default="strict"
        )
        
        # Build asset definition
        asset = {
            "asset": {
                "name": asset_name,
                "source_type": source_connector,
                "object": object_name,
                "version": version,
                "schema": schema_fields,
                "governance": {
                    "owner": owner,
                    "tags": tags,
                    "retention_days": retention_days
                },
                "target": {
                    "file_format": file_format,
                    "partitioning": partitioning,
                    "mode": mode
                }
            }
        }
        
        # Add classifications if any
        if classifications:
            asset["asset"]["governance"]["classification"] = sorted(list(classifications))
        
        return asset
    
    def generate_job(self, asset_name: str, asset_path: str, source_connector: str, tenant_id: str) -> Dict:
        """Generate job configuration interactively."""
        print("\n" + "=" * 80)
        print("JOB CONFIGURATION GENERATION")
        print("=" * 80)
        
        connector_info = self.registry.get_connector(source_connector)
        
        # Basic job info
        print("\n--- Basic Information ---")
        environment = self.prompt_choice(
            "Environment",
            ["dev", "staging", "prod"],
            default="dev"
        )
        
        # Source configuration
        print("\n--- Source Configuration ---")
        source_config = {}
        
        # Objects configuration (for API connectors)
        if connector_info and connector_info.get("objects_supported"):
            object_name = asset_path.split("/")[-1].replace(".yaml", "")
            # Extract object from asset_name (e.g., stripe_customers -> customers)
            suggested_object = object_name.split("_")[-1]
            objects_str = self.prompt("Objects to sync (comma-separated)", default=suggested_object)
            source_config["objects"] = [obj.strip() for obj in objects_str.split(",")]
        
        # Tables configuration (for database connectors)
        if connector_info and connector_info.get("requires_tables"):
            print("\nDatabase table configuration:")
            table_name = self.prompt("Table name (e.g., public.orders)")
            object_name = self.prompt("Object name", default=table_name.split(".")[-1])
            
            tables = [{
                "name": table_name,
                "object": object_name
            }]
            
            # Add cursor field if incremental is supported
            if connector_info.get("supports_incremental"):
                cursor_field = connector_info.get("incremental_strategy_default", "updated_at")
                cursor = self.prompt("Cursor field for incremental sync", default=cursor_field)
                tables[0]["cursor_field"] = cursor
            
            source_config["tables"] = tables
        
        # Incremental sync configuration
        if connector_info and connector_info.get("supports_incremental"):
            if self.prompt_yes_no("\nEnable incremental sync?", default=True):
                lookback_days = int(self.prompt("Lookback days", default="1"))
                source_config["incremental"] = {"lookback_days": lookback_days}
        
        # Connection configuration (for database connectors)
        if connector_info and connector_info.get("category") == "database":
            if self.prompt_yes_no("\nConfigure database connection?", default=True):
                connection_template = self.recipe_loader.get_connection_template(source_connector)
                connection = {}
                
                if connection_template:
                    print(f"\nConnection template: {connection_template}")
                    for key, value in connection_template.items():
                        # Check if it's an env var reference
                        if isinstance(value, str) and value.startswith("${"):
                            # Keep the env var reference
                            connection[key] = value
                        else:
                            # Prompt for value
                            connection[key] = self.prompt(f"{key}", default=str(value))
                else:
                    # Manual configuration
                    host = self.prompt("Host", default="${PGHOST}" if source_connector == "postgres" else "${MYSQL_HOST}")
                    port = self.prompt("Port", default="${PGPORT}" if source_connector == "postgres" else "${MYSQL_PORT}")
                    database = self.prompt("Database", default="${PGDATABASE}" if source_connector == "postgres" else "${MYSQL_DATABASE}")
                    
                    connection = {
                        "host": host,
                        "port": port,
                        "database": database
                    }
                
                source_config["connection"] = connection
        
        # Target configuration
        print("\n--- Target Configuration ---")
        print("\nAvailable target connectors:")
        target_connectors = self.registry.list_target_connectors()
        print(f"  {', '.join(target_connectors)}")
        
        target_connector = self.prompt_choice(
            "\nSelect target connector",
            target_connectors,
            default="iceberg" if "iceberg" in target_connectors else target_connectors[0]
        )
        
        target_config = {}
        
        # Branch configuration
        branch = self.prompt("Target branch", default=tenant_id)
        target_config["branch"] = branch
        
        # Warehouse path
        warehouse = self.prompt("Warehouse path", default=f"s3://lake/{tenant_id}/")
        target_config["warehouse"] = warehouse
        
        # Connection configuration for target
        if self.prompt_yes_no("\nConfigure target connection?", default=True):
            connection = {}
            
            # S3/MinIO configuration
            bucket = self.prompt("S3/MinIO bucket", default=f"{tenant_id}-data-lake")
            prefix = self.prompt("S3 prefix", default=f"raw/{source_connector}/{asset_name}")
            
            connection["s3"] = {
                "bucket": bucket,
                "prefix": prefix
            }
            
            # Catalog configuration (for Iceberg)
            if target_connector == "iceberg":
                if self.prompt_yes_no("Configure Nessie catalog?", default=True):
                    nessie_uri = self.prompt(
                        "Nessie URI",
                        default=f"http://nessie.{tenant_id}.internal:19120/api/v1"
                    )
                    connection["nessie"] = {"uri": nessie_uri}
            
            target_config["connection"] = connection
        
        # Logging configuration
        print("\n--- Logging Configuration ---")
        log_level = self.prompt_choice(
            "Log level",
            ["DEBUG", "INFO", "WARNING", "ERROR"],
            default="INFO"
        )
        
        redaction = self.prompt_yes_no("Enable log redaction?", default=True)
        
        # Build job configuration
        job = {
            "tenant_id": tenant_id,
            "environment": environment,
            "source_connector": source_connector,
            "source_connector_path": f"/app/connectors/{source_connector}.yaml",
            "target_connector": target_connector,
            "target_connector_path": f"/app/connectors/{target_connector}.yaml",
            "asset": asset_name,
            "asset_path": asset_path,
            "source": source_config,
            "target": target_config,
            "logging": {
                "redaction": redaction,
                "level": log_level
            }
        }
        
        return job
    
    def save_yaml(self, data: Dict, output_path: Path) -> None:
        """Save data to YAML file."""
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False, indent=2)
        
        print(f"\n✓ Saved to: {output_path}")
    
    def run(self) -> int:
        """Run interactive generator."""
        print("\n" + "=" * 80)
        print("DATIVO JOB & ASSET GENERATOR")
        print("=" * 80)
        print("\nThis interactive tool will guide you through creating:")
        print("  1. Asset definition (schema, governance, target config)")
        print("  2. Job configuration (source, target, scheduling)")
        
        # Tenant ID
        print("\n--- Tenant Configuration ---")
        tenant_id = self.prompt("Tenant ID (e.g., acme, corp)", default="acme")
        
        # Source connector selection
        print("\n--- Source Connector Selection ---")
        print("\nAvailable source connectors:")
        source_connectors = self.registry.list_source_connectors()
        
        for connector in source_connectors:
            print(f"\n{connector}:")
            info = self.registry.get_connector(connector)
            print(f"  Category: {info.get('category', 'N/A')}")
            print(f"  Incremental: {info.get('supports_incremental', False)}")
            if info.get("objects_supported"):
                print(f"  Objects: {', '.join(info['objects_supported'])}")
        
        source_connector = self.prompt_choice(
            "\nSelect source connector",
            source_connectors
        )
        
        # Generate asset
        asset_data = self.generate_asset(source_connector, tenant_id)
        asset_name = asset_data["asset"]["name"]
        
        # Determine asset save path
        print("\n--- Save Asset Definition ---")
        default_asset_dir = f"/workspace/assets/{source_connector}/v1.0"
        asset_dir = self.prompt("Asset directory", default=default_asset_dir)
        asset_filename = self.prompt("Asset filename", default=f"{asset_name}.yaml")
        asset_path = Path(asset_dir) / asset_filename
        
        # Save asset
        self.save_yaml(asset_data, asset_path)
        
        # Generate job
        job_asset_path = f"/app/assets/{source_connector}/v1.0/{asset_filename}"
        job_data = self.generate_job(asset_name, job_asset_path, source_connector, tenant_id)
        
        # Determine job save path
        print("\n--- Save Job Configuration ---")
        default_job_dir = f"/workspace/jobs/{tenant_id}"
        job_dir = self.prompt("Job directory", default=default_job_dir)
        job_filename = self.prompt("Job filename", default=f"{asset_name}_to_{job_data['target_connector']}.yaml")
        job_path = Path(job_dir) / job_filename
        
        # Save job
        self.save_yaml(job_data, job_path)
        
        # Summary
        print("\n" + "=" * 80)
        print("GENERATION COMPLETE!")
        print("=" * 80)
        print(f"\nAsset Definition: {asset_path}")
        print(f"Job Configuration: {job_path}")
        print("\nNext steps:")
        print(f"  1. Review and edit the generated files if needed")
        print(f"  2. Run the job: dativo run --config {job_path} --mode self_hosted")
        print(f"  3. Or add to orchestration: update configs/runner.yaml with schedule")
        
        return 0


def main() -> int:
    """Entry point for generator CLI."""
    try:
        generator = InteractiveGenerator()
        return generator.run()
    except KeyboardInterrupt:
        print("\n\nGenerator cancelled by user.")
        return 1
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 2


if __name__ == "__main__":
    sys.exit(main())
