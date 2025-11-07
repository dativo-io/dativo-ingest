# MVP Execution Plan: Next 12 Weeks

**Goal**: Ship production-ready platform for AI/ML use cases  
**Target Date**: Week 12 (February 2026)  
**Success Metric**: 5 paying customers using Dativo in production

---

## Week-by-Week Breakdown

### **Week 1-2: Stripe Connector**
**Owner**: Backend Engineer  
**Priority**: P0 (Critical Path)

**Day 1-2: Setup & Design**
- [ ] Review Stripe API documentation (v2024-06-20)
- [ ] Design extractor architecture (incremental sync, rate limiting)
- [ ] Create asset schemas (customers, charges, invoices, subscriptions)
- [ ] Setup Stripe test account and API keys
- [ ] Document technical design

**Day 3-5: Core Implementation**
- [ ] Implement `StripeExtractor` class
- [ ] Add pagination handling (100 records per page)
- [ ] Add incremental sync (timestamp-based cursors)
- [ ] Implement rate limiting (100 req/sec default)

**Day 6-8: Error Handling**
- [ ] Add retry logic for transient failures
- [ ] Handle 429 (rate limit) errors with backoff
- [ ] Handle 401 (auth) errors gracefully
- [ ] Add connection pooling for API sessions

**Day 9-10: Testing**
- [ ] Write unit tests (target: 85% coverage)
- [ ] Write integration tests with Stripe test account
- [ ] End-to-end smoke test (Stripe → Parquet → S3)
- [ ] Performance test (target: 10K records/min)

**Deliverables**:
- ✅ `src/dativo_ingest/connectors/stripe_extractor.py`
- ✅ `assets/stripe/v1.0/*.yaml` (4 objects)
- ✅ `tests/test_stripe_extractor.py`
- ✅ Documentation: `docs/connectors/STRIPE.md`

**Acceptance Criteria**:
- ✅ All 4 objects extractable (customers, charges, invoices, subscriptions)
- ✅ Incremental sync persists state correctly
- ✅ Rate limiting prevents 429 errors
- ✅ Test coverage >80%
- ✅ End-to-end smoke test passes

---

### **Week 3-4: HubSpot Connector**
**Owner**: Backend Engineer  
**Priority**: P0 (Critical Path)

**Day 1-2: Setup & Design**
- [ ] Review HubSpot API v3 documentation
- [ ] Design cursor-based pagination strategy
- [ ] Create asset schemas (contacts, deals, companies, tickets)
- [ ] Setup HubSpot test account
- [ ] Implement OAuth2 flow

**Day 3-5: Core Implementation**
- [ ] Implement `HubSpotExtractor` class
- [ ] Add cursor-based pagination (after token)
- [ ] Add incremental sync (lastmodifieddate)
- [ ] Implement batch property fetching

**Day 6-8: Associations & Auth**
- [ ] Add association fetching (contacts → deals)
- [ ] Implement OAuth2 token refresh
- [ ] Add API key authentication (fallback)
- [ ] Handle rate limiting (100 req/10sec)

**Day 9-10: Testing**
- [ ] Write unit tests (target: 85% coverage)
- [ ] Write integration tests with HubSpot test account
- [ ] End-to-end smoke test
- [ ] Performance test

**Deliverables**:
- ✅ `src/dativo_ingest/connectors/hubspot_extractor.py`
- ✅ `connectors/hubspot.yaml` (updated)
- ✅ `assets/hubspot/v1.0/*.yaml` (4 objects)
- ✅ `tests/test_hubspot_extractor.py`
- ✅ Documentation: `docs/connectors/HUBSPOT.md`

---

### **Week 5-6: Error Handling Framework**
**Owner**: Senior Backend Engineer  
**Priority**: P0 (Production Blocker)

**Day 1-3: Error Classification**
- [ ] Implement `ErrorClassifier` (transient, rate limit, auth, permanent)
- [ ] Map HTTP status codes to error types
- [ ] Add error pattern matching (regex-based)
- [ ] Create error type enum

**Day 4-6: Retry Logic**
- [ ] Implement `RetryHandler` with exponential backoff
- [ ] Add jitter to prevent thundering herd
- [ ] Per-error-type retry policies
- [ ] Add retry callback hooks

**Day 7-9: Circuit Breaker & DLQ**
- [ ] Implement `CircuitBreaker` (open/closed/half-open states)
- [ ] Implement `DeadLetterQueue` for failed records
- [ ] S3 persistence for DLQ records
- [ ] Add metrics for monitoring

**Day 10: Integration**
- [ ] Integrate with Stripe connector
- [ ] Integrate with HubSpot connector
- [ ] Integrate with Postgres connector
- [ ] End-to-end testing

**Deliverables**:
- ✅ `src/dativo_ingest/error_handler.py`
- ✅ `src/dativo_ingest/circuit_breaker.py`
- ✅ `src/dativo_ingest/dead_letter_queue.py`
- ✅ `configs/error_handling.yaml`
- ✅ Documentation: `docs/ERROR_HANDLING.md`

---

### **Week 7-8: MySQL Connector**
**Owner**: Backend Engineer  
**Priority**: P1 (Important)

**Day 1-2: Design**
- [ ] Review Postgres connector implementation
- [ ] Design MySQL-specific differences (types, connection pooling)
- [ ] Create asset schemas

**Day 3-6: Implementation**
- [ ] Implement `MySQLExtractor` class
- [ ] Add connection pooling (5 connections default)
- [ ] Full table sync
- [ ] Incremental sync (cursor-based)

**Day 7-8: Testing**
- [ ] Unit tests
- [ ] Integration tests with MySQL test DB
- [ ] Performance tests (large tables)

**Day 9-10: Documentation**
- [ ] Write connector documentation
- [ ] Example job configs
- [ ] Migration guide from Postgres

**Deliverables**:
- ✅ `src/dativo_ingest/connectors/mysql_extractor.py`
- ✅ `tests/test_mysql_extractor.py`
- ✅ Documentation: `docs/connectors/MYSQL.md`

---

### **Week 9-10: Google Drive & Sheets Connectors**
**Owner**: Backend Engineer  
**Priority**: P1 (File-based sources)

**Day 1-3: OAuth2 Setup**
- [ ] Implement OAuth2 handler with token refresh
- [ ] Document OAuth2 setup process
- [ ] Create test Google Cloud project
- [ ] Setup OAuth2 credentials

**Day 4-6: Google Drive CSV**
- [ ] Implement `GoogleDriveCsvExtractor`
- [ ] File discovery by folder ID
- [ ] Modified time tracking
- [ ] Large file streaming (>100MB)

**Day 7-9: Google Sheets**
- [ ] Implement `GoogleSheetsExtractor`
- [ ] Spreadsheet reading by ID
- [ ] Multiple sheets support
- [ ] Range-based extraction (A1 notation)

**Day 10: Testing & Documentation**
- [ ] Unit tests for both connectors
- [ ] Integration tests with test Google account
- [ ] End-to-end smoke tests
- [ ] Documentation

**Deliverables**:
- ✅ `src/dativo_ingest/connectors/gdrive_csv_extractor.py`
- ✅ `src/dativo_ingest/connectors/google_sheets_extractor.py`
- ✅ `src/dativo_ingest/oauth2_handler.py`
- ✅ Documentation: `docs/connectors/GOOGLE_OAUTH2_SETUP.md`

---

### **Week 11-12: Observability & Launch Prep**
**Owner**: DevOps + Backend Engineers  
**Priority**: P0 (Production Readiness)

**Day 1-3: Metrics**
- [ ] Implement Prometheus metrics collector
- [ ] Add job duration metrics
- [ ] Add throughput metrics (records/sec)
- [ ] Add error rate metrics

**Day 4-6: Dashboards**
- [ ] Create Grafana dashboard (job success rate, throughput, errors)
- [ ] Setup Prometheus alerting rules
- [ ] Configure alert notifications (Slack, email)
- [ ] Cost attribution dashboard

**Day 7-8: Documentation**
- [ ] Write "Build a RAG Pipeline" tutorial
- [ ] Record video walkthrough (Stripe → Markdown-KV → LLM)
- [ ] Update README with new connectors
- [ ] Production deployment guide

**Day 9-10: Launch Preparation**
- [ ] Final end-to-end testing
- [ ] Performance benchmarking
- [ ] Security review
- [ ] Prepare launch blog post
- [ ] Identify 10 target companies for outreach

**Deliverables**:
- ✅ `src/dativo_ingest/metrics.py` (enhanced)
- ✅ `configs/grafana/dativo_dashboard.json`
- ✅ `configs/prometheus/*.yml`
- ✅ Documentation: `docs/OBSERVABILITY.md`
- ✅ Tutorial: `docs/tutorials/RAG_PIPELINE.md`
- ✅ Video: Stripe to LLM demo

---

## Weekly Ceremonies

### Monday: Sprint Planning (1 hour)
- Review previous week's accomplishments
- Plan current week's tasks
- Identify blockers and dependencies
- Assign tasks to team members

### Wednesday: Mid-Week Check-in (30 min)
- Progress update
- Adjust priorities if needed
- Address blockers

### Friday: Sprint Review & Demo (1 hour)
- Demo completed work
- Review test coverage and code quality
- Plan next week

### Daily Standup (15 min)
- What did I complete yesterday?
- What will I work on today?
- Any blockers?

---

## Resource Allocation

### Team Structure (Minimum)

| Role | Allocation | Responsibilities |
|------|------------|------------------|
| **Senior Backend Engineer** | 100% | Error handling, architecture, code reviews |
| **Backend Engineer #1** | 100% | Stripe, HubSpot connectors |
| **Backend Engineer #2** | 100% | MySQL, Google connectors |
| **DevOps Engineer** | 50% | Observability, CI/CD, deployment |
| **QA Engineer** | 50% | Integration testing, performance testing |
| **Technical Writer** | 25% | Documentation, tutorials |

**Total**: ~4.5 FTEs

### Optional Enhancements (Nice to Have)

If more resources available:
- **Frontend Engineer** (25%): Build monitoring dashboard UI
- **Data Engineer** (25%): Advanced Markdown-KV transformations
- **Marketing** (25%): Launch preparation, content creation

---

## Risk Management

### High Priority Risks

| Risk | Impact | Mitigation | Owner |
|------|--------|------------|-------|
| **API rate limiting blocks testing** | High | Setup multiple test accounts, implement rate limiting early | Backend #1 |
| **OAuth2 complexity delays Google connectors** | Medium | Use existing libraries (google-auth-oauthlib), start early | Backend #2 |
| **Performance doesn't meet targets** | High | Benchmark early (week 2), optimize incrementally | Senior Backend |
| **Security vulnerability discovered** | Critical | Security review in week 1, dependency scanning in CI | DevOps |

### Medium Priority Risks

| Risk | Impact | Mitigation | Owner |
|------|--------|------------|-------|
| **Test coverage falls below 80%** | Medium | Mandatory code review checklist, CI gates | Senior Backend |
| **Documentation incomplete** | Medium | Documentation tasks in each sprint, dedicated writer | Tech Writer |
| **Integration tests flaky** | Medium | Retry logic, better test isolation | QA Engineer |

---

## Success Metrics

### Engineering Metrics (Week 12 Targets)

```yaml
Code Quality:
  - Test coverage: >85%
  - Lines of code: ~15,000 new (connectors + framework)
  - PR review time: <24 hours
  - CI/CD pass rate: >95%

Performance:
  - Stripe connector: 10K records/min
  - HubSpot connector: 8K records/min
  - MySQL connector: 50K records/min
  - Parquet writing: 500MB/min

Reliability:
  - Error rate: <0.1%
  - Retry success rate: >95%
  - Uptime: >99.5%
```

### Product Metrics (Week 12 Targets)

```yaml
Adoption:
  - Design partners: 5 customers
  - GitHub stars: 100+
  - Documentation views: 500+/week

Usage:
  - Active deployments: 5+
  - Daily jobs: 50+
  - Data synced: 100GB/day
```

---

## Definition of Done (MVP)

The MVP is considered **DONE** when:

### Core Features
- ✅ 6 connectors production-ready:
  - Postgres ✅ (already complete)
  - Stripe
  - HubSpot
  - MySQL
  - Google Drive CSV
  - Google Sheets
- ✅ Error handling framework operational
- ✅ Retry logic handles 95%+ of transient failures
- ✅ Observability (Prometheus + Grafana) deployed

### Quality Gates
- ✅ Test coverage >85% across all connectors
- ✅ All integration tests passing
- ✅ End-to-end smoke tests passing
- ✅ Performance benchmarks met
- ✅ Security review complete (no critical vulnerabilities)

### Documentation
- ✅ Connector documentation complete
- ✅ "Build a RAG Pipeline" tutorial published
- ✅ Video walkthrough recorded
- ✅ Production deployment guide ready

### Customer Validation
- ✅ 5 design partner customers committed
- ✅ At least 1 customer in production
- ✅ Positive feedback (NPS >40)

---

## Post-MVP Actions (Week 13+)

Once MVP is complete, immediately begin:

1. **Customer Onboarding** (Week 13-14)
   - Hands-on support for design partners
   - Gather feedback
   - Prioritize feature requests

2. **Marketing Launch** (Week 13)
   - Publish launch blog post
   - Share on HackerNews, Reddit, LinkedIn
   - Email target companies
   - Submit to AI/ML newsletters

3. **Open Source Release** (Week 14)
   - Finalize license (Apache 2.0 or MIT)
   - Prepare GitHub repo
   - Create CONTRIBUTING.md
   - Setup GitHub Issues and Discussions

4. **Plan Q2 Roadmap** (Week 15)
   - Review customer feedback
   - Prioritize next connectors (Salesforce, Snowflake)
   - Plan security & compliance sprint
   - Schedule v2.0.0 release

---

## Communication Plan

### Internal (Team)
- **Daily**: Slack updates in #engineering channel
- **Daily**: 9:00 AM standup (15 min)
- **Weekly**: Monday sprint planning, Friday demo
- **Ad-hoc**: Pair programming sessions as needed

### External (Stakeholders)
- **Weekly**: Friday email update (progress, blockers, metrics)
- **Bi-weekly**: Demo to leadership (30 min)
- **Monthly**: Board update (if applicable)

### Customers (Design Partners)
- **Weekly**: Check-in calls (30 min)
- **Bi-weekly**: Feature previews
- **Monthly**: Feedback sessions

---

## Contingency Plans

### If We're Behind Schedule (Week 6 Check-in)

**Scenario**: 2+ weeks behind target

**Actions**:
1. **Descope non-critical features**:
   - Remove Google Sheets (keep only Drive CSV)
   - Simplify OAuth2 (API key only for MVP)
   - Defer advanced error handling (keep basic retry)

2. **Add resources**:
   - Hire contractor for documentation
   - Bring in QA contractor for testing
   - Reduce other commitments

3. **Extend timeline**:
   - Shift launch to Week 14
   - Communicate to stakeholders

### If Key Engineer Unavailable

**Scenario**: Backend Engineer #1 unexpectedly unavailable

**Actions**:
1. **Reassign tasks**:
   - Senior Backend takes over critical path
   - Backend #2 handles both MySQL and Stripe
   
2. **Simplify scope**:
   - Remove HubSpot from MVP
   - Focus on Stripe + MySQL only

3. **Cross-training**:
   - Document all work-in-progress
   - Pair programming sessions

---

## Tools & Infrastructure

### Development Environment
```bash
# Required tools
- Python 3.10+
- Docker & Docker Compose
- Git
- VS Code or PyCharm

# Services (docker-compose.dev.yml)
- PostgreSQL 15
- MySQL 8.0
- MinIO (S3-compatible storage)
- Nessie (Iceberg catalog)
- Prometheus
- Grafana

# External accounts needed
- Stripe test account
- HubSpot test account
- Google Cloud project (for Drive/Sheets)
```

### CI/CD Pipeline
```yaml
# GitHub Actions workflows
- Unit tests (on every commit)
- Integration tests (on PR)
- Smoke tests (on merge to main)
- Security scanning (daily)
- Docker build (on release)
```

### Monitoring & Observability
```yaml
# Metrics
- Prometheus (metrics collection)
- Grafana (dashboards)
- AlertManager (alerting)

# Logging
- JSON structured logs
- CloudWatch or ELK Stack (production)

# Tracing (deferred to Q2)
- OpenTelemetry
```

---

## Budget Estimate

### Infrastructure Costs (Monthly)

```yaml
Development:
  - AWS/GCP compute: $200
  - S3/GCS storage: $50
  - Test accounts (Stripe, HubSpot): $0 (free tiers)
  Total: $250/month

Production (5 design partners):
  - AWS/GCP compute: $500
  - S3/GCS storage: $200
  - Monitoring (Datadog/NewRelic): $100
  Total: $800/month
```

### Personnel Costs (12 weeks)

```yaml
Senior Backend Engineer: $50K
Backend Engineer #1: $40K
Backend Engineer #2: $40K
DevOps Engineer (50%): $15K
QA Engineer (50%): $12K
Technical Writer (25%): $6K

Total: $163K for MVP (12 weeks)
```

**Note**: Costs vary significantly by location and seniority. These are rough estimates for US-based contractors.

---

## Appendix: Quick Reference

### Key Files to Create/Update

```
src/dativo_ingest/connectors/
  ├── stripe_extractor.py          [NEW - Week 1-2]
  ├── hubspot_extractor.py         [NEW - Week 3-4]
  ├── mysql_extractor.py           [NEW - Week 7-8]
  ├── gdrive_csv_extractor.py      [NEW - Week 9-10]
  └── google_sheets_extractor.py   [NEW - Week 9-10]

src/dativo_ingest/
  ├── error_handler.py             [NEW - Week 5-6]
  ├── circuit_breaker.py           [NEW - Week 5-6]
  ├── dead_letter_queue.py         [NEW - Week 5-6]
  ├── oauth2_handler.py            [NEW - Week 9-10]
  └── metrics.py                   [ENHANCE - Week 11-12]

assets/
  ├── stripe/v1.0/*.yaml           [NEW - Week 1-2]
  ├── hubspot/v1.0/*.yaml          [NEW - Week 3-4]
  └── google_sheets/v1.0/*.yaml    [NEW - Week 9-10]

configs/
  ├── error_handling.yaml          [NEW - Week 5-6]
  ├── prometheus/prometheus.yml    [NEW - Week 11-12]
  └── grafana/dativo_dashboard.json [NEW - Week 11-12]

docs/connectors/
  ├── STRIPE.md                    [NEW - Week 2]
  ├── HUBSPOT.md                   [NEW - Week 4]
  ├── MYSQL.md                     [NEW - Week 8]
  └── GOOGLE_OAUTH2_SETUP.md       [NEW - Week 10]

docs/
  ├── ERROR_HANDLING.md            [NEW - Week 6]
  ├── OBSERVABILITY.md             [NEW - Week 12]
  └── tutorials/RAG_PIPELINE.md    [NEW - Week 12]
```

### Command Cheatsheet

```bash
# Development
make setup-dev          # Setup development environment
make test-unit          # Run unit tests
make test-integration   # Run integration tests
make test-smoke         # Run smoke tests
make lint               # Run linters

# Testing individual connectors
pytest tests/test_stripe_extractor.py -v
pytest tests/test_hubspot_extractor.py -v

# Running smoke tests
dativo_ingest run --config tests/fixtures/jobs/stripe_customers.yaml

# Docker
docker-compose -f docker-compose.dev.yml up -d   # Start services
docker-compose -f docker-compose.dev.yml down    # Stop services

# Monitoring
open http://localhost:9090  # Prometheus
open http://localhost:3000  # Grafana
```

---

**Document Owner**: Engineering Lead  
**Last Updated**: 2025-11-07  
**Review Frequency**: Weekly (during MVP phase)  
**Status**: Active Execution
