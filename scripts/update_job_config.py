#!/usr/bin/env python3
"""Update job config with Terraform outputs (replace placeholders)."""

import sys
import yaml
import json
import re
from pathlib import Path


def replace_placeholders(obj, outputs):
    """
    Recursively replace Terraform output placeholders in an object.
    
    Placeholder format: {{terraform_outputs.<key>}}
    
    Args:
        obj: Object to process (dict, list, str, or other)
        outputs: Dictionary of Terraform outputs
        
    Returns:
        Object with placeholders replaced
    """
    if isinstance(obj, dict):
        return {k: replace_placeholders(v, outputs) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [replace_placeholders(item, outputs) for item in obj]
    elif isinstance(obj, str):
        pattern = r'\{\{terraform_outputs\.([a-zA-Z0-9_]+)\}\}'
        
        def replacer(match):
            key = match.group(1)
            if key in outputs:
                # Handle both direct values and Terraform output format
                output_value = outputs[key]
                if isinstance(output_value, dict) and 'value' in output_value:
                    return str(output_value['value'])
                return str(output_value)
            # Keep placeholder if output not found
            print(f"WARNING: Terraform output '{key}' not found, keeping placeholder", file=sys.stderr)
            return match.group(0)
        
        return re.sub(pattern, replacer, obj)
    return obj


def update_job_config(job_config_path, terraform_outputs_path):
    """
    Update job config with Terraform outputs.
    
    Args:
        job_config_path: Path to job configuration YAML file
        terraform_outputs_path: Path to Terraform outputs JSON file
    """
    # Read Terraform outputs
    with open(terraform_outputs_path, 'r') as f:
        outputs = json.load(f)
    
    # Read job config
    with open(job_config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    if 'infrastructure' not in config:
        print(f"WARNING: No infrastructure section in {job_config_path}, nothing to update", file=sys.stderr)
        return
    
    # Replace placeholders in resource_identifiers
    if 'resource_identifiers' in config['infrastructure']:
        original_identifiers = config['infrastructure']['resource_identifiers'].copy()
        config['infrastructure']['resource_identifiers'] = replace_placeholders(
            config['infrastructure']['resource_identifiers'],
            outputs
        )
        
        # Log changes
        for key, value in config['infrastructure']['resource_identifiers'].items():
            original_value = original_identifiers.get(key)
            if original_value != value:
                print(f"  {key}: {original_value} → {value}", file=sys.stderr)
    
    # Write updated config (preserve formatting as much as possible)
    with open(job_config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
    
    print(f"✅ Updated {job_config_path} with Terraform outputs", file=sys.stderr)


def main():
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: update_job_config.py <job_config_path> <terraform_outputs_path>", file=sys.stderr)
        print("", file=sys.stderr)
        print("Updates job config by replacing {{terraform_outputs.*}} placeholders", file=sys.stderr)
        print("with actual values from Terraform outputs JSON.", file=sys.stderr)
        sys.exit(1)
    
    job_config_path = Path(sys.argv[1])
    terraform_outputs_path = Path(sys.argv[2])
    
    if not job_config_path.exists():
        print(f"ERROR: Job config file not found: {job_config_path}", file=sys.stderr)
        sys.exit(1)
    
    if not terraform_outputs_path.exists():
        print(f"ERROR: Terraform outputs file not found: {terraform_outputs_path}", file=sys.stderr)
        sys.exit(1)
    
    update_job_config(job_config_path, terraform_outputs_path)


if __name__ == '__main__':
    main()
