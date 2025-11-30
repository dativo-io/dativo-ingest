# Connector Development Guide

End-to-end instructions for adding a new connector (source or target), wiring up assets, and verifying everything via CLI and tests.

## Who should read this?

- Data/platform engineers extending the connector catalog for their company.
- Contributors from the community proposing new SaaS/DB integrations.
- Plugin authors who want to ship a turnkey recipe before going full custom.

## Prerequisites

- Python 3.10+ with this repo installed in editable mode (`pip install -e .[dev]`).
- Familiarity with ODCS v3.0.2 schemas (see [docs/MINIMAL_ASSET_EXAMPLE.md](MINIMAL_ASSET_EXAMPLE.md)).
- Access to the target system (API keys, database creds, mock server, etc.).
- Ability to run `make schema-validate` and `pytest` locally.

## Repository layout refresher

```
connectors/              # Connector YAML recipes (engines, auth, defaults)
assets/{source}/v1.0/    # ODCS-compliant asset schemas
jobs/{tenant}/           # Example jobs referencing connectors + assets
registry/connectors.yaml # Capabilities + mode restrictions
tests/connectors/        # Unit + integration tests per connector
examples/                # Runnable scenarios (use them as inspiration)
```

## Workflow overview

1. **Design the connector contract**  
   - Decide on a connector `type` (e.g., `toy_http`) and whether it uses a built-in extractor, Airbyte/Singer, or a custom plugin.
   - Document supported objects/streams up front so assets can be versioned correctly.

2. **Create the connector recipe (`connectors/<name>.yaml`)**  
   - Start from an existing YAML (e.g., [`connectors/stripe.yaml`](../connectors/stripe.yaml)).  
   - Specify engine (`airbyte`, `native`, `custom_plugin`), auth fields, and mode restrictions.

3. **Add asset schemas (`assets/<name>/v1.0/*.yaml`)**  
   - Use [docs/MINIMAL_ASSET_EXAMPLE.md](MINIMAL_ASSET_EXAMPLE.md) as a template.  
   - Capture governance metadata (owners, tags, classification) so downstream catalogs get populated.

4. **Author a sample job (`jobs/<tenant>/<job>.yaml`)**  
   - Point to the connector + asset paths.  
   - Include realistic overrides (incremental config, markdown_kv storage, catalog settings).  
   - For shared examples, use the `tests/fixtures` tenant to keep secrets simple.

5. **Register the connector (`registry/connectors.yaml`)**  
   - Declare availability, allowed modes (`self_hosted`, `cloud`), and engines.  
   - Update any derived docs or tables that list supported sources/targets.

6. **Document configuration knobs**  
   - Update [`docs/CONFIG_REFERENCE.md`](CONFIG_REFERENCE.md) with new fields.  
   - Mention experimental status in [`ROADMAP.md`](../ROADMAP.md) if needed.

7. **Test everything**  
   - Write unit tests in `tests/connectors/test_<name>*.py`.  
   - If you have a mock server or Docker Compose stack, drop it under `examples/<scenario>/`.  
   - Run:

     ```bash
     make schema-validate
     pytest tests/connectors/test_<name>.py -q
     dativo discover --connector <name> --verbose   # optional sanity check
     ```

8. **Update docs/examples**  
   - Link the new scenario from [`README.md`](../README.md#examples) and [`docs/README.md`](README.md).  
   - Provide step-by-step instructions in an `examples/<scenario>/README.md`.

## Mini example: toy HTTP API connector

Connector recipe (`connectors/toy_http.yaml`):

```yaml
type: toy_http
version: 1.0.0
default_engine:
  type: airbyte
  image: dativo/toy_http:1.0.0
auth:
  required:
    - name: api_key
      env: TOY_HTTP_API_KEY
objects:
  - name: tickets
    cursor_field: updated_at
    primary_key: id
```

Asset schema ([`assets/toy_http/v1.0/tickets.yaml`](../assets/toy_http/v1.0/tickets.yaml)):

```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: toy_http_tickets
version: "1.0"
source_type: toy_http
object: tickets
schema:
  - name: id
    type: string
    required: true
  - name: status
    type: string
    enum: [open, closed, pending]
target:
  file_format: parquet
  partitioning: [ingest_date]
```

Job ([`jobs/examples/toy_http_tickets.yaml`](../jobs/examples/toy_http_tickets.yaml)):

```yaml
tenant_id: demo
source_connector: toy_http
source_connector_path: connectors/toy_http.yaml
asset: toy_http_tickets
asset_path: assets/toy_http/v1.0/tickets.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
source:
  connection:
    base_url: https://mock.toy-http.dev
    api_key: "${TOY_HTTP_API_KEY}"
  incremental:
    cursor_field: updated_at
    lookback_days: 2
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "raw/toy_http/tickets"
```

## Review checklist

- [ ] Connector recipe added + referenced in `registry/connectors.yaml`.
- [ ] Asset schemas and optional Markdown-KV configs checked in.
- [ ] Example job (and optional example project) provided.
- [ ] Tests + `make schema-validate` pass locally and in CI.
- [ ] README/docs updated with the new capability.

Ship it!

