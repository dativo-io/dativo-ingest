# Connectors Reference

Complete reference for all source and target connectors available in Dativo Ingestion Platform.

## Connector Status

| Connector | Role | Status | Notes |
|-----------|------|--------|-------|
| **Stripe** | Source | Stable | Payments API connector. Supports customers, charges, invoices. Timestamp-based incremental sync. Airbyte-based implementation. |
| **HubSpot** | Source | Stable | CRM API connector. Supports contacts, deals, companies. Cursor-based incremental sync. Airbyte-based implementation. |
| **CSV** | Source, Target | Stable | Bidirectional file connector. Supports incremental sync by file modification time. Native Python implementation. |
| **Google Sheets** | Source, Target | Stable | Bidirectional spreadsheet connector. Supports range-based reading and change detection. Native implementation with Airbyte/Meltano options. |
| **Google Drive CSV** | Source | Stable | File connector for CSV files in Google Drive. Supports file discovery and incremental sync by modification time. Native implementation with Airbyte/Meltano options. |
| **Markdown-KV** | Source, Target | Stable | Bidirectional connector for Markdown-KV format (LLM-optimized). Supports string, structured, and raw file storage modes. |
| **Iceberg** | Target | Stable | Apache Iceberg table format. Writes Parquet files to S3/MinIO. Optional Nessie catalog integration. Supports schema evolution. |
| **S3** | Source, Target | Stable | Amazon S3 object storage. Bidirectional connector for reading and writing objects. Native implementation. |
| **MinIO** | Source, Target | Stable | S3-compatible object storage. Bidirectional connector. Native implementation. Ideal for local development. |
| **PostgreSQL** | Source, Target | Beta | Database connector. Read-only ingest with full table and incremental sync. Cursor-based incremental with state management. Self-hosted only (not available in cloud mode). No CDC support yet. |
| **MySQL** | Source, Target | Beta | Database connector. Read-only ingest with full table and incremental sync. Cursor-based incremental with state management. WAL checkpointing support. Self-hosted only (not available in cloud mode). No CDC support yet. |
| **Azure Blob Storage** | Source, Target | Planned | Azure Blob Storage connector. Registered in connector registry but not yet implemented. |

## Planned Connectors (v2.1+)

The following connectors are planned for future releases:

- **Salesforce** - CRM API connector
- **Zendesk** - Support ticket system connector
- **MongoDB** - NoSQL database connector
- **Snowflake** - Data warehouse connector
- **BigQuery** - Google Cloud data warehouse connector
- **Kafka/Event Streams** - Real-time streaming connector

## Connector Capabilities

### Incremental Sync Support

All source connectors support incremental sync with different strategies:

- **Timestamp-based**: Stripe (uses `created` field)
- **Cursor-based**: HubSpot (uses `updatedAt` field), PostgreSQL, MySQL
- **File-based**: CSV, Google Drive CSV (uses file modification time)
- **Spreadsheet-based**: Google Sheets (uses spreadsheet modification time)

### Cloud Mode Support

Most connectors support cloud mode (SaaS deployment), except:

- **PostgreSQL** - Self-hosted only (requires direct database access)
- **MySQL** - Self-hosted only (requires direct database access)

### Engine Support

Connectors support different execution engines:

- **Native**: Direct Python implementation (CSV, Google Sheets, Google Drive CSV, Iceberg, S3, MinIO, Markdown-KV)
- **Airbyte**: Docker-based connector execution (Stripe, HubSpot, Google Sheets, Google Drive CSV)
- **Meltano**: Meltano tap/target execution (PostgreSQL, MySQL - placeholder, not yet implemented)

## Related Documentation

- [Config Reference](CONFIG_REFERENCE.md) - Complete configuration documentation
- [Custom Plugins](CUSTOM_PLUGINS.md) - Build custom connectors with Python/Rust
- [Plugin Decision Tree](PLUGIN_DECISION_TREE.md) - When to use connectors vs. plugins
- [Secret Management](SECRET_MANAGEMENT.md) - How to configure connector credentials
