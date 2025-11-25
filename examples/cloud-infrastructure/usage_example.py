#!/usr/bin/env python3
"""
Usage example for Dativo cloud infrastructure integration.

This script demonstrates:
1. Loading job configuration with infrastructure block
2. Initializing infrastructure manager (AWS or GCP)
3. Validating infrastructure
4. Generating Terraform variables
5. Applying tags/labels to resources
6. Exporting Terraform outputs

Run:
    python examples/cloud-infrastructure/usage_example.py
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from dativo_ingest.config import JobConfig, AssetDefinition
from dativo_ingest.cloud_infrastructure import (
    AWSInfrastructureManager,
    GCPInfrastructureManager,
)


def main():
    """Main entry point for infrastructure integration example."""
    
    print("=" * 80)
    print("Dativo Cloud Infrastructure Integration - Usage Example")
    print("=" * 80)
    print()
    
    # Example 1: AWS EMR Infrastructure
    print("Example 1: AWS EMR Infrastructure")
    print("-" * 80)
    
    # Load job configuration
    aws_job_path = Path(__file__).parent / "aws-emr-complete.yaml"
    if aws_job_path.exists():
        print(f"✓ Loading job config: {aws_job_path}")
        job_config = JobConfig.from_yaml(str(aws_job_path))
        
        # Load asset definition
        print(f"✓ Loading asset: {job_config.asset_path}")
        # Note: Would need actual asset file in production
        # asset = AssetDefinition.from_yaml(job_config.get_asset_path())
        
        # For demo purposes, create mock asset
        from dativo_ingest.config import TeamModel
        asset = AssetDefinition(
            name="postgres_orders",
            version="1.0",
            status="active",
            source_type="postgres",
            object="orders",
            schema=[{"name": "id", "type": "integer"}],
            team=TeamModel(owner="data-team@acme.com"),
        )
        
        # Initialize AWS infrastructure manager
        print("✓ Initializing AWS Infrastructure Manager")
        aws_manager = AWSInfrastructureManager(job_config, asset)
        
        # Log infrastructure context
        print("\nInfrastructure Context:")
        print(f"  Tenant: {aws_manager.context.tenant_id}")
        print(f"  Environment: {aws_manager.context.environment}")
        print(f"  Provider: {aws_manager.context.provider}")
        print(f"  Platform: {aws_manager.context.platform}")
        print(f"  Cluster ID: {aws_manager.context.cluster_id}")
        print(f"  Tags: {len(aws_manager.context.tags)} tags")
        
        # Display some key tags
        print("\nKey Tags:")
        for key in ["TenantId", "Environment", "CostCenter", "Platform"]:
            if key in aws_manager.context.tags:
                print(f"  {key}: {aws_manager.context.tags[key]}")
        
        # Generate Terraform variables
        print("\n✓ Generating Terraform variables...")
        tf_vars = aws_manager.get_terraform_variables()
        print(f"  Generated {len(tf_vars)} Terraform variables")
        print(f"  Sample variables:")
        for key in ["tenant_id", "environment", "instance_type", "instance_count"]:
            if key in tf_vars:
                print(f"    {key}: {tf_vars[key]}")
        
        # Generate tfvars file (to temp location for demo)
        output_dir = Path("/tmp/dativo-terraform")
        output_dir.mkdir(exist_ok=True)
        tfvars_path = output_dir / "aws-dativo.auto.tfvars"
        
        print(f"\n✓ Writing Terraform tfvars to: {tfvars_path}")
        aws_manager.generate_terraform_tfvars(str(tfvars_path))
        
        # Export outputs
        outputs_path = output_dir / "aws-outputs.json"
        print(f"✓ Exporting Terraform outputs to: {outputs_path}")
        aws_manager.export_terraform_outputs(str(outputs_path))
        
        print("\n✅ AWS infrastructure integration complete!")
    else:
        print(f"⚠️  Example file not found: {aws_job_path}")
    
    print()
    print("=" * 80)
    print()
    
    # Example 2: GCP GKE Infrastructure
    print("Example 2: GCP GKE Infrastructure")
    print("-" * 80)
    
    gcp_job_path = Path(__file__).parent / "gcp-gke-complete.yaml"
    if gcp_job_path.exists():
        print(f"✓ Loading job config: {gcp_job_path}")
        job_config = JobConfig.from_yaml(str(gcp_job_path))
        
        # Create mock asset for demo
        asset = AssetDefinition(
            name="stripe_customers",
            version="1.0",
            status="active",
            source_type="stripe",
            object="customers",
            schema=[{"name": "id", "type": "string"}],
            team=TeamModel(owner="payments-team@acme.com"),
        )
        
        # Initialize GCP infrastructure manager
        print("✓ Initializing GCP Infrastructure Manager")
        gcp_manager = GCPInfrastructureManager(job_config, asset)
        
        # Log infrastructure context
        print("\nInfrastructure Context:")
        print(f"  Tenant: {gcp_manager.context.tenant_id}")
        print(f"  Environment: {gcp_manager.context.environment}")
        print(f"  Provider: {gcp_manager.context.provider}")
        print(f"  Platform: {gcp_manager.context.platform}")
        print(f"  Namespace: {gcp_manager.context.labels.get('component', 'N/A')}")
        print(f"  Tags: {len(gcp_manager.context.tags)} tags")
        
        # Display converted labels (GCP format)
        print("\nConverted GCP Labels (sample):")
        labels = gcp_manager._convert_tags_to_labels(
            {k: v for k, v in list(gcp_manager.context.tags.items())[:5]}
        )
        for key, value in labels.items():
            print(f"  {key}: {value}")
        
        # Generate Terraform variables
        print("\n✓ Generating Terraform variables...")
        tf_vars = gcp_manager.get_terraform_variables()
        print(f"  Generated {len(tf_vars)} Terraform variables")
        print(f"  Sample variables:")
        for key in ["tenant_id", "environment", "machine_type", "node_count"]:
            if key in tf_vars:
                print(f"    {key}: {tf_vars[key]}")
        
        # Generate tfvars file
        output_dir = Path("/tmp/dativo-terraform")
        output_dir.mkdir(exist_ok=True)
        tfvars_path = output_dir / "gcp-dativo.auto.tfvars"
        
        print(f"\n✓ Writing Terraform tfvars to: {tfvars_path}")
        gcp_manager.generate_terraform_tfvars(str(tfvars_path))
        
        # Export outputs
        outputs_path = output_dir / "gcp-outputs.json"
        print(f"✓ Exporting Terraform outputs to: {outputs_path}")
        gcp_manager.export_terraform_outputs(str(outputs_path))
        
        print("\n✅ GCP infrastructure integration complete!")
    else:
        print(f"⚠️  Example file not found: {gcp_job_path}")
    
    print()
    print("=" * 80)
    print("\n📖 Next Steps:")
    print("  1. Review generated tfvars files in /tmp/dativo-terraform/")
    print("  2. Review Terraform output files in /tmp/dativo-terraform/")
    print("  3. Apply Terraform configuration:")
    print("     cd terraform/aws/emr-dativo && terraform apply")
    print("     cd terraform/gcp/gke-dativo && terraform apply")
    print("  4. Run Dativo job with provisioned infrastructure")
    print()
    print("=" * 80)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)
