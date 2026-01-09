# FAQ: Frequently Asked Questions

Common questions about Dativo Ingestion Platform.

## General Questions

### How is Dativo different from Airbyte?

**Airbyte** focuses on UI-driven configuration and hosted management. **Dativo** is headless and code-driven:

- **Headless operation**: No UI required – perfect for GitOps, CI/CD, and infrastructure-as-code
- **Schema enforcement**: Built-in [ODCS v3.0.2](SCHEMA_VALIDATION.md) data contract validation (strict/warn modes)
- **Governance-first**: Per-asset ownership, classification, and FinOps tags out-of-the-box
- **Multi-tenant**: Built-in tenant isolation for state, secrets, and data
- **Uses Airbyte connectors**: You get Airbyte's connector ecosystem without the UI/overhead
- **Custom plugins**: Extend with Python or Rust plugins (see [Custom Plugins](CUSTOM_PLUGINS.md) for performance details)

**Use Airbyte if**: You need 300+ pre-built connectors and prefer UI-driven configuration.  
**Use Dativo if**: You need headless operation, schema enforcement, multi-tenancy, or custom plugins.

### How is Dativo different from writing my own scripts?

**Custom scripts** require you to build everything yourself. **Dativo** provides:

- **Production-ready infrastructure**: Retry policies, error handling, state management, observability
- **Schema validation**: ODCS v3.0.2 compliant data contracts with strict validation
- **Connector ecosystem**: Reuse Airbyte connectors without building API integrations
- **Multi-tenant isolation**: Built-in tenant separation for state, secrets, and data
- **Iceberg integration**: Direct integration with modern data lake formats
- **Plugin system**: Custom readers/writers without rebuilding the entire pipeline

**Write custom scripts if**: You have very specific requirements that don't fit standard patterns.  
**Use Dativo if**: You want production-ready infrastructure with governance and schema enforcement.

### Can I use Airbyte connectors with Dativo?

**Yes!** Dativo uses Airbyte connectors under the hood. You get:

- Access to Airbyte's connector ecosystem (Stripe, HubSpot, etc.)
- Headless operation without Airbyte's UI/overhead
- Schema enforcement and governance on top
- Multi-tenant isolation
- Custom Python/Rust plugins alongside Airbyte connectors

See [Connector Reference](connectors.md) for supported connectors.

### What about Singer/Meltano?

**Singer/Meltano** use a different plugin architecture (taps/targets). Dativo:

- Uses Airbyte connectors (more modern, better maintained)
- Provides schema validation and governance out-of-the-box
- Supports multi-tenancy natively
- Offers Rust plugins for performance gains (see [Custom Plugins](CUSTOM_PLUGINS.md) and [Performance](PERFORMANCE.md) for details)

**Use Singer/Meltano if**: You're already invested in the Singer ecosystem.  
**Use Dativo if**: You want modern connectors with governance and multi-tenancy.

## Architecture Questions

### Why "One Asset Per Job"?

Dativo enforces a **one-asset-per-job** design pattern: each job configuration corresponds to exactly one asset (e.g., `stripe_customers`, `hubspot_contacts`). This delivers:

**🎯 Simpler Governance**
- Per-asset ownership: Each asset has clear owners, classification, and FinOps tags
- Policy-as-code: Governance rules apply naturally at the asset level
- Accountability: Cost and compliance metrics are tracked per-asset, not per-job

**📊 Easier Schema Versioning**
- Each asset has its own versioned schema definition (`assets/stripe/v1.0/customers.yaml`)
- Schema changes are isolated: updating `customers` doesn't affect `charges` or `invoices`
- Version rollback is straightforward: change the asset path, not complex job logic

**🔗 Per-Asset Lineage**
- Clean lineage tracking: one job → one table → one set of metadata
- Catalog integration (OpenMetadata, Glue, Unity) maps naturally: job run = asset refresh
- No conflicts between job-level and asset-level governance metadata

**🛡️ Operational Isolation**
- Clear failure semantics: One job fails = one asset fails (no partial failures)
- Independent scheduling: Each asset has its own cron schedule in `runner.yaml`
- Simple retries: Retry logic is straightforward - just retry the job
- Easy debugging: Logs and state are per-asset, making issues easy to trace

**📈 Scales Better**
- Simple, codegen-friendly configuration model
- Orchestration layer (Dagster) handles dependencies between assets
- Matches industry best practices (dbt's one-model-per-table, modern data contracts)

When you need to coordinate multiple assets, use the orchestration layer (Dagster) to group single-asset jobs rather than creating multi-asset jobs. This preserves the simplicity and governance benefits while allowing flexible execution patterns.

> 📖 **Learn More**: See [Design: One Asset Per Job](design/one-asset-per-job.md) for the complete rationale and implementation details.

### How does multi-tenancy work?

Dativo is built with **multi-tenancy as a first-class feature**:

**Tenant Isolation**
- **State Isolation**: Each tenant has separate state files (`state/{tenant_id}/`)
- **Secret Isolation**: Secrets are tenant-scoped (`secrets/{tenant_id}/`)
- **Data Isolation**: Tenant ID included in S3 paths and Iceberg table names
- **Logging Isolation**: Tenant ID tagged in all log entries

**Tenant Configuration**
```yaml
tenant_id: acme  # Required in all job configs
environment: prod
```

**Orchestration**
- **Serial Execution**: One job per tenant at a time (prevents Nessie commit conflicts)
- **Tenant-Level Scheduling**: Schedules are tenant-aware
- **Resource Quotas**: (Future) Tenant-level resource limits

See [Runner and Orchestration](RUNNER_AND_ORCHESTRATION.md) for orchestration details.

## Technical Questions

### What Python version is required?

**Python 3.10+ is REQUIRED**. Python 3.9 and below are not supported.

Check your version:
```bash
python3 --version  # Should show 3.10.0 or higher
```

See [Python Setup Guide](python-setup.md) for installation instructions.

### How do I handle secrets?

Dativo supports multiple secret management backends:

- **Environment Variables** (`env`) - For local development
- **Filesystem** (`filesystem`) - Filesystem-based secrets (tenant-organized)
- **HashiCorp Vault** (`vault`) - Enterprise secret management
- **AWS Secrets Manager** (`aws`) - AWS-native secret management
- **GCP Secret Manager** (`gcp`) - Google Cloud secret management

See [Secret Management](SECRET_MANAGEMENT.md) for complete configuration examples.

### What file formats are supported?

**Sources**: CSV, JSON, Parquet, Markdown-KV, database tables (PostgreSQL, MySQL)

**Targets**: Parquet (for Iceberg tables), written to S3/MinIO

**Note**: Dativo focuses on ingestion to Iceberg Parquet format. For transformations, use your data lake's transformation layer (dbt, Spark, etc.) after ingestion.

### How does schema validation work?

Dativo uses [ODCS v3.0.2](SCHEMA_VALIDATION.md) schema definitions for validation:

- **Strict mode**: Rejects records that don't match the schema
- **Warn mode**: Logs validation warnings but continues processing
- **Schema versioning**: Each asset has a versioned schema (`assets/stripe/v1.0/customers.yaml`)
- **Data contracts**: Schema definitions become versioned artifacts that map directly to data contracts

See [Schema Validation](SCHEMA_VALIDATION.md) for complete details.

### Can I use Dativo without Iceberg catalog?

**Yes!** Iceberg catalog is optional. Without catalog, Parquet files are written directly to S3/MinIO. The catalog provides table metadata and lineage, but is not required for file writing.

See [Catalog Limitations](CATALOG_LIMITATIONS.md) for details.

## Performance Questions

### How fast is Dativo?

Performance varies by workload:

**Rust Plugins** (when using custom Rust plugins):
- Parquet Writing: ~3x faster than PyArrow
- Throughput: 25,000-55,000 records/second
- Memory: Constant memory usage with streaming

**Python Plugins**:
- Suitable for moderate workloads (1,000-10,000 records/second)
- Easier to develop and iterate

**Built-in Connectors**:
- Optimized for common use cases
- Performance varies by connector type and data volume

See [Performance & Scaling](PERFORMANCE.md) for detailed benchmarks and scaling strategies.

### How do I improve performance?

1. **Use Rust plugins**: For high-throughput workloads, use Rust plugins for significant performance improvements
2. **Parallel job execution**: Run multiple independent jobs concurrently via Dagster
3. **Spark engine**: For very large datasets, use Spark engine for distributed processing
4. **Optimize batch sizes**: Tune `batch_size` and `row_group_size` for your workload
5. **Incremental sync**: Use incremental sync to minimize data processing

See [Performance & Scaling](PERFORMANCE.md) for complete scaling strategies.

### What are the scaling limitations?

**Current Capabilities**:
- ✅ Multiple parallel jobs via Dagster orchestration
- ✅ Per-tenant isolation with independent state and secrets
- ✅ Spark engine support for large-scale processing
- ✅ Batch processing with configurable batch sizes
- ✅ Incremental sync to reduce processing time

**Current Limitations**:
- ⚠️ Single-threaded per job (no intra-job parallelism)
- ⚠️ No horizontal scaling (jobs run on single node)
- ⚠️ Serial tenant execution (prevents catalog conflicts)

**Future Scaling** (planned for v2.0.0):
- 🔜 Parallel job execution within tenants
- 🔜 Horizontal scaling across multiple nodes
- 🔜 Connection pooling for optimized database connections
- 🔜 Caching for frequently accessed data

See [Performance & Scaling](PERFORMANCE.md) for complete scaling details.

## Access Control Questions

### Does Dativo support RBAC?

**Current Limitations**: Dativo does not currently provide multi-user RBAC (Role-Based Access Control). Each deployment is effectively **single-tenant in practice**, with access to jobs and configurations scoped by:

- **File System Structure**: Access control is managed through folder/branch structure in your repository
- **Git-Based Access**: Use Git repository permissions and branch protection rules to control who can modify job configs
- **Infrastructure-Level Controls**: Rely on your deployment infrastructure (Kubernetes RBAC, IAM policies, etc.) for access control

**Workarounds for Multi-User Scenarios**:
- Use separate Git repositories or branches per tenant/team
- Implement access control at the infrastructure layer (Kubernetes namespaces, IAM roles)
- Use CI/CD pipelines with branch protection and approval workflows
- Deploy separate Dativo instances per tenant/team if strict isolation is required

**Roadmap**: RBAC and user isolation features are planned for a future release.

See [RBAC & Access Control](RBAC.md) for complete details and workarounds.

## Troubleshooting

### Exit codes

- `0`: Success - All jobs completed successfully
- `1`: Partial success - Some jobs succeeded, some failed
- `2`: Failure - Configuration errors, missing files, or startup failures. Note: Jobs may complete with validation warnings but still return exit code 2.

### Services not starting?

```bash
docker-compose -f docker-compose.dev.yml ps
docker-compose -f docker-compose.dev.yml logs
```

### Command not found?

```bash
# Reinstall package
pip install -e .
```

### Environment variables not working?

```bash
source .env
```

## More Questions?

- See [Documentation Index](index.md) for complete documentation
- Check [Configuration Reference](CONFIG_REFERENCE.md) for configuration questions
- Review [CLI Reference](CLI_REFERENCE.md) for command-line usage
- Open a [GitHub Issue](https://github.com/YOUR_ORG/dativo-ingest/issues) for bugs or feature requests

