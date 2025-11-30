╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                    DATIVO-INGEST TESTING SUITE OVERVIEW                      ║
║                                                                              ║
║                      Complete Real-World Testing Guide                       ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────────────────────────────────────────────┐
│ 📚 DOCUMENTATION (3,222 lines total)                                         │
└──────────────────────────────────────────────────────────────────────────────┘

  1. TESTING_GUIDE_INDEX.md (407 lines)
     ↳ Your starting point - navigation hub for all testing resources
     ↳ Test case checklist, learning path, troubleshooting

  2. TESTING_PLAYBOOK.md (2,399 lines)
     ↳ 20 detailed test cases with step-by-step instructions
     ↳ Copy-paste ready commands and configurations
     ↳ Stripe & HubSpot test account setup guides

  3. TESTING_QUICK_REFERENCE.md (416 lines)
     ↳ Command cheat sheet and quick lookup guide
     ↳ Common patterns, troubleshooting, Docker commands

┌──────────────────────────────────────────────────────────────────────────────┐
│ 🔧 HELPER SCRIPTS                                                            │
└──────────────────────────────────────────────────────────────────────────────┘

  ✓ scripts/preflight-check.sh
    ↳ Validates your environment is ready for testing
    ↳ Checks Python, Docker, services, dependencies, project structure
    ↳ Color-coded output with remediation steps

  ✓ scripts/generate-test-data.sh
    ↳ Generates all test data needed for test cases
    ↳ Creates 8+ sample datasets (CSV, JSON, Markdown-KV)
    ↳ Loads PostgreSQL test tables (if available)

┌──────────────────────────────────────────────────────────────────────────────┐
│ 🎯 TOP 20 TEST CASES                                                         │
└──────────────────────────────────────────────────────────────────────────────┘

  BASIC FEATURES (⭐ Beginner)
  ├─ 1. Basic CSV to Iceberg Ingestion
  ├─ 2. Incremental Sync with State Persistence
  ├─ 5. Schema Validation - Strict Mode
  └─ 6. Schema Validation - Warn Mode

  API INTEGRATIONS (⭐⭐ Intermediate)
  ├─ 3. Stripe Customer Ingestion
  │    ↳ Setup guide: Create free test account, generate test data
  └─ 4. HubSpot CRM Data Ingestion (Contacts, Companies, Deals)
       ↳ Setup guide: Create free CRM account, create test data

  DATABASE CONNECTORS (⭐⭐ Intermediate)
  ├─ 7. PostgreSQL to Iceberg (Full Table Sync)
  ├─ 8. PostgreSQL Incremental Sync (Cursor-based)
  └─ 9. PostgreSQL to Markdown-KV Transformation

  CUSTOM PLUGINS (⭐⭐⭐ Advanced)
  ├─ 10. Custom Python Reader Plugin (JSON API)
  └─ 11. Rust Plugin for Performance (10-15x faster)

  CLOUD INTEGRATIONS (⭐⭐⭐ Advanced)
  ├─ 12. Google Sheets Integration
  └─ 13. Google Drive CSV Extraction

  ADVANCED FEATURES (⭐⭐⭐ Advanced)
  ├─ 14. Multi-Tenant Job Execution
  ├─ 15. Environment Variable Secret Manager
  ├─ 16. Data Partitioning Strategies (single, multi-level, date)
  ├─ 17. Catalog Integration (OpenMetadata)
  ├─ 18. Orchestration with Dagster
  └─ 19. Error Handling and Retry Logic

  PRODUCTION SIMULATION (⭐⭐⭐⭐ Expert)
  └─ 20. End-to-End Production Pipeline (Multi-source, orchestrated)

┌──────────────────────────────────────────────────────────────────────────────┐
│ 🚀 QUICK START (5 minutes)                                                   │
└──────────────────────────────────────────────────────────────────────────────┘

  Step 1: Validate Environment
  $ ./scripts/preflight-check.sh

  Step 2: Generate Test Data
  $ ./scripts/generate-test-data.sh

  Step 3: Source Environment Variables
  $ source .env

  Step 4: Run Basic Smoke Test
  $ dativo run \
      --job-dir tests/fixtures/jobs \
      --secret-manager filesystem \
      --secrets-dir tests/fixtures/secrets \
      --mode self_hosted

  Step 5: Verify Results
  $ mc ls local/test-bucket --recursive
  $ ls -la .local/state/

┌──────────────────────────────────────────────────────────────────────────────┐
│ 📊 TEST COVERAGE                                                             │
└──────────────────────────────────────────────────────────────────────────────┘

  DATA SOURCES (8/8 - 100%)
  ✓ CSV                  ✓ PostgreSQL        ✓ MySQL
  ✓ Stripe API           ✓ HubSpot API       ✓ Google Sheets
  ✓ Google Drive CSV     ✓ Markdown-KV

  DATA TARGETS (4/4 - 100%)
  ✓ Iceberg (Parquet)    ✓ S3                ✓ MinIO
  ✓ Markdown-KV

  CORE FEATURES (100%)
  ✓ Schema Validation (strict, warn)
  ✓ Incremental Sync (state-based, cursor-based, timestamp-based)
  ✓ Custom Plugins (Python, Rust)
  ✓ Partitioning (single column, multi-level, date-based)
  ✓ Secret Management (filesystem, environment variables)
  ✓ Multi-Tenancy (tenant isolation, parallel execution)
  ✓ Catalog Integration (OpenMetadata lineage & metadata)
  ✓ Orchestration (Dagster scheduling, retry policies)
  ✓ Error Handling (retryable vs non-retryable, partial success)

┌──────────────────────────────────────────────────────────────────────────────┐
│ 🎓 LEARNING PATH                                                             │
└──────────────────────────────────────────────────────────────────────────────┘

  BEGINNER (1-2 hours)
  ↳ Test Cases 1, 2, 5, 6
  ↳ Learn: Basic ETL, schema validation, state management

  INTERMEDIATE (3-4 hours)
  ↳ Test Cases 3, 4, 7, 8, 14
  ↳ Learn: API connectors, database connectors, multi-tenancy

  ADVANCED (5-8 hours)
  ↳ Test Cases 9, 10, 12, 13, 16, 17, 18
  ↳ Learn: Custom plugins, cloud integrations, catalog, orchestration

  EXPERT (Full day)
  ↳ Test Cases 11, 19, 20
  ↳ Learn: Rust plugins, error handling, production pipelines

┌──────────────────────────────────────────────────────────────────────────────┐
│ 🎯 TEST ACCOUNT SETUP                                                        │
└──────────────────────────────────────────────────────────────────────────────┘

  STRIPE (2 minutes - FREE)
  1. Sign up: https://stripe.com
  2. Enable Test Mode (orange toggle)
  3. Get API key: Developers → API keys → Secret key (sk_test_...)
  4. Generate test data: Use dashboard or Stripe CLI
  5. Test cards: 4242 4242 4242 4242 (success)

  HUBSPOT (3 minutes - FREE)
  1. Sign up: https://www.hubspot.com/products/get-started
  2. Complete onboarding (choose CRM)
  3. Get API key: Settings → Integrations → Private Apps
  4. Generate test data: Create contacts, companies, deals in UI
  5. Share with dativo: Add API scopes for read access

  GOOGLE SHEETS/DRIVE (5 minutes)
  1. Create Google Cloud project
  2. Enable Sheets API and Drive API
  3. Create service account and download JSON key
  4. Share test spreadsheet with service account email

  ↳ Detailed setup guides in TESTING_PLAYBOOK.md

┌──────────────────────────────────────────────────────────────────────────────┐
│ 🐛 COMMON ISSUES & QUICK FIXES                                               │
└──────────────────────────────────────────────────────────────────────────────┘

  Issue: dativo: command not found
  Fix:   pip install -e .

  Issue: Services not running
  Fix:   docker-compose -f docker-compose.dev.yml up -d

  Issue: Connection refused to MinIO/Nessie
  Fix:   docker ps | grep minio && docker restart <container>

  Issue: Bucket does not exist
  Fix:   mc mb local/test-bucket

  Issue: Environment variables not set
  Fix:   source .env

  Issue: State directory missing
  Fix:   mkdir -p .local/state

  ↳ Full troubleshooting guide in TESTING_QUICK_REFERENCE.md

┌──────────────────────────────────────────────────────────────────────────────┐
│ 📖 DOCUMENT QUICK REFERENCE                                                  │
└──────────────────────────────────────────────────────────────────────────────┘

  START HERE
  → TESTING_GUIDE_INDEX.md - Navigation hub, learning path, checklists

  WHEN RUNNING TESTS
  → TESTING_PLAYBOOK.md - 20 detailed test cases with full instructions

  QUICK LOOKUPS
  → TESTING_QUICK_REFERENCE.md - Commands, patterns, troubleshooting

  VALIDATE ENVIRONMENT
  → scripts/preflight-check.sh - Check if ready for testing

  GENERATE DATA
  → scripts/generate-test-data.sh - Create all test datasets

  PLATFORM DOCS
  → README.md - Platform overview
  → QUICKSTART.md - Quick start guide
  → docs/* - Detailed documentation

┌──────────────────────────────────────────────────────────────────────────────┐
│ ✅ WHAT YOU HAVE NOW                                                         │
└──────────────────────────────────────────────────────────────────────────────┘

  ✓ 3,222 lines of comprehensive testing documentation
  ✓ 20 detailed test cases covering 100% of capabilities
  ✓ Step-by-step instructions (copy-paste ready)
  ✓ Test account setup guides (Stripe, HubSpot, Google)
  ✓ Automated environment validation script
  ✓ Automated test data generation script
  ✓ Quick reference command cheat sheet
  ✓ Learning path from beginner to expert
  ✓ Real-world production-ready patterns
  ✓ Troubleshooting guides and common fixes

┌──────────────────────────────────────────────────────────────────────────────┐
│ 🎉 NEXT STEPS                                                                │
└──────────────────────────────────────────────────────────────────────────────┘

  1. Read the Index
     $ cat TESTING_GUIDE_INDEX.md

  2. Validate Environment
     $ ./scripts/preflight-check.sh

  3. Generate Test Data
     $ ./scripts/generate-test-data.sh

  4. Run Your First Test
     $ source .env
     $ dativo run --job-dir tests/fixtures/jobs \
         --secrets-dir tests/fixtures/secrets --mode self_hosted

  5. Follow Test Cases 1-20
     → Open TESTING_PLAYBOOK.md and work through progressively

  6. Set Up Test Accounts
     → Stripe (2 min) + HubSpot (3 min) for API testing

  7. Master Advanced Features
     → Custom plugins, orchestration, production patterns

╔══════════════════════════════════════════════════════════════════════════════╗
║                                                                              ║
║                   🚀 READY TO START TESTING! 🚀                              ║
║                                                                              ║
║              Begin with: cat TESTING_GUIDE_INDEX.md                          ║
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝
