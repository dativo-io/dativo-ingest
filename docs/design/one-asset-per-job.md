# Design Decision: One Asset Per Job

## Core Invariant

**One Job = One Asset = One Source Object**

This is a hard invariant enforced by the platform. Each job configuration file must reference exactly one asset definition via `asset_path`, and each asset definition (specs-as-code) corresponds to exactly one source object (e.g., "customers", "charges", "contacts").

## Relationship to Specs-as-Code

Jobs reference exactly one `asset_definition` spec path (specs-as-code):

```yaml
# Job config references one asset definition
tenant_id: acme
asset_path: /app/assets/stripe/v1.0/customers.yaml  # One asset definition per job
source:
  object: customers  # Must match asset definition's object field
```

The asset definition is a versioned artifact that defines:
- Schema validation rules
- Governance metadata (ownership, classification, compliance)
- Target configuration (format, partitioning)
- Data contracts and SLAs

This 1:1 relationship ensures that each job configuration maps directly to a single data contract, enabling:
- Version-controlled schema changes
- Per-asset governance and ownership
- Clear lineage (one job → one table → one asset definition)

## Orchestration Pattern

The orchestrator (Dagster) schedules multiple single-asset jobs via `runner.yaml`:

```yaml
runner:
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_customers_hourly
        config: /app/jobs/acme/stripe_customers.yaml
        cron: "0 * * * *"
      - name: stripe_charges_hourly
        config: /app/jobs/acme/stripe_charges.yaml
        cron: "0 * * * *"
      - name: stripe_invoices_daily
        config: /app/jobs/acme/stripe_invoices.yaml
        cron: "15 2 * * *"
    concurrency_per_tenant: 1  # Serial execution per tenant
```

Each schedule references a separate job file, each with its own asset definition. This approach:
- Enables independent scheduling per asset
- Allows different cron patterns for different assets
- Maintains clear separation of concerns
- Supports orchestration-level dependencies if needed

See [Runner and Orchestration](../RUNNER_AND_ORCHESTRATION.md) for complete orchestration details.

## Serial Execution and Nessie Commits

Serial execution per tenant protects Nessie commits from conflicts. As documented in [Runner and Orchestration](../RUNNER_AND_ORCHESTRATION.md), tenant-level serialization (`concurrency_per_tenant: 1`) ensures only one job runs per tenant at a time, preventing concurrent Nessie commit conflicts and ensuring data consistency.

Given this serial execution model, multi-asset jobs don't provide concurrency benefits but do introduce complexity in failure handling and retry semantics. The one-asset-per-job pattern aligns with this execution model.

## Rationale

### 1. Operational Simplicity

**Scheduling Granularity**
- Each job has its own entry in `runner.yaml` with its own cron schedule
- Changing the schedule for `stripe_customers` vs `stripe_charges` is a one-line change
- No need for per-asset schedule logic inside a single config

**Failure Behavior & Retries**
- Job failure maps naturally: one job failed → one asset failed
- Exit codes and logs are per-asset
- Retry logic is straightforward: "retry this job"
- No need for per-asset sub-states or nested retry policies

**Serial Execution**
- Given serial per-tenant execution (to avoid Nessie commit conflicts), multi-asset jobs don't provide concurrency benefits
- But they do make failure & retry semantics more complex

### 2. Governance & Metadata

**Per-Asset Observability**
- Asset definitions encode schema, classification, owners, FinOps tags
- Each asset maps to a single Iceberg table
- Policy-as-code and FinOps telemetry are naturally per table / per asset
- Governance modules can treat "job run" ≈ "asset refresh" with simple semantics

**Lineage & Catalog Integration**
- Lineage is straightforward: one job → one table, one set of governance metadata
- OpenMetadata/lineage emissions are per-asset
- No conflicts between job-level and asset-level governance metadata

**FinOps & Accountability**
- FinOps aggregators want per-asset metrics (`cost_per_asset`, `violations_per_asset`)
- Multi-asset jobs would force either:
  - Duplicating metadata per asset (essentially single-asset jobs internally), or
  - Blurring responsibility (job-level only), which hurts accountability

### 3. Performance & Resource Management

**Connection Reuse**
- Multi-asset jobs could theoretically reuse connections/clients
- But this can be achieved at the orchestration layer:
  - A Dagster job that runs `stripe_customers`, `stripe_charges`, `stripe_invoices` back-to-back
  - Shared client and rate-limit handling inside the orchestrator
  - Engine's config model stays simple and atomic

**Container Overhead**
- Each run is a stateless Docker job
- Container startup overhead exists once per run, not per asset
- This cost exists whether using 1 or 5 assets in the job

**Rate Limits**
- Serial per-tenant execution already limits concurrency
- Cross-asset rate-limit impact is minimal
- Can be handled at orchestration layer if needed

### 4. Development, Debugging & Testing

**Reasoning About Jobs**
- Very easy to reason about: "this YAML defines everything needed to refresh this table"
- One file, one concern principle

**Debugging**
- Logs carry job, asset, source, etc., and map 1:1 to a single table
- If `stripe_customers` fails but `stripe_charges` is fine, no "partial job failures" to think about
- Clear attribution: "did that log line belong to customers or charges?"

**Testing**
- Per-asset integration tests: "run this job against test Stripe, assert schema & sample row count"
- CI can treat each asset_definition & job pair as a unit test
- No need to test cross-asset behavior and error handling within a job

### 5. Scalability

**Config Sprawl**
- With 100 assets, you'll have ~100 job files
- But they are short, regular YAMLs
- Can generate them from a higher-level manifest (e.g., "assets registry → codegen for jobs")
- `runner.yaml` already acts as a central index of jobs per tenant

**Dependencies**
- Cross-asset dependencies (e.g., invoices depend on customers) are a DAG/orchestration concern
- Use Dagster to define job dependencies:
  - Op A runs `stripe_customers.yaml`
  - Op B runs `stripe_invoices.yaml` (depends on A)
- Let Dagster manage order and status propagation
- Keep ingestion engine blind to dependency logic

### 6. Industry Patterns

**dbt**
- Strongly encourages one model per table/view
- Orchestration (dbt run, Airflow, Dagster) handles groups & dependencies

**Fivetran / Airbyte**
- They allow multiple tables/streams from one "connection"
- But this introduces complexity: overlaps in schedules, per-stream overrides, partial failures
- Many teams end up treating each important object as its own conceptual pipeline

**Modern Data Contracts**
- Typically per dataset/table, with distinct owners and SLAs
- Aligned with ODCS-style asset definitions and governance practices

## Implementation

### Validation

The platform enforces this invariant in `JobExecutor._load_asset()`:

```python
# Validate that source.objects matches asset definition's object field
if len(source_objects) > 1:
    self.logger.error(
        f"Multiple objects specified in source.objects: {source_objects}. "
        f"Each job should extract only one object that matches the asset definition. "
        f"Asset definition specifies object: '{asset_object}'. "
        "Create separate job files for each object.",
    )
    return 2
```

### Grouping Multiple Assets

When you need coordinated execution of multiple assets:

**Option 1: Orchestration Layer (Recommended)**
- Use Dagster to group multiple single-asset jobs
- Define a Dagster job with multiple ops, each running a separate job config
- Shared client/rate-limit handling can be done in the orchestrator
- Each asset still has its own config, state, and governance

**Option 2: Composite Jobs (Future Enhancement)**
- If truly needed, implement as a composite job that orchestrates multiple single-asset job runs internally
- Keep the job schema and state model unchanged
- Composite job = wrapper that calls multiple `JobExecutor` instances
- This preserves the engine's simplicity while allowing grouping

## Example: Stripe Multi-Asset Setup

Instead of one job with multiple assets:

```yaml
# ❌ NOT SUPPORTED
source:
  object: customers  # Only one object per job
  # Cannot specify multiple objects - create separate jobs instead
```

Create separate job files:

```yaml
# jobs/tenant/stripe_customers.yaml
asset: stripe_customers
asset_path: assets/examples/stripe/v1.0/customers.yaml
source:
  object: customers

# jobs/tenant/stripe_charges.yaml
asset: stripe_charges
asset_path: assets/examples/stripe/v1.0/charges.yaml
source:
  object: charges

# jobs/tenant/stripe_invoices.yaml
asset: stripe_invoices
asset_path: assets/examples/stripe/v1.0/invoices.yaml
source:
  object: invoices
```

Then schedule them in `runner.yaml`:

```yaml
runner:
  orchestrator:
    schedules:
      - name: stripe_customers_hourly
        config: /app/jobs/tenant/stripe_customers.yaml
        cron: "0 * * * *"
      - name: stripe_charges_frequent
        config: /app/jobs/tenant/stripe_charges.yaml
        cron: "*/15 * * * *"
      - name: stripe_invoices_daily
        config: /app/jobs/tenant/stripe_invoices.yaml
        cron: "15 2 * * *"
```

Or use Dagster dependencies for coordinated execution:

```python
@job
def stripe_full_sync():
    customers = run_job_op("stripe_customers.yaml")
    charges = run_job_op("stripe_charges.yaml")
    invoices = run_job_op("stripe_invoices.yaml", deps=[customers])
```

## Benefits Summary

| Aspect | One Asset Per Job | Multi-Asset Per Job |
|--------|------------------|---------------------|
| **Scheduling** | ✅ Per-asset cron, simple | ❌ Complex per-asset schedules |
| **Failure Handling** | ✅ Clear: one job = one failure | ❌ Partial failures, complex retries |
| **Governance** | ✅ Per-asset metadata, clear ownership | ❌ Conflicting metadata, blurred responsibility |
| **Debugging** | ✅ Clear logs, easy attribution | ❌ Mixed logs, unclear attribution |
| **Testing** | ✅ Per-asset unit tests | ❌ Cross-asset integration tests needed |
| **Scalability** | ✅ Simple configs, codegen-friendly | ❌ Complex configs, harder to scale |
| **Dependencies** | ✅ Orchestration layer handles it | ❌ Need dependency logic in engine |
| **Specs-as-Code** | ✅ 1:1 mapping to asset definitions | ❌ Breaks specs-as-code contract model |
| **Orchestration** | ✅ Natural fit for Dagster scheduling | ❌ Requires complex orchestration logic |

## Conclusion

The one-asset-per-job pattern is the right choice for dativo-ingest because it:

1. **Simplifies operations**: Clear failure semantics, straightforward retries, per-asset scheduling
2. **Enables governance**: Per-asset observability, clear ownership, FinOps accountability
3. **Aligns with specs-as-code**: Each job references exactly one asset definition, maintaining the 1:1 relationship between jobs and data contracts
4. **Integrates with orchestration**: Dagster schedules multiple single-asset jobs naturally via `runner.yaml`
5. **Protects Nessie commits**: Serial execution per tenant prevents commit conflicts
6. **Improves developer experience**: Easy to reason about, debug, and test
7. **Scales well**: Simple configs, orchestration handles dependencies
8. **Aligns with industry best practices**: Matches dbt, modern data contracts, governance patterns

If grouping is needed, use the orchestration layer (Dagster) rather than changing the core job model.

## Related Documentation

- [Runner and Orchestration](../RUNNER_AND_ORCHESTRATION.md) - Orchestration with Dagster and serial execution per tenant
- [Configuration Reference](../CONFIG_REFERENCE.md) - Job and asset configuration details
- [Asset Definitions](../CONFIG_REFERENCE.md#asset-definitions) - Specs-as-code asset definition format

