# Documentation Index

Welcome to the Dativo Ingestion Platform documentation. This index helps you navigate all available documentation.

## Who Should Read This?

- **New users**: Start with [Quick Start](QUICKSTART.md) and [Setup Guide](SETUP_AND_ONBOARDING.md)
- **Developers**: See [Connector Development](CONNECTOR_DEVELOPMENT.md) and [Custom Plugins](CUSTOM_PLUGINS.md)
- **DevOps/Infra**: See [Secret Management](SECRET_MANAGEMENT.md) and [Security Considerations](../README.md#security-considerations)
- **Data Engineers**: See [Config Reference](CONFIG_REFERENCE.md) and [Execution Flow](INGESTION_EXECUTION.md)

## Prerequisites

- Python 3.10+
- Docker and Docker Compose (for local infrastructure)
- Basic understanding of YAML configuration
- Familiarity with data ingestion concepts (ETL, incremental sync, schema validation)

## Getting Started

### Setup & Testing
- **[QUICKSTART.md](../QUICKSTART.md)** - 5-minute quick start guide
- **[SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md)** - Comprehensive setup guide
- **[SETUP_AND_TESTING.md](SETUP_AND_TESTING.md)** - Detailed setup and testing instructions

### Configuration
- **[CONFIG_REFERENCE.md](CONFIG_REFERENCE.md)** - Complete configuration reference
- **[MINIMAL_ASSET_EXAMPLE.md](MINIMAL_ASSET_EXAMPLE.md)** - Minimal asset definition example
- **[SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md)** - All secret manager backends (env, filesystem, Vault, AWS, GCP)

## Core Concepts

### Execution Flow
- **[INGESTION_EXECUTION.md](INGESTION_EXECUTION.md)** - Detailed execution flow (Extract → Validate → Write → Commit → State)

### Connector Registry & Assets
- **[Connector Registry](../registry/)** - Connector capabilities and validation
- **[Asset Schemas](../assets/)** - ODCS v3.0.2 compliant schema definitions
- **[SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md)** - Schema validation modes and behavior

### Data Storage
- **[MARKDOWN_KV_STORAGE.md](MARKDOWN_KV_STORAGE.md)** - Markdown-KV storage patterns (STRING, raw file, structured)
- **[CATALOG_LIMITATIONS.md](CATALOG_LIMITATIONS.md)** - Iceberg catalog limitations and workarounds
- **[CATALOG_INTEGRATION.md](CATALOG_INTEGRATION.md)** - Data catalog integration (OpenMetadata, AWS Glue, Databricks, Nessie)

## Development

### Custom Plugins
- **[CUSTOM_PLUGINS.md](CUSTOM_PLUGINS.md)** - Comprehensive guide for Python and Rust plugins
- **[PLUGIN_DECISION_TREE.md](PLUGIN_DECISION_TREE.md)** - When to use connectors vs. plugins
- **[PLUGIN_SANDBOXING.md](PLUGIN_SANDBOXING.md)** - Security guide for plugin sandboxing
- **[Plugin Examples](../examples/plugins/)** - Example plugins (Python and Rust)

### Connector Development
- **[CONNECTOR_DEVELOPMENT.md](CONNECTOR_DEVELOPMENT.md)** - Guide for developing new connectors
- **[Connector Examples](../docs/examples/jobs/)** - Example job configurations

### Orchestration
- **[RUNNER_AND_ORCHESTRATION.md](RUNNER_AND_ORCHESTRATION.md)** - Runner and orchestration documentation
- **[Dagster Integration](../README.md#start-orchestrated-mode)** - Dagster orchestrator setup

## Advanced Topics

### Tag Management
- **[TAG_PRECEDENCE.md](TAG_PRECEDENCE.md)** - Tag precedence and inheritance
- **[TAG_PROPAGATION.md](TAG_PROPAGATION.md)** - How tags propagate through the pipeline

### Infrastructure
- **[COLIMA_CONFIGURATION.md](COLIMA_CONFIGURATION.md)** - Colima configuration for local development
- **[MOUNT_POINTS_ANALYSIS.md](MOUNT_POINTS_ANALYSIS.md)** - Docker mount points analysis

### Security
- **[SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md)** - Secret management best practices
- **[PLUGIN_SANDBOXING.md](PLUGIN_SANDBOXING.md)** - Plugin security and sandboxing
- **[Security Considerations](../README.md#security-considerations)** - Security overview in README

## Examples

### Job Examples
- **[examples/jobs/](../docs/examples/jobs/)** - Complete job configuration examples
  - Stripe to Iceberg
  - HubSpot to S3
  - Postgres incremental sync
  - Google Drive CSV ingestion
  - MySQL to Iceberg

### Plugin Examples
- **[examples/plugins/](../examples/plugins/)** - Custom plugin examples
  - Python: JSON API reader, JSON file writer
  - Rust: CSV reader, Parquet writer

## Troubleshooting

### Common Issues
- **Services not starting**: Check [SETUP_AND_TESTING.md](SETUP_AND_TESTING.md)
- **Connection errors**: See [SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md)
- **Schema validation failures**: See [SCHEMA_VALIDATION.md](SCHEMA_VALIDATION.md)
- **Catalog issues**: See [CATALOG_LIMITATIONS.md](CATALOG_LIMITATIONS.md)

### Getting Help
- Check existing [GitHub Issues](https://github.com/dativo-io/dativo-ingest/issues)
- Review [CONTRIBUTING.md](../.github/CONTRIBUTING.md) for development guidelines
- See [ROADMAP.md](../ROADMAP.md) for upcoming features

## Reference

### Project Structure
```
connectors/          # Connector recipes (tenant-agnostic)
assets/              # Asset schemas (ODCS v3.0.2)
  {source}/v{version}/
jobs/                # Job configs (tenant-specific)
  {tenant_id}/
configs/             # Runner and policy configs
registry/            # Connector capabilities registry
secrets/             # (Optional) filesystem secrets (tenant-organized)
state/               # Incremental sync state
src/dativo_ingest/   # Source code
```

### CLI Commands
- `dativo run` - Run a single job or directory of jobs
- `dativo check` - Validate connections without running job
- `dativo discover` - List available streams from connector
- `dativo start orchestrated` - Start Dagster orchestrator
- `dativo --version` - Show version number

See [README.md](../README.md#cli-usage) for complete CLI documentation.

## Contributing

- **[CONTRIBUTING.md](../.github/CONTRIBUTING.md)** - Contribution guidelines
- **[ROADMAP.md](../ROADMAP.md)** - Upcoming features and connectors
- **[Issue Templates](../.github/ISSUE_TEMPLATE/)** - Bug reports and feature requests

---

**Last Updated**: 2025-01-XX
