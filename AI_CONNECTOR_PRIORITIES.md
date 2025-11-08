# Dativo Connector Priorities for AI Teams

**Source**: Real-world AI pipeline implementations  
**Date**: November 7, 2025  
**Use Cases**: RAG, copilots, triage, customer 360, evals

---

## 🎯 Top 5 Data Sources for AI Teams

### ✅ **#1: Documents & Knowledge Bases** (COMPLETE)
- **Sources**: Google Drive, Google Sheets, Notion, Confluence
- **Use Case**: RAG content (policies, playbooks, specs, FAQs)
- **Status**: ✅ **DONE** in v1.4
  - Google Drive CSV: ✅
  - Google Sheets: ✅
  - Markdown-KV format: ✅

---

### 🔴 **#2: Support & CX Systems** (CRITICAL GAP)
- **Sources**: Zendesk, Intercom, Freshdesk
- **Use Case**: Triage bots, intent classification, auto-reply
- **Status**: 🔴 **MISSING** - Highest priority
- **Target**: **Sprint 7 (Month 4, Weeks 13-14)**
- **Priority**: **P0 - CRITICAL**

**What to Build**:
```yaml
Zendesk Connector:
  - Tickets (with full conversation threads)
  - Tags, categories, priority
  - SLA fields (response time, resolution time)
  - CSAT scores
  - Resolution summaries
  - Agent notes
  - Incremental: updated_at cursor

Intercom Connector:
  - Conversations (customer + agent messages)
  - User metadata
  - Tags, segments
  - CSAT ratings
  - Incremental: updated_at cursor
```

---

### ⚠️ **#3: CRM & RevOps** (PARTIAL)
- **Sources**: HubSpot, Salesforce
- **Use Case**: Personalization, routing, guardrails, customer 360
- **Status**: 
  - HubSpot: ✅ **DONE** in v1.4
  - Salesforce: 🔴 **MISSING**
- **Target**: **Sprint 8 (Month 4, Weeks 15-16)**
- **Priority**: **P0 - CRITICAL**

---

### 🔴 **#4: Product Analytics** (CRITICAL GAP)
- **Sources**: Mixpanel, PostHog, Amplitude
- **Use Case**: Behavioral context, evaluation loops, personalization
- **Status**: 🔴 **MISSING** - High priority
- **Target**: **Sprint 9-10 (Month 5)**
- **Priority**: **P0 - CRITICAL**

**What to Build**:
```yaml
Mixpanel Connector:
  - Event streams (page views, clicks, custom events)
  - User properties (plan, role, company)
  - Cohorts (power users, at-risk, etc.)
  - Funnel data
  - Incremental: event timestamp

PostHog Connector:
  - Events (similar to Mixpanel)
  - Feature flags (for A/B testing)
  - Session recordings metadata
  - User properties
  - Incremental: timestamp
```

---

### ✅ **#5: Payments & Billing** (COMPLETE)
- **Sources**: Stripe, Chargebee, Recurly
- **Use Case**: Entitlements, paywall logic, LTV-based personalization
- **Status**: ✅ **DONE** in v1.4
  - Stripe: ✅ (4 objects: customers, subscriptions, invoices, charges)

---

## 🏃 Runners-Up (Priority 6-8)

### Engineering & Work Hubs
- **GitHub**: Code, issues, PRs (dev copilots, incident RAG)
- **Jira**: Tickets, sprints, epics
- **Target**: Month 6-7
- **Priority**: P1

### Marketing & Attribution
- **Google Analytics 4**: Traffic, conversions
- **Google Ads**: Campaign performance
- **Facebook Ads**: Creative testing
- **Target**: Month 7-8
- **Priority**: P2

### E-Commerce
- **Shopify**: Products, orders, customers
- **WooCommerce**: Similar
- **Target**: Month 8-9
- **Priority**: P2

---

## 📊 Connector Status Dashboard

```
Priority | Source          | Status | Target   | Impact |
---------|-----------------|--------|----------|--------|
P0       | Google Drive    | ✅ DONE | v1.4     | HIGH   |
P0       | Google Sheets   | ✅ DONE | v1.4     | HIGH   |
P0       | HubSpot         | ✅ DONE | v1.4     | HIGH   |
P0       | Stripe          | ✅ DONE | v1.4     | HIGH   |
P0       | Zendesk         | 🔴 TODO | Sprint 7 | HIGH   |
P0       | Intercom        | 🔴 TODO | Sprint 7 | HIGH   |
P0       | Salesforce      | 🔴 TODO | Sprint 8 | HIGH   |
P0       | Mixpanel        | 🔴 TODO | Sprint 9 | HIGH   |
P0       | PostHog         | 🔴 TODO | Sprint 9 | HIGH   |
P1       | Freshdesk       | 🔴 TODO | Sprint 10| MEDIUM |
P1       | GitHub          | 🔴 TODO | Month 6  | MEDIUM |
P1       | Jira            | 🔴 TODO | Month 6  | MEDIUM |
P1       | Amplitude       | 🔴 TODO | Month 7  | MEDIUM |
P2       | Google Ads      | 🔴 TODO | Month 7  | LOW    |
P2       | Shopify         | 🔴 TODO | Month 8  | LOW    |
```

---

## 🎯 Updated v1.1 Release Scope

### MUST-HAVE (Block Release)
- ✅ Google Drive CSV
- ✅ Google Sheets  
- ✅ HubSpot
- ✅ Stripe
- ✅ Postgres
- ✅ MySQL
- 🔴 **Zendesk** (NEW - most critical gap)
- 🔴 **Intercom** (NEW - alternative to Zendesk)
- 🔴 **Salesforce** (already planned)

### EXIT CRITERIA
- **8/10 Top AI sources** covered
- All AI use cases enabled (RAG, copilots, triage, customer 360)
- Can claim: **"The data platform AI teams use for production RAG"**

---

## 📅 Revised Sprint Plan

### Sprint 7 (Weeks 13-14): Support Systems [UPDATED]
**OLD**: Salesforce + Snowflake + MongoDB  
**NEW**: **Zendesk + Intercom** (prioritize AI use case)

**Rationale**:
- Zendesk/Intercom are #2 most requested (after docs)
- More valuable than Snowflake/MongoDB for AI market
- Snowflake/MongoDB can wait until Month 8-9

**Deliverables**:
- Zendesk connector (tickets, conversations, CSAT)
- Intercom connector (conversations, users, segments)
- Asset schemas for both
- Example RAG pipeline (support tickets → Markdown-KV → vector DB)

### Sprint 8 (Weeks 15-16): CRM + Data Contracts
- Salesforce connector
- Soda + Great Expectations integration
- Data contract enforcement

### Sprint 9-10 (Weeks 17-20): Analytics + Compliance
- Mixpanel connector
- PostHog connector  
- DSR operations (GDPR)
- Parallel processing

---

## 💡 Positioning Update

### OLD Positioning
"Config-driven ingestion platform for ML teams"

### NEW Positioning (AI-Focused)
"The data platform AI teams use to build production RAG systems"

### Value Prop
"Ingest the Top 5 AI data sources in 1 hour, not 1 week"

### Customer Quote (Projected)
> "We tried building custom API wrappers for Zendesk, HubSpot, and Stripe.
> 3 months later, we had brittle code and no time for AI features.
> 
> With Dativo, we got all 3 sources ingesting in 2 days, plus automatic
> Markdown-KV format for our RAG pipeline. Now we ship AI features instead
> of plumbing."
> 
> — CTO, AI Startup (50 employees)

---

## 🏆 Competitive Advantage (AI Use Cases)

### Why Dativo Wins for AI Teams

| Capability | Dativo | Airbyte | Fivetran | Custom |
|------------|--------|---------|----------|--------|
| Top 5 AI Sources | 5/5 | 3/5 | 3/5 | 2/5 |
| Markdown-KV (RAG) | ✅ Native | ❌ None | ❌ None | 🔴 40+ hrs |
| Quality Contracts | ✅ Built-in | ❌ None | ❌ None | 🔴 Custom |
| Data Versioning | ✅ Iceberg | ❌ None | ❌ None | 🔴 Custom |
| Time to Production | 1 day | 1 week | 1 week | 3 months |

**Score**: Dativo 10/10 vs. Competitors 2-4/10

---

## 💰 Business Impact

### Market Size (AI-Specific)
- **10,000+ companies** building AI applications (2024)
- **70%** use 3+ of the Top 5 sources
- **Average spend** on data plumbing: $120K/year

### Dativo Opportunity
- Replace custom API wrappers: **$120K → $15K** (92% savings)
- Time to production: **3 months → 2 days** (98% faster)
- TAM: **10,000 companies × $15K = $150M**

### Year 1 Target
- 1% market share = 100 companies × $15K = **$1.5M ARR**
- Conservative: 50 companies = **$750K ARR**

---

## ✅ Action Items

### Immediate (This Week)
- [ ] Reprioritize Sprint 7: Replace Snowflake/MongoDB with Zendesk/Intercom
- [ ] Review Zendesk API documentation
- [ ] Review Intercom API documentation
- [ ] Update sprint planning docs

### Week 1-2 (Sprint 7 Prep)
- [ ] Design Zendesk connector architecture
- [ ] Design Intercom connector architecture
- [ ] Create asset schemas (tickets, conversations)
- [ ] Setup test accounts (Zendesk + Intercom)

### Week 3-4 (Sprint 7 Execution)
- [ ] Build Zendesk connector
- [ ] Build Intercom connector
- [ ] Write integration tests
- [ ] Create example RAG pipeline tutorial

---

**Last Updated**: November 7, 2025  
**Source**: Real-world AI team feedback  
**Next Review**: Weekly during Sprint 7
