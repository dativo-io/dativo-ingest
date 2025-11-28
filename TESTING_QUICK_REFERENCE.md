# Testing Quick Reference

## Top 20 Test Cases Summary

### Category 1: Basic Source Connectors
| # | Test Case | Command | Expected Result |
|---|-----------|---------|-----------------|
| 1 | CSV to Iceberg | `dativo run --config tests/fixtures/jobs/csv_employee_to_iceberg.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` | Parquet files in MinIO |
| 2 | CSV to MinIO | `dativo run --config tests/fixtures/jobs/csv_product_to_minio.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` | Direct MinIO storage |
| 3 | CSV to S3 | `dativo run --config tests/fixtures/jobs/csv_person_to_s3.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` | Files in S3 bucket |
| 4 | CSV State Persistence | `dativo run --config tests/fixtures/jobs/csv_employee_state_persistence.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` | Incremental sync works |
| 5 | CSV Strict Validation | `dativo run --config tests/fixtures/jobs/csv_product_strict_validation.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` | Fails on invalid data |

### Category 2: Database Connectors
| # | Test Case | Prerequisites | Command |
|---|-----------|---------------|---------|
| 6 | PostgreSQL to Iceberg | PostgreSQL running | `dativo run --config tests/fixtures/jobs/postgres_employee_to_iceberg_markdown_kv.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 7 | MySQL to Iceberg | MySQL running | `dativo run --config tests/fixtures/jobs/mysql_employees_to_iceberg_markdown_kv.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 8 | PostgreSQL Error | PostgreSQL stopped | `dativo run --config tests/fixtures/jobs/postgres_connection_failure.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 9 | Multiple Tables | PostgreSQL with multiple tables | Create custom job config |

### Category 3: API Connectors
| # | Test Case | Setup Required | Command |
|---|-----------|----------------|---------|
| 10 | Stripe Customers | Stripe test account + API key | `dativo run --config tests/fixtures/jobs/stripe_customers_to_iceberg.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 11 | Stripe Charges | Stripe test account + test charges | Create custom job config |
| 12 | HubSpot Contacts | HubSpot account + API key | `dativo run --config tests/fixtures/jobs/hubspot_contacts_to_iceberg.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 13 | HubSpot Deals | HubSpot account + test deals | Create custom job config |

### Category 4: Google Services
| # | Test Case | Prerequisites | Command |
|---|-----------|---------------|---------|
| 14 | Google Drive CSV | Google Cloud project + service account | `dativo run --config tests/fixtures/jobs/gdrive_csv_to_iceberg.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 15 | Google Sheets | Google Cloud project + shared sheet | `dativo run --config tests/fixtures/jobs/google_sheets_to_iceberg.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 16 | Iceberg to Sheets | Google Cloud project + destination sheet | `dativo run --config tests/fixtures/jobs/iceberg_to_google_sheets.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |

### Category 5: Advanced Features
| # | Test Case | Command |
|---|-----------|---------|
| 17 | Markdown-KV Source | `dativo run --config tests/fixtures/jobs/markdown_kv_source_to_iceberg.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 18 | Python Plugin | `dativo run --config examples/jobs/custom_plugin_example.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |
| 19 | Rust Plugin | `cd examples/plugins/rust && make build-release` then run job |
| 20 | Catalog Integration | `dativo run --config tests/fixtures/jobs/csv_employee_to_iceberg_with_catalog.yaml --secrets-dir tests/fixtures/secrets --mode self_hosted` |

---

## Stripe Test Account Setup (Quick)

1. **Sign up**: https://stripe.com → Create free account
2. **Get API key**: Dashboard → Developers → API keys → Copy `sk_test_...`
3. **Create test data**:
   ```bash
   # Using Stripe CLI
   stripe login
   stripe customers create --email="test@example.com" --name="Test Customer"
   stripe charges create --amount=2000 --currency=usd --source=tok_visa
   ```
4. **Set credentials**:
   ```bash
   export DATIVO_SECRET__TEST_TENANT__stripe_api_key__text="sk_test_your_key"
   ```

---

## HubSpot Test Account Setup (Quick)

1. **Sign up**: https://www.hubspot.com → Get started free
2. **Get API key**: Settings → Integrations → Private Apps → Create app → Copy API key
3. **Create test data**:
   ```bash
   # Using Python
   python -c "
   import requests
   API_KEY = 'pat-na1-your-key'
   headers = {'Authorization': f'Bearer {API_KEY}', 'Content-Type': 'application/json'}
   for i in range(5):
       requests.post('https://api.hubapi.com/crm/v3/objects/contacts',
                    headers=headers,
                    json={'properties': {'email': f'test{i}@example.com', 'firstname': 'Test', 'lastname': f'Contact {i}'}})
   "
   ```
4. **Set credentials**:
   ```bash
   export DATIVO_SECRET__TEST_TENANT__hubspot_api_key__text="pat-na1-your_key"
   ```

---

## Common Commands

### Setup
```bash
./scripts/setup-dev.sh
source .env
```

### Verify Connection
```bash
dativo check --config <job.yaml> --verbose
```

### Discover Streams
```bash
dativo discover --config <job.yaml> --verbose
```

### Run Single Job
```bash
dativo run --config <job.yaml> --secrets-dir tests/fixtures/secrets --mode self_hosted
```

### Run All Tests
```bash
make test-smoke
# or
./tests/smoke_tests.sh
```

### Check Results
```bash
# MinIO
mc ls local/test-bucket --recursive

# S3
aws s3 ls s3://bucket-name/ --recursive

# Nessie
curl http://localhost:19120/api/v1/config
```

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Connection refused | `docker ps` → `docker-compose restart` |
| API key invalid | `dativo check --config <job> --verbose` |
| File not found | Check `tests/fixtures/seeds/` |
| Schema validation failed | Review asset definition, use `warn` mode |

---

## Test Data Locations

- **CSV files**: `tests/fixtures/seeds/`
- **Database scripts**: `tests/fixtures/seeds/test_db/`
- **Job configs**: `tests/fixtures/jobs/`
- **Secrets**: `tests/fixtures/secrets/` (or environment variables)

---

For detailed instructions, see [TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md)
