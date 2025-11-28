# Testing Guide Index

Welcome to the comprehensive testing guide for dativo-ingest! This index helps you navigate all testing resources.

## 📚 Documentation Overview

### 1. **[TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md)** - Complete Testing Guide
**START HERE!** Comprehensive playbook with 20 detailed test cases covering all dativo-ingest capabilities.

**What's Inside:**
- Prerequisites & environment setup
- Test account setup for Stripe & HubSpot (with test data generation)
- 20 real-world test cases with step-by-step instructions
- Advanced testing scenarios
- Complete capability coverage

**Test Cases Covered:**
1. Basic CSV to Iceberg Ingestion
2. Incremental Sync with State Persistence
3. Stripe Customer Ingestion
4. HubSpot CRM Data Ingestion
5. Schema Validation - Strict Mode
6. Schema Validation - Warn Mode
7. PostgreSQL to Iceberg (Full Table Sync)
8. PostgreSQL Incremental Sync
9. PostgreSQL to Markdown-KV Transformation
10. Custom Python Reader Plugin
11. Rust Plugin for Performance
12. Google Sheets Integration
13. Google Drive CSV Extraction
14. Multi-Tenant Job Execution
15. Environment Variable Secret Manager
16. Data Partitioning Strategies
17. Catalog Integration (OpenMetadata)
18. Orchestration with Dagster
19. Error Handling and Retry Logic
20. End-to-End Production Simulation

---

### 2. **[TESTING_QUICK_REFERENCE.md](TESTING_QUICK_REFERENCE.md)** - Quick Command Reference
**Use this for quick lookups!** Cheat sheet with common commands, patterns, and troubleshooting.

**What's Inside:**
- CLI command cheat sheet
- Common job configuration patterns
- Secret management quick setups
- Stripe & HubSpot 1-minute setup guides
- Troubleshooting commands
- Docker commands
- Verification commands
- Quick test sequence

---

### 3. **Helper Scripts**

#### **[scripts/preflight-check.sh](scripts/preflight-check.sh)** - Environment Validation
**Run this first!** Validates your environment is ready for testing.

```bash
./scripts/preflight-check.sh
```

**Checks:**
- Python environment (version 3.10+)
- Docker and containers (Nessie, MinIO, PostgreSQL)
- Infrastructure services running
- Environment variables configured
- Project directory structure
- MinIO bucket setup
- Python dependencies installed
- Test data availability

---

#### **[scripts/generate-test-data.sh](scripts/generate-test-data.sh)** - Test Data Generator
Generates sample datasets for all test cases.

```bash
./scripts/generate-test-data.sh
```

**Generates:**
- employees.csv (5 rows)
- orders.csv (5 rows with timestamps for incremental testing)
- products.csv (5 rows)
- sales.csv (6 rows for partitioning tests)
- large_dataset.csv (100K rows for performance testing)
- malformed_data.csv (for validation testing)
- sample_api_response.json (for custom plugin testing)
- sample_markdown_kv.md (Markdown-KV format example)
- PostgreSQL test tables (test_employees, test_orders)

---

## 🚀 Quick Start Sequence

### Step 1: Validate Environment
```bash
./scripts/preflight-check.sh
```

### Step 2: Generate Test Data
```bash
./scripts/generate-test-data.sh
```

### Step 3: Run Basic Smoke Test
```bash
source .env

dativo run \
  --job-dir tests/fixtures/jobs \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

### Step 4: Verify Results
```bash
# Check data in MinIO
mc ls local/test-bucket --recursive

# Check state files
ls -la .local/state/

# Access MinIO Console
open http://localhost:9001  # minioadmin/minioadmin

# Access Dagster UI (if orchestrator running)
open http://localhost:3000
```

### Step 5: Follow Test Cases
Open [TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md) and work through test cases 1-20.

---

## 🎯 Testing by Capability

### Data Sources
| Source | Test Case | Difficulty |
|--------|-----------|------------|
| CSV | Test Case 1 | ⭐ Beginner |
| PostgreSQL | Test Cases 7-8 | ⭐⭐ Intermediate |
| Stripe API | Test Case 3 | ⭐⭐ Intermediate |
| HubSpot API | Test Case 4 | ⭐⭐ Intermediate |
| Google Sheets | Test Case 12 | ⭐⭐⭐ Advanced |
| Google Drive | Test Case 13 | ⭐⭐⭐ Advanced |

### Data Targets
| Target | Test Cases | Difficulty |
|--------|-----------|------------|
| Iceberg/Parquet | Test Cases 1, 3-8 | ⭐ Beginner |
| Markdown-KV | Test Case 9 | ⭐⭐ Intermediate |
| S3/MinIO | All test cases | ⭐ Beginner |

### Features
| Feature | Test Cases | Difficulty |
|---------|-----------|------------|
| Incremental Sync | Test Cases 2, 8 | ⭐⭐ Intermediate |
| Schema Validation | Test Cases 5-6 | ⭐⭐ Intermediate |
| Custom Plugins (Python) | Test Case 10 | ⭐⭐⭐ Advanced |
| Custom Plugins (Rust) | Test Case 11 | ⭐⭐⭐⭐ Expert |
| Partitioning | Test Case 16 | ⭐⭐ Intermediate |
| Multi-Tenancy | Test Case 14 | ⭐⭐ Intermediate |
| Secret Management | Test Case 15 | ⭐⭐ Intermediate |
| Catalog Integration | Test Case 17 | ⭐⭐⭐ Advanced |
| Orchestration | Test Case 18 | ⭐⭐⭐ Advanced |
| Error Handling | Test Case 19 | ⭐⭐ Intermediate |
| End-to-End Pipeline | Test Case 20 | ⭐⭐⭐⭐ Expert |

---

## 📋 Test Case Checklist

Use this checklist to track your testing progress:

### Basic Features (⭐ Beginner)
- [ ] Test Case 1: Basic CSV to Iceberg
- [ ] Test Case 2: Incremental Sync with State
- [ ] Test Case 5: Schema Validation - Strict Mode
- [ ] Test Case 6: Schema Validation - Warn Mode

### API Integrations (⭐⭐ Intermediate)
- [ ] Test Case 3: Stripe Customer Ingestion
  - [ ] Created Stripe test account
  - [ ] Generated test customers
  - [ ] Configured API key
- [ ] Test Case 4: HubSpot CRM Ingestion
  - [ ] Created HubSpot free account
  - [ ] Generated test contacts/companies/deals
  - [ ] Configured API key

### Database Connectors (⭐⭐ Intermediate)
- [ ] Test Case 7: PostgreSQL Full Table Sync
- [ ] Test Case 8: PostgreSQL Incremental Sync
- [ ] Test Case 9: PostgreSQL to Markdown-KV

### Advanced Features (⭐⭐⭐ Advanced)
- [ ] Test Case 10: Custom Python Reader Plugin
- [ ] Test Case 11: Rust Plugin for Performance
- [ ] Test Case 12: Google Sheets Integration
- [ ] Test Case 13: Google Drive CSV Extraction
- [ ] Test Case 17: Catalog Integration (OpenMetadata)
- [ ] Test Case 18: Orchestration with Dagster

### Production Patterns (⭐⭐⭐⭐ Expert)
- [ ] Test Case 14: Multi-Tenant Job Execution
- [ ] Test Case 15: Environment Variable Secrets
- [ ] Test Case 16: Data Partitioning Strategies
- [ ] Test Case 19: Error Handling and Retry Logic
- [ ] Test Case 20: End-to-End Production Simulation

---

## 🔧 Setting Up Test Accounts

### Stripe (Free Test Account)
**Time:** 2 minutes

1. Sign up at https://stripe.com (free, no credit card)
2. Enable **Test Mode** (orange toggle in dashboard)
3. Get API key: Developers → API keys → Secret key (starts with `sk_test_`)
4. Generate test data:
   - Use Stripe Dashboard to create customers
   - Or use Stripe CLI: `stripe customers create --email=test@example.com`
   - Test card: 4242 4242 4242 4242

**Detailed Instructions:** See TESTING_PLAYBOOK.md → Test Account Setup → Stripe

### HubSpot (Free CRM Account)
**Time:** 3 minutes

1. Sign up at https://www.hubspot.com/products/get-started (free)
2. Complete onboarding (choose CRM)
3. Get API key: Settings → Integrations → Private Apps
   - Create app with scopes: `crm.objects.contacts.read`, `crm.objects.companies.read`, `crm.objects.deals.read`
4. Generate test data:
   - Use HubSpot UI to create contacts, companies, deals
   - Or use HubSpot API to bulk create test data

**Detailed Instructions:** See TESTING_PLAYBOOK.md → Test Account Setup → HubSpot

### Google Sheets/Drive (Service Account)
**Time:** 5 minutes

1. Create Google Cloud project
2. Enable Google Sheets API and Google Drive API
3. Create service account and download JSON key
4. Share test spreadsheet/files with service account email

**Detailed Instructions:** See TESTING_PLAYBOOK.md → Test Cases 12-13

---

## 🐛 Troubleshooting

### Common Issues

| Issue | Solution | Quick Fix |
|-------|----------|-----------|
| `dativo: command not found` | Install package | `pip install -e .` |
| Services not running | Start containers | `docker-compose -f docker-compose.dev.yml up -d` |
| Connection refused to MinIO | Check service | `docker ps \| grep minio` |
| Bucket does not exist | Create bucket | `mc mb local/test-bucket` |
| Environment variables not set | Source .env | `source .env` |
| State directory missing | Create directory | `mkdir -p .local/state` |

**Full troubleshooting guide:** See TESTING_QUICK_REFERENCE.md → Troubleshooting

---

## 📖 Additional Resources

### Platform Documentation
- [README.md](README.md) - Platform overview and architecture
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [ROADMAP.md](ROADMAP.md) - Feature roadmap and version history

### Configuration Guides
- [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) - Complete configuration reference
- [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md) - Secret management patterns
- [docs/CATALOG_INTEGRATION.md](docs/CATALOG_INTEGRATION.md) - Data catalog integration

### Development Guides
- [docs/CUSTOM_PLUGINS.md](docs/CUSTOM_PLUGINS.md) - Custom plugin development (Python & Rust)
- [docs/PLUGIN_DECISION_TREE.md](docs/PLUGIN_DECISION_TREE.md) - When to use connectors vs plugins
- [docs/SETUP_AND_TESTING.md](docs/SETUP_AND_TESTING.md) - Setup and testing guide

### Advanced Topics
- [docs/MARKDOWN_KV_STORAGE.md](docs/MARKDOWN_KV_STORAGE.md) - Markdown-KV storage patterns
- [docs/RUNNER_AND_ORCHESTRATION.md](docs/RUNNER_AND_ORCHESTRATION.md) - Orchestration with Dagster
- [docs/SCHEMA_VALIDATION.md](docs/SCHEMA_VALIDATION.md) - Schema validation details

---

## 🎓 Learning Path

### Beginner (1-2 hours)
1. Run preflight check
2. Generate test data
3. Complete Test Cases 1-2 (CSV ingestion and incremental sync)
4. Complete Test Cases 5-6 (schema validation)

### Intermediate (3-4 hours)
1. Set up Stripe test account
2. Complete Test Case 3 (Stripe ingestion)
3. Set up HubSpot test account
4. Complete Test Case 4 (HubSpot ingestion)
5. Complete Test Cases 7-8 (PostgreSQL ingestion)
6. Complete Test Case 14 (multi-tenant)

### Advanced (5-8 hours)
1. Complete Test Case 9 (Markdown-KV transformation)
2. Complete Test Case 10 (custom Python plugin)
3. Complete Test Case 12-13 (Google Sheets/Drive)
4. Complete Test Case 16 (partitioning strategies)
5. Complete Test Case 17 (catalog integration)
6. Complete Test Case 18 (orchestration)

### Expert (Full day)
1. Complete Test Case 11 (Rust plugins)
2. Complete Test Case 19 (error handling)
3. Complete Test Case 20 (end-to-end production simulation)
4. Experiment with custom scenarios
5. Performance tuning and optimization

---

## 💡 Tips for Effective Testing

### 1. Start Small
Begin with Test Case 1 (basic CSV ingestion) to understand the workflow before moving to more complex scenarios.

### 2. Use Verification Commands
After each test, verify results:
```bash
# Check MinIO data
mc ls local/test-bucket --recursive

# Check state files
cat .local/state/mytenant/myobject_state.json

# Check logs for errors
grep -i error /path/to/log
```

### 3. Test Incrementally
Don't jump straight to Test Case 20. Build up your understanding by completing test cases in order.

### 4. Keep Notes
Document any issues you encounter and solutions you find. This will help with troubleshooting later.

### 5. Use the Quick Reference
Keep [TESTING_QUICK_REFERENCE.md](TESTING_QUICK_REFERENCE.md) open for quick command lookups.

### 6. Clean Up Between Tests
```bash
# Clear state for fresh start
rm -rf .local/state/mytenant/

# Clear MinIO data
mc rm local/test-bucket/mytenant/ --recursive --force
```

---

## 🤝 Getting Help

If you encounter issues:

1. Check [TESTING_QUICK_REFERENCE.md](TESTING_QUICK_REFERENCE.md) → Troubleshooting
2. Run preflight check: `./scripts/preflight-check.sh`
3. Check service logs: `docker-compose -f docker-compose.dev.yml logs`
4. Review error messages in dativo output
5. Consult platform documentation in [docs/](docs/)

---

## 📊 Test Coverage Summary

This testing suite covers:

| Category | Coverage |
|----------|----------|
| Data Sources | 8/8 (100%) - CSV, PostgreSQL, MySQL*, Stripe, HubSpot, Google Sheets, Google Drive, Markdown-KV |
| Data Targets | 4/4 (100%) - Iceberg, S3, MinIO, Markdown-KV |
| Validation Modes | 2/2 (100%) - Strict, Warn |
| Sync Strategies | 2/2 (100%) - Full, Incremental |
| Secret Managers | 2/5 (40%) - Filesystem, Environment (Vault, AWS, GCP in docs) |
| Plugin Types | 2/2 (100%) - Python, Rust |
| Partitioning | 3/3 (100%) - Single column, Multi-level, Date-based |
| Catalog Types | 1/4 (25%) - OpenMetadata (AWS Glue, Databricks, Nessie in docs) |
| Orchestration | 1/1 (100%) - Dagster |

\* MySQL tests can be derived from PostgreSQL test cases

---

**Last Updated:** November 28, 2025  
**Version:** 1.1.0

---

**Ready to start testing? Run: `./scripts/preflight-check.sh`** 🚀
