# Test Fixtures

This directory contains sample CSV data files for smoke testing CSV to Iceberg ingestion.

## Available Datasets

### AdventureWorks
- **Source**: https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works/data-warehouse-install-script
- **License**: Microsoft SQL Server Samples
- **Description**: Sample database for a fictitious bicycle manufacturer - Data Warehouse tables
- **Files**: 30+ CSV files including:
  - Dimension tables: `DimAccount.csv`, `DimCustomer.csv`, `DimProduct.csv`, `DimDate.csv`, etc.
  - Fact tables: `FactInternetSales.csv`, `FactResellerSales.csv`, `FactFinance.csv`, etc.
  - Legacy tables: `Person.csv`, `SalesOrderHeader.csv`, `Product.csv`
  - See `adventureworks/README.md` for complete list

### Music Listening Data
- **Source**: https://www.kaggle.com/datasets/gabrielkahen/music-listening-data-500k-users
- **License**: MIT (see `music_listening/LICENSE.md`)
- **Description**: Music listening data for 500k users
- **Files**:
  - `listening_history.csv` - Music listening history (10 rows)

### Employee Dataset
- **Source**: https://www.kaggle.com/datasets/rockyt07/cassandra-employee-dataset
- **License**: MIT (see `employee/LICENSE.md`)
- **Description**: Employee test dataset
- **Files**:
  - `Employee_Complete_Dataset.csv` - Employee records

## Usage

These fixtures are used by smoke tests in `test_smoke_csv_to_iceberg.py`. You can select which dataset to test:

```bash
# Run all datasets
pytest tests/test_smoke_csv_to_iceberg.py -v

# Run specific dataset using marker
pytest tests/test_smoke_csv_to_iceberg.py -m adventureworks -v
pytest tests/test_smoke_csv_to_iceberg.py -m music_listening -v
pytest tests/test_smoke_csv_to_iceberg.py -m employee -v

# Run specific dataset using command line flag
pytest tests/test_smoke_csv_to_iceberg.py --dataset=adventureworks -v
pytest tests/test_smoke_csv_to_iceberg.py --dataset=music_listening -v
pytest tests/test_smoke_csv_to_iceberg.py --dataset=employee -v
```

## Dataset Registry

Dataset metadata is defined in `datasets.yaml`, which includes:
- Dataset name and description
- Source URL
- License information
- Asset mappings (CSV files to asset definitions)
