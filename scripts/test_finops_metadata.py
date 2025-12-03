#!/usr/bin/env python3
"""Script to test FinOps metadata in Iceberg table properties.

This script demonstrates how to:
1. Query Iceberg table properties to verify FinOps metadata
2. Test that FinOps metadata from asset definitions is properly stored
3. Verify metadata is accessible via PyIceberg

Usage:
    python scripts/test_finops_metadata.py
"""

import os
import sys
import json
from pathlib import Path
from typing import Dict, Any, Optional

try:
    import boto3
except ImportError:
    print("ERROR: boto3 is required. Install with: pip install boto3")
    sys.exit(1)


def get_s3_client():
    """Create and return S3/MinIO client."""
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


def find_iceberg_metadata_files(s3_client, bucket: str, tenant_id: str, table_name: str) -> list:
    """Find Iceberg metadata.json files for a table.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        tenant_id: Tenant ID
        table_name: Table name
        
    Returns:
        List of metadata.json file paths
    """
    # Iceberg stores metadata in: bucket/tenant/table/metadata/metadata-*.json
    prefixes = [
        f"{tenant_id}/{table_name}/metadata/",
        f"{tenant_id}/default/{table_name}/metadata/",
        f"{table_name}/metadata/",
    ]
    
    metadata_files = []
    
    for prefix in prefixes:
        try:
            paginator = s3_client.get_paginator('list_objects_v2')
            for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
                if 'Contents' not in page:
                    continue
                for obj in page['Contents']:
                    if obj['Key'].endswith('.metadata.json') or 'metadata-' in obj['Key']:
                        metadata_files.append(obj['Key'])
        except Exception:
            pass
    
    return sorted(metadata_files, reverse=True)  # Most recent first


def read_iceberg_metadata(s3_client, bucket: str, key: str) -> Optional[Dict[str, Any]]:
    """Read Iceberg metadata.json file from S3.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Parsed metadata dictionary or None
    """
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        metadata_json = response['Body'].read().decode('utf-8')
        return json.loads(metadata_json)
    except Exception as e:
        print(f"    ERROR: Failed to read metadata from {key}: {e}")
        return None


def extract_table_properties_from_metadata(metadata: Dict[str, Any]) -> Dict[str, str]:
    """Extract table properties from Iceberg metadata.
    
    Args:
        metadata: Iceberg metadata dictionary
        
    Returns:
        Dictionary of table properties
    """
    properties = {}
    
    # Table properties are in metadata.properties
    if 'properties' in metadata:
        properties.update(metadata['properties'])
    
    # Also check current-schema-id and format-version
    if 'format-version' in metadata:
        properties['format-version'] = str(metadata['format-version'])
    
    return properties


def test_finops_metadata_from_s3(
    bucket: str,
    tenant_id: str,
    table_name: str,
    expected_finops: dict
):
    """Test FinOps metadata by reading Iceberg metadata files from S3.
    
    Args:
        bucket: S3 bucket name
        tenant_id: Tenant ID
        table_name: Table name
        expected_finops: Expected FinOps metadata dictionary
        
    Returns:
        True if all FinOps metadata matches, False otherwise
    """
    print(f"\n{'='*70}")
    print(f"Testing FinOps Metadata from Iceberg Metadata Files")
    print(f"{'='*70}")
    print(f"Bucket: {bucket}")
    print(f"Table: {tenant_id}/{table_name}")
    print()
    
    try:
        s3_client = get_s3_client()
        
        # Find metadata files
        print("Searching for Iceberg metadata files...")
        metadata_files = find_iceberg_metadata_files(s3_client, bucket, tenant_id, table_name)
        
        if not metadata_files:
            print(f"✗ No Iceberg metadata files found for {table_name}")
            print("  This could mean:")
            print("  1. The job hasn't been run with catalog configured")
            print("  2. The table path is different than expected")
            print("  3. Iceberg metadata files haven't been created yet")
            print()
            print("  Note: FinOps metadata is only stored in Iceberg table properties")
            print("  when a catalog is configured. Without a catalog, FinOps metadata")
            print("  is not written to S3.")
            return False
        
        print(f"✓ Found {len(metadata_files)} metadata file(s)")
        print(f"  Using most recent: {metadata_files[0]}")
        print()
        
        # Read the most recent metadata file
        metadata = read_iceberg_metadata(s3_client, bucket, metadata_files[0])
        if not metadata:
            print("✗ Failed to read metadata file")
            return False
        
        # Extract table properties
        properties = extract_table_properties_from_metadata(metadata)
        
        print(f"Found {len(properties)} table properties")
        print()
        
        # Check FinOps properties
        finops_properties = {k: v for k, v in properties.items() if k.startswith('finops.')}
        
        print("FinOps Properties Found:")
        if finops_properties:
            for key, value in sorted(finops_properties.items()):
                print(f"  ✓ {key} = {value}")
        else:
            print("  ✗ No FinOps properties found")
            print()
            print("  This could mean:")
            print("  1. The job was run without catalog configured")
            print("  2. FinOps metadata wasn't written to table properties")
            print("  3. The metadata file is from an older version")
        
        print()
        print("Validation:")
        
        all_match = True
        
        # Check cost_center
        expected_cost_center = expected_finops.get('cost_center')
        if expected_cost_center:
            actual_cost_center = properties.get('finops.cost_center')
            if actual_cost_center:
                if actual_cost_center == expected_cost_center:
                    print(f"  ✓ finops.cost_center: {actual_cost_center}")
                else:
                    print(f"  ✗ finops.cost_center: expected '{expected_cost_center}', got '{actual_cost_center}'")
                    all_match = False
            else:
                print(f"  ✗ finops.cost_center: missing (expected '{expected_cost_center}')")
                all_match = False
        
        # Check business_tags
        expected_business_tags = expected_finops.get('business_tags', [])
        if expected_business_tags:
            actual_business_tags_str = properties.get('finops.business_tags', '')
            if actual_business_tags_str:
                actual_business_tags = [t.strip() for t in actual_business_tags_str.split(',')]
                expected_set = set(expected_business_tags)
                actual_set = set(actual_business_tags)
                if expected_set == actual_set:
                    print(f"  ✓ finops.business_tags: {', '.join(actual_business_tags)}")
                else:
                    print(f"  ✗ finops.business_tags: expected {expected_business_tags}, got {actual_business_tags}")
                    all_match = False
            else:
                print(f"  ✗ finops.business_tags: missing (expected {expected_business_tags})")
                all_match = False
        
        # Check project
        expected_project = expected_finops.get('project')
        if expected_project:
            actual_project = properties.get('finops.project')
            if actual_project:
                if actual_project == expected_project:
                    print(f"  ✓ finops.project: {actual_project}")
                else:
                    print(f"  ✗ finops.project: expected '{expected_project}', got '{actual_project}'")
                    all_match = False
            else:
                print(f"  ✗ finops.project: missing (expected '{expected_project}')")
                all_match = False
        
        # Check environment
        expected_environment = expected_finops.get('environment')
        if expected_environment:
            actual_environment = properties.get('finops.environment')
            if actual_environment:
                if actual_environment == expected_environment:
                    print(f"  ✓ finops.environment: {actual_environment}")
                else:
                    print(f"  ✗ finops.environment: expected '{expected_environment}', got '{actual_environment}'")
                    all_match = False
            else:
                print(f"  ✗ finops.environment: missing (expected '{expected_environment}')")
                all_match = False
        
        # Show all relevant properties for reference
        print()
        print("All Relevant Table Properties:")
        relevant_keys = [k for k in properties.keys() if k.startswith(('finops.', 'classification.', 'governance.', 'asset.'))]
        if relevant_keys:
            for key in sorted(relevant_keys):
                print(f"  {key} = {properties[key]}")
        else:
            print("  (No relevant properties found)")
        
        return all_match
        
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Main execution function."""
    # Configuration
    bucket = os.getenv("S3_BUCKET") or os.getenv("MINIO_BUCKET") or "test-bucket"
    tenant_id = os.getenv("TENANT_ID", "testcase3")
    table_name = os.getenv("TABLE_NAME", "stripe_customers")
    
    # Expected FinOps metadata from asset definition
    project_root = Path(__file__).parent.parent
    asset_path = project_root / "assets/examples/stripe/v1.0/customers.yaml"
    
    if not asset_path.exists():
        print(f"ERROR: Asset definition not found: {asset_path}")
        return 1
    
    import yaml
    with open(asset_path, 'r') as f:
        asset_def = yaml.safe_load(f)
    
    expected_finops = asset_def.get('finops', {})
    
    if not expected_finops:
        print("ERROR: No FinOps metadata found in asset definition")
        return 1
    
    print("Expected FinOps Metadata from Asset Definition:")
    for key, value in expected_finops.items():
        print(f"  {key}: {value}")
    
    # Test FinOps metadata from S3
    success = test_finops_metadata_from_s3(
        bucket=bucket,
        tenant_id=tenant_id,
        table_name=table_name,
        expected_finops=expected_finops
    )
    
    print()
    print("="*70)
    if success:
        print("✓ ALL FINOPS METADATA VALIDATED SUCCESSFULLY")
        return 0
    else:
        print("✗ FINOPS METADATA VALIDATION FAILED")
        print()
        print("To fix this:")
        print("1. Ensure the job has a catalog configured")
        print("2. Run the job with catalog: dativo run --config jobs/testcase3/stripe_customers_with_catalog.yaml")
        print("3. Verify the job completed successfully")
        print("4. Check that Iceberg metadata files were created in S3")
        return 1


if __name__ == "__main__":
    sys.exit(main())

