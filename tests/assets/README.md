# Test Asset Definitions

This directory contains asset definitions specifically for smoke tests.

## Structure

- `csv/v1.0/` - Asset definitions for CSV source connectors used in smoke tests

## Asset Definitions

### AdventureWorks Assets
- `person.yaml` - Person/contact data schema
- `sales_order_header.yaml` - Sales order header schema
- `product.yaml` - Product catalog schema

### Music Listening Assets
- `listening_history.yaml` - Music listening history schema

### Employee Assets
- `employee.yaml` - Employee dataset schema

## Usage

These asset definitions are used by smoke tests in `test_smoke_csv_to_iceberg.py`. They are separate from production asset definitions to ensure test isolation.

