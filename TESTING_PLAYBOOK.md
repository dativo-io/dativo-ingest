# Dativo-Ingest Testing Playbook

## Overview

This playbook provides step-by-step instructions for testing all major capabilities of dativo-ingest. It covers 20 comprehensive test cases organized by category, including detailed setup instructions for Stripe and HubSpot test accounts.

## Prerequisites

Before starting, ensure you have:

1. **Environment Setup**:
   ```bash
   # Run automated setup
   ./scripts/setup-dev.sh
   source .env
   ```

2. **Infrastructure Running**:
   - Docker and Docker Compose
   - Nessie catalog (http://localhost:19120)
   - MinIO object storage (http://localhost:9000)
   - PostgreSQL (optional, for database tests)
   - MySQL (optional, for database tests)

3. **Python Environment**:
   ```bash
   pip install -e .
   export PYTHONPATH=src:$PYTHONPATH
   ```

---

## Test Cases Overview

### Category 1: Basic Source Connectors (5 tests)
1. CSV to Iceberg (basic extraction)
2. CSV to MinIO (alternative target)
3. CSV to S3 (cloud storage)
4. CSV with state persistence (incremental sync)
5. CSV with strict validation (error handling)

### Category 2: Database Connectors (4 tests)
6. PostgreSQL to Iceberg (Markdown-KV format)
7. MySQL to Iceberg (Markdown-KV format)
8. PostgreSQL connection failure (error handling)
9. Database with multiple tables (batch processing)

### Category 3: API Connectors (4 tests)
10. Stripe customers to Iceberg
11. Stripe charges to Iceberg
12. HubSpot contacts to Iceberg
13. HubSpot deals to Iceberg

### Category 4: Google Services (3 tests)
14. Google Drive CSV to Iceberg (native engine)
15. Google Sheets to Iceberg (native engine)
16. Google Sheets as target (bidirectional)

### Category 5: Advanced Features (4 tests)
17. Markdown-KV source to Iceberg (LLM-optimized)
18. Custom Python plugin (JSON API reader)
19. Custom Rust plugin (high-performance CSV)
20. Catalog integration (OpenMetadata/AWS Glue)

---

## Category 1: Basic Source Connectors

### Test Case 1: CSV to Iceberg (Basic Extraction)

**Purpose**: Verify basic CSV file ingestion into Iceberg format.

**Steps**:
1. **Verify test data exists**:
   ```bash
   ls -la tests/fixtures/seeds/employee/Employee_Complete_Dataset.csv
   ```

2. **Check job configuration**:
   ```bash
   cat tests/fixtures/jobs/csv_employee_to_iceberg.yaml
   ```

3. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/csv_employee_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

4. **Verify results**:
   ```bash
   # Check MinIO bucket
   mc ls local/test-bucket/raw/csv/employee/ --recursive
   
   # Or using AWS CLI
   aws --endpoint-url=http://localhost:9000 s3 ls s3://test-bucket/raw/csv/employee/ --recursive
   ```

5. **Expected outcome**:
   - Job completes with exit code 0
   - Parquet files created in MinIO
   - Iceberg table metadata updated
   - Records match source CSV

---

### Test Case 2: CSV to MinIO (Alternative Target)

**Purpose**: Test direct MinIO storage without Iceberg catalog.

**Steps**:
1. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/csv_product_to_minio.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

2. **Verify MinIO files**:
   ```bash
   mc ls local/test-bucket/raw/csv/product/ --recursive
   ```

3. **Expected outcome**:
   - Parquet files written directly to MinIO
   - No Iceberg catalog interaction
   - Files accessible via S3 API

---

### Test Case 3: CSV to S3 (Cloud Storage)

**Purpose**: Test AWS S3 integration (can use MinIO as S3-compatible endpoint).

**Steps**:
1. **Set S3 credentials** (if using real S3):
   ```bash
   export AWS_ACCESS_KEY_ID="your-key"
   export AWS_SECRET_ACCESS_KEY="your-secret"
   export AWS_REGION="us-east-1"
   export S3_BUCKET="your-bucket"
   ```

2. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/csv_person_to_s3.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

3. **Verify S3 files**:
   ```bash
   aws s3 ls s3://${S3_BUCKET}/raw/csv/person/ --recursive
   ```

4. **Expected outcome**:
   - Files uploaded to S3
   - Correct bucket and prefix structure
   - Files accessible via AWS CLI

---

### Test Case 4: CSV with State Persistence (Incremental Sync)

**Purpose**: Test incremental sync using state management.

**Steps**:
1. **First run** (full sync):
   ```bash
   dativo run \
     --config tests/fixtures/jobs/csv_employee_state_persistence.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

2. **Check state file created**:
   ```bash
   ls -la state/test_tenant/csv_employee_state_persistence/
   cat state/test_tenant/csv_employee_state_persistence/state.json
   ```

3. **Modify source file** (add new records):
   ```bash
   # Add a new line to the CSV
   echo "999,New,Employee,new@example.com" >> tests/fixtures/seeds/employee/Employee_Complete_Dataset.csv
   ```

4. **Second run** (incremental sync):
   ```bash
   dativo run \
     --config tests/fixtures/jobs/csv_employee_state_persistence.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

5. **Verify only new data processed**:
   - Check logs for "Skipping unchanged file" messages
   - Verify state file updated with new timestamp

6. **Expected outcome**:
   - First run: Processes all records
   - Second run: Only processes changed/new files
   - State file tracks file modification times

---

### Test Case 5: CSV with Strict Validation (Error Handling)

**Purpose**: Test strict schema validation that fails on invalid data.

**Steps**:
1. **Review the job config** (should have `schema_validation_mode: strict`):
   ```bash
   cat tests/fixtures/jobs/csv_product_strict_validation.yaml
   ```

2. **Run the job** (should fail):
   ```bash
   dativo run \
     --config tests/fixtures/jobs/csv_product_strict_validation.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

3. **Verify error handling**:
   - Exit code should be 2 (validation failure)
   - Error messages indicate which records failed validation
   - No data written to target

4. **Expected outcome**:
   - Job fails with clear validation errors
   - Invalid records identified
   - No partial data written

---

## Category 2: Database Connectors

### Test Case 6: PostgreSQL to Iceberg (Markdown-KV Format)

**Purpose**: Test PostgreSQL extraction with Markdown-KV transformation.

**Prerequisites**:
- PostgreSQL running (can use Docker):
  ```bash
  docker run -d --name postgres-test \
    -e POSTGRES_PASSWORD=testpass \
    -e POSTGRES_DB=testdb \
    -p 5432:5432 \
    postgres:15
  ```

**Steps**:
1. **Load test data** (if not already loaded):
   ```bash
   # Connect to PostgreSQL and load test data
   psql -h localhost -U postgres -d testdb -f tests/fixtures/seeds/test_db/employees.sql
   ```

2. **Set PostgreSQL credentials**:
   ```bash
   export DATIVO_SECRET__TEST_TENANT__postgres__env="PGHOST=localhost\nPGPORT=5432\nPGUSER=postgres\nPGPASSWORD=testpass\nPGDATABASE=testdb"
   ```

3. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/postgres_employee_to_iceberg_markdown_kv.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

4. **Verify results**:
   - Check MinIO for Markdown-KV formatted files
   - Verify data transformation from SQL to Markdown-KV

5. **Expected outcome**:
   - PostgreSQL data extracted
   - Converted to Markdown-KV format
   - Written to Iceberg table

---

### Test Case 7: MySQL to Iceberg (Markdown-KV Format)

**Purpose**: Test MySQL extraction with Markdown-KV transformation.

**Prerequisites**:
- MySQL running (can use Docker):
  ```bash
  docker run -d --name mysql-test \
    -e MYSQL_ROOT_PASSWORD=testpass \
    -e MYSQL_DATABASE=testdb \
    -p 3306:3306 \
    mysql:8.0
  ```

**Steps**:
1. **Load test data**:
   ```bash
   mysql -h localhost -u root -ptestpass testdb < tests/fixtures/seeds/test_db/employees.sql
   ```

2. **Set MySQL credentials**:
   ```bash
   export DATIVO_SECRET__TEST_TENANT__mysql__env="MYSQL_HOST=localhost\nMYSQL_PORT=3306\nMYSQL_USER=root\nMYSQL_PASSWORD=testpass\nMYSQL_DATABASE=testdb"
   ```

3. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/mysql_employees_to_iceberg_markdown_kv.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

4. **Expected outcome**:
   - MySQL data extracted
   - Converted to Markdown-KV format
   - Written to Iceberg table

---

### Test Case 8: PostgreSQL Connection Failure (Error Handling)

**Purpose**: Test error handling when database connection fails.

**Steps**:
1. **Stop PostgreSQL** (if running):
   ```bash
   docker stop postgres-test
   ```

2. **Run the job** (should fail):
   ```bash
   dativo run \
     --config tests/fixtures/jobs/postgres_connection_failure.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

3. **Verify error handling**:
   - Exit code should be 2
   - Clear error message about connection failure
   - No partial data written

4. **Expected outcome**:
   - Job fails gracefully with connection error
   - Error message is clear and actionable

---

### Test Case 9: Database with Multiple Tables (Batch Processing)

**Purpose**: Test extracting multiple tables in a single job.

**Steps**:
1. **Create a job config** with multiple objects:
   ```yaml
   source:
     objects: [employees, departments, salaries]
   ```

2. **Run the job**:
   ```bash
   dativo run \
     --config jobs/test_tenant/multi_table_job.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

3. **Verify all tables extracted**:
   - Check MinIO for separate prefixes per table
   - Verify all tables have data

4. **Expected outcome**:
   - All specified tables extracted
   - Separate Iceberg tables created
   - Correct data in each table

---

## Category 3: API Connectors

### Test Case 10: Stripe Customers to Iceberg

**Purpose**: Test Stripe API integration for customer data extraction.

**Prerequisites - Stripe Test Account Setup**:

1. **Create Stripe Account**:
   - Go to https://stripe.com
   - Click "Start now" or "Sign in"
   - Create a free account (no credit card required for test mode)

2. **Get Test API Key**:
   - Log into Stripe Dashboard
   - Go to **Developers** → **API keys**
   - Copy the **Test mode** secret key (starts with `sk_test_`)
   - Also note the publishable key (starts with `pk_test_`) for reference

3. **Create Test Data in Stripe**:
   
   **Option A: Using Stripe Dashboard**:
   - Go to **Customers** → **Add customer**
   - Create 3-5 test customers with:
     - Name
     - Email
     - Phone (optional)
     - Address (optional)
   
   **Option B: Using Stripe CLI** (recommended for automation):
   ```bash
   # Install Stripe CLI
   # macOS: brew install stripe/stripe-cli/stripe
   # Linux: Download from https://github.com/stripe/stripe-cli/releases
   
   # Login to Stripe
   stripe login
   
   # Create test customers
   stripe customers create --email="test1@example.com" --name="Test Customer 1"
   stripe customers create --email="test2@example.com" --name="Test Customer 2"
   stripe customers create --email="test3@example.com" --name="Test Customer 3"
   
   # Create test charges
   stripe charges create --amount=2000 --currency=usd --customer=<customer_id>
   
   # Create test invoices
   stripe invoices create --customer=<customer_id>
   ```

   **Option C: Using Python Script**:
   ```python
   import stripe
   
   stripe.api_key = "sk_test_your_key_here"
   
   # Create customers
   customers = []
   for i in range(5):
       customer = stripe.Customer.create(
           email=f"test{i}@example.com",
           name=f"Test Customer {i}",
           description=f"Test customer for dativo-ingest testing"
       )
       customers.append(customer)
       print(f"Created customer: {customer.id}")
   
   # Create charges
   for customer in customers:
       charge = stripe.Charge.create(
           amount=2000,  # $20.00
           currency="usd",
           customer=customer.id,
           description="Test charge"
       )
       print(f"Created charge: {charge.id}")
   ```

4. **Set Stripe API Key**:
   ```bash
   export DATIVO_SECRET__TEST_TENANT__stripe_api_key__text="sk_test_your_actual_key_here"
   # Or using filesystem secrets:
   echo "sk_test_your_actual_key_here" > tests/fixtures/secrets/test_tenant/stripe_api_key
   ```

**Test Execution Steps**:

1. **Verify credentials**:
   ```bash
   dativo check \
     --config tests/fixtures/jobs/stripe_customers_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted \
     --verbose
   ```

2. **Discover available streams**:
   ```bash
   dativo discover \
     --config tests/fixtures/jobs/stripe_customers_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted \
     --verbose
   ```

3. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/stripe_customers_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

4. **Verify results**:
   ```bash
   # Check MinIO for Parquet files
   mc ls local/test-bucket/raw/stripe/customers/ --recursive
   
   # Verify data matches Stripe API
   ```

5. **Expected outcome**:
   - Customers extracted from Stripe API
   - Data written to Iceberg table
   - Incremental sync works (only new customers on subsequent runs)

---

### Test Case 11: Stripe Charges to Iceberg

**Purpose**: Test Stripe charges/transactions extraction.

**Steps**:
1. **Create test charges** (if not already created):
   ```bash
   # Using Stripe CLI
   stripe charges create --amount=5000 --currency=usd --source=tok_visa
   ```

2. **Create job config** for charges:
   ```yaml
   source:
     objects: [charges]
     incremental:
       strategy: created
       cursor_field: created
       lookback_days: 7
   ```

3. **Run the job**:
   ```bash
   dativo run \
     --config jobs/test_tenant/stripe_charges_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

4. **Expected outcome**:
   - Charges extracted from Stripe
   - Transaction data in Iceberg table
   - Incremental sync based on creation date

---

### Test Case 12: HubSpot Contacts to Iceberg

**Purpose**: Test HubSpot CRM API integration for contacts.

**Prerequisites - HubSpot Test Account Setup**:

1. **Create HubSpot Account**:
   - Go to https://www.hubspot.com
   - Click "Get started free"
   - Create a free account (no credit card required)
   - Complete the onboarding process

2. **Get API Key**:
   - Log into HubSpot
   - Go to **Settings** (gear icon) → **Integrations** → **Private Apps**
   - Click **Create a private app**
   - Name it "Dativo Test App"
   - Go to **Scopes** tab and enable:
     - `crm.objects.contacts.read`
     - `crm.objects.deals.read`
     - `crm.objects.companies.read`
   - Click **Create app**
   - Copy the **API key** (starts with `pat-na1-` or similar)

3. **Create Test Data in HubSpot**:
   
   **Option A: Using HubSpot Dashboard**:
   - Go to **Contacts** → **Create contact**
   - Create 5-10 test contacts with:
     - First name
     - Last name
     - Email
     - Phone
     - Company
     - Lifecycle stage
   
   **Option B: Using HubSpot API** (recommended):
   ```bash
   # Set your API key
   export HUBSPOT_API_KEY="pat-na1-your-key-here"
   
   # Create contacts using curl
   curl -X POST "https://api.hubapi.com/crm/v3/objects/contacts" \
     -H "Authorization: Bearer $HUBSPOT_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "properties": {
         "email": "test1@example.com",
         "firstname": "Test",
         "lastname": "Contact 1",
         "phone": "+1234567890",
         "company": "Test Company"
       }
     }'
   ```

   **Option C: Using Python Script**:
   ```python
   import requests
   
   API_KEY = "pat-na1-your-key-here"
   headers = {
       "Authorization": f"Bearer {API_KEY}",
       "Content-Type": "application/json"
   }
   
   # Create contacts
   for i in range(10):
       data = {
           "properties": {
               "email": f"test{i}@example.com",
               "firstname": f"Test",
               "lastname": f"Contact {i}",
               "phone": f"+123456789{i}",
               "company": f"Test Company {i}",
               "lifecyclestage": "customer"
           }
       }
       response = requests.post(
           "https://api.hubapi.com/crm/v3/objects/contacts",
           headers=headers,
           json=data
       )
       print(f"Created contact: {response.json()}")
   
   # Create deals
   for i in range(5):
       data = {
           "properties": {
               "dealname": f"Test Deal {i}",
               "dealstage": "qualifiedtobuy",
               "amount": str(1000 * (i + 1)),
               "closedate": "2024-12-31"
           }
       }
       response = requests.post(
           "https://api.hubapi.com/crm/v3/objects/deals",
           headers=headers,
           json=data
       )
       print(f"Created deal: {response.json()}")
   
   # Create companies
   for i in range(5):
       data = {
           "properties": {
               "name": f"Test Company {i}",
               "domain": f"testcompany{i}.com",
               "industry": "Technology"
           }
       }
       response = requests.post(
           "https://api.hubapi.com/crm/v3/objects/companies",
           headers=headers,
           json=data
       )
       print(f"Created company: {response.json()}")
   ```

4. **Set HubSpot API Key**:
   ```bash
   export DATIVO_SECRET__TEST_TENANT__hubspot_api_key__text="pat-na1-your_actual_key_here"
   # Or using filesystem secrets:
   echo "pat-na1-your_actual_key_here" > tests/fixtures/secrets/test_tenant/hubspot_api_key
   ```

**Test Execution Steps**:

1. **Verify credentials**:
   ```bash
   dativo check \
     --config tests/fixtures/jobs/hubspot_contacts_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted \
     --verbose
   ```

2. **Discover available streams**:
   ```bash
   dativo discover \
     --config tests/fixtures/jobs/hubspot_contacts_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted \
     --verbose
   ```

3. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/hubspot_contacts_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

4. **Verify results**:
   ```bash
   # Check MinIO for Parquet files
   mc ls local/test-bucket/raw/hubspot/contacts/ --recursive
   ```

5. **Expected outcome**:
   - Contacts extracted from HubSpot API
   - Data written to Iceberg table
   - Incremental sync works (only updated contacts on subsequent runs)

---

### Test Case 13: HubSpot Deals to Iceberg

**Purpose**: Test HubSpot deals/opportunities extraction.

**Steps**:
1. **Create test deals** (if not already created, see HubSpot setup above)

2. **Create job config** for deals:
   ```yaml
   source:
     objects: [deals]
     incremental:
       strategy: updated_after
       cursor_field: updatedAt
       lookback_days: 7
   ```

3. **Run the job**:
   ```bash
   dativo run \
     --config jobs/test_tenant/hubspot_deals_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

4. **Expected outcome**:
   - Deals extracted from HubSpot
   - Deal data in Iceberg table
   - Incremental sync based on update timestamp

---

## Category 4: Google Services

### Test Case 14: Google Drive CSV to Iceberg (Native Engine)

**Purpose**: Test Google Drive CSV file extraction using native engine.

**Prerequisites**:
1. **Google Cloud Project Setup**:
   - Go to https://console.cloud.google.com
   - Create a new project or select existing
   - Enable **Google Drive API**

2. **Create Service Account**:
   - Go to **IAM & Admin** → **Service Accounts**
   - Click **Create Service Account**
   - Name: "dativo-test"
   - Grant role: **Editor** (or minimal required permissions)
   - Click **Create Key** → **JSON**
   - Download the JSON key file

3. **Share Google Drive File**:
   - Upload a CSV file to Google Drive
   - Right-click → **Share**
   - Add the service account email (from JSON key file)
   - Grant **Viewer** access

4. **Set Credentials**:
   ```bash
   export DATIVO_SECRET__TEST_TENANT__google_credentials__json='{"type":"service_account","project_id":"..."}'
   # Or save JSON to file and reference it
   ```

**Steps**:
1. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/gdrive_csv_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

2. **Expected outcome**:
   - CSV file downloaded from Google Drive
   - Data extracted and written to Iceberg

---

### Test Case 15: Google Sheets to Iceberg (Native Engine)

**Purpose**: Test Google Sheets extraction using native engine.

**Prerequisites**:
- Same Google Cloud setup as Test Case 14
- Create a Google Sheet with test data
- Share with service account

**Steps**:
1. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/google_sheets_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

2. **Expected outcome**:
   - Google Sheet data extracted
   - Written to Iceberg table

---

### Test Case 16: Iceberg to Google Sheets (Bidirectional Connector)

**Purpose**: Test writing data back to Google Sheets (target connector).

**Steps**:
1. **Create a Google Sheet** (destination)

2. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/iceberg_to_google_sheets.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

3. **Verify Google Sheet updated**:
   - Check the sheet has new data

4. **Expected outcome**:
   - Data written from Iceberg to Google Sheets
   - Sheet updated with new rows

---

## Category 5: Advanced Features

### Test Case 17: Markdown-KV Source to Iceberg (LLM-Optimized)

**Purpose**: Test Markdown-KV format for LLM-optimized data ingestion.

**Steps**:
1. **Review Markdown-KV source file**:
   ```bash
   cat tests/fixtures/seeds/markdown_kv/*.md
   ```

2. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/markdown_kv_source_to_iceberg.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

3. **Verify Markdown-KV storage**:
   - Check storage mode (string, raw_file, or structured)
   - Verify data format in Iceberg

4. **Expected outcome**:
   - Markdown-KV files parsed
   - Data stored in LLM-friendly format
   - Preserves key-value structure

---

### Test Case 18: Custom Python Plugin (JSON API Reader)

**Purpose**: Test custom Python reader plugin.

**Steps**:
1. **Review plugin code**:
   ```bash
   cat examples/plugins/json_api_reader.py
   ```

2. **Create job config** using custom plugin:
   ```yaml
   source:
     custom_reader: "/app/examples/plugins/json_api_reader.py:JSONAPIReader"
     connection:
       base_url: "https://api.example.com"
   ```

3. **Run the job**:
   ```bash
   dativo run \
     --config examples/jobs/custom_plugin_example.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

4. **Expected outcome**:
   - Custom plugin loaded
   - Data extracted using custom logic
   - Written to target

---

### Test Case 19: Custom Rust Plugin (High-Performance CSV)

**Purpose**: Test Rust plugin for performance optimization.

**Prerequisites**:
- Rust installed: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh`

**Steps**:
1. **Build Rust plugin**:
   ```bash
   cd examples/plugins/rust
   make build-release
   ```

2. **Run the job**:
   ```bash
   dativo run \
     --config examples/jobs/rust_plugin_example_full.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

3. **Compare performance**:
   - Note execution time
   - Compare with Python plugin version

4. **Expected outcome**:
   - Rust plugin loads successfully
   - 10-100x performance improvement
   - Lower memory usage

---

### Test Case 20: Catalog Integration (OpenMetadata/AWS Glue)

**Purpose**: Test data catalog integration for lineage tracking.

**Prerequisites**:
- OpenMetadata running (Docker):
  ```bash
  docker run -d --name openmetadata \
    -p 8585:8585 \
    openmetadata/openmetadata-server:latest
  ```

**Steps**:
1. **Create job config with catalog**:
   ```yaml
   catalog:
     type: openmetadata
     connection:
       api_url: "http://localhost:8585/api"
     database: test_database
     push_lineage: true
     push_metadata: true
   ```

2. **Run the job**:
   ```bash
   dativo run \
     --config tests/fixtures/jobs/csv_employee_to_iceberg_with_catalog.yaml \
     --secrets-dir tests/fixtures/secrets \
     --mode self_hosted
   ```

3. **Verify catalog**:
   - Check OpenMetadata UI: http://localhost:8585
   - Verify table created
   - Check lineage information

4. **Expected outcome**:
   - Table metadata in catalog
   - Lineage tracked (source → target)
   - Tags and owners propagated

---

## Running All Tests

### Quick Test Suite

Run all smoke tests at once:

```bash
# Run all smoke tests
make test-smoke

# Or directly
./tests/smoke_tests.sh
```

### Selective Testing

Run tests by category:

```bash
# Basic connectors only
dativo run --job-dir tests/fixtures/jobs \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted \
  --job csv_employee_to_iceberg.yaml \
  --job csv_product_to_minio.yaml

# API connectors only (requires credentials)
dativo run --job-dir tests/fixtures/jobs \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted \
  --job stripe_customers_to_iceberg.yaml \
  --job hubspot_contacts_to_iceberg.yaml
```

---

## Troubleshooting

### Common Issues

1. **"Connection refused" errors**:
   - Check Docker containers: `docker ps`
   - Restart services: `docker-compose -f docker-compose.dev.yml restart`

2. **"API key invalid" errors**:
   - Verify credentials: `dativo check --config <job> --verbose`
   - Check secret manager configuration

3. **"File not found" errors**:
   - Verify test data exists: `ls -la tests/fixtures/seeds/`
   - Check file paths in job configs

4. **"Schema validation failed"**:
   - Review asset definition schema
   - Check data types match schema
   - Use `--schema-validation-mode warn` for debugging

### Debug Mode

Enable verbose logging:

```bash
dativo run --config <job> \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted \
  --logging-level DEBUG
```

---

## Test Data Management

### Creating Test Data

1. **CSV files**: Place in `tests/fixtures/seeds/`
2. **Database data**: Use SQL scripts in `tests/fixtures/seeds/test_db/`
3. **API data**: Use test accounts (Stripe/HubSpot)

### Cleaning Up

```bash
# Clean MinIO bucket
mc rm local/test-bucket --recursive --force

# Clean state files
rm -rf state/test_tenant/*

# Reset Docker containers
docker-compose -f docker-compose.dev.yml down -v
```

---

## Next Steps

After completing these tests:

1. **Explore Custom Plugins**: Create your own readers/writers
2. **Performance Testing**: Benchmark with large datasets
3. **Production Setup**: Configure for production use
4. **Monitoring**: Set up observability and alerting

---

## Additional Resources

- [README.md](README.md) - Project overview
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) - Configuration reference
- [docs/CUSTOM_PLUGINS.md](docs/CUSTOM_PLUGINS.md) - Custom plugins guide
- [tests/README.md](tests/README.md) - Testing documentation

---

## Summary

This playbook covers 20 comprehensive test cases across:
- ✅ 5 Basic source connector tests
- ✅ 4 Database connector tests
- ✅ 4 API connector tests (with Stripe/HubSpot setup guides)
- ✅ 3 Google services tests
- ✅ 4 Advanced feature tests

Each test includes step-by-step instructions, expected outcomes, and troubleshooting tips. Follow the playbook systematically to validate all capabilities of dativo-ingest.
