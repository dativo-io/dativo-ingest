# Dativo-Ingest Testing Playbook
## Comprehensive Guide for Real-World Testing

This playbook covers 21 real-world test cases to validate all capabilities of dativo-ingest, including setup instructions for Stripe and HubSpot test accounts.

---

## Table of Contents
1. [Prerequisites & Setup](#prerequisites--setup)
2. [Test Account Setup (Stripe & HubSpot)](#test-account-setup)
3. [Top 21 Test Cases](#top-21-test-cases)
4. [Advanced Testing Scenarios](#advanced-testing-scenarios)

---

## Prerequisites & Setup

### Prerequisites Checklist

Before starting, ensure you have:
- **Python 3.10 or higher** (Python 3.9 and below will NOT work)
- Docker and Docker Compose
- Git

**Check Python version:**
```bash
python3 --version  # Should show 3.10.x or higher
```

If you have Python 3.9 or below, see [docs/python-setup.md](docs/python-setup.md) for upgrade instructions.

### 1. Environment Setup (5 minutes)

```bash
# 1. Clone and navigate to the repository
cd /path/to/dativo-ingest

# 2. Run automated setup script
# This will:
#   - Create a virtual environment (venv) with Python 3.10+
#   - Install all dependencies
#   - Start Docker services (Nessie, MinIO, PostgreSQL)
#   - Create necessary directories and buckets
./scripts/setup-dev.sh

# 3. Activate virtual environment (IMPORTANT!)
# The setup script activates it, but if you open a new terminal, you need to activate it again:
source venv/bin/activate

# You should see (venv) in your prompt after activation
# Example: (venv) user@hostname dativo-ingest %

# 4. Source environment variables
source .env

# 5. Verify services are running
docker ps | grep -E '(nessie|minio|postgres)'
```

**Important Notes:**
- The `dativo` command is only available when the virtual environment is activated
- If you see "command not found: dativo", activate the venv: `source venv/bin/activate`
- Each new terminal session requires reactivating the venv

### 2. Verify Installation

```bash
# 1. Verify virtual environment is activated
# Check that (venv) appears in your prompt, or:
which python  # Should show: .../dativo-ingest/venv/bin/python
python --version  # Should show Python 3.10+ (not 3.9 or below)

# 2. Test CLI command
dativo --help

# If "command not found", activate venv:
# source venv/bin/activate

# Alternative: Use Python module directly (works without venv activation)
python -m dativo_ingest.cli --help

# 3. Check infrastructure services
curl http://localhost:19120/api/v1/config  # Nessie
curl http://localhost:9000/minio/health/live  # MinIO

# 4. MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
```

### 3. Troubleshooting Common Issues

**Issue: "command not found: dativo"**

**Solution:** Activate the virtual environment:
```bash
source venv/bin/activate
```

**Issue: "Python 3.9.x" when running `python --version`**

**Solution:** You're not using the venv's Python. Activate the venv:
```bash
source venv/bin/activate
python --version  # Should now show 3.10+
```

**Issue: Virtual environment not found**

**Solution:** Run the setup script to create it:
```bash
./scripts/setup-dev.sh
```

**Issue: Services not starting**

**Solution:** Check Docker is running and start services manually:
```bash
docker ps  # Verify Docker is running
docker-compose -f docker-compose.dev.yml up -d
```

**Alternative: Run without activating venv**

If you prefer not to activate the venv, you can use the Python module directly:
```bash
# Instead of: dativo ingest --config ...
venv/bin/python -m dativo_ingest.cli ingest --config ...
```

---

## Test Account Setup

### Setting Up Stripe Test Account

Stripe provides a comprehensive test environment with no real money involved.

#### Step 1: Create Stripe Account
1. Go to https://stripe.com
2. Click "Sign up" (free, no credit card required)
3. Complete registration with your email

#### Step 2: Access Test Mode
1. After login, ensure you're in **Test Mode** (toggle in top-right corner)
2. Test mode has orange indicator - **NEVER use Live mode for testing**

#### Step 3: Get API Keys
1. Click "Developers" in the left menu
2. Click "API keys"
3. Copy your **Secret key** (starts with `sk_test_`)
4. Store it securely - you'll need it for dativo-ingest

#### Step 4: Generate Test Data
Stripe automatically provides test data, but you can create more:

```bash
# Install Stripe CLI (optional but helpful)
brew install stripe/stripe-cli/stripe  # Mac
# or
snap install stripe  # Linux

# Login to Stripe CLI
stripe login

# Generate test customers
stripe customers create --email=customer1@example.com --name="Test Customer 1"
stripe customers create --email=customer2@example.com --name="Test Customer 2"

# Generate test charges
stripe charges create --amount=5000 --currency=usd --source=tok_visa --description="Test charge"

# Generate test invoices
stripe invoices create --customer=$(stripe customers list --limit=1 | grep 'id' | cut -d'"' -f4)
```

**Alternative: Use Stripe Dashboard**
1. Go to "Customers" → "Add customer" to create test customers
2. Go to "Payments" → "New payment" to create test charges
3. Go to "Subscriptions" → create test subscriptions

#### Test Credit Cards (for test mode only)
- Success: `4242 4242 4242 4242`
- Decline: `4000 0000 0000 0002`
- Any future expiry date, any CVC

### Setting Up HubSpot Test Account

HubSpot offers a free tier perfect for testing.

#### Step 1: Create Free HubSpot Account
1. Go to https://www.hubspot.com/products/get-started
2. Click "Get started free"
3. Complete registration (requires email verification)

#### Step 2: Complete Onboarding
1. Choose "Marketing Hub" or "CRM"
2. Select "Self" (for testing purposes)
3. Skip team invitations

#### Step 3: Get API Key
**Option A: Private App (Recommended)**
1. Click Settings (gear icon in top-right)
2. Navigate to "Integrations" → "Private Apps"
3. Click "Create private app"
4. Name it "Dativo Test"
5. Set Scopes:
   - `crm.objects.contacts.read`
   - `crm.objects.companies.read`
   - `crm.objects.deals.read`
6. Click "Create app" and copy the access token

**Option B: API Key (Legacy)**
1. Settings → "Integrations" → "API Key"
2. Click "Show" to reveal key (starts with `pat-na1-` or similar)

#### Step 4: Generate Test Data
1. **Add Contacts:**
   - Go to "Contacts" → "Create contact"
   - Add test contacts with:
     - Email: testcontact1@example.com
     - First Name: Test
     - Last Name: Contact 1
     - Phone: (555) 123-4567
   - Create 5-10 test contacts

2. **Add Companies:**
   - Go to "Contacts" → "Companies" → "Create company"
   - Add test companies:
     - Name: Acme Corp Test
     - Domain: acme-test.com
     - Industry: Technology
   - Create 3-5 test companies

3. **Add Deals:**
   - Go to "Sales" → "Deals" → "Create deal"
   - Add test deals:
     - Deal Name: Test Deal 1
     - Amount: $10,000
     - Close Date: Next month
     - Stage: Qualified
   - Create 3-5 test deals

4. **Link Contacts to Companies:**
   - Open a contact
   - Click "Add" next to "Associated Company"
   - Select a test company

**Quick Data Generation Script (using HubSpot API):**
```bash
# Set your API key
export HUBSPOT_API_KEY="your_key_here"

# Create contacts
for i in {1..5}; do
  curl -X POST "https://api.hubapi.com/crm/v3/objects/contacts" \
    -H "Authorization: Bearer $HUBSPOT_API_KEY" \
    -H "Content-Type: application/json" \
    -d "{
      \"properties\": {
        \"email\": \"testcontact${i}@example.com\",
        \"firstname\": \"Test${i}\",
        \"lastname\": \"Contact\",
        \"phone\": \"555-100-000${i}\"
      }
    }"
done

# Create companies
curl -X POST "https://api.hubapi.com/crm/v3/objects/companies" \
  -H "Authorization: Bearer $HUBSPOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "properties": {
      "name": "Acme Test Corp",
      "domain": "acme-test.com",
      "industry": "Technology"
    }
  }'
```

---

## Top 21 Test Cases

> **⚠️ Important:** Before running any test case, ensure your virtual environment is activated:
> ```bash
> source venv/bin/activate
> ```
> If you see "command not found: dativo", the venv is not activated. See [Prerequisites & Setup](#prerequisites--setup) for details.

### Test Case 1: Basic CSV to Iceberg Ingestion
**Purpose:** Validate basic ETL pipeline with Parquet writing and Iceberg integration

**Steps:**
```bash
# 1. Prepare test data
mkdir -p data/test_case_1
cat > data/test_case_1/employees.csv << 'EOF'
id,name,email,department,salary
1,John Doe,john@example.com,Engineering,120000
2,Jane Smith,jane@example.com,Marketing,95000
3,Bob Johnson,bob@example.com,Sales,85000
EOF

# 2. Create asset definition
mkdir -p assets/examples/csv/v1.0
cat > assets/examples/csv/v1.0/employees.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: employees
version: "1.0"
source_type: csv
object: employees
schema:
  - name: id
    type: integer
    required: true
  - name: name
    type: string
    required: true
  - name: email
    type: string
    required: true
  - name: department
    type: string
  - name: salary
    type: integer
target:
  file_format: parquet
  partitioning: [ingest_date]
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 3. Create job config
mkdir -p jobs/testcase1
cat > jobs/testcase1/employees_to_iceberg.yaml << 'EOF'
tenant_id: testcase1
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: assets/examples/csv/v1.0/employees.yaml
source:
  files:
    - path: data/test_case_1/employees.csv
      object: employees
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 4. Create secrets
mkdir -p secrets/testcase1
cat > secrets/testcase1/iceberg.env << 'EOF'
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
NESSIE_URI=http://localhost:19120/api/v1
EOF

# 5. Run the job
dativo ingest \
  --config jobs/testcase1/employees_to_iceberg.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 6. Verify results
mc ls local/test-bucket/testcase1/employees/ --recursive

# Expected: Parquet files with Hive-style partitioning (ingest_date=YYYY-MM-DD)
```

**Success Criteria:**
- ✅ Exit code 0
- ✅ Parquet files created in MinIO at `testcase1/employees/ingest_date=YYYY-MM-DD/`
- ✅ Files are 128-200 MB (or smaller for small datasets)
- ✅ Schema matches asset definition
- ✅ Iceberg table registered in Nessie (if catalog working)

---

### Test Case 2: Incremental Sync with State Persistence
**Purpose:** Test incremental loading with state tracking

**Steps:**
```bash
# 1. Create directory and initial dataset
mkdir -p data/test_case_2
cat > data/test_case_2/orders_initial.csv << 'EOF'
order_id,customer_id,order_date,amount,updated_at
1001,501,2025-01-01,150.50,2025-01-01T10:00:00Z
1002,502,2025-01-02,275.00,2025-01-02T11:00:00Z
1003,503,2025-01-03,89.99,2025-01-03T12:00:00Z
EOF

# 2. Create asset
cat > assets/examples/csv/v1.0/orders.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: orders
version: "1.0"
source_type: csv
object: orders
schema:
  - name: order_id
    type: integer
    required: true
  - name: customer_id
    type: integer
  - name: order_date
    type: date
  - name: amount
    type: decimal
  - name: updated_at
    type: timestamp
    required: true
target:
  file_format: parquet
  partitioning: [ingest_date]
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 3. Create job with incremental config
mkdir -p jobs/testcase2
cat > jobs/testcase2/orders_incremental.yaml << 'EOF'
tenant_id: testcase2
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: orders
asset_path: assets/examples/csv/v1.0/orders.yaml
source:
  files:
    - path: data/test_case_2/orders.csv
      object: orders
  incremental:
    enabled: true
    strategy: file_modified_time
    lookback_days: 1
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 4. Copy initial data
cp data/test_case_2/orders_initial.csv data/test_case_2/orders.csv

# 5. First run (full sync)
mkdir -p secrets/testcase2
cp secrets/testcase1/iceberg.env secrets/testcase2/

dativo ingest \
  --config jobs/testcase2/orders_incremental.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 6. Check state file
cat .local/state/testcase2/csv.orders.state.json
# Should show file modification time tracking (e.g., "file_data/test_case_2/orders.csv": {"last_modified": "...", "file_id": "..."})

# 7. Touch the file to simulate modification (or add new records)
cat >> data/test_case_2/orders.csv << 'EOF'
1004,504,2025-01-04,199.99,2025-01-04T13:00:00Z
1005,505,2025-01-05,325.50,2025-01-05T14:00:00Z
EOF

# 8. Second run (incremental sync - will process file again since it was modified)
dativo ingest \
  --config jobs/testcase2/orders_incremental.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 9. Verify file was processed again (all 5 records should be in S3)
# Check logs for "Processing incremental sync" message
```

**Success Criteria:**
- ✅ First run processes all 3 records
- ✅ State file created with file modification time tracking
- ✅ Second run processes file again (since file was modified) - all 5 records in S3
- ✅ Note: CSV incremental sync tracks file modification time, not cursor field values
- ✅ State file updated with new file modification time

---

### Test Case 3: Stripe Customer Ingestion
**Purpose:** Ingest real customer data from Stripe test account

**Steps:**
```bash
# 1. Create Stripe connector secrets
mkdir -p secrets/testcase3
cat > secrets/testcase3/stripe.env << EOF
STRIPE_API_KEY=sk_test_YOUR_TEST_KEY_HERE
EOF

cat > secrets/testcase3/iceberg.env << 'EOF'
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
NESSIE_URI=http://localhost:19120/api/v1
EOF

# 2. Use existing Stripe asset
# assets/examples/stripe/v1.0/customers.yaml already exists

# 3. Create job
mkdir -p jobs/testcase3
cat > jobs/testcase3/stripe_customers.yaml << 'EOF'
tenant_id: testcase3
source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/examples/stripe/v1.0/customers.yaml
source:
  object: customers
  incremental:
    enabled: true
    lookback_days: 7
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 4. Test connection first
dativo check \
  --config jobs/testcase3/stripe_customers.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --verbose

# 5. Discover available Stripe objects
dativo discover \
  --config jobs/testcase3/stripe_customers.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --verbose

# 6. Run ingestion
dativo ingest \
  --config jobs/testcase3/stripe_customers.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 7. Verify data
mc ls local/test-bucket/testcase3/stripe_customers/ --recursive
```

**Success Criteria:**
- ✅ Connection check passes
- ✅ Discovers customers, charges, invoices objects
- ✅ Ingests all test customers from Stripe
- ✅ Parquet files contain customer data (id, email, name, created timestamp)

---

### Test Case 4: HubSpot CRM Data Ingestion
**Purpose:** Extract contacts, companies, and deals from HubSpot

**Steps:**
```bash
# 1. Create HubSpot secrets
mkdir -p secrets/testcase4
cat > secrets/testcase4/hubspot.env << EOF
# HubSpot Private App credentials (recommended for testing)
# Airbyte HubSpot 6.0.15+ supports Private App tokens
# From HubSpot Settings > Integrations > Private Apps
HUBSPOT_API_KEY=pat-eu1-YOUR_ACCESS_TOKEN_HERE

# Alternative: OAuth credentials (for production with refresh tokens)
# HUBSPOT_CLIENT_ID=your_oauth_client_id
# HUBSPOT_OAUTH_CLIENT_SECRET=your_oauth_client_secret
# HUBSPOT_REFRESH_TOKEN=your_refresh_token
EOF

cp secrets/testcase3/iceberg.env secrets/testcase4/

# 2. Create job directory and job for contacts
mkdir -p jobs/testcase4
cat > jobs/testcase4/hubspot_contacts.yaml << 'EOF'
tenant_id: testcase4
source_connector: hubspot
source_connector_path: connectors/hubspot.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: hubspot_contacts
asset_path: assets/examples/hubspot/v1.0/contacts.yaml
source:
  object: contacts
  incremental:
    enabled: true
    lookback_days: 7
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 3. Create job for companies
cat > jobs/testcase4/hubspot_companies.yaml << 'EOF'
tenant_id: testcase4
source_connector: hubspot
source_connector_path: connectors/hubspot.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: hubspot_companies
asset_path: assets/examples/hubspot/v1.0/companies.yaml
source:
  object: companies
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 4. Create job for deals
cat > jobs/testcase4/hubspot_deals.yaml << 'EOF'
tenant_id: testcase4
source_connector: hubspot
source_connector_path: connectors/hubspot.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: hubspot_deals
asset_path: assets/examples/hubspot/v1.0/deals.yaml
source:
  object: deals
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 5. Test connection
dativo check \
  --config jobs/testcase4/hubspot_contacts.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --verbose

# 6. Run all HubSpot jobs
dativo ingest \
  --job-dir jobs/testcase4 \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 7. Verify data
# Verify contacts
mc ls local/test-bucket/testcase4/hubspot_contacts/ --recursive
# Verify companies
mc ls local/test-bucket/testcase4/hubspot_companies/ --recursive
# Verify deals
mc ls local/test-bucket/testcase4/hubspot_deals/ --recursive
```

**Success Criteria:**
- ✅ All 3 objects (contacts, companies, deals) ingested
- ✅ Contact properties extracted (email, firstname, lastname, phone)
- ✅ Company properties extracted (name, domain, industry)
- ✅ Deal properties extracted (dealname, amount, closedate)

---

### Test Case 5: Schema Validation - Strict Mode
**Purpose:** Test strict schema validation that fails on invalid data

**Steps:**
```bash
# 1. Create directory and data with schema violations
mkdir -p data/test_case_5
cat > data/test_case_5/products_invalid.csv << 'EOF'
product_id,product_name,price,category,in_stock
1,Widget A,29.99,Electronics,true
2,Widget B,invalid_price,Electronics,true
3,,19.99,Home,false
4,Widget D,39.99,,true
EOF

# 2. Create asset definition (validation mode is set in job config, not asset)
mkdir -p assets/examples/csv/v1.0
cat > assets/examples/csv/v1.0/products.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: products
version: "1.0"
source_type: csv
object: products
schema:
  - name: product_id
    type: integer
    required: true
  - name: product_name
    type: string
    required: true
  - name: price
    type: decimal
    required: true
  - name: category
    type: string
    required: true
  - name: in_stock
    type: boolean
target:
  file_format: parquet
  partitioning: []
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 3. Create job with strict validation mode
mkdir -p jobs/testcase5 secrets/testcase5
cat > jobs/testcase5/products_strict.yaml << 'EOF'
tenant_id: testcase5
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: products
asset_path: assets/examples/csv/v1.0/products.yaml
schema_validation_mode: strict  # Fail on any validation error
source:
  files:
    - path: data/test_case_5/products_invalid.csv
      object: products
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

cp secrets/testcase1/iceberg.env secrets/testcase5/

# 4. Run job (expect failure)
dativo ingest \
  --config jobs/testcase5/products_strict.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# Expected: Exit code 2 (validation errors)
# Expected: Logs show validation errors for rows 2, 3, 4

# 5. Fix data and re-run
cat > data/test_case_5/products_valid.csv << 'EOF'
product_id,product_name,price,category,in_stock
1,Widget A,29.99,Electronics,true
2,Widget B,49.99,Electronics,true
3,Widget C,19.99,Home,false
4,Widget D,39.99,Home,true
EOF

# 6. Update job config to use valid file
# On macOS, use: sed -i '' 's/products_invalid/products_valid/g' jobs/testcase5/products_strict.yaml
# On Linux, use: sed -i 's/products_invalid/products_valid/g' jobs/testcase5/products_strict.yaml
sed -i '' 's/products_invalid/products_valid/g' jobs/testcase5/products_strict.yaml 2>/dev/null || sed -i 's/products_invalid/products_valid/g' jobs/testcase5/products_strict.yaml

# 7. Run again
dativo ingest \
  --config jobs/testcase5/products_strict.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# Expected: Exit code 0
```

**Success Criteria:**
- ✅ First run fails with validation errors
- ✅ Logs clearly identify invalid rows and reasons
- ✅ No Parquet files written on validation failure
- ✅ Second run with valid data succeeds

---

### Test Case 6: Schema Validation - Warn Mode
**Purpose:** Test warn mode that logs errors but continues processing

**Steps:**
```bash
# 1. Create asset definition (validation mode is set in job config, not asset)
mkdir -p assets/examples/csv/v1.0
cat > assets/examples/csv/v1.0/products_warn.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: products_warn
version: "1.0"
source_type: csv
object: products
schema:
  - name: product_id
    type: integer
    required: true
  - name: product_name
    type: string
    required: true
  - name: price
    type: decimal
    required: true
  - name: category
    type: string
    required: false  # Allow nulls
  - name: in_stock
    type: boolean
target:
  file_format: parquet
  partitioning: []
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 2. Create job with warn validation mode
mkdir -p jobs/testcase6 secrets/testcase6
cat > jobs/testcase6/products_warn.yaml << 'EOF'
tenant_id: testcase6
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: products_warn
asset_path: assets/examples/csv/v1.0/products_warn.yaml
schema_validation_mode: warn  # Log warnings but continue processing
source:
  files:
    - path: data/test_case_5/products_invalid.csv
      object: products
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

cp secrets/testcase1/iceberg.env secrets/testcase6/

# 3. Run job
dativo ingest \
  --config jobs/testcase6/products_warn.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# Expected: Exit code 2 (warnings present) but files written
# Expected: Logs show warnings for invalid data

# 4. Verify files were created despite warnings
mc ls local/test-bucket/testcase6/products/ --recursive
```

**Success Criteria:**
- ✅ Job completes with exit code 2 (warnings)
- ✅ Warnings logged for invalid rows
- ✅ Parquet files created with valid rows only
- ✅ Invalid rows skipped but logged

---

### Test Case 7: PostgreSQL to Iceberg (Full Table Sync)
**Purpose:** Extract full table from PostgreSQL

**Steps:**
```bash
# 1. Verify PostgreSQL is running (from docker-compose)
docker ps | grep postgres

# Identify the correct container name if you have multiple postgres containers:
# docker ps --filter "name=postgres" --format "{{.Names}}\t{{.Ports}}"
# Use the container name that matches your docker-compose setup (typically 'dativo-postgres')
# If your container has a different name, replace 'dativo-postgres' in the commands below

# 2. Setup PostgreSQL employees table
# Run the testing playbook setup script to create the employees table with test data
./scripts/testing-playbook-setup-postgres-employees.sh

# Alternative: Manual setup (if script doesn't work with your setup)
# docker exec -i dativo-postgres psql -U postgres << 'EOF'
# CREATE TABLE IF NOT EXISTS employees (
#   emp_id SERIAL PRIMARY KEY,
#   first_name VARCHAR(50),
#   last_name VARCHAR(50),
#   email VARCHAR(100),
#   hire_date DATE,
#   salary DECIMAL(10,2),
#   department VARCHAR(50),
#   updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
# );
# 
# INSERT INTO employees (first_name, last_name, email, hire_date, salary, department, updated_at) VALUES
# ('Alice', 'Johnson', 'alice@example.com', '2023-01-15', 95000.00, 'Engineering', CURRENT_TIMESTAMP),
# ('Bob', 'Smith', 'bob@example.com', '2023-02-20', 87000.00, 'Marketing', CURRENT_TIMESTAMP),
# ('Carol', 'Williams', 'carol@example.com', '2023-03-10', 92000.00, 'Engineering', CURRENT_TIMESTAMP),
# ('David', 'Brown', 'david@example.com', '2023-04-05', 78000.00, 'Sales', CURRENT_TIMESTAMP);
# EOF

# 3. Create asset
cat > assets/examples/postgres/v1.0/db_employees.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: db_employees
version: "1.0"
source_type: postgres
object: employees
schema:
  - name: emp_id
    type: integer
    required: true
  - name: first_name
    type: string
  - name: last_name
    type: string
  - name: email
    type: string
  - name: hire_date
    type: date
  - name: salary
    type: decimal
  - name: department
    type: string
target:
  file_format: parquet
  partitioning: [department]  # Suggested partitioning (must be set in job config to use)
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 4. Create secrets
mkdir -p secrets/testcase7
cat > secrets/testcase7/postgres.env << 'EOF'
PGHOST=localhost
PGPORT=5432
PGDATABASE=postgres
PGUSER=postgres
PGPASSWORD=postgres
EOF

cp secrets/testcase1/iceberg.env secrets/testcase7/

# 5. Create job
mkdir -p jobs/testcase7
cat > jobs/testcase7/postgres_employees.yaml << 'EOF'
tenant_id: testcase7
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: db_employees
asset_path: assets/examples/postgres/v1.0/db_employees.yaml
source:
  tables:
    - name: employees
      schema: public
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
  # Note: Partitioning can be set here to override asset definition
  # If not specified, uses connector recipe default (typically [ingest_date])
  # To partition by department as defined in asset, uncomment:
  # partitioning: [department]
EOF

# 6. Run job
dativo ingest \
  --config jobs/testcase7/postgres_employees.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 7. Verify data
mc ls local/test-bucket/testcase7/db_employees/ --recursive
# By default, files are partitioned by ingest_date (e.g., ingest_date=2025-12-29/)
# If you set partitioning: [department] in job config, you'll see:
#   department=Engineering/, department=Marketing/, department=Sales/
# Note: The path uses the asset name 'db_employees', not 'postgres/employees'
```

**Success Criteria:**
- ✅ Employee records extracted (check logs for exact count)
- ✅ Parquet files created in S3/MinIO at `testcase7/db_employees/ingest_date=YYYY-MM-DD/`
- ✅ Schema correctly mapped from PostgreSQL types
- ✅ Files are readable and contain expected data

**Note on Partitioning:**
- By default, files are partitioned by `ingest_date` (from connector recipe default)
- The asset definition specifies `partitioning: [department]`, but this is only used if:
  1. The job config's `target.partitioning` is set to `[department]`, OR
  2. The connector recipe doesn't have a `partitioning_default`
- To partition by department, add `partitioning: [department]` to the job's `target` section

---

### Test Case 8: PostgreSQL Incremental Sync
**Purpose:** Test cursor-based incremental sync from PostgreSQL

**Steps:**
```bash
# 1. Setup PostgreSQL employees table (if not already done)
# The setup script creates the employees table with updated_at column
# If you already ran Test Case 7, you can skip this step
./scripts/testing-playbook-setup-postgres-employees.sh

# Alternative: If employees table exists but missing updated_at column
# docker exec -i dativo-postgres psql -U postgres << 'EOF'
# ALTER TABLE employees ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
# UPDATE employees SET updated_at = CURRENT_TIMESTAMP;
# EOF

# 2. Update asset to include updated_at
cat > assets/examples/postgres/v1.0/db_employees_incremental.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: db_employees_incremental
version: "1.0"
source_type: postgres
object: employees
schema:
  - name: emp_id
    type: integer
    required: true
  - name: first_name
    type: string
  - name: last_name
    type: string
  - name: email
    type: string
  - name: hire_date
    type: date
  - name: salary
    type: decimal
  - name: department
    type: string
  - name: updated_at
    type: timestamp
    required: true
target:
  file_format: parquet
  partitioning: [ingest_date]
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 3. Create incremental job
# Note: The 'strategy' field should match the connector's incremental_strategy_default from registry/connectors.yaml
# For postgres, this is 'updated_at'. Semantic strategy names (updated_at, created, updated_after) are
# automatically mapped to 'cursor_field' strategy implementation.
mkdir -p jobs/testcase8 secrets/testcase8
cat > jobs/testcase8/postgres_employees_incremental.yaml << 'EOF'
tenant_id: testcase8
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: db_employees_incremental
asset_path: assets/examples/postgres/v1.0/db_employees_incremental.yaml
source:
  tables:
    - name: employees
      schema: public
      object: employees  # Specify object name for better state file naming
  incremental:
    enabled: true
    strategy: updated_at  # Semantic name (automatically mapped to 'cursor_field' strategy)
    cursor_field: updated_at  # The actual column to track
    lookback_days: 1
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

cp secrets/testcase7/postgres.env secrets/testcase8/
cp secrets/testcase7/iceberg.env secrets/testcase8/

# 4. First run (full sync)
dativo ingest \
  --config jobs/testcase8/postgres_employees_incremental.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 5. Check state
# State file path format: .local/state/{tenant_id}/{connector_type}.{object_name}.state.json
# If object is not specified in tables config, it defaults to "default"
cat .local/state/testcase8/postgres.employees.state.json
# Note: State file may not exist until after first successful incremental sync with changes

# 6. Add new employee
docker exec -i dativo-postgres psql -U postgres << 'EOF'
INSERT INTO employees (first_name, last_name, email, hire_date, salary, department, updated_at)
VALUES ('Eve', 'Davis', 'eve@example.com', '2023-05-01', 89000.00, 'Engineering', CURRENT_TIMESTAMP);
EOF

# 7. Update existing employee
docker exec -i dativo-postgres psql -U postgres << 'EOF'
UPDATE employees
SET salary = 98000.00, updated_at = CURRENT_TIMESTAMP
WHERE email = 'alice@example.com';
EOF

# 8. Second run (incremental)
dativo ingest \
  --config jobs/testcase8/postgres_employees_incremental.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# Expected: Only 2 records processed (new insert + update)
```

**Success Criteria:**
- ✅ First run processes all employees
- ✅ State file created at `.local/state/testcase8/postgres.employees.state.json`
- ✅ State file contains max `updated_at` value: `{"employees.updated_at": {"last_value": "...", "updated_at": "..."}}`
- ✅ Second run processes only changed records (new inserts + updates)
- ✅ State file updated with new max cursor value

**Note on State Files:**
- State file path: `.local/state/{tenant_id}/{connector_type}.{object_name}.state.json`
- If `object` is not specified in table config, it defaults to "default"
- State is only written after successfully processing records
- State format for cursor-based incremental: `{object_name}.{cursor_field} -> {last_value, updated_at}`

---

### Test Case 9: PostgreSQL to Markdown-KV Transformation
**Purpose:** Transform relational data to LLM-optimized Markdown-KV format

**Steps:**
```bash
# 1. Setup PostgreSQL employees table (if not already done)
# The setup script creates the employees table required for this test case
# If you already ran Test Case 7 or 8, you can skip this step
./scripts/testing-playbook-setup-postgres-employees.sh

# 2. Create job with markdown_kv target
mkdir -p jobs/testcase9 secrets/testcase9
cat > jobs/testcase9/postgres_to_markdown_kv.yaml << 'EOF'
tenant_id: testcase9
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: markdown_kv
target_connector_path: connectors/markdown_kv.yaml
asset: employees_markdown_kv_string
asset_path: assets/examples/markdown_kv/v1.0/employees_string.yaml
source:
  tables:
    - name: employees
      schema: public
target:
  markdown_kv_storage:
    mode: string  # Store entire document as single column in Parquet
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

cp secrets/testcase7/postgres.env secrets/testcase9/
cp secrets/testcase7/iceberg.env secrets/testcase9/

# 3. Run job
dativo ingest \
  --config jobs/testcase9/postgres_to_markdown_kv.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 4. Download and inspect output files
# Files are stored as Parquet files in markdown_kv/employees/ path
# (with mode: string, content is stored as markdown_kv_content column in Parquet)
mc cp local/test-bucket/testcase9/markdown_kv/employees/ . --recursive

# To view the Parquet file contents, you can use Python:
# python -c "import pyarrow.parquet as pq; df = pq.read_table('employees_markdown_kv_string_000000.parquet').to_pandas(); print(df[['doc_id', 'markdown_kv_content']].to_string())"

# Expected format in markdown_kv_content column:
# emp_id:: 1
# first_name:: Alice
# last_name:: Johnson
# email:: alice@example.com
# hire_date:: 2023-01-15
# salary:: 95000.00
# department:: Engineering
# updated_at:: 2023-01-15T10:30:00
# ---
# (next employee record)
```

**Success Criteria:**
- ✅ Data transformed to Markdown-KV format
- ✅ Files stored in S3/MinIO
- ✅ Format is LLM-friendly with key: value pairs
- ✅ Multiple records separated by `---`

---

### Test Case 10: Custom Python Reader Plugin
**Purpose:** Create and use a custom Python reader for JSON API

**Steps:**
```bash
# 1. Create custom reader plugin
mkdir -p plugins/testcase10
cat > plugins/testcase10/json_api_reader.py << 'EOF'
"""Custom JSON API Reader Plugin"""
import requests
from typing import Iterator, Dict, Any
from dativo_ingest.plugins import BaseReader

class JSONAPIReader(BaseReader):
    """Read data from a JSON API endpoint"""
    
    __version__ = "1.0.0"
    
    def extract(self, state_manager=None) -> Iterator[Dict[str, Any]]:
        """Extract data from API"""
        connection = self.source_config.connection
        base_url = connection.get("base_url")
        endpoint = connection.get("endpoint", "/data")
        
        # Make API request
        response = requests.get(f"{base_url}{endpoint}")
        response.raise_for_status()
        
        # Yield records
        data = response.json()
        if isinstance(data, list):
            for record in data:
                yield record
        elif isinstance(data, dict):
            # Handle paginated responses
            records = data.get("records", data.get("data", []))
            for record in records:
                yield record
    
    def check_connection(self) -> tuple[bool, str, Dict[str, Any]]:
        """Test API connectivity"""
        try:
            connection = self.source_config.connection
            base_url = connection.get("base_url")
            response = requests.get(f"{base_url}/health")
            if response.status_code == 200:
                return True, "API is accessible", {"status": "healthy"}
            return False, f"API returned {response.status_code}", {}
        except Exception as e:
            return False, str(e), {}
    
    def discover(self) -> Dict[str, Any]:
        """Discover available endpoints"""
        return {
            "streams": [
                {"name": "data", "schema": {}}
            ]
        }
EOF

# 2. Create mock API server (for testing)
cat > plugins/testcase10/mock_api_server.py << 'EOF'
from flask import Flask, jsonify
app = Flask(__name__)

@app.route('/health')
def health():
    return jsonify({"status": "healthy"})

@app.route('/data')
def data():
    return jsonify([
        {"product_id": 1, "product_name": "Product A", "price": 29.99, "category": "Electronics", "in_stock": True},
        {"product_id": 2, "product_name": "Product B", "price": 49.99, "category": "Electronics", "in_stock": True},
        {"product_id": 3, "product_name": "Product C", "price": 19.99, "category": "Home", "in_stock": False}
    ])

if __name__ == '__main__':
    app.run(port=8080)
EOF

# 3. Install Flask and start mock server in background
# CRITICAL: Do NOT use 'python' or 'python3' - they point to Python 3.12.7
# Flask is installed for Python 3.13, so you MUST use ./venv/bin/python3.13 explicitly
# Background processes may not inherit venv environment properly

# Install Flask (if not already installed)
source venv/bin/activate
pip install flask

# Start mock server - MUST use explicit Python 3.13 path
# Using 'python' or 'python3' will fail with "ModuleNotFoundError: No module named 'flask'"
./venv/bin/python3.13 plugins/testcase10/mock_api_server.py > /tmp/mock_api_server.log 2>&1 &
MOCK_SERVER_PID=$!
sleep 2

# Verify server is running
curl -s http://localhost:8080/health || echo "Warning: Server may not have started. Check /tmp/mock_api_server.log"

# 4. Create job using custom reader
mkdir -p jobs/testcase10 secrets/testcase10
cat > jobs/testcase10/custom_reader_job.yaml << 'EOF'
tenant_id: testcase10
source_connector: csv  # Just for metadata
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: products
asset_path: assets/examples/csv/v1.0/products.yaml
source:
  custom_reader: "plugins/testcase10/json_api_reader.py:JSONAPIReader"
  connection:
    base_url: "http://localhost:8080"
    endpoint: "/data"
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

cp secrets/testcase1/iceberg.env secrets/testcase10/

# 5. Run job
dativo ingest \
  --config jobs/testcase10/custom_reader_job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 6. Clean up
kill $MOCK_SERVER_PID

# 7. Verify data
# Note: The output path uses the asset name 'products', not 'api_products'
mc ls local/test-bucket/testcase10/products/ --recursive
```

**Success Criteria:**
- ✅ Custom reader successfully loads
- ✅ API data extracted
- ✅ Data written to Parquet
- ✅ Plugin interface works correctly

---

### Test Case 11: Rust Plugin for Performance (CSV Reader)
**Purpose:** Use Rust plugin for high-performance CSV reading

**Steps:**
```bash
# 1. Build Rust CSV reader plugin
cd examples/plugins/rust
make build-release
cd /workspace

# 2. Create directory and large CSV file for performance test
mkdir -p data/test_case_11
cat > data/test_case_11/generate_large_csv.py << 'EOF'
import csv
import random
from datetime import datetime, timedelta

with open('data/test_case_11/large_dataset.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'name', 'email', 'created_at', 'value'])
    
    for i in range(100000):  # 100K records
        writer.writerow([
            i,
            f"User_{i}",
            f"user{i}@example.com",
            (datetime.now() - timedelta(days=random.randint(0, 365))).isoformat(),
            round(random.uniform(10.0, 1000.0), 2)
        ])
EOF

mkdir -p data/test_case_11
python data/test_case_11/generate_large_csv.py

# 3. Create asset
cat > assets/examples/csv/v1.0/large_dataset.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: large_dataset
version: "1.0"
source_type: csv
object: large_dataset
schema:
  - name: id
    type: integer
    required: true
  - name: name
    type: string
  - name: email
    type: string
  - name: created_at
    type: timestamp
  - name: value
    type: decimal
target:
  file_format: parquet
  partitioning: []
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 4. Create job with Rust reader
mkdir -p jobs/testcase11 secrets/testcase11
cat > jobs/testcase11/rust_csv_reader.yaml << 'EOF'
tenant_id: testcase11
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: large_dataset
asset_path: assets/examples/csv/v1.0/large_dataset.yaml
source:
  custom_reader: "examples/plugins/rust/target/release/libcsv_reader_plugin.so:create_reader"
  files:
    - path: "data/test_case_11/large_dataset.csv"
  engine:
    options:
      batch_size: 50000  # Large batches for Rust
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

cp secrets/testcase1/iceberg.env secrets/testcase11/

# 5. Run with Python reader (baseline)
# Modify job to use native CSV reader
sed 's/custom_reader:.*//' jobs/testcase11/rust_csv_reader.yaml > jobs/testcase11/python_csv_reader.yaml

time dativo ingest \
  --config jobs/testcase11/python_csv_reader.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 6. Run with Rust reader (compare performance)
time dativo ingest \
  --config jobs/testcase11/rust_csv_reader.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# Expected: Rust should be 10-15x faster
```

**Success Criteria:**
- ✅ Rust plugin loads successfully
- ✅ 100K records processed
- ✅ Rust version significantly faster (10-15x)
- ✅ Memory usage lower with Rust

---

### Test Case 12: Google Sheets Integration
**Purpose:** Extract data from Google Sheets

**Prerequisites:**
- Google Cloud project with Sheets API enabled
- Service account with Sheets access
- Service account JSON key file

**Steps:**
```bash
# 1. Enable Google Sheets API
# - Go to https://console.cloud.google.com
# - Create/select project
# - Enable "Google Sheets API"
# - Create service account
# - Download JSON key file

# 2. Create test spreadsheet
# - Go to https://sheets.google.com
# - Create new spreadsheet: "Test Data"
# - Add data:
#   A1: name, B1: email, C1: age
#   A2: Alice, B2: alice@test.com, C2: 30
#   A3: Bob, B3: bob@test.com, C3: 25
# - Share with service account email (from JSON key)

# 3. Save service account credentials
mkdir -p secrets/testcase12
# Copy your service account JSON to:
# secrets/testcase12/gsheets_service_account.json

cat > secrets/testcase12/gsheets.json << 'EOF'
{
  "credentials_path": "secrets/testcase12/gsheets_service_account.json"
}
EOF

cp secrets/testcase1/iceberg.env secrets/testcase12/

# 4. Create asset
cat > assets/examples/google_sheets/v1.0/test_data.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: test_data
version: "1.0"
source_type: google_sheets
object: Sheet1
schema:
  - name: name
    type: string
    required: true
  - name: email
    type: string
  - name: age
    type: integer
target:
  file_format: parquet
  partitioning: []
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 5. Create job
mkdir -p jobs/testcase12
cat > jobs/testcase12/google_sheets_job.yaml << 'EOF'
tenant_id: testcase12
source_connector: google_sheets
source_connector_path: connectors/google_sheets.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: test_data
asset_path: assets/examples/google_sheets/v1.0/test_data.yaml
source:
  spreadsheet_id: "YOUR_SPREADSHEET_ID_HERE"  # From spreadsheet URL
  sheet_name: "Sheet1"
  range: "A1:C100"
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 6. Run job
dativo ingest \
  --config jobs/testcase12/google_sheets_job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 7. Verify data
mc ls local/test-bucket/testcase12/google_sheets/test_data/ --recursive
```

**Success Criteria:**
- ✅ Service account authenticated
- ✅ Spreadsheet data extracted
- ✅ Data written to Parquet with correct schema
- ✅ All rows from sheet ingested

---

### Test Case 13: Google Drive CSV Extraction
**Purpose:** Extract CSV files from Google Drive

**Steps:**
```bash
# 1. Upload CSV to Google Drive
# - Go to https://drive.google.com
# - Upload a CSV file (e.g., products.csv)
# - Share with service account email
# - Note the file ID from URL

# 2. Create secrets (reuse from Test Case 12)
mkdir -p secrets/testcase13
cp secrets/testcase12/gsheets_service_account.json secrets/testcase13/gdrive_service_account.json

cat > secrets/testcase13/gdrive.json << 'EOF'
{
  "credentials_path": "secrets/testcase13/gdrive_service_account.json"
}
EOF

cp secrets/testcase1/iceberg.env secrets/testcase13/

# 3. Create job
mkdir -p jobs/testcase13
cat > jobs/testcase13/gdrive_csv_job.yaml << 'EOF'
tenant_id: testcase13
source_connector: gdrive_csv
source_connector_path: connectors/gdrive_csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: products
asset_path: assets/examples/csv/v1.0/products.yaml
source:
  files:
    - file_id: "YOUR_GDRIVE_FILE_ID_HERE"
      object: products
  incremental:
    enabled: true
    lookback_days: 7
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 4. Run job
dativo ingest \
  --config jobs/testcase13/gdrive_csv_job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 5. Update file in Google Drive and re-run
# Expected: Only processes updated file
```

**Success Criteria:**
- ✅ Google Drive file accessed
- ✅ CSV content extracted
- ✅ Incremental sync tracks file modification time
- ✅ Re-run only processes updated files

---

### Test Case 14: Multi-Tenant Job Execution
**Purpose:** Run multiple jobs for different tenants in parallel

**Steps:**
```bash
# 1. Create jobs for multiple tenants
for tenant in tenant_a tenant_b tenant_c; do
  mkdir -p jobs/$tenant secrets/$tenant data/test_case_14
  
  # Create tenant-specific CSV
  cat > data/test_case_14/${tenant}_data.csv << EOF
id,tenant,value
1,$tenant,100
2,$tenant,200
3,$tenant,300
EOF

  # Create job
  cat > jobs/$tenant/tenant_job.yaml << EOF
tenant_id: $tenant
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: assets/examples/csv/v1.0/employees.yaml
source:
  files:
    - path: data/test_case_14/${tenant}_data.csv
      object: employees
target:
  connection:
    s3:
      bucket: "\${S3_BUCKET}"
EOF

  # Create secrets
  cp secrets/testcase1/iceberg.env secrets/$tenant/
done

# 2. Run all tenant jobs
dativo ingest \
  --job-dir jobs/tenant_a \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted &

dativo ingest \
  --job-dir jobs/tenant_b \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted &

dativo ingest \
  --job-dir jobs/tenant_c \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted &

wait

# 3. Verify data isolation
mc ls local/test-bucket/tenant_a/ --recursive
mc ls local/test-bucket/tenant_b/ --recursive
mc ls local/test-bucket/tenant_c/ --recursive

# 4. Verify state isolation
ls .local/state/tenant_a/
ls .local/state/tenant_b/
ls .local/state/tenant_c/
```

**Success Criteria:**
- ✅ All tenant jobs run successfully
- ✅ Data isolated in separate S3 prefixes
- ✅ State files isolated by tenant
- ✅ No cross-tenant data contamination

---

### Test Case 15: Environment Variable Secret Manager
**Purpose:** Use environment variables for secret management

**Steps:**
```bash
# 1. Set environment variables with dativo format
export DATIVO_SECRET__TESTCASE15__postgres__env=$'PGHOST=localhost\nPGPORT=5432\nPGDATABASE=postgres\nPGUSER=postgres\nPGPASSWORD=postgres'

export DATIVO_SECRET__TESTCASE15__iceberg__env=$'S3_ENDPOINT=http://localhost:9000\nAWS_ACCESS_KEY_ID=minioadmin\nAWS_SECRET_ACCESS_KEY=minioadmin\nAWS_REGION=us-east-1\nS3_BUCKET=test-bucket\nNESSIE_URI=http://localhost:19120/api/v1'

# 2. Create job
mkdir -p jobs/testcase15
cat > jobs/testcase15/env_secrets_job.yaml << 'EOF'
tenant_id: testcase15
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: db_employees
asset_path: assets/examples/postgres/v1.0/db_employees.yaml
source:
  tables:
    - name: employees
      schema: public
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# 3. Run job with env secret manager (default)
dativo ingest \
  --config jobs/testcase15/env_secrets_job.yaml \
  --secret-manager env \
  --mode self_hosted

# OR just omit --secret-manager (env is default)
dativo ingest \
  --config jobs/testcase15/env_secrets_job.yaml \
  --mode self_hosted

# 4. Test with global secrets
export DATIVO_SECRET__GLOBAL__aws_access_key__text="minioadmin"
export DATIVO_SECRET__GLOBAL__aws_secret_key__text="minioadmin"

# 5. Verify data
mc ls local/test-bucket/testcase15/employees/ --recursive
```

**Success Criteria:**
- ✅ Secrets loaded from environment variables
- ✅ Namespace format (DATIVO_SECRET__{TENANT}__{SECRET_NAME}) works
- ✅ Global secrets accessible to all tenants
- ✅ Job runs successfully with env secrets

---

### Understanding Partitioning Configuration

**How Partitioning Works:**

Partitioning can be configured at three levels (in order of precedence):

1. **Job Config** (`target.partitioning`) - Highest priority, overrides everything
2. **Asset Definition** (`target.partitioning`) - Used if job config doesn't specify
3. **Connector Recipe** (`partitioning_default`) - Fallback default if neither is set

**Example:**
```yaml
# Asset definition (assets/examples/postgres/v1.0/db_employees.yaml)
target:
  partitioning: [department]  # Suggested partitioning

# Connector recipe (connectors/iceberg.yaml)
partitioning_default: [ingest_date]  # Default fallback

# Job config (jobs/testcase7/postgres_employees.yaml)
target:
  partitioning: [department]  # This overrides both asset and connector default
```

**Important Notes:**
- If you want to use the asset definition's partitioning, you must explicitly set it in the job config
- The connector recipe's `partitioning_default` is used when neither job nor asset specify partitioning
- Common partition columns: `ingest_date` (automatic date), custom columns from your data
- Partition columns must exist in the schema

**Special Case: `ingest_date`**
- `ingest_date` is a special partition column that's automatically set to the current date
- It doesn't need to exist in your source data schema
- It's commonly used as a default for time-based partitioning

---

### Test Case 16: Data Partitioning Strategies
**Purpose:** Test different partitioning strategies (date, column, multi-level)

**Steps:**
```bash
# 1. Create directory and dataset with multiple partition candidates
mkdir -p data/test_case_16
cat > data/test_case_16/sales_data.csv << 'EOF'
order_id,customer_id,order_date,region,product_category,amount
1001,5001,2025-01-01,US-West,Electronics,299.99
1002,5002,2025-01-01,US-East,Clothing,89.99
1003,5003,2025-01-02,US-West,Electronics,199.99
1004,5004,2025-01-02,EU-North,Home,149.99
1005,5005,2025-01-03,US-East,Electronics,399.99
1006,5006,2025-01-03,EU-West,Clothing,59.99
EOF

# Test different partitioning strategies

# Strategy A: Single column partitioning (region)
cat > assets/examples/csv/v1.0/sales_by_region.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: sales_by_region
version: "1.0"
source_type: csv
object: sales
schema:
  - name: order_id
    type: integer
    required: true
  - name: customer_id
    type: integer
  - name: order_date
    type: date
  - name: region
    type: string
  - name: product_category
    type: string
  - name: amount
    type: decimal
target:
  file_format: parquet
  partitioning: [region]  # Single column
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# Strategy B: Multi-level partitioning (region → product_category)
cat > assets/examples/csv/v1.0/sales_multi_partition.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: sales_multi_partition
version: "1.0"
source_type: csv
object: sales
schema:
  - name: order_id
    type: integer
    required: true
  - name: customer_id
    type: integer
  - name: order_date
    type: date
  - name: region
    type: string
  - name: product_category
    type: string
  - name: amount
    type: decimal
target:
  file_format: parquet
  partitioning: [region, product_category]  # Multi-level
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# Strategy C: Date partitioning (ingest_date - automatic)
cat > assets/examples/csv/v1.0/sales_date_partition.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: sales_date_partition
version: "1.0"
source_type: csv
object: sales
schema:
  - name: order_id
    type: integer
    required: true
  - name: customer_id
    type: integer
  - name: order_date
    type: date
  - name: region
    type: string
  - name: product_category
    type: string
  - name: amount
    type: decimal
target:
  file_format: parquet
  partitioning: [ingest_date]  # Date-based
team:
  owner: test@example.com
compliance:
  classification: []
EOF

# 2. Create jobs for each strategy
mkdir -p jobs/testcase16 secrets/testcase16
cp secrets/testcase1/iceberg.env secrets/testcase16/

# IMPORTANT: Partitioning must be set in job config to use asset definition's partitioning
# If omitted, connector recipe default ([ingest_date]) will be used instead

# Job A: Single column partitioning
cat > jobs/testcase16/sales_by_region.yaml << 'EOF'
tenant_id: testcase16
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: sales_by_region
asset_path: assets/examples/csv/v1.0/sales_by_region.yaml
source:
  files:
    - path: data/test_case_16/sales_data.csv
      object: sales
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
  partitioning: [region]  # Must set here to use asset definition's partitioning
EOF

# Job B: Multi-level partitioning
cat > jobs/testcase16/sales_multi_partition.yaml << 'EOF'
tenant_id: testcase16
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: sales_multi_partition
asset_path: assets/examples/csv/v1.0/sales_multi_partition.yaml
source:
  files:
    - path: data/test_case_16/sales_data.csv
      object: sales
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
  partitioning: [region, product_category]  # Must set here to use asset definition's partitioning
EOF

# Job C: Date partitioning
cat > jobs/testcase16/sales_date_partition.yaml << 'EOF'
tenant_id: testcase16
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: sales_date_partition
asset_path: assets/examples/csv/v1.0/sales_date_partition.yaml
source:
  files:
    - path: data/test_case_16/sales_data.csv
      object: sales
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
  partitioning: [ingest_date]  # Must set here to use asset definition's partitioning
EOF

# 3. Run all strategies
for strategy in by_region multi_partition date_partition; do
  dativo ingest \
    --config jobs/testcase16/sales_${strategy}.yaml \
    --secret-manager filesystem \
    --secrets-dir secrets \
    --mode self_hosted
done

# 4. Verify partition structures
mc tree local/test-bucket/testcase16/sales_by_region/
# Expected: region=US-West/, region=US-East/, region=EU-North/, region=EU-West/

mc tree local/test-bucket/testcase16/sales_multi_partition/
# Expected: region=US-West/product_category=Electronics/, etc.

mc tree local/test-bucket/testcase16/sales_date_partition/
# Expected: ingest_date=2025-11-28/
```

**Success Criteria:**
- ✅ Single-column partitioning creates correct structure
- ✅ Multi-level partitioning creates nested structure
- ✅ Date partitioning uses ingest_date
- ✅ Query performance improved with partitioning

---

### Test Case 17: Catalog Integration (OpenMetadata)
**Purpose:** Push lineage and metadata to OpenMetadata catalog

**Steps:**
```bash
# 1. Start OpenMetadata (optional - for full testing)
# Download from https://open-metadata.org or use Docker:
docker run -d --name openmetadata \
  -p 8585:8585 \
  openmetadata/server:latest

# Wait for startup
sleep 30

# 2. Create catalog configuration
mkdir -p jobs/testcase17 secrets/testcase17
cat > jobs/testcase17/catalog_integration_job.yaml << 'EOF'
tenant_id: testcase17
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: assets/examples/csv/v1.0/employees.yaml
source:
  files:
    - path: data/test_case_1/employees.csv
      object: employees
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"

# Catalog integration
catalog:
  type: openmetadata
  connection:
    api_url: "http://localhost:8585/api"
    auth_token: "${OPENMETADATA_AUTH_TOKEN}"  # Get from OpenMetadata UI
  database: testcase17_db
  push_lineage: true
  push_metadata: true
EOF

cp secrets/testcase1/iceberg.env secrets/testcase17/

# Add OpenMetadata token
cat >> secrets/testcase17/iceberg.env << 'EOF'
OPENMETADATA_AUTH_TOKEN=your_token_here
EOF

# 3. Run job
dativo ingest \
  --config jobs/testcase17/catalog_integration_job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 4. Verify in OpenMetadata UI
# Go to http://localhost:8585
# Check for:
# - Table: testcase17_db.employees
# - Lineage: CSV → Iceberg
# - Metadata: owner, tags, descriptions
```

**Success Criteria:**
- ✅ Table registered in OpenMetadata
- ✅ Lineage shows source → target relationship
- ✅ Metadata (tags, owner) pushed to catalog
- ✅ Schema visible in catalog

---

### Test Case 18: Orchestration with Dagster
**Purpose:** Schedule and orchestrate jobs with Dagster

**Steps:**
```bash
# 1. Create runner configuration
cat > configs/testcase18_runner.yaml << 'EOF'
scheduler:
  type: dagster
  concurrency:
    max_concurrent_jobs: 3

jobs:
  - name: daily_employee_sync
    config_path: jobs/testcase1/employees_to_iceberg.yaml
    schedule:
      type: cron
      cron: "0 2 * * *"  # 2 AM daily
      timezone: "UTC"
    retry_policy:
      max_attempts: 3
      backoff_seconds: 60
  
  - name: hourly_orders_sync
    config_path: jobs/testcase2/orders_incremental.yaml
    schedule:
      type: interval
      interval_minutes: 60
    retry_policy:
      max_attempts: 2
      backoff_seconds: 30

tenant_id: testcase18
secret_manager: filesystem
secrets_dir: secrets
mode: self_hosted
EOF

# 2. Start Dagster orchestrator
dativo start orchestrated --runner-config configs/testcase18_runner.yaml &

# Wait for startup
sleep 10

# 3. Access Dagster UI
# Open http://localhost:3000
# Should see:
# - Asset: daily_employee_sync
# - Asset: hourly_orders_sync
# - Schedules configured

# 4. Manually trigger a job from UI or CLI
# (Dagster UI provides manual trigger option)

# 5. View job runs in UI
# - Check run history
# - View logs
# - See retry behavior

# 6. Stop orchestrator
# Ctrl+C or kill process
```

**Success Criteria:**
- ✅ Dagster starts successfully
- ✅ Jobs registered as schedules
- ✅ UI accessible at localhost:3000
- ✅ Manual trigger works
- ✅ Schedules execute at configured times
- ✅ Retry policy applied on failures

---

### Test Case 19: Error Handling and Retry Logic
**Purpose:** Test error scenarios and retry behavior

**Steps:**
```bash
# Scenario A: Invalid credentials (non-retryable)
mkdir -p jobs/testcase19 secrets/testcase19
cat > secrets/testcase19/postgres.env << 'EOF'
PGHOST=localhost
PGPORT=5432
PGDATABASE=postgres
PGUSER=invalid_user
PGPASSWORD=wrong_password
EOF

cp secrets/testcase1/iceberg.env secrets/testcase19/

cat > jobs/testcase19/invalid_creds.yaml << 'EOF'
tenant_id: testcase19
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: db_employees
asset_path: assets/examples/postgres/v1.0/db_employees.yaml
source:
  tables:
    - name: employees
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# Run and expect immediate failure (non-retryable)
dativo ingest \
  --config jobs/testcase19/invalid_creds.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# Expected: Exit code 2, "Authentication failed" error

# Scenario B: Connection timeout (retryable)
cat > secrets/testcase19/postgres_timeout.env << 'EOF'
PGHOST=10.255.255.1  # Non-routable IP
PGPORT=5432
PGDATABASE=postgres
PGUSER=postgres
PGPASSWORD=postgres
EOF

# Run with retry policy
# (Normally configured in orchestrator or retry_policy.yaml)

# Scenario C: Partial success (some jobs succeed, some fail)
mkdir -p jobs/testcase19_multi

# Job 1: Success
cat > jobs/testcase19_multi/success_job.yaml << 'EOF'
tenant_id: testcase19
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: assets/examples/csv/v1.0/employees.yaml
source:
  files:
    - path: data/test_case_1/employees.csv
      object: employees
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# Job 2: Failure (missing file)
cat > jobs/testcase19_multi/failure_job.yaml << 'EOF'
tenant_id: testcase19
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: employees
asset_path: assets/examples/csv/v1.0/employees.yaml
source:
  files:
    - path: data/nonexistent.csv
      object: employees
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
EOF

# Run both jobs
dativo ingest \
  --job-dir jobs/testcase19_multi \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# Expected: Exit code 1 (partial success)
# Expected: success_job completes, failure_job fails
```

**Success Criteria:**
- ✅ Invalid credentials fail immediately (non-retryable)
- ✅ Connection timeouts trigger retries
- ✅ Partial success returns exit code 1
- ✅ Error messages are clear and actionable
- ✅ Logs show retry attempts

---

### Test Case 20: End-to-End Production Simulation
**Purpose:** Simulate a full production pipeline with multiple sources

**Steps:**
```bash
# 1. Set up production-like scenario
mkdir -p jobs/production secrets/production

# Pipeline:
# - Extract: Stripe customers, HubSpot contacts, PostgreSQL orders
# - Transform: Validate, partition, enrich
# - Load: Write to Iceberg with catalog integration
# - Orchestrate: Schedule with Dagster

# Job 1: Stripe customers (daily at 2 AM)
cat > jobs/production/stripe_customers_daily.yaml << 'EOF'
tenant_id: production
source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/examples/stripe/v1.0/customers.yaml
source:
  object: customers
  incremental:
    enabled: true
    lookback_days: 1
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
catalog:
  type: openmetadata
  connection:
    api_url: "${OPENMETADATA_API_URL}"
  database: production_db
  push_lineage: true
  push_metadata: true
EOF

# Job 2: HubSpot contacts (every 6 hours)
cat > jobs/production/hubspot_contacts_hourly.yaml << 'EOF'
tenant_id: production
source_connector: hubspot
source_connector_path: connectors/hubspot.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: hubspot_contacts
asset_path: assets/examples/hubspot/v1.0/contacts.yaml
source:
  object: contacts
  incremental:
    enabled: true
    lookback_days: 1
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
catalog:
  type: openmetadata
  connection:
    api_url: "${OPENMETADATA_API_URL}"
  database: production_db
  push_lineage: true
  push_metadata: true
EOF

# Job 3: PostgreSQL orders (every 15 minutes)
cat > jobs/production/postgres_orders_frequent.yaml << 'EOF'
tenant_id: production
source_connector: postgres
source_connector_path: connectors/postgres.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: db_employees_incremental
asset_path: assets/examples/postgres/v1.0/db_employees_incremental.yaml
source:
  tables:
    - name: employees
      schema: public
  incremental:
    enabled: true
    cursor_field: updated_at
    lookback_days: 1
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
catalog:
  type: openmetadata
  connection:
    api_url: "${OPENMETADATA_API_URL}"
  database: production_db
  push_lineage: true
  push_metadata: true
EOF

# 2. Set up secrets
mkdir -p secrets/production

# Combine all secrets
cat > secrets/production/stripe.env << EOF
STRIPE_API_KEY=sk_test_YOUR_KEY
EOF

cat > secrets/production/hubspot.env << EOF
HUBSPOT_API_KEY=pat-na1-YOUR_KEY
EOF

cat > secrets/production/postgres.env << 'EOF'
PGHOST=localhost
PGPORT=5432
PGDATABASE=postgres
PGUSER=postgres
PGPASSWORD=postgres
EOF

cat > secrets/production/iceberg.env << 'EOF'
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
NESSIE_URI=http://localhost:19120/api/v1
OPENMETADATA_API_URL=http://localhost:8585/api
EOF

# 3. Create orchestration config
cat > configs/production_runner.yaml << 'EOF'
scheduler:
  type: dagster
  concurrency:
    max_concurrent_jobs: 5

jobs:
  - name: stripe_customers_daily
    config_path: jobs/production/stripe_customers_daily.yaml
    schedule:
      type: cron
      cron: "0 2 * * *"
      timezone: "UTC"
    retry_policy:
      max_attempts: 3
      backoff_seconds: 300
  
  - name: hubspot_contacts_6hourly
    config_path: jobs/production/hubspot_contacts_hourly.yaml
    schedule:
      type: cron
      cron: "0 */6 * * *"
      timezone: "UTC"
    retry_policy:
      max_attempts: 2
      backoff_seconds: 180
  
  - name: postgres_orders_15min
    config_path: jobs/production/postgres_orders_frequent.yaml
    schedule:
      type: interval
      interval_minutes: 15
    retry_policy:
      max_attempts: 5
      backoff_seconds: 60

tenant_id: production
secret_manager: filesystem
secrets_dir: secrets
mode: self_hosted
EOF

# 4. Test each job individually first
for job in stripe_customers_daily hubspot_contacts_hourly postgres_orders_frequent; do
  echo "Testing job: $job"
  dativo check \
    --config jobs/production/${job}.yaml \
    --secret-manager filesystem \
    --secrets-dir secrets \
    --verbose
done

# 5. Run all jobs once
dativo ingest \
  --job-dir jobs/production \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 6. Start orchestration
dativo start orchestrated --runner-config configs/production_runner.yaml

# 7. Monitor via Dagster UI (http://localhost:3000)
# - View asset lineage
# - Check run history
# - Monitor schedules
# - Review logs

# 8. Verify data in MinIO
mc ls local/test-bucket/production/ --recursive

# 9. Verify metadata in OpenMetadata (http://localhost:8585)
# - Check tables in production_db
# - View lineage graphs
# - Check metadata propagation

# 10. Test incremental sync
# - Trigger manual run
# - Verify only new/updated data processed
# - Check state files updated
```

**Success Criteria:**
- ✅ All 3 sources (Stripe, HubSpot, PostgreSQL) working
- ✅ Jobs scheduled and running on schedule
- ✅ Incremental sync working for all sources
- ✅ Data written to S3/MinIO with correct partitioning
- ✅ Catalog integration shows full lineage
- ✅ State management tracking cursor values
- ✅ Retry logic working on failures
- ✅ Monitoring and observability working
- ✅ Multi-tenant isolation maintained

---

### Test Case 21: Mimesis Synthetic Data Generation to Iceberg
**Purpose:** Generate realistic synthetic data using Mimesis connector and write to Iceberg tables

**Use Cases:**
- Performance testing with large datasets
- Development and testing environments
- Generating test data without external dependencies
- Schema validation testing

**Steps:**
```bash
# 1. Create asset definition for synthetic customer data
mkdir -p assets/examples/mimesis/v1.0
cat > assets/examples/mimesis/v1.0/customers.yaml << 'EOF'
$schema: ../../schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: mimesis_customers
version: "1.0"
source_type: mimesis
object: customers

# Schema definition - fields will be generated using Mimesis
schema:
  - name: customer_id
    type: integer
    required: true
  - name: name
    type: string
    required: true
  - name: email
    type: string
    required: true
  - name: phone
    type: string
    required: false
  - name: signup_date
    type: date
    required: true
  - name: account_balance
    type: double
    required: false
  - name: is_active
    type: boolean
    required: true
  - name: country
    type: string
    required: false

# Target configuration
target:
  file_format: parquet
  partitioning: [ingest_date]

# Governance
team:
  owner: test@example.com

compliance:
  classification: []  # Synthetic data - no PII concerns
EOF

# 2. Create job configuration
mkdir -p jobs/testcase21
cat > jobs/testcase21/mimesis_customers_to_iceberg.yaml << 'EOF'
tenant_id: testcase21
source_connector: mimesis
source_connector_path: connectors/mimesis.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: mimesis_customers
asset_path: assets/examples/mimesis/v1.0/customers.yaml

# Source configuration - Mimesis synthetic data generation
source:
  type: mimesis
  object: customers
  engine:
    type: native
    options:
      native:
        row_count: 10000  # Generate 10,000 synthetic records
        batch_size: 1000   # Process in batches of 1,000
        locale: "en"       # English locale for names, addresses, etc.
        seed: 42           # Fixed seed for reproducible data
        null_probability: 0.1  # 10% chance of null for optional fields

# Target configuration
target:
  type: iceberg
  connection:
    s3:
      bucket: "${S3_BUCKET}"
  partitioning: [ingest_date]

# Catalog configuration (optional - for Iceberg table registration)
catalog:
  type: nessie
  connection:
    uri: "${NESSIE_URI}"
  database: test_db
  table_name: synthetic_customers

# Schema validation
schema_validation_mode: warn
EOF

# 3. Create secrets (reuse from previous test cases)
mkdir -p secrets/testcase21
cat > secrets/testcase21/iceberg.env << 'EOF'
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
NESSIE_URI=http://localhost:19120/api/v1
EOF

# 4. Run the job
dativo ingest \
  --config jobs/testcase21/mimesis_customers_to_iceberg.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 5. Verify results
# Check Parquet files in MinIO
# Note: Files are written using the asset name 'mimesis_customers', not the catalog table name
mc ls local/test-bucket/testcase21/mimesis_customers/ --recursive

# Verify file count and sizes
mc stat local/test-bucket/testcase21/mimesis_customers/ingest_date=*/mimesis_customers_*.parquet

# 6. Generate larger dataset for performance testing
# Update job config to generate 100K records
cat > jobs/testcase21/mimesis_performance_test.yaml << 'EOF'
tenant_id: testcase21
source_connector: mimesis
source_connector_path: connectors/mimesis.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: mimesis_customers
asset_path: assets/examples/mimesis/v1.0/customers.yaml
source:
  type: mimesis
  object: customers
  engine:
    type: native
    options:
      native:
        row_count: 100000  # 100K records for performance testing
        batch_size: 10000  # Larger batches for better performance
        locale: "en"
        seed: 42
target:
  type: iceberg
  connection:
    s3:
      bucket: "${S3_BUCKET}"
  partitioning: [ingest_date]
schema_validation_mode: warn
EOF

# Run performance test
time dativo ingest \
  --config jobs/testcase21/mimesis_performance_test.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 7. Test with different locales
cat > jobs/testcase21/mimesis_multilocale.yaml << 'EOF'
tenant_id: testcase21
source_connector: mimesis
source_connector_path: connectors/mimesis.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: mimesis_customers
asset_path: assets/examples/mimesis/v1.0/customers.yaml
source:
  type: mimesis
  object: customers
  engine:
    type: native
    options:
      native:
        row_count: 5000
        locale: "ru"  # Russian locale for Cyrillic names
        seed: 123
target:
  type: iceberg
  connection:
    s3:
      bucket: "${S3_BUCKET}"
  partitioning: [ingest_date]
EOF

# Run with different locale
dativo ingest \
  --config jobs/testcase21/mimesis_multilocale.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# 8. Verify data quality
# Check that generated data matches schema
# All required fields should be present
# Optional fields may be null based on null_probability
# Data types should match schema definitions
```

**Success Criteria:**
- ✅ Exit code 0
- ✅ Synthetic data generated successfully
- ✅ Parquet files created in MinIO at `testcase21/mimesis_customers/ingest_date=YYYY-MM-DD/`
- ✅ Generated data matches asset schema
- ✅ Required fields are always present
- ✅ Optional fields respect null_probability setting
- ✅ Data types match schema definitions (integer, string, date, double, boolean)
- ✅ Locale settings affect generated names/addresses appropriately
- ✅ Seed ensures reproducible data generation
- ✅ Performance test completes in reasonable time (100K records)
- ✅ Iceberg table registered in Nessie catalog (if catalog enabled)

**Key Features Demonstrated:**
- Schema-driven synthetic data generation
- Automatic field type mapping (email → email addresses, name → names, etc.)
- Configurable row counts and batch sizes
- Locale support for internationalized data
- Seed-based reproducibility
- Null probability control for optional fields
- Integration with Iceberg target connector
- Performance testing capabilities

**Tips:**
- Use `seed` parameter for reproducible test data across runs
- Adjust `row_count` based on your testing needs (1000 for quick tests, 100K+ for performance)
- Use different `locale` values to generate data in different languages/regions
- Set `null_probability: 0.0` if you want all optional fields populated
- Increase `batch_size` for better performance with large datasets
- See [docs/connectors/mimesis.md](docs/connectors/mimesis.md) for complete field mapping reference

---

## Advanced Testing Scenarios

### Scenario A: Disaster Recovery
**Test state recovery after infrastructure failure**

```bash
# 1. Run a job and capture state
dativo ingest --config jobs/testcase2/orders_incremental.yaml ...

# 2. Simulate failure - stop MinIO
docker stop $(docker ps -q -f name=minio)

# 3. Attempt to run job (should fail gracefully)
dativo ingest --config jobs/testcase2/orders_incremental.yaml ...

# 4. Restart MinIO
docker start $(docker ps -a -q -f name=minio)

# 5. Run job again (should resume from last state)
dativo ingest --config jobs/testcase2/orders_incremental.yaml ...
```

### Scenario B: Schema Evolution
**Test handling schema changes in source data**

```bash
# 1. Run initial ingestion
dativo ingest --config jobs/testcase1/employees_to_iceberg.yaml ...

# 2. Add new column to CSV
cat >> data/test_case_1/employees.csv << 'EOF'
4,New Employee,new@example.com,IT,100000,Manager
EOF

# 3. Update asset schema to include new column
# Edit assets/examples/csv/v1.0/employees.yaml - add "title" field

# 4. Re-run job
dativo ingest --config jobs/testcase1/employees_to_iceberg.yaml ...

# Expected: Schema evolution handled (if catalog supports it)
```

### Scenario C: Large-Scale Performance Testing
**Test with 1M+ records**

```bash
# Generate 1M records
python << 'EOF'
import csv
for i in range(1000000):
    if i == 0:
        print("id,name,value")
    print(f"{i},User_{i},{i * 1.5}")
EOF > data/large_scale_test.csv

# Run with Rust plugin for performance
dativo ingest --config jobs/large_scale_job.yaml ...

# Monitor:
# - Memory usage
# - Execution time
# - File sizes
# - Partitioning effectiveness
```

---

## Summary

This playbook covers:

### ✅ Core Capabilities Tested
1. **Data Sources:** CSV, PostgreSQL, MySQL, Stripe, HubSpot, Google Sheets, Google Drive, Mimesis (synthetic)
2. **Data Targets:** Iceberg, S3, MinIO, Markdown-KV
3. **ETL Features:** Extraction, validation, transformation, loading
4. **Schema Validation:** Strict vs warn modes
5. **Incremental Sync:** State-based, cursor-based, timestamp-based
6. **Custom Plugins:** Python and Rust readers/writers
7. **Partitioning:** Single, multi-level, date-based
8. **Secret Management:** Filesystem, environment variables
9. **Orchestration:** Dagster scheduling and retry policies
10. **Catalog Integration:** OpenMetadata lineage and metadata
11. **Multi-Tenancy:** Tenant isolation and parallel execution
12. **Error Handling:** Retry logic, partial success, failure modes
13. **Performance:** Rust plugins for high-performance processing, synthetic data generation
14. **Production Patterns:** End-to-end multi-source pipelines
15. **Synthetic Data:** Mimesis connector for testing and development

### 🎯 Next Steps
1. Start with Test Cases 1-2 (basic CSV ingestion)
2. Set up Stripe and HubSpot accounts (Test Cases 3-4)
3. Progress through database connectors (Test Cases 7-9)
4. Experiment with custom plugins (Test Cases 10-11)
5. Test synthetic data generation (Test Case 21) - great for performance testing
6. Test advanced features (Test Cases 12-20)
7. Simulate production scenarios (Test Case 20)

### 📚 Additional Resources
- [README.md](README.md) - Platform overview
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [docs/CUSTOM_PLUGINS.md](docs/CUSTOM_PLUGINS.md) - Plugin development
- [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md) - Secret managers
- [docs/CATALOG_INTEGRATION.md](docs/CATALOG_INTEGRATION.md) - Catalog setup

---

**Happy Testing! 🚀**
