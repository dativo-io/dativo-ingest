#!/usr/bin/env python3
"""Extract job metadata from Dativo job configuration for Terraform."""

import sys
import yaml
import json
from pathlib import Path


def extract_metadata(job_config_path):
    """
    Extract infrastructure metadata from job config.
    
    Args:
        job_config_path: Path to job configuration YAML file
        
    Returns:
        Dictionary with job metadata for Terraform variables
    """
    with open(job_config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    if 'infrastructure' not in config:
        print(f"WARNING: No infrastructure section found in {job_config_path}", file=sys.stderr)
        return None
    
    infra = config['infrastructure']
    tags = infra.get('tags', {})
    
    # Validate required tags
    required_tags = ['job_name', 'team', 'pipeline_type', 'environment', 'cost_center']
    missing_tags = [tag for tag in required_tags if tag not in tags]
    if missing_tags:
        print(f"ERROR: Missing required tags in {job_config_path}: {', '.join(missing_tags)}", file=sys.stderr)
        sys.exit(1)
    
    metadata = {
        'job_name': tags.get('job_name'),
        'team': tags.get('team'),
        'pipeline_type': tags.get('pipeline_type'),
        'environment': tags.get('environment'),
        'cost_center': tags.get('cost_center'),
        'provider': infra.get('provider'),
        'runtime_type': infra.get('runtime', {}).get('type'),
        'region': infra.get('region'),
        'container_image': infra.get('runtime', {}).get('image'),
        'cpu': infra.get('runtime', {}).get('cpu'),
        'memory': infra.get('runtime', {}).get('memory'),
    }
    
    # Add optional tags
    for key, value in tags.items():
        if key not in required_tags:
            metadata[f'tag_{key}'] = value
    
    return metadata


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: extract_job_metadata.py <job_config_path>", file=sys.stderr)
        print("", file=sys.stderr)
        print("Extracts infrastructure metadata from Dativo job config for Terraform.", file=sys.stderr)
        sys.exit(1)
    
    job_config_path = Path(sys.argv[1])
    
    if not job_config_path.exists():
        print(f"ERROR: Job config file not found: {job_config_path}", file=sys.stderr)
        sys.exit(1)
    
    metadata = extract_metadata(job_config_path)
    
    if metadata:
        print(json.dumps(metadata, indent=2))
    else:
        sys.exit(1)


if __name__ == '__main__':
    main()
