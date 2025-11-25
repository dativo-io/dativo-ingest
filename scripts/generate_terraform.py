#!/usr/bin/env python3
"""Generate Terraform configurations from Dativo job definitions.

This script reads job configuration files and generates Terraform configurations
for AWS or GCP deployments with comprehensive tag propagation.
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import JobConfig
from dativo_ingest.infrastructure_terraform import TerraformGenerator


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate Terraform configurations from Dativo job definitions"
    )
    parser.add_argument(
        "job_config",
        type=str,
        help="Path to job configuration YAML file",
    )
    parser.add_argument(
        "--cloud",
        choices=["aws", "gcp"],
        default="aws",
        help="Cloud provider (default: aws)",
    )
    parser.add_argument(
        "--resource-type",
        choices=["ecs_fargate", "lambda", "cloud_run", "cloud_function"],
        default="ecs_fargate",
        help="Resource type (default: ecs_fargate)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="terraform",
        help="Output directory for Terraform files (default: terraform)",
    )
    parser.add_argument(
        "--format",
        choices=["hcl", "json"],
        default="hcl",
        help="Output format (default: hcl)",
    )

    args = parser.parse_args()

    # Load job configuration
    try:
        job_config = JobConfig.from_yaml(args.job_config, validate_schema=True)
    except Exception as e:
        print(f"ERROR: Failed to load job configuration: {e}", file=sys.stderr)
        sys.exit(1)

    # Check if infrastructure block is present
    if not job_config.infrastructure:
        print(
            "WARNING: No infrastructure block found in job configuration.",
            file=sys.stderr,
        )
        print(
            "Using default infrastructure settings.",
            file=sys.stderr,
        )

    # Generate Terraform configuration
    try:
        generator = TerraformGenerator(job_config, cloud_provider=args.cloud)

        # Determine output path
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Generate filename based on tenant and asset
        filename = f"{job_config.tenant_id}-{job_config.asset or 'job'}"
        output_path = output_dir / filename

        # Generate and write Terraform configuration
        generator.write_terraform_file(
            output_path=output_path,
            resource_type=args.resource_type,
        )

        print(f"✓ Generated Terraform configuration: {output_path}.tf")
        print(f"✓ Tags extracted: {len(generator.generate_tags())} tags")
        print(f"\nTags:")
        for key, value in sorted(generator.generate_tags().items()):
            print(f"  {key} = {value}")

    except Exception as e:
        print(f"ERROR: Failed to generate Terraform configuration: {e}", file=sys.stderr)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
