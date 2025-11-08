# Job & Asset Generator - Quick Start

## What is it?

An interactive CLI tool that creates job configurations and asset definitions for Dativo, with intelligent suggestions based on the connector registry.

## Installation

Already integrated! Just use the Dativo CLI:

```bash
# Check it's available
dativo generate --help

# Or use the convenience script
./generate_job.sh
```

## Quick Usage

```bash
# Launch the generator
dativo generate

# Follow the prompts:
# 1. Enter tenant ID (e.g., "acme")
# 2. Select source connector (e.g., "stripe")
# 3. Define asset schema interactively
# 4. Configure job settings
# 5. Files are automatically saved
```

## What It Generates

### Asset Definition
Location: `/workspace/assets/{connector}/v1.0/{name}.yaml`

Contains:
- Schema fields with types and constraints
- Governance (owner, tags, classification, retention)
- Target configuration (format, partitioning, mode)

### Job Configuration
Location: `/workspace/jobs/{tenant}/{name}_to_{target}.yaml`

Contains:
- Source connector configuration
- Target connector configuration
- Incremental sync settings
- Logging configuration

## Features

✅ **Smart Suggestions** - Based on connector capabilities
✅ **PII Detection** - Auto-detects sensitive fields
✅ **Registry Integration** - Knows connector capabilities
✅ **Incremental Sync** - Configures when supported
✅ **Complete Workflow** - Asset + Job in one session

## Example Session (5 minutes)

```bash
$ dativo generate

--- Tenant Configuration ---
Tenant ID: mycompany

--- Source Connector Selection ---
Select source connector:
  1. csv
  2. stripe  ← Select this
  3. postgres
  ...

--- Asset Definition Generation ---
Asset name: stripe_customers
Object name [customers]: ← Press Enter
Version [1.0]: ← Press Enter

Add 'id' field (string, required)? [Y/n]: y
Add 'email' field...
(Continue adding fields)

--- Job Configuration Generation ---
Environment:
  1. dev  ← Select this
  2. staging
  3. prod

Enable incremental sync? [Y/n]: y
Lookback days [1]: ← Press Enter

Target connector:
  1. iceberg  ← Select this
  2. s3

✓ Generated files:
  - /workspace/assets/stripe/v1.0/stripe_customers.yaml
  - /workspace/jobs/mycompany/stripe_customers_to_iceberg.yaml
```

## Next Steps

After generation:

```bash
# 1. Review the generated files
cat /workspace/assets/stripe/v1.0/stripe_customers.yaml
cat /workspace/jobs/mycompany/stripe_customers_to_iceberg.yaml

# 2. Test the job
dativo run --config /workspace/jobs/mycompany/stripe_customers_to_iceberg.yaml \
  --mode self_hosted

# 3. Add to orchestration (optional)
# Edit configs/runner.yaml to add a schedule
```

## Tips

1. **Use Defaults**: Press Enter to accept suggested values
2. **Environment Variables**: Use `${VAR_NAME}` for credentials
3. **Multiple Objects**: Separate with commas for API connectors
4. **Incremental Sync**: Always recommended for large datasets
5. **PII Fields**: Generator auto-detects common PII field names

## Connector Examples

### Stripe (API Connector)
- Objects: customers, charges, invoices
- Incremental: ✅ (by created date)
- Suggested fields: id, email, created, balance

### Postgres (Database Connector)
- Tables: Specify schema.table
- Incremental: ✅ (by updated_at)
- Suggested fields: id, updated_at

### CSV (File Connector)
- Files: Local or S3 paths
- Incremental: ✅ (by file modified time)
- Suggested fields: Custom based on your data

## Troubleshooting

**Q: Generator not found?**
```bash
# Ensure package is installed
pip install -e .

# Or use module directly
python3 -m src.dativo_ingest.cli generate
```

**Q: Missing connectors?**
```bash
# Check registry
cat registry/connectors.yaml
```

**Q: Want to edit existing files?**
- Generator only creates new files
- Edit YAML files directly for updates
- Or delete and regenerate

**Q: Need non-interactive mode?**
- Currently interactive only
- Future: CLI flags for automation

## Full Documentation

- **Complete Guide**: [docs/GENERATOR_CLI.md](docs/GENERATOR_CLI.md)
- **Implementation Details**: [IMPLEMENTATION_NOTES.md](IMPLEMENTATION_NOTES.md)
- **Summary**: [GENERATOR_SUMMARY.md](GENERATOR_SUMMARY.md)

## Support

Questions? Check:
1. [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) - Config details
2. [registry/connectors.yaml](registry/connectors.yaml) - Available connectors
3. [docs/examples/jobs/](docs/examples/jobs/) - Example jobs

---

**Ready to generate your first job?** Run `dativo generate` now! 🚀
