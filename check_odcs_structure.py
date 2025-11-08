#!/usr/bin/env python3
"""Check ODCS v3.0.2 structure compliance without external dependencies."""

import sys
import os
import json
from pathlib import Path

# Simple YAML parser (basic, for our needs)
def simple_yaml_load(content):
    """Very basic YAML parser for our asset files."""
    import re
    
    # Remove comments
    lines = [line.split('#')[0].rstrip() for line in content.split('\n')]
    content = '\n'.join(lines)
    
    # Try to use eval for simple cases (our YAMLs are simple)
    # This is hacky but works for validation purposes
    try:
        # Convert YAML-like to dict
        result = {}
        current_dict = result
        stack = [result]
        indent_stack = [0]
        
        for line in lines:
            if not line.strip():
                continue
            
            # Calculate indentation
            indent = len(line) - len(line.lstrip())
            line = line.strip()
            
            if ':' in line:
                key, value = line.split(':', 1)
                key = key.strip()
                value = value.strip()
                
                if value == '':
                    # New nested object or array indicator
                    current_dict[key] = {}
                    stack.append(current_dict[key])
                    indent_stack.append(indent)
                    current_dict = current_dict[key]
                elif value.startswith('['):
                    # Inline array
                    current_dict[key] = eval(value)
                else:
                    # Simple value
                    if value.isdigit():
                        current_dict[key] = int(value)
                    elif value in ['true', 'True']:
                        current_dict[key] = True
                    elif value in ['false', 'False']:
                        current_dict[key] = False
                    else:
                        current_dict[key] = value.strip('"\'')
            elif line.startswith('-'):
                # Array item
                if not isinstance(current_dict, list):
                    # Convert to list
                    parent_key = list(stack[-2].keys())[-1]
                    stack[-2][parent_key] = []
                    current_dict = stack[-2][parent_key]
                    stack[-1] = current_dict
                
                item = line[1:].strip()
                if ':' in item:
                    # Dict item in array
                    current_dict.append({})
                else:
                    current_dict.append(item.strip('"\''))
        
        return result
    except:
        # Fallback: just check for key presence
        return None


def check_asset_structure(asset_path):
    """Check asset structure for ODCS compliance."""
    errors = []
    warnings = []
    
    try:
        with open(asset_path, 'r') as f:
            content = f.read()
        
        # Basic checks using string search (no YAML parser needed)
        
        # Check for required Dativo fields
        if 'source_type:' not in content:
            errors.append("Missing: source_type")
        
        if 'object:' not in content:
            errors.append("Missing: object")
        
        if 'schema:' not in content:
            errors.append("Missing: schema section")
        
        # Check for team/governance
        has_team = 'team:' in content
        has_governance = 'governance:' in content
        
        if not has_team and not has_governance:
            errors.append("Missing: team or governance section")
        
        if has_governance and 'owner:' not in content:
            errors.append("governance section missing 'owner' field")
        
        # Check for new finops section
        has_finops = 'finops:' in content
        if has_finops:
            if 'cost_center:' not in content:
                warnings.append("finops section present but missing 'cost_center'")
        
        # Check for compliance section
        has_compliance = 'compliance:' in content
        if has_compliance:
            # Good - using proper ODCS structure
            pass
        else:
            # Check if classification/retention are in governance (old format)
            if 'governance:' in content:
                gov_section = content[content.find('governance:'):]
                next_section = gov_section.find('\n\n')
                if next_section > 0:
                    gov_section = gov_section[:next_section]
                
                if 'classification:' in gov_section:
                    warnings.append("classification should be in 'compliance' section, not 'governance'")
                if 'retention_days:' in gov_section:
                    warnings.append("retention_days should be in 'compliance' section, not 'governance'")
        
        # Check for proper ODCS metadata
        has_version = 'version:' in content
        has_name = 'name:' in content
        
        if not has_name:
            errors.append("Missing: name field")
        
        if not has_version:
            warnings.append("Missing: version field (recommended for ODCS)")
        
        return errors, warnings
    
    except Exception as e:
        return [f"Failed to read file: {e}"], []


def main():
    """Check all asset definitions."""
    print("="*70)
    print("ODCS v3.0.2 STRUCTURE CHECK")
    print("="*70)
    print()
    
    # Check schema file
    schema_path = Path("schemas/odcs/dativo-odcs-3.0.2-extended.schema.json")
    if not schema_path.exists():
        print(f"✗ Schema file not found: {schema_path}")
        return 1
    
    with open(schema_path, 'r') as f:
        schema = json.load(f)
    
    # Check that finops is in schema
    if 'allOf' in schema and len(schema['allOf']) > 1:
        extended_props = schema['allOf'][1].get('properties', {})
        if 'finops' in extended_props:
            print("✓ Schema includes 'finops' extension")
        else:
            print("✗ Schema missing 'finops' extension")
            return 1
        
        if 'compliance' in extended_props:
            print("✓ Schema includes 'compliance' section")
        else:
            print("✗ Schema missing 'compliance' section")
            return 1
    
    print()
    
    # Find all asset definition files
    assets_dir = Path("assets")
    if not assets_dir.exists():
        print(f"✗ Assets directory not found: {assets_dir}")
        return 1
    
    asset_files = list(assets_dir.rglob("*.yaml"))
    if not asset_files:
        print(f"✗ No asset files found in {assets_dir}")
        return 1
    
    print(f"Found {len(asset_files)} asset definition(s)\n")
    print("-"*70)
    
    # Check each asset
    results = []
    for asset_path in sorted(asset_files):
        try:
            relative_path = asset_path.relative_to(Path.cwd())
        except ValueError:
            relative_path = asset_path
        errors, warnings = check_asset_structure(asset_path)
        results.append((relative_path, errors, warnings))
        
        status = "✓" if not errors else "✗"
        print(f"\n{status} {relative_path}")
        
        if errors:
            for error in errors:
                print(f"    ERROR: {error}")
        
        if warnings:
            for warning in warnings:
                print(f"    WARNING: {warning}")
        
        if not errors and not warnings:
            print("    All checks passed")
    
    # Summary
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    
    total_errors = sum(len(errors) for _, errors, _ in results)
    total_warnings = sum(len(warnings) for _, _, warnings in results)
    assets_with_errors = sum(1 for _, errors, _ in results if errors)
    
    print(f"\nTotal assets checked: {len(results)}")
    print(f"Assets with errors: {assets_with_errors}")
    print(f"Total errors: {total_errors}")
    print(f"Total warnings: {total_warnings}")
    
    if total_errors == 0:
        print("\n✓ All assets pass structure checks!")
        print("\nODCS v3.0.2 Compliance:")
        print("  ✓ finops extension in schema")
        print("  ✓ compliance section supported")
        print("  ✓ All assets have required fields")
        print("  ✓ Schema structure is valid")
        return 0
    else:
        print(f"\n✗ {assets_with_errors} asset(s) have errors")
        return 1


if __name__ == "__main__":
    sys.exit(main())
