# Test Fixtures

This directory contains all test-related files for smoke tests, organized into two main categories:

## Directory Structure

```
tests/fixtures/
├── specs/           # Data contract definitions (ODCS YAML schemas)
│   └── csv/v1.0/   # CSV source connector contracts
├── seeds/          # Test data files (CSV files)
│   ├── adventureworks/
│   ├── employee/
│   └── music_listening/
└── datasets.yaml   # Dataset metadata registry
```

## Distinction: Assets vs Seeds

### `specs/` - Data Contracts (Configuration/Metadata)
**Purpose**: Defines the **structure and governance** of data (what the data should look like)

- **Format**: ODCS v3.0.2 YAML files
- **Content**: Schema definitions, governance metadata, compliance rules
- **Example**: `specs/csv/v1.0/person.yaml` defines the schema for Person data
- **Used by**: Tests to validate data structure and ensure governance requirements

### `seeds/` - Test Data Files (Actual Data)
**Purpose**: Contains the **actual CSV data files** used in tests (the data itself)

- **Format**: CSV files
- **Content**: Sample data rows
- **Example**: `seeds/adventureworks/Person.csv` contains actual person records
- **Used by**: Tests to perform actual ingestion operations

### `datasets.yaml` - Dataset Registry
**Purpose**: Maps CSV files to their corresponding asset definitions

- **Format**: YAML metadata
- **Content**: Dataset information, file mappings, source URLs, licenses
- **Example**: Maps `Person.csv` → `person.yaml` asset definition

## Available Datasets

### AdventureWorks
- **Source**: https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works/data-warehouse-install-script
- **License**: Microsoft SQL Server Samples
- **Description**: Sample database for a fictitious bicycle manufacturer - Data Warehouse tables
- **Files**: 30+ CSV files including:
  - Dimension tables: `DimAccount.csv`, `DimCustomer.csv`, `DimProduct.csv`, `DimDate.csv`, etc.
  - Fact tables: `FactInternetSales.csv`, `FactResellerSales.csv`, `FactFinance.csv`, etc.
  - Legacy tables: `Person.csv`, `SalesOrderHeader.csv`, `Product.csv`
  - See `seeds/adventureworks/README.md` for complete list
- **Data Contracts**: `specs/csv/v1.0/person.yaml`, `sales_order_header.yaml`, `product.yaml`

### Music Listening Data
- **Source**: https://www.kaggle.com/datasets/gabrielkahen/music-listening-data-500k-users
- **License**: MIT (see `seeds/music_listening/LICENSE.md`)
- **Description**: Music listening data for 500k users
- **Files**:
  - `seeds/music_listening/listening_history.csv` - Music listening history (10 rows)
- **Data Contract**: `specs/csv/v1.0/listening_history.yaml`

### Employee Dataset
- **Source**: https://www.kaggle.com/datasets/rockyt07/cassandra-employee-dataset
- **License**: MIT (see `seeds/employee/LICENSE.md`)
- **Description**: Employee test dataset
- **Files**:
  - `seeds/employee/Employee_Complete_Dataset.csv` - Employee records
- **Data Contract**: `specs/csv/v1.0/employee.yaml`

## Usage

These fixtures are used by smoke tests. To run smoke tests, simply execute the CLI with the test fixtures:

```bash
# Run all jobs in the fixtures directory
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets

# Or run a specific job
dativo_ingest run --config tests/fixtures/jobs/adventureworks_person_to_iceberg.yaml --secrets-dir tests/fixtures/secrets
```

## Data Contracts (ODCS v3.0.2)

All data contracts in `specs/` follow the **Open Data Contract Standard (ODCS) v3.0.2** structure:

- Follow ODCS v3.0.2 flat structure (no nested `asset:` wrapper)
- Reference the extended schema via `$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json`
- Include `apiVersion: v3.0.2` to indicate ODCS version
- Extend ODCS with dativo-specific fields: `source_type`, `object`, `target`, `compliance`, `change_management`
- Satisfy governance requirements: strong ownership, compliance, data quality monitoring, change management

See `specs/README.md` for more details on data contracts.
