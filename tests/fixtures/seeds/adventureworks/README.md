# AdventureWorks Data Warehouse Test Fixtures

This directory contains CSV files from the AdventureWorks Data Warehouse sample database.

## Source

**Repository**: https://github.com/microsoft/sql-server-samples/tree/master/samples/databases/adventure-works/data-warehouse-install-script

**License**: Microsoft SQL Server Samples (sample data for testing purposes)

## Files

### Dimension Tables (Dim*)
- `DimAccount.csv` - Account dimension
- `DimCurrency.csv` - Currency dimension
- `DimCustomer.csv` - Customer dimension
- `DimDate.csv` - Date dimension
- `DimDepartmentGroup.csv` - Department group dimension
- `DimEmployee.csv` - Employee dimension
- `DimGeography.csv` - Geography dimension
- `DimOrganization.csv` - Organization dimension
- `DimProduct.csv` - Product dimension
- `DimProductCategory.csv` - Product category dimension
- `DimProductSubcategory.csv` - Product subcategory dimension
- `DimPromotion.csv` - Promotion dimension
- `DimReseller.csv` - Reseller dimension
- `DimSalesReason.csv` - Sales reason dimension
- `DimSalesTerritory.csv` - Sales territory dimension
- `DimScenario.csv` - Scenario dimension

### Fact Tables (Fact*)
- `FactAdditionalInternationalProductDescription.csv` - Additional product descriptions
- `FactCallCenter.csv` - Call center facts
- `FactCurrencyRate.csv` - Currency rate facts
- `FactFinance.csv` - Finance facts
- `FactInternetSales.csv` - Internet sales facts
- `FactInternetSalesReason.csv` - Internet sales reason facts
- `FactProductInventory.csv` - Product inventory facts
- `FactResellerSales.csv` - Reseller sales facts
- `FactSalesQuota.csv` - Sales quota facts
- `FactSurveyResponse.csv` - Survey response facts

### Other Tables
- `DatabaseLog.csv` - Database log entries
- `NewFactCurrencyRate.csv` - New currency rate facts
- `ProspectiveBuyer.csv` - Prospective buyer data

### Legacy Tables (from original AdventureWorks)
- `Person.csv` - Person/contact data
- `SalesOrderHeader.csv` - Sales order header data
- `Product.csv` - Product catalog data

## Usage

These fixtures are used by smoke tests. The tests can validate CSV to Iceberg ingestion for any of these tables.

To test with AdventureWorks data:
```bash
# Run all jobs
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets

# Or run a specific AdventureWorks job
dativo_ingest run --config tests/fixtures/jobs/adventureworks_person_to_iceberg.yaml --secrets-dir tests/fixtures/secrets
```

