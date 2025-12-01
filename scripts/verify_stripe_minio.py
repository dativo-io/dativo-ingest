#!/usr/bin/env python3
"""Script to verify Stripe customer data in MinIO/S3.

This script:
1. Connects to MinIO
2. Lists Parquet files for Stripe customers
3. Reads and validates the data
4. Displays summary statistics
"""

import os
import sys
from pathlib import Path
from typing import Dict, List, Any

try:
    import boto3
    import pandas as pd
    import pyarrow.parquet as pq
    from io import BytesIO
except ImportError as e:
    print(f"ERROR: Missing required library: {e}")
    print("Install with: pip install boto3 pandas pyarrow")
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


def find_stripe_files(s3_client, bucket: str, tenant_id: str = "testcase3") -> List[Dict[str, Any]]:
    """Find all Stripe customer Parquet files in MinIO.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        tenant_id: Tenant ID (used in path)
        
    Returns:
        List of file metadata dictionaries
    """
    # Expected path structure: bucket/tenant_id/stripe_customers/ingest_date=YYYY-MM-DD/file.parquet
    # Or: bucket/tenant_id/default/stripe_customers/ingest_date=YYYY-MM-DD/file.parquet
    table_name = "stripe_customers"
    
    # Try different path patterns
    prefixes = [
        f"{tenant_id}/{table_name}",
        f"{tenant_id}/default/{table_name}",
        f"{tenant_id}/stripe/{table_name}",
        table_name,  # Direct table name
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
                            'prefix': prefix
                        })
        except Exception as e:
            print(f"Warning: Could not list files with prefix '{prefix}': {e}")
            continue
    
    return all_files


def read_parquet_file(s3_client, bucket: str, key: str) -> pd.DataFrame:
    """Read a Parquet file from S3/MinIO.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        
    Returns:
        Pandas DataFrame with the data
    """
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
        parquet_file = BytesIO(response['Body'].read())
        df = pd.read_parquet(parquet_file)
        
        # Check if data is in Airbyte format (has 'data' field with JSON strings)
        # If so, extract the actual customer records
        if 'data' in df.columns and 'stream' in df.columns:
            print(f"    Detected Airbyte format - extracting customer records from 'data' field")
            import json
            customer_records = []
            for idx, row in df.iterrows():
                try:
                    # Parse JSON from 'data' field
                    if isinstance(row['data'], str):
                        customer_data = json.loads(row['data'])
                    else:
                        customer_data = row['data']
                    customer_records.append(customer_data)
                except (json.JSONDecodeError, TypeError) as e:
                    print(f"    Warning: Could not parse record {idx}: {e}")
                    continue
            
            if customer_records:
                # Convert to DataFrame
                df = pd.DataFrame(customer_records)
                print(f"    Extracted {len(df)} customer records")
        
        return df
    except Exception as e:
        print(f"ERROR: Failed to read file {key}: {e}")
        raise


def validate_stripe_schema(df: pd.DataFrame) -> Dict[str, Any]:
    """Validate that DataFrame has expected Stripe customer fields.
    
    Args:
        df: DataFrame to validate
        
    Returns:
        Dictionary with validation results
    """
    expected_fields = {
        'id': 'string',
        'created': 'timestamp',
    }
    
    optional_fields = {
        'email', 'balance', 'object', 'address', 'currency', 
        'default_source', 'delinquent', 'description', 'discount',
        'invoice_prefix', 'invoice_settings', 'livemode', 'metadata',
        'name', 'next_invoice_sequence', 'phone', 'preferred_locales',
        'shipping', 'tax_exempt', 'test_clock'
    }
    
    results = {
        'has_required_fields': True,
        'missing_fields': [],
        'extra_fields': [],
        'field_types': {},
        'record_count': len(df),
        'validation_passed': True
    }
    
    # Check required fields
    for field, expected_type in expected_fields.items():
        if field not in df.columns:
            results['missing_fields'].append(field)
            results['has_required_fields'] = False
            results['validation_passed'] = False
        else:
            results['field_types'][field] = str(df[field].dtype)
    
    # Check for extra fields (not in expected or optional)
    all_expected = set(expected_fields.keys()) | optional_fields
    for col in df.columns:
        if col not in all_expected:
            results['extra_fields'].append(col)
    
    return results


def display_summary(files: List[Dict[str, Any]], all_data: pd.DataFrame, validation: Dict[str, Any]):
    """Display summary of Stripe data verification.
    
    Args:
        files: List of file metadata
        all_data: Combined DataFrame with all records
        validation: Validation results
    """
    print("=" * 80)
    print("STRIPE CUSTOMER DATA VERIFICATION - MINIO/S3")
    print("=" * 80)
    print()
    
    print(f"Files Found: {len(files)}")
    for i, file_info in enumerate(files, 1):
        size_mb = file_info['size'] / (1024 * 1024)
        print(f"  {i}. {file_info['key']}")
        print(f"     Size: {size_mb:.2f} MB")
        print(f"     Modified: {file_info['modified']}")
    print()
    
    print(f"Total Records: {len(all_data)}")
    print()
    
    print("Schema Validation:")
    if validation['validation_passed']:
        print("  ✓ Validation PASSED")
    else:
        print("  ✗ Validation FAILED")
    
    if validation['missing_fields']:
        print(f"  Missing required fields: {', '.join(validation['missing_fields'])}")
    
    if validation['extra_fields']:
        print(f"  Extra fields found: {', '.join(validation['extra_fields'])}")
    
    print()
    print("Field Types:")
    for field, dtype in validation['field_types'].items():
        print(f"  {field}: {dtype}")
    print()
    
    print("Sample Data (first 5 records):")
    print("-" * 80)
    # Display key fields
    display_cols = ['id', 'email', 'created', 'balance']
    available_cols = [col for col in display_cols if col in all_data.columns]
    if available_cols:
        print(all_data[available_cols].head().to_string())
    else:
        print(all_data.head().to_string())
    print()
    
    print("Data Statistics:")
    print("-" * 80)
    if 'created' in all_data.columns:
        print(f"  Created date range:")
        if all_data['created'].dtype == 'object':
            # Try to parse if it's string
            try:
                created_dates = pd.to_datetime(all_data['created'])
                print(f"    From: {created_dates.min()}")
                print(f"    To: {created_dates.max()}")
            except:
                print(f"    (Could not parse dates)")
        else:
            print(f"    From: {all_data['created'].min()}")
            print(f"    To: {all_data['created'].max()}")
    
    if 'balance' in all_data.columns:
        print(f"  Balance statistics:")
        print(f"    Min: {all_data['balance'].min()}")
        print(f"    Max: {all_data['balance'].max()}")
        print(f"    Mean: {all_data['balance'].mean():.2f}")
    
    print()
    print("=" * 80)
    
    if validation['validation_passed']:
        print("✓ VERIFICATION SUCCESSFUL: Stripe customer data is correctly stored in MinIO")
        return 0
    else:
        print("✗ VERIFICATION FAILED: Some validation checks did not pass")
        return 1


def main():
    """Main execution function."""
    # Get configuration from environment
    bucket = os.getenv("S3_BUCKET") or os.getenv("MINIO_BUCKET") or "test-bucket"
    tenant_id = os.getenv("TENANT_ID") or "testcase3"
    
    print(f"Connecting to MinIO...")
    print(f"  Bucket: {bucket}")
    print(f"  Tenant: {tenant_id}")
    print()
    
    try:
        s3_client = get_minio_client()
        
        # Test connection
        try:
            s3_client.head_bucket(Bucket=bucket)
            print("✓ Connected to MinIO successfully")
        except Exception as e:
            print(f"✗ Failed to connect to MinIO: {e}")
            return 1
        
        print()
        print("Searching for Stripe customer Parquet files...")
        files = find_stripe_files(s3_client, bucket, tenant_id)
        
        if not files:
            print("✗ No Parquet files found for Stripe customers")
            print(f"  Searched in bucket '{bucket}' with tenant '{tenant_id}'")
            return 1
        
        print(f"✓ Found {len(files)} Parquet file(s)")
        print()
        
        # Read all files and combine
        print("Reading Parquet files...")
        all_dataframes = []
        for file_info in files:
            print(f"  Reading: {file_info['key']}")
            df = read_parquet_file(s3_client, bucket, file_info['key'])
            all_dataframes.append(df)
            print(f"    Records: {len(df)}")
        
        # Combine all dataframes
        if len(all_dataframes) > 1:
            all_data = pd.concat(all_dataframes, ignore_index=True)
        else:
            all_data = all_dataframes[0]
        
        print(f"✓ Total records loaded: {len(all_data)}")
        print()
        
        # Validate schema
        print("Validating schema...")
        validation = validate_stripe_schema(all_data)
        
        # Display summary
        return display_summary(files, all_data, validation)
        
    except Exception as e:
        print(f"✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

