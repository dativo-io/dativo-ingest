# Test Job Configurations

This directory contains job configurations generated during smoke tests.

## Structure

- `smoke/` - Job configurations created during CSV to Iceberg smoke tests

## Generated Jobs

Job configurations are automatically generated during smoke test execution and saved here for reference. Each job configuration follows the pattern:

`{dataset_name}_{asset_name}_to_iceberg.yaml`

For example:
- `adventureworks_person_to_iceberg.yaml`
- `music_listening_listening_history_to_iceberg.yaml`
- `employee_employee_to_iceberg.yaml`

## Usage

These job configurations are created dynamically during test execution. They demonstrate how to configure CSV to Iceberg ingestion jobs for different datasets.

