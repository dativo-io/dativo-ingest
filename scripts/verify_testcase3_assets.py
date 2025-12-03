#!/usr/bin/env python3
"""Script to verify that MinIO data matches asset definitions for testcase3.

This script:
1. Loads asset definitions from jobs/testcase3/
2. Connects to MinIO and finds corresponding Parquet files
3. Validates that Parquet file schemas match asset definition schemas
4. Reports any mismatches
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Dict, List, Any, Optional, Set
from collections import defaultdict

try:
    import boto3
    import pandas as pd
    import pyarrow.parquet as pq
    from io import BytesIO
except ImportError as e:
    print(f"ERROR: Missing required library: {e}")
    print("Install with: pip install boto3 pandas pyarrow pyyaml")
    sys.exit(1)


def get_minio_client():
    """Create and return MinIO/S3 client."""
    endpoint_url = os.getenv("S3_ENDPOINT") or os.getenv("MINIO_ENDPOINT") or "http://localhost:9000"
    access_key = os.getenv("AWS_ACCESS_KEY_ID") or os.getenv("MINIO_ACCESS_KEY") or "minioadmin"
    secret_key = os.getenv("AWS_SECRET_ACCESS_KEY") or os.getenv("MINIO_SECRET_KEY") or "minioadmin"
    region = os.getenv("AWS_REGION") or "us-east-1"
    
    s3_client = boto3.client(
        's3',
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region
    )
    
    return s3_client


def load_job_configs(job_dir: Path) -> List[Dict[str, Any]]:
    """Load all job configurations from a directory.
    
    Args:
        job_dir: Directory containing job YAML files
        
    Returns:
        List of job configuration dictionaries
    """
    jobs = []
    for job_file in job_dir.glob("*.yaml"):
        try:
            with open(job_file, 'r') as f:
                job_config = yaml.safe_load(f)
                job_config['_file'] = job_file.name
                jobs.append(job_config)
        except Exception as e:
            print(f"Warning: Could not load {job_file}: {e}")
    return jobs


def load_asset_definition(asset_path: Path) -> Dict[str, Any]:
    """Load asset definition from YAML file.
    
    Args:
        asset_path: Path to asset definition YAML file
        
    Returns:
        Asset definition dictionary
    """
    with open(asset_path, 'r') as f:
        return yaml.safe_load(f)


def get_expected_schema_fields(asset_def: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract expected schema fields from asset definition.
    
    Args:
        asset_def: Asset definition dictionary
        
    Returns:
        Dictionary mapping field name to field definition
    """
    schema = asset_def.get('schema', [])
    fields = {}
    for field in schema:
        field_name = field.get('name')
        if field_name:
            fields[field_name] = {
                'type': field.get('type', 'string'),
                'required': field.get('required', False),
                'classification': field.get('classification'),
            }
    return fields


def find_parquet_files(s3_client, bucket: str, tenant_id: str, table_name: str) -> List[Dict[str, Any]]:
    """Find Parquet files for a given table in MinIO.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        tenant_id: Tenant ID
        table_name: Table/asset name
        
    Returns:
        List of file metadata dictionaries
    """
    # Try different path patterns
    prefixes = [
        f"{tenant_id}/{table_name}",
        f"{tenant_id}/default/{table_name}",
        f"{tenant_id}/stripe/{table_name}",
        table_name,
    ]
    
    all_files = []
    
    for prefix in prefixes:
        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                if 'Contents' not in page:
                    continue
                for obj in page['Contents']:
                    if obj['Key'].endswith('.parquet'):
                        all_files.append({
                            'key': obj['Key'],
                            'size': obj['Size'],
                            'modified': obj['LastModified'],
                        })
        except Exception as e:
            # Silently continue if prefix doesn't exist
            pass
    
    # Remove duplicates based on key
    seen = set()
    unique_files = []
    for file_info in all_files:
        if file_info['key'] not in seen:
            seen.add(file_info['key'])
            unique_files.append(file_info)
    
    return unique_files


def read_parquet_schema(s3_client, bucket: str, key: str) -> Dict[str, str]:
    """Read Parquet file schema from S3/MinIO.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Dictionary mapping column name to pandas dtype (as string)
    """
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        parquet_file = BytesIO(response['Body'].read())
        parquet_table = pq.read_table(parquet_file)
        
        # Get schema information
        schema_dict = {}
        for field in parquet_table.schema:
            # Convert PyArrow type to string representation
            schema_dict[field.name] = str(field.type)
        
        return schema_dict
    except Exception as e:
        print(f"    ERROR: Failed to read schema from {key}: {e}")
        return {}


def get_s3_object_metadata(s3_client, bucket: str, key: str) -> Dict[str, Any]:
    """Get S3 object metadata and tags.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Dictionary with 'metadata' and 'tags' keys
    """
    result = {'metadata': {}, 'tags': {}}
    
    try:
        # Get object metadata
        response = s3_client.head_object(Bucket=bucket, Key=key)
        result['metadata'] = response.get('Metadata', {})
        
        # Get object tags
        try:
            tag_response = s3_client.get_object_tagging(Bucket=bucket, Key=key)
            tags = {}
            for tag in tag_response.get('TagSet', []):
                tags[tag['Key']] = tag['Value']
            result['tags'] = tags
        except Exception:
            # Tags might not be supported or object might not have tags
            pass
            
    except Exception as e:
        print(f"    ERROR: Failed to read metadata from {key}: {e}")
    
    return result


def read_parquet_sample(s3_client, bucket: str, key: str, n_rows: int = 5) -> Optional[pd.DataFrame]:
    """Read a sample of records from a Parquet file.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        n_rows: Number of rows to read
        
    Returns:
        Pandas DataFrame with sample data
    """
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        parquet_file = BytesIO(response['Body'].read())
        # Read full file then take first n_rows
        df = pd.read_parquet(parquet_file)
        return df.head(n_rows) if len(df) > n_rows else df
    except Exception as e:
        print(f"    ERROR: Failed to read sample from {key}: {e}")
        return None


def map_pandas_dtype_to_asset_type(pandas_dtype: str) -> str:
    """Map pandas/PyArrow dtype to asset definition type.
    
    Args:
        pandas_dtype: Pandas/PyArrow dtype string
        
    Returns:
        Asset definition type string
    """
    dtype_lower = str(pandas_dtype).lower()
    
    if 'int' in dtype_lower:
        return 'integer'
    elif 'float' in dtype_lower or 'double' in dtype_lower:
        return 'double'
    elif 'bool' in dtype_lower:
        return 'boolean'
    elif 'timestamp' in dtype_lower or 'datetime' in dtype_lower:
        return 'timestamp'
    elif 'date' in dtype_lower:
        return 'date'
    else:
        return 'string'


def validate_metadata_match(
    asset_def: Dict[str, Any],
    s3_metadata: Dict[str, str],
    s3_tags: Dict[str, str]
) -> Dict[str, Any]:
    """Validate that S3 metadata matches asset definition.
    
    Args:
        asset_def: Asset definition dictionary
        s3_metadata: S3 object metadata
        s3_tags: S3 object tags
        
    Returns:
        Validation result dictionary
    """
    result = {
        'matches': True,
        'missing_metadata': [],
        'mismatched_metadata': [],
        'found_metadata': [],
        'warnings': [],
    }
    
    # Check asset name
    expected_name = asset_def.get('name', '')
    actual_name = s3_metadata.get('asset-name', '')
    if expected_name:
        if actual_name:
            if actual_name == expected_name:
                result['found_metadata'].append(f"asset-name: {actual_name}")
            else:
                result['mismatched_metadata'].append({
                    'key': 'asset-name',
                    'expected': expected_name,
                    'actual': actual_name
                })
                result['matches'] = False
        else:
            result['missing_metadata'].append('asset-name')
            result['matches'] = False
    
    # Check asset version
    expected_version = str(asset_def.get('version', ''))
    actual_version = s3_metadata.get('asset-version', '')
    if expected_version:
        if actual_version:
            if actual_version == expected_version:
                result['found_metadata'].append(f"asset-version: {actual_version}")
            else:
                result['mismatched_metadata'].append({
                    'key': 'asset-version',
                    'expected': expected_version,
                    'actual': actual_version
                })
                result['matches'] = False
        else:
            result['missing_metadata'].append('asset-version')
            result['matches'] = False
    
    # Check compliance/retention
    compliance = asset_def.get('compliance', {})
    if compliance:
        expected_retention = compliance.get('retention_days')
        if expected_retention:
            actual_retention = s3_metadata.get('retention-days')
            if actual_retention:
                if str(actual_retention) == str(expected_retention):
                    result['found_metadata'].append(f"retention-days: {actual_retention}")
                else:
                    result['mismatched_metadata'].append({
                        'key': 'retention-days',
                        'expected': str(expected_retention),
                        'actual': actual_retention
                    })
                    result['matches'] = False
            else:
                result['missing_metadata'].append('retention-days')
                result['matches'] = False
        
        expected_classification = compliance.get('classification', [])
        if expected_classification:
            actual_classification = s3_metadata.get('classification', '')
            if actual_classification:
                # Parse comma-separated classification
                actual_list = [c.strip() for c in actual_classification.split(',')]
                expected_set = set(expected_classification)
                actual_set = set(actual_list)
                if expected_set == actual_set:
                    result['found_metadata'].append(f"classification: {actual_classification}")
                else:
                    result['mismatched_metadata'].append({
                        'key': 'classification',
                        'expected': ','.join(expected_classification),
                        'actual': actual_classification
                    })
                    result['matches'] = False
            else:
                result['missing_metadata'].append('classification')
                result['matches'] = False
    
    # Check team/owner
    team = asset_def.get('team', {})
    if team and team.get('owner'):
        expected_owner = team.get('owner')
        actual_owner = s3_metadata.get('owner', '')
        if actual_owner:
            if actual_owner == expected_owner:
                result['found_metadata'].append(f"owner: {actual_owner}")
            else:
                result['mismatched_metadata'].append({
                    'key': 'owner',
                    'expected': expected_owner,
                    'actual': actual_owner
                })
                result['matches'] = False
        else:
            result['missing_metadata'].append('owner')
            result['matches'] = False
    
    # Check finops (from tags or metadata)
    # Note: FinOps metadata is typically written to Iceberg table properties when catalog is configured
    # When no catalog is configured, it may not be written to S3 metadata/tags
    finops = asset_def.get('finops', {})
    if finops:
        expected_cost_center = finops.get('cost_center')
        if expected_cost_center:
            # Look for cost_center in tags or metadata
            found_cost_center = False
            cost_center_value = None
            
            # Check S3 tags
            for tag_key, tag_value in s3_tags.items():
                if 'cost-center' in tag_key.lower() or tag_value == expected_cost_center:
                    cost_center_value = tag_value
                    found_cost_center = True
                    break
            
            # Check metadata (if stored there)
            if not found_cost_center:
                for key, value in s3_metadata.items():
                    if 'cost' in key.lower() and 'center' in key.lower():
                        cost_center_value = value
                        found_cost_center = True
                        break
            
            if found_cost_center:
                result['found_metadata'].append(f"finops.cost_center: {cost_center_value}")
            else:
                # Don't fail validation - finops may only be in Iceberg table properties
                result['warnings'].append(
                    f"finops.cost_center not found in S3 metadata/tags (may be in Iceberg table properties if catalog configured)"
                )
        
        expected_business_tags = finops.get('business_tags', [])
        if expected_business_tags:
            # Look for business tags in S3 tags
            found_tags = []
            for tag_value in s3_tags.values():
                if tag_value in expected_business_tags:
                    found_tags.append(tag_value)
            if found_tags:
                result['found_metadata'].append(f"finops.business_tags: {', '.join(found_tags)}")
            if len(found_tags) < len(expected_business_tags):
                result['warnings'].append(
                    f"Some business tags missing in S3 tags: expected {expected_business_tags}, found {found_tags} "
                    f"(may be in Iceberg table properties if catalog configured)"
                )
    
    # Check asset tags
    expected_tags = asset_def.get('tags', [])
    if expected_tags:
        found_asset_tags = []
        for tag_value in s3_tags.values():
            if tag_value in expected_tags:
                found_asset_tags.append(tag_value)
        if found_asset_tags:
            result['found_metadata'].append(f"asset.tags: {', '.join(found_asset_tags)}")
        if len(found_asset_tags) < len(expected_tags):
            result['warnings'].append(
                f"Some asset tags missing: expected {expected_tags}, found {found_asset_tags}"
            )
    
    return result


def validate_schema_match(
    expected_fields: Dict[str, Dict[str, Any]],
    actual_schema: Dict[str, str],
    sample_df: Optional[pd.DataFrame] = None
) -> Dict[str, Any]:
    """Validate that actual Parquet schema matches expected asset definition.
    
    Args:
        expected_fields: Expected fields from asset definition
        actual_schema: Actual schema from Parquet file
        sample_df: Optional sample DataFrame for additional validation
        
    Returns:
        Validation result dictionary
    """
    result = {
        'matches': True,
        'missing_fields': [],
        'extra_fields': [],
        'type_mismatches': [],
        'missing_required': [],
        'warnings': [],
    }
    
    expected_field_names = set(expected_fields.keys())
    actual_field_names = set(actual_schema.keys())
    
    # Check for missing expected fields
    missing = expected_field_names - actual_field_names
    if missing:
        result['matches'] = False
        result['missing_fields'] = sorted(missing)
        # Check if any missing fields are required
        for field_name in missing:
            if expected_fields[field_name].get('required', False):
                result['missing_required'].append(field_name)
    
    # Check for extra fields (not in asset definition)
    extra = actual_field_names - expected_field_names
    if extra:
        result['extra_fields'] = sorted(extra)
        result['warnings'].append(f"Found {len(extra)} extra field(s) not in asset definition")
    
    # Check type compatibility for common fields
    common_fields = expected_field_names & actual_field_names
    for field_name in common_fields:
        expected_type = expected_fields[field_name].get('type', 'string')
        actual_type_str = actual_schema[field_name]
        actual_type = map_pandas_dtype_to_asset_type(actual_type_str)
        
        # Type compatibility check (loose matching)
        if expected_type != actual_type:
            # Some types are compatible
            compatible = False
            if expected_type == 'double' and actual_type == 'integer':
                compatible = True  # Integer can be double
            elif expected_type == 'timestamp' and actual_type in ['date', 'string']:
                compatible = True  # Date/string can be timestamp
            elif expected_type == 'string' and actual_type != 'string':
                compatible = True  # Most types can be string
            
            if not compatible:
                result['type_mismatches'].append({
                    'field': field_name,
                    'expected': expected_type,
                    'actual': actual_type,
                    'actual_dtype': actual_type_str,
                })
                result['matches'] = False
    
    # Additional validation using sample data if available
    if sample_df is not None:
        for field_name in expected_fields:
            if field_name in sample_df.columns:
                # Check for null values in required fields
                if expected_fields[field_name].get('required', False):
                    null_count = sample_df[field_name].isna().sum()
                    if null_count > 0:
                        result['warnings'].append(
                            f"Required field '{field_name}' has {null_count} null values in sample"
                        )
    
    return result


def print_validation_report(
    asset_name: str,
    asset_def: Dict[str, Any],
    files: List[Dict[str, Any]],
    schema_validation: Dict[str, Any],
    metadata_validation: Dict[str, Any]
):
    """Print validation report for an asset.
    
    Args:
        asset_name: Name of the asset
        asset_def: Asset definition dictionary
        files: List of Parquet files found
        validation: Validation result dictionary
    """
    print(f"\n{'='*70}")
    print(f"Asset: {asset_name}")
    print(f"{'='*70}")
    print(f"Object: {asset_def.get('object', 'N/A')}")
    print(f"Source Type: {asset_def.get('source_type', 'N/A')}")
    expected_fields = asset_def.get('schema', [])
    print(f"Expected Fields: {len(expected_fields)}")
    print(f"Parquet Files Found: {len(files)}")
    
    if files:
        total_size = sum(f['size'] for f in files)
        print(f"Total Size: {total_size:,} bytes ({total_size / 1024:.2f} KB)")
        print(f"\nFiles:")
        for f in files:
            print(f"  - {f['key']} ({f['size']:,} bytes)")
    
    expected_fields = asset_def.get('schema', [])
    print(f"\nSchema Validation:")
    if schema_validation['matches']:
        print("  ✓ Schema matches asset definition")
        # Show matched fields
        if expected_fields:
            print(f"\n  Matched Fields ({len(expected_fields)}):")
            for field in expected_fields[:10]:  # Show first 10
                field_name = field.get('name', '')
                field_type = field.get('type', 'string')
                required = "REQUIRED" if field.get('required', False) else "optional"
                print(f"    ✓ {field_name} ({field_type}, {required})")
            if len(expected_fields) > 10:
                print(f"    ... and {len(expected_fields) - 10} more fields")
    else:
        print("  ✗ Schema does NOT match asset definition")
    
    if schema_validation['missing_fields']:
        print(f"\n  Missing Fields ({len(schema_validation['missing_fields'])}):")
        for field in schema_validation['missing_fields']:
            required = "REQUIRED" if field in schema_validation['missing_required'] else "optional"
            print(f"    - {field} ({required})")
    
    if schema_validation['extra_fields']:
        print(f"\n  Extra Fields ({len(schema_validation['extra_fields'])}):")
        for field in schema_validation['extra_fields']:
            print(f"    - {field}")
    
    if schema_validation['type_mismatches']:
        print(f"\n  Type Mismatches ({len(schema_validation['type_mismatches'])}):")
        for mismatch in schema_validation['type_mismatches']:
            print(f"    - {mismatch['field']}: expected {mismatch['expected']}, "
                  f"got {mismatch['actual']} ({mismatch['actual_dtype']})")
    
    if schema_validation['warnings']:
        print(f"\n  Warnings ({len(schema_validation['warnings'])}):")
        for warning in schema_validation['warnings']:
            print(f"    - {warning}")
    
    print(f"\nMetadata Validation:")
    if metadata_validation['matches']:
        print("  ✓ Metadata matches asset definition")
        if metadata_validation['found_metadata']:
            print(f"\n  Found Metadata ({len(metadata_validation['found_metadata'])}):")
            for meta in metadata_validation['found_metadata']:
                print(f"    ✓ {meta}")
    else:
        print("  ✗ Metadata does NOT match asset definition")
    
    if metadata_validation['missing_metadata']:
        print(f"\n  Missing Metadata ({len(metadata_validation['missing_metadata'])}):")
        for meta_key in metadata_validation['missing_metadata']:
            print(f"    - {meta_key}")
    
    if metadata_validation['mismatched_metadata']:
        print(f"\n  Mismatched Metadata ({len(metadata_validation['mismatched_metadata'])}):")
        for mismatch in metadata_validation['mismatched_metadata']:
            print(f"    - {mismatch['key']}: expected '{mismatch['expected']}', "
                  f"got '{mismatch['actual']}'")
    
    if metadata_validation['warnings']:
        print(f"\n  Warnings ({len(metadata_validation['warnings'])}):")
        for warning in metadata_validation['warnings']:
            print(f"    - {warning}")


def main():
    """Main execution function."""
    # Get configuration from environment
    bucket = os.getenv("S3_BUCKET") or os.getenv("MINIO_BUCKET") or "test-bucket"
    tenant_id = "testcase3"
    project_root = Path(__file__).parent.parent
    
    job_dir = project_root / "jobs" / tenant_id
    if not job_dir.exists():
        print(f"ERROR: Job directory not found: {job_dir}")
        return 1
    
    print(f"Verifying MinIO data against asset definitions for {tenant_id}")
    print(f"Project root: {project_root}")
    print(f"Job directory: {job_dir}")
    print(f"Bucket: {bucket}")
    print()
    
    # Load job configurations
    print("Loading job configurations...")
    jobs = load_job_configs(job_dir)
    if not jobs:
        print(f"ERROR: No job configurations found in {job_dir}")
        return 1
    
    print(f"✓ Found {len(jobs)} job(s)")
    for job in jobs:
        print(f"  - {job['_file']}: {job.get('asset', 'N/A')}")
    print()
    
    # Connect to MinIO
    print("Connecting to MinIO...")
    try:
        s3_client = get_minio_client()
        s3_client.head_bucket(Bucket=bucket)
        print("✓ Connected to MinIO successfully")
    except Exception as e:
        print(f"✗ Failed to connect to MinIO: {e}")
        return 1
    
    print()
    
    # Validate each job's asset
    all_valid = True
    for job in jobs:
        asset_name = job.get('asset')
        asset_path_str = job.get('asset_path')
        
        if not asset_name or not asset_path_str:
            print(f"Warning: Job {job['_file']} missing asset or asset_path, skipping")
            continue
        
        # Load asset definition
        asset_path = project_root / asset_path_str
        if not asset_path.exists():
            print(f"ERROR: Asset definition not found: {asset_path}")
            all_valid = False
            continue
        
        try:
            asset_def = load_asset_definition(asset_path)
        except Exception as e:
            print(f"ERROR: Failed to load asset definition {asset_path}: {e}")
            all_valid = False
            continue
        
        # Get expected schema
        expected_fields = get_expected_schema_fields(asset_def)
        
        # Find Parquet files
        files = find_parquet_files(s3_client, bucket, tenant_id, asset_name)
        
        if not files:
            print(f"\n{'='*70}")
            print(f"Asset: {asset_name}")
            print(f"{'='*70}")
            print("✗ No Parquet files found in MinIO")
            all_valid = False
            continue
        
        # Read schema from first file
        first_file = files[0]
        actual_schema = read_parquet_schema(s3_client, bucket, first_file['key'])
        
        if not actual_schema:
            print(f"ERROR: Could not read schema from {first_file['key']}")
            all_valid = False
            continue
        
        # Read sample data for additional validation
        sample_df = read_parquet_sample(s3_client, bucket, first_file['key'], n_rows=5)
        
        # Get S3 object metadata and tags
        s3_metadata_info = get_s3_object_metadata(s3_client, bucket, first_file['key'])
        s3_metadata = s3_metadata_info.get('metadata', {})
        s3_tags = s3_metadata_info.get('tags', {})
        
        # Validate schema match
        schema_validation = validate_schema_match(expected_fields, actual_schema, sample_df)
        
        # Validate metadata match
        metadata_validation = validate_metadata_match(asset_def, s3_metadata, s3_tags)
        
        # Print report
        print_validation_report(asset_name, asset_def, files, schema_validation, metadata_validation)
        
        if not schema_validation['matches'] or not metadata_validation['matches']:
            all_valid = False
    
    print(f"\n{'='*70}")
    if all_valid:
        print("✓ ALL ASSETS VALIDATED SUCCESSFULLY")
        return 0
    else:
        print("✗ SOME ASSETS HAVE VALIDATION ISSUES")
        return 1


if __name__ == "__main__":
    sys.exit(main())

