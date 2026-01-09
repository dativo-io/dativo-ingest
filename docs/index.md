# Dativo Ingestion Platform Documentation

Welcome to the Dativo Ingestion Platform documentation. This index provides organized access to all documentation resources.

## Table of Contents

### Getting Started
- **[Quick Start Guide](quickstart.md)** - Get up and running in 5 minutes
- **[Python Setup Guide](python-setup.md)** - Python 3.10+ installation and setup
- **[Setup and Onboarding](SETUP_AND_ONBOARDING.md)** - Comprehensive setup guide
- **[Setup and Testing](SETUP_AND_TESTING.md)** - Testing environment setup

### Core Documentation
- **[Configuration Reference](CONFIG_REFERENCE.md)** - Complete configuration guide
- **[Connector Reference](connectors.md)** - Available connectors and capabilities
- **[Secret Management](SECRET_MANAGEMENT.md)** - Secret manager backends and configuration
- **[Schema Validation](SCHEMA_VALIDATION.md)** - Asset schema validation guide
- **[CLI Reference](CLI_REFERENCE.md)** - Complete CLI command reference

### Architecture & Design
- **[Architecture Overview](architecture.md)** - Component descriptions and system architecture
- **[Data Flow Architecture](../DATA_FLOW_ARCHITECTURE.md)** - How data moves through the system
- **[Design: One Asset Per Job](design/one-asset-per-job.md)** - Design rationale and specs-as-code relationship
- **[Ingestion Execution](INGESTION_EXECUTION.md)** - ETL pipeline execution flow
- **[Runner and Orchestration](RUNNER_AND_ORCHESTRATION.md)** - Orchestration with Dagster

### Connectors & Plugins
- **[Connector vs Plugin Decision Tree](CONNECTOR_VS_PLUGIN_DECISION_TREE.md)** - When to use connectors vs plugins
- **[Custom Plugins](CUSTOM_PLUGINS.md)** - Creating Python and Rust plugins
- **[Plugin Decision Tree](PLUGIN_DECISION_TREE.md)** - Plugin selection guide
- **[Plugin Sandboxing](PLUGIN_SANDBOXING.md)** - Security and sandboxing

### Data Storage
- **[Markdown-KV Storage](MARKDOWN_KV_STORAGE.md)** - Markdown-KV format and storage patterns
- **[Minimal Asset Example](MINIMAL_ASSET_EXAMPLE.md)** - Minimal asset definition template

### Catalog Integration
- **[Catalog Integration](CATALOG_INTEGRATION.md)** - Data catalog integration guide
- **[Catalog Limitations](CATALOG_LIMITATIONS.md)** - Known limitations and workarounds

### Advanced Features
- **[Comparison: Dativo vs. Alternatives](comparisons.md)** - Detailed feature comparisons and migration guidance
- **[FAQ](FAQ.md)** - Frequently asked questions
- **[Performance & Scaling](PERFORMANCE.md)** - Performance benchmarks and scaling strategies
- **[RBAC & Access Control](RBAC.md)** - Access control workarounds and limitations
- **[WAL Checkpointing](WAL_CHECKPOINTING.md)** - Write-Ahead Log checkpointing
- **[Tag Propagation](TAG_PROPAGATION.md)** - Governance tag propagation
- **[Tag Precedence](TAG_PRECEDENCE.md)** - Tag precedence rules
- **[Testing FinOps Metadata](TESTING_FINOPS_METADATA.md)** - FinOps metadata testing

### Developer Resources
- **[Developer Guide](DEVELOPER.md)** - Development setup and guidelines
- **[Git Commit Guide](git-commit-guide.md)** - Commit message guidelines
- **[Testing Overview](testing-overview.md)** - Testing documentation overview

### Infrastructure & Operations
- **[Colima Configuration](COLIMA_CONFIGURATION.md)** - Colima setup for macOS
- **[Mount Points Analysis](MOUNT_POINTS_ANALYSIS.md)** - Docker mount point configuration
- **[Seccomp Profile Update](SECCOMP_PROFILE_UPDATE.md)** - Security profile updates
- **[Cleanup](CLEANUP.md)** - Cleanup procedures

### Roadmap
- **[Roadmap](roadmap.md)** - Development roadmap and version history

### Experimental
- **[Agentic AI Orchestration](experimental/AGENTIC_AI_ORCHESTRATION_Dativo.md)** - Experimental AI orchestration features
- **[Governance and FinOps](experimental/GOVERNANCE_AND_FINOPS_Dativo.md)** - Experimental governance features

## Quick Links

### For New Users
1. Start with [Quick Start Guide](quickstart.md)
2. Review [Python Setup Guide](python-setup.md) if needed
3. Read [Configuration Reference](CONFIG_REFERENCE.md) for job configuration
4. Explore [Connector Reference](connectors.md) for available connectors

### For Developers
1. Review [Developer Guide](DEVELOPER.md)
2. Understand [Data Flow Architecture](../DATA_FLOW_ARCHITECTURE.md)
3. Read [Custom Plugins](CUSTOM_PLUGINS.md) for extending functionality
4. Check [Plugin Sandboxing](PLUGIN_SANDBOXING.md) for security

### For Operators
1. Review [Setup and Onboarding](SETUP_AND_ONBOARDING.md)
2. Configure [Secret Management](SECRET_MANAGEMENT.md)
3. Set up [Catalog Integration](CATALOG_INTEGRATION.md)
4. Monitor with [WAL Checkpointing](WAL_CHECKPOINTING.md)

## Documentation Structure

```
docs/
├── index.md                    # This file - documentation index
├── connectors.md               # Connector reference
├── quickstart.md               # Quick start guide
├── python-setup.md             # Python setup guide
├── git-commit-guide.md         # Git commit guidelines
├── roadmap.md                  # Development roadmap
├── testing-overview.md         # Testing overview
├── experimental/               # Experimental features
│   ├── AGENTIC_AI_ORCHESTRATION_Dativo.md
│   └── GOVERNANCE_AND_FINOPS_Dativo.md
└── [other documentation files]
```

## Contributing

To contribute documentation:
1. Follow the [Git Commit Guide](git-commit-guide.md)
2. Update this index when adding new documentation
3. Ensure all links are valid and working
4. Use clear, concise language

## Feedback

Found an issue with the documentation? Please open an issue or submit a PR with improvements.
