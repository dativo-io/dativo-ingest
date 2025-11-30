# Documentation Index

Central hub for the Dativo docs. Pick the persona or task that matches what you are trying to do and jump directly to the right guide.

## Execution flow cheat sheet

```
 SaaS / DB Sources
        |
        v
   Extract  -->  Validate  -->  Write  -->  Commit  -->  State
      |             |            |           |            |
      |        ODCS Schemas   Parquet    Iceberg/S3   Incremental
      |        + Registry     Writer     Catalog      checkpoints
```

## Audience map

### Platform & infra engineers

- [QUICKSTART.md](../QUICKSTART.md) – clone, install, run in <5 minutes.
- [docs/SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) – workstation setup, Docker, GPU/arm notes.
- [docs/SETUP_AND_TESTING.md](SETUP_AND_TESTING.md) – smoke + integration tests, CI parity.
- [docs/SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md) – how to switch from filesystem secrets to Vault/AWS/GCP.

### Data & analytics engineers

- [docs/CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) – every knob in job configs.
- [docs/MINIMAL_ASSET_EXAMPLE.md](MINIMAL_ASSET_EXAMPLE.md) – smallest valid ODCS contract.
- [docs/INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) – end-to-end lifecycle with examples.
- [examples/](../examples) – runnable jobs, plugins, and cross-cloud scenarios.

### Plugin & connector authors

- [docs/CONNECTOR_DEVELOPMENT.md](CONNECTOR_DEVELOPMENT.md) – step-by-step for adding a new connector/asset/registry entry.
- [docs/CUSTOM_PLUGINS.md](CUSTOM_PLUGINS.md) + [docs/PLUGIN_DECISION_TREE.md](PLUGIN_DECISION_TREE.md) – when to reach for Python vs. Rust plugins.
- [examples/plugins/](../examples/plugins) – ready-made JSON/Rust samples with Makefiles.

### Security & governance partners

- [docs/SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md) – rotation patterns, IAM examples.
- [docs/CATALOG_INTEGRATION.md](CATALOG_INTEGRATION.md) & [docs/CATALOG_LIMITATIONS.md](CATALOG_LIMITATIONS.md) – lineage push + caveats.
- [docs/TAG_PROPAGATION.md](TAG_PROPAGATION.md) & [docs/TAG_PRECEDENCE.md](TAG_PRECEDENCE.md) – metadata layering rules.
- [ROADMAP.md](../ROADMAP.md) – upcoming compliance and observability work.

## Task-based quick links

| Need to… | Read this |
| --- | --- |
| Spin up the CLI locally | [`QUICKSTART.md`](../QUICKSTART.md), [`docs/SETUP_AND_TESTING.md`](SETUP_AND_TESTING.md) |
| Configure secrets | [`docs/SECRET_MANAGEMENT.md`](SECRET_MANAGEMENT.md) |
| Add a new connector + asset | [`docs/CONNECTOR_DEVELOPMENT.md`](CONNECTOR_DEVELOPMENT.md) |
| Understand ODCS schema rules | [`docs/CONFIG_REFERENCE.md`](CONFIG_REFERENCE.md), [`docs/MINIMAL_ASSET_EXAMPLE.md`](MINIMAL_ASSET_EXAMPLE.md) |
| Run orchestrated mode | [`docs/RUNNER_AND_ORCHESTRATION.md`](RUNNER_AND_ORCHESTRATION.md) |
| Debug sandboxed plugins | [`docs/PLUGIN_SANDBOXING.md`](PLUGIN_SANDBOXING.md) |
| Inspect available sample jobs | [`docs/examples/jobs`](examples/jobs/) & [`examples/stripe_to_s3_iceberg/`](../examples/stripe_to_s3_iceberg/README.md) |

## Contributing pointers

1. Read [`.github/CONTRIBUTING.md`](../.github/CONTRIBUTING.md) for coding standards.
2. Follow the flow in [docs/CONNECTOR_DEVELOPMENT.md](CONNECTOR_DEVELOPMENT.md) when adding connectors/assets.
3. Run `make test`, `make schema-validate`, and the relevant `pytest` target before filing a PR.
4. Document new behavior in the relevant guide listed above so future contributors know where to look.

