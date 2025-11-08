#!/usr/bin/env python3
"""Helper script to generate example job configurations for smoke tests.

This script creates example job configurations based on the datasets.yaml file.
Run this script to populate tests/fixtures/jobs/ with example jobs before running
the startup sequence.

Usage:
    python tests/fixtures/jobs/generate_example_jobs.py
"""

import yaml
from pathlib import Path

# Project root (assuming script is in tests/fixtures/jobs/)
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
DATASETS_YAML = PROJECT_ROOT / "tests" / "fixtures" / "datasets.yaml"
JOBS_DIR = PROJECT_ROOT / "tests" / "fixtures" / "jobs"
ASSETS_DIR = PROJECT_ROOT / "tests" / "fixtures" / "assets" / "csv" / "v1.0"
SEEDS_DIR = PROJECT_ROOT / "tests" / "fixtures" / "seeds"


def generate_job_config(dataset_name: str, asset_info: dict) -> dict:
    """Generate a job configuration for a dataset asset."""
    asset_name = asset_info["name"]
    csv_file = asset_info["csv_file"]
    asset_file = asset_info.get("asset_file", f"{asset_name}.yaml")
    object_name = asset_info.get("object", asset_name)
    
    # Construct paths relative to project root
    csv_path = f"tests/fixtures/seeds/{dataset_name}/{csv_file}"
    asset_path = f"tests/fixtures/assets/csv/v1.0/{asset_file}"
    
    return {
        "tenant_id": "test_tenant",
        "environment": "test",
        "source_connector": "csv",
        "source_connector_path": "connectors/csv.yaml",
        "target_connector": "iceberg",
        "target_connector_path": "connectors/iceberg.yaml",
        "asset": asset_name,
        "asset_path": asset_path,
        "source": {
            "files": [
                {
                    "file_path": csv_path,
                    "object": object_name
                }
            ]
        },
        "target": {
            "branch": "test_tenant",
            "warehouse": f"s3://test-lake/{dataset_name}/",
            "connection": {
                "nessie": {
                    "uri": "${NESSIE_URI}"
                },
                "s3": {
                    "endpoint": "${S3_ENDPOINT}",
                    "bucket": "test-bucket",
                    "access_key_id": "${AWS_ACCESS_KEY_ID}",
                    "secret_access_key": "${AWS_SECRET_ACCESS_KEY}",
                    "region": "${AWS_REGION}",
                    "path_style_access": True
                }
            }
        },
        "infrastructure": {
            "provider": "aws",
            "region": "us-east-1",
            "runtime": {"type": "aws_fargate"},
            "resource_identifiers": {
                "cluster_name": "{{terraform_outputs.cluster_name}}",
                "service_name": "{{terraform_outputs.service_name}}"
            },
            "tags": {
                "job_name": f"{dataset_name}_{asset_name}_runtime",
                "team": "data_platform",
                "pipeline_type": "ingestion",
                "environment": "test",
                "cost_center": "FINOPS-TEST"
            }
        },
        "logging": {
            "redaction": False,
            "level": "INFO"
        }
    }


def main():
    """Generate example job configurations."""
    # Load datasets configuration
    with open(DATASETS_YAML, "r") as f:
        datasets_config = yaml.safe_load(f)
    
    datasets = datasets_config.get("datasets", {})
    
    # Generate jobs for each dataset asset
    generated = 0
    skipped = 0
    
    for dataset_name, dataset_info in datasets.items():
        assets = dataset_info.get("assets", [])
        
        for asset_info in assets:
            asset_name = asset_info["name"]
            asset_file = asset_info.get("asset_file", f"{asset_name}.yaml")
            
            # Check if asset file exists
            asset_path = ASSETS_DIR / asset_file
            if not asset_path.exists():
                print(f"⚠️  Skipping {dataset_name}/{asset_name}: asset file not found ({asset_path})")
                skipped += 1
                continue
            
            # Generate job config
            job_config = generate_job_config(dataset_name, asset_info)
            
            # Write job file
            job_filename = f"{dataset_name}_{asset_name}_to_iceberg.yaml"
            job_path = JOBS_DIR / job_filename
            
            with open(job_path, "w") as f:
                yaml.dump(job_config, f, default_flow_style=False, sort_keys=False)
            
            print(f"✅ Generated: {job_filename}")
            generated += 1
    
    print(f"\n📊 Summary: {generated} jobs generated, {skipped} skipped")
    print(f"📁 Jobs directory: {JOBS_DIR}")


if __name__ == "__main__":
    main()

