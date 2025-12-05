# Documentation Index

Complete guide to all Dativo Ingestion Platform documentation, organized by topic.

## Getting Started

- **[Quick Start Guide](quickstart.md)** - Get up and running in 5 minutes
- **[Python Setup](python-setup.md)** - Python 3.10+ installation guide
- **[Environment Setup](environment-setup.md)** - Environment variables reference
- **[Setup & Onboarding](SETUP_AND_ONBOARDING.md)** - Comprehensive setup guide
- **[Setup & Testing](SETUP_AND_TESTING.md)** - Setup guide with testing instructions

## Configuration & Architecture

- **[Config Reference](CONFIG_REFERENCE.md)** - Complete configuration documentation
- **[Data Flow Architecture](data-flow-architecture.md)** - How data moves from readers to writers
- **[Design Decisions](DESIGN_ONE_ASSET_PER_JOB.md)** - Why one asset per job
- **[Minimal Asset Example](MINIMAL_ASSET_EXAMPLE.md)** - Simple asset definition example
- **[Ingestion Execution](INGESTION_EXECUTION.md)** - How jobs execute end-to-end

## Connectors & Sources

- **[Connectors Reference](connectors.md)** - Complete list of all source/target connectors with status and capabilities
- **[Connector vs Plugin Decision Tree](CONNECTOR_VS_PLUGIN_DECISION_TREE.md)** - When to use connectors vs. plugins
- **[Plugin Decision Tree](PLUGIN_DECISION_TREE.md)** - Plugin selection guide
- **[Custom Plugins](CUSTOM_PLUGINS.md)** - Python and Rust plugin development guide
- **[Plugin Sandboxing](PLUGIN_SANDBOXING.md)** - Security and isolation for plugins

## Data Management

- **[Schema Validation](SCHEMA_VALIDATION.md)** - Schema validation modes and rules
- **[WAL Checkpointing](WAL_CHECKPOINTING.md)** - Write-ahead log for fault tolerance
- **[Markdown-KV Storage](MARKDOWN_KV_STORAGE.md)** - LLM-optimized data ingestion

## Data Catalogs

- **[Catalog Integration](CATALOG_INTEGRATION.md)** - OpenMetadata, AWS Glue, Unity Catalog, Nessie
- **[Catalog Limitations](CATALOG_LIMITATIONS.md)** - Current limitations and workarounds

## Security & Secrets

- **[Secret Management](SECRET_MANAGEMENT.md)** - All secret backends (env, filesystem, Vault, AWS, GCP)
- **[Plugin Sandboxing](PLUGIN_SANDBOXING.md)** - Security and isolation for plugins
- **[Seccomp Profile Update](SECCOMP_PROFILE_UPDATE.md)** - Security profile configuration

## Governance & Tags

- **[Tag Propagation](TAG_PROPAGATION.md)** - Data classification and governance tags
- **[Tag Precedence](TAG_PRECEDENCE.md)** - How tags are prioritized and applied
- **[Testing FinOps Metadata](TESTING_FINOPS_METADATA.md)** - Financial operations metadata testing

## Orchestration & Operations

- **[Runner & Orchestration](RUNNER_AND_ORCHESTRATION.md)** - Dagster orchestration and oneshot modes
- **[Git Commit Guide](git-commit-guide.md)** - Contribution guidelines

## Testing

- **[Testing Guide Index](testing-guide-index.md)** - Complete testing documentation index
- **[Testing Playbook](testing-playbook.md)** - 20 detailed test cases
- **[Testing Quick Reference](testing-quick-reference.md)** - Quick command reference
- **[Testing Resources Summary](testing-resources-summary.md)** - Testing infrastructure overview
- **[Testing Overview](testing-overview.md)** - Visual guide to the testing suite and test cases

## Advanced Features

### Experimental

- **[Agentic AI Orchestration](experimental/AGENTIC_AI_ORCHESTRATION_Dativo.md)** - AI-powered orchestration and workflow automation
- **[Governance and FinOps](experimental/GOVERNANCE_AND_FINOPS_Dativo.md)** - Advanced governance, compliance, and financial operations features

## Developer Resources

- **[Developer Guide](DEVELOPER.md)** - Developer documentation and guidelines
- **[Colima Configuration](COLIMA_CONFIGURATION.md)** - Colima setup for local development
- **[Mount Points Analysis](MOUNT_POINTS_ANALYSIS.md)** - Docker mount point configuration
- **[Cleanup](CLEANUP.md)** - Cleanup procedures and utilities

## Project Information

- **[Roadmap](roadmap.md)** - Development roadmap and version milestones
- **[Changelog](../CHANGELOG.md)** - Version history and release notes

---

## Quick Links

- [Main README](../README.md) - Project overview and quick start
- [Examples](../examples/) - Configuration examples
- [Test Suite](../tests/README.md) - Detailed test suite documentation

