# Comparison: Dativo vs. Alternatives

This document provides a detailed comparison of Dativo with other data ingestion tools to help you choose the right solution for your needs.

## Feature Comparison

| Feature | Dativo | Airbyte | Meltano |
|--------|--------|---------|---------|
| **Architecture** | Headless, config-driven | UI-first, API-driven | CLI-first, plugin-based |
| **Deployment** | Docker, Kubernetes | Docker, Cloud | Python package |
| **Configuration** | YAML files (GitOps) | Web UI + API | YAML files |
| **Multi-Tenancy** | ✅ Built-in isolation (required `tenant_id`) | ❌ Single tenant | ❌ Single tenant |
| **Iceberg Support** | ✅ Native Iceberg + Nessie commit | ❌ Limited | ❌ Limited |
| **Custom Plugins** | ✅ Python + Rust | ❌ Connectors only | ✅ Python (Singer) |
| **Orchestration** | ✅ Dagster built-in | ❌ External only | ❌ External only |
| **Catalog Integration** | ✅ OpenMetadata, Glue, Unity, Nessie | ❌ Limited | ❌ Limited |
| **Schema Validation** | ✅ Asset definitions with strict/warn modes | ⚠️ Basic | ⚠️ Basic |
| **Secret Management** | ✅ [Multiple backends](SECRET_MANAGEMENT.md) | ⚠️ Basic | ⚠️ Basic |
| **Uses Airbyte Connectors** | ✅ Yes (via AirbyteExtractor) | ✅ Native | ❌ No (Singer ecosystem) |
| **Best For** | Multi-tenant SaaS, data platforms | Single-tenant, UI-driven | Singer ecosystem |

## When to Choose Dativo

Choose Dativo if you need:

1. **Multi-tenant architecture**: Built-in tenant isolation for state, secrets, and data paths (`tenant_id` required in all job configs). Each tenant has separate state files, secrets, and data paths.

2. **Headless operation**: GitOps-friendly, CI/CD integrated ingestion. All configurations are YAML files that live in version control, enabling PR-based reviews, policy-as-code enforcement, and infrastructure-as-code integration.

3. **Iceberg-native integration**: Direct integration with Apache Iceberg tables via Nessie commits. Writes Parquet files and commits metadata to Iceberg catalog (not just raw Parquet storage).

4. **Custom plugins**: Extend with Python or Rust plugins. Rust plugins provide significant performance improvements for data-intensive operations. See [Custom Plugins](CUSTOM_PLUGINS.md) for details.

5. **Built-in orchestration**: Dagster orchestration included. Configure schedules in `runner.yaml` without requiring external orchestration tools.

6. **Schema enforcement**: Asset definitions with strict/warn validation modes at ingestion time. Schema definitions become versioned artifacts that map directly to data contracts.

7. **Catalog integration**: Supports OpenMetadata, AWS Glue, Databricks Unity Catalog, and Nessie for lineage tracking and metadata management. See [Catalog Integration](CATALOG_INTEGRATION.md) for details.

## When to Choose Airbyte

Choose Airbyte if you need:

1. **300+ pre-built connectors**: Large connector ecosystem with minimal setup. Note: Dativo uses Airbyte connectors under the hood, so you can access Airbyte's connector ecosystem without the UI/overhead.

2. **UI-driven configuration**: Prefer web-based configuration and management over YAML files and GitOps workflows.

3. **Single-tenant use case**: Don't need multi-tenancy. Airbyte requires separate deployments per tenant if multi-tenancy is needed.

4. **Cloud-hosted option**: Want hosted/managed service option (Airbyte Cloud).

## When to Choose Meltano

Choose Meltano if you:

1. **Already use Singer**: Invested in the Singer taps/targets ecosystem. Meltano is built on Singer protocol.

2. **Prefer Python-only plugins**: Don't need Rust performance gains. Meltano supports Python plugins via Singer.

3. **CLI-first workflow**: Prefer command-line tools over config files for operational tasks.

4. **Don't need multi-tenancy**: Single-tenant deployments are sufficient. Meltano requires separate deployments per tenant if multi-tenancy is needed.

5. **Want lightweight solution**: Minimal infrastructure footprint without built-in orchestration.

## Detailed Feature Analysis

### Configuration Approach

**Dativo**: YAML-based, GitOps-friendly. All configurations live in version control, enabling:
- PR-based reviews for ingestion pipelines
- Policy-as-code enforcement
- Infrastructure-as-code integration
- Repeatable deployments

**Airbyte**: Web UI + API. Configuration managed through:
- Browser-based configuration
- API access for automation
- Limited GitOps support (requires exporting configs)
- UI dependency for initial setup

**Meltano**: YAML files + CLI. Singer-based:
- YAML configuration files
- CLI-driven operations
- Singer tap/target ecosystem
- Python plugin support

### Multi-Tenancy

**Dativo**: ✅ Built-in multi-tenant architecture
- `tenant_id` required in all job configurations
- Tenant isolation for state files (`state/{tenant_id}/`)
- Tenant-scoped secrets (`secrets/{tenant_id}/`)
- Tenant-specific data paths in S3 and Iceberg tables
- Per-tenant scheduling and resource management
- Serial execution per tenant (prevents Nessie commit conflicts)
- Tenant-scoped logging and metrics

**Airbyte**: ❌ Single-tenant only
- No built-in tenant isolation
- Requires separate deployments per tenant
- Manual isolation setup required

**Meltano**: ❌ Single-tenant only
- No built-in tenant isolation
- Requires separate deployments per tenant

### Iceberg Integration

**Dativo**: ✅ Native Iceberg + Nessie support
- Writes Parquet files to S3/MinIO
- Commits metadata to Iceberg catalog via Nessie
- Supports schema evolution
- Branch-based table management
- See [Iceberg Integration](INGESTION_EXECUTION.md#icebergnessie-integration) for details

**Airbyte**: ❌ Limited Iceberg support
- Primarily writes to raw object storage (S3, GCS)
- No native Iceberg catalog integration
- Requires post-processing to create Iceberg tables

**Meltano**: ❌ Limited Iceberg support
- Targets focus on Singer protocol destinations
- No native Iceberg integration

### Performance & Scalability

**Dativo**:
- Rust plugins for significant performance improvements (documented in [Performance](PERFORMANCE.md))
- Streaming processing for large datasets with constant memory usage
- Configurable batch sizes and file sizing
- Spark engine support for large-scale processing

**Airbyte**:
- Optimized for common use cases
- Performance varies by connector
- Limited customization options

**Meltano**:
- Python-based processing (Singer protocol)
- Performance limited by Python/Singer architecture
- Suitable for moderate workloads

### Schema Validation

**Dativo**: ✅ Asset definitions with validation modes
- Strict mode: Rejects records that don't match the schema
- Warn mode: Logs validation warnings but continues processing
- Schema versioning: Each asset has a versioned schema (`assets/{source}/v{version}/`)
- Data contracts: Schema definitions become versioned artifacts
- See [Schema Validation](SCHEMA_VALIDATION.md) for details

**Airbyte**: ⚠️ Basic validation
- Limited schema enforcement
- No data contract support
- Schema inferred from source data

**Meltano**: ⚠️ Basic validation
- Singer-based schema handling
- Limited validation capabilities
- Schema defined by taps

### Catalog Integration

**Dativo**: ✅ Multiple catalog integrations
- **OpenMetadata**: Full lineage and metadata support
- **AWS Glue**: Table creation and metadata updates
- **Databricks Unity Catalog**: Table creation via SQL API
- **Nessie**: Git-like versioning for Iceberg tables
- Automatic lineage tracking and metadata push
- See [Catalog Integration](CATALOG_INTEGRATION.md) for details

**Airbyte**: ❌ Limited catalog integration
- Primarily focuses on data movement
- Limited lineage tracking capabilities
- Metadata management is external

**Meltano**: ❌ Limited catalog integration
- Singer protocol doesn't include catalog integration
- Requires external tools for lineage tracking

## Migration Paths

### From Airbyte to Dativo

If you're currently using Airbyte and want to migrate to Dativo:

1. **Keep your connectors**: Dativo uses Airbyte connectors via `AirbyteExtractor`, so most connectors work as-is. Just reference the same Docker images.

2. **Convert configurations**: Translate UI-based configs to YAML job configuration files. See [Configuration Reference](CONFIG_REFERENCE.md) for format.

3. **Add asset definitions**: Define asset schemas using the asset definition format. See [Asset Definitions](CONFIG_REFERENCE.md#asset-definitions) for details.

4. **Set up multi-tenancy**: Organize jobs by tenant if applicable. Add `tenant_id` to all job configs.

5. **Migrate orchestration**: Move from external orchestrators (Airflow, etc.) to Dagster schedules in `runner.yaml`. See [Runner and Orchestration](RUNNER_AND_ORCHESTRATION.md) for details.

### From Meltano to Dativo

If you're using Meltano/Singer:

1. **Evaluate connectors**: Check if Airbyte equivalents exist (Dativo uses Airbyte connectors). Many Singer taps have Airbyte equivalents.

2. **Convert configurations**: Translate Singer configs to Dativo job config YAML format.

3. **Migrate plugins**: Rewrite Singer taps/targets as Dativo plugins if needed. See [Custom Plugins](CUSTOM_PLUGINS.md) for plugin development.

4. **Add asset schemas**: Define asset schemas for validation. This adds schema enforcement that Singer doesn't provide.

5. **Set up orchestration**: Configure Dagster schedules in `runner.yaml` instead of external orchestrators.

## Summary

| Your Need | Recommended Tool |
|-----------|-----------------|
| Multi-tenant SaaS platform | **Dativo** |
| GitOps/CI/CD integration | **Dativo** |
| Iceberg data lake with Nessie | **Dativo** |
| 300+ pre-built connectors with headless operation | **Dativo** (uses Airbyte connectors) |
| UI-driven configuration | **Airbyte** |
| Singer ecosystem | **Meltano** |
| Custom Python plugins | **Dativo** or **Meltano** |
| Custom Rust plugins for performance | **Dativo** |
| Built-in orchestration (Dagster) | **Dativo** |
| Catalog integration (OpenMetadata, Glue, Unity) | **Dativo** |

## FAQ: Comparison Questions

### How is Dativo different from Airbyte?

**Airbyte** focuses on UI-driven configuration and hosted management. **Dativo** is headless and code-driven:

- **Headless operation**: No UI required – perfect for GitOps, CI/CD, and infrastructure-as-code
- **Schema enforcement**: Built-in asset definitions with strict/warn validation modes
- **Governance-first**: Per-asset ownership, classification, and FinOps tags out-of-the-box
- **Multi-tenant**: Built-in tenant isolation for state, secrets, and data
- **Uses Airbyte connectors**: You get Airbyte's connector ecosystem without the UI/overhead
- **Custom plugins**: Extend with Python or Rust plugins

**Use Airbyte if**: You need 300+ pre-built connectors and prefer UI-driven configuration.  
**Use Dativo if**: You need headless operation, schema enforcement, multi-tenancy, or custom plugins.

### Can I use Airbyte connectors with Dativo?

**Yes!** Dativo uses Airbyte connectors under the hood via `AirbyteExtractor`. You get:

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
- Offers Rust plugins for performance gains

**Use Singer/Meltano if**: You're already invested in the Singer ecosystem.  
**Use Dativo if**: You want modern connectors with governance and multi-tenancy.

### How is Dativo different from writing my own scripts?

**Custom scripts** require you to build everything yourself. **Dativo** provides:

- **Production-ready infrastructure**: Retry policies, error handling, state management, observability
- **Schema validation**: Asset definitions with strict validation
- **Connector ecosystem**: Reuse Airbyte connectors without building API integrations
- **Multi-tenant isolation**: Built-in tenant separation for state, secrets, and data
- **Iceberg integration**: Direct integration with modern data lake formats
- **Plugin system**: Custom readers/writers without rebuilding the entire pipeline

**Write custom scripts if**: You have very specific requirements that don't fit standard patterns.  
**Use Dativo if**: You want production-ready infrastructure with governance and schema enforcement.

## Related Documentation

- [FAQ](FAQ.md) - Frequently asked questions about Dativo
- [Configuration Reference](CONFIG_REFERENCE.md) - Job and asset configuration
- [Connector Reference](connectors.md) - Available connectors and capabilities
- [Custom Plugins](CUSTOM_PLUGINS.md) - Plugin development guide
- [Performance & Scaling](PERFORMANCE.md) - Performance benchmarks and scaling strategies
- [Catalog Integration](CATALOG_INTEGRATION.md) - Catalog integration details
- [Architecture](design/one-asset-per-job.md) - Dativo architecture details

