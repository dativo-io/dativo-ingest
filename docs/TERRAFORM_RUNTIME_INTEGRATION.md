# Terraform Runtime Integration Guide

This guide explains how Dativo job definitions consume infrastructure provisioned by external Terraform pipelines while keeping metadata, tagging, and FinOps requirements in sync.

## End-to-End Flow

1. **Job author** defines runtime metadata in the job YAML (`infrastructure` block) including mandatory tags.
2. **CI/CD pipeline** reads the job definition, extracts `infrastructure.tags`, and passes them to the Terraform module as `var.tags`.
3. **Terraform module** merges `var.default_tags` (provider/landing zone defaults) with job tags and provisions the runtime (Fargate, Container Apps, Cloud Run).
4. **Terraform apply** emits outputs such as `cluster_name`, `service_name`, and `endpoint_url`.
5. **CI/CD pipeline** captures the outputs (`terraform output -json`) and writes them to a JSON file (e.g., `.terraform-runtime/<tenant>/<job>.json`).
6. **Job deployment step** renders the job YAML, replacing `{{terraform_outputs.*}}` placeholders with actual values before calling `dativo-ingest` or committing the rendered config.

## Required Tag Keys

| Key | Purpose | Example |
| --- | ------- | ------- |
| `job_name` | Traceability back to the Dativo job definition | `mysql-customers-to-s3` |
| `team` | Ownership / on-call routing | `data-platform` |
| `pipeline_type` | Workload classification (batch, streaming, ml) | `batch` |
| `environment` | Deployment environment | `prod` |
| `cost_center` | FinOps / chargeback | `FINOPS-001` |

> Add additional metadata (`data_classification`, `compliance`, `lifecycle`) as needed—everything in `tags` flows directly into Terraform.

## Reference Modules

| Runtime | Module | Notes |
| ------- | ------ | ----- |
| AWS Fargate | `terraform/modules/aws_fargate_runtime` | Produces `cluster_name`, `service_name`, `endpoint_url`, and `applied_tags`. |
| Azure Container Apps | `terraform/modules/azure_container_apps_runtime` | Produces `environment_name`, `service_name`, `endpoint_url`, and `applied_tags`. |
| GCP Cloud Run | `terraform/modules/gcp_cloud_run_runtime` | Produces `service_name`, `endpoint_url`, and `applied_tags` (labels). |

Each module follows the same contract:

- **Inputs**: `region`, `runtime_type`, `tags`, `default_tags`, and provider-specific identifiers (`project_id`, `resource_group_name`, etc.).
- **Tag propagation**: `local.merged_tags = merge(var.default_tags, var.tags)` (or `local.normalized_labels` for GCP). Apply this map to every resource.
- **Outputs**: Identifiers consumed by the job definition via `{{terraform_outputs.<name>}}`.

## Rendering Job Configurations with Terraform Outputs

After `terraform apply`, capture the outputs:

```bash
terraform output -json > .terraform-runtime/acme/mysql_customers_to_s3.json
```

Render the job configuration by replacing placeholders:

```bash
jq -r '
  . + {
    target: (.target // {}) + {
      connection: (.target.connection // {}) + {
        runtime_endpoint: (inputjson.endpoint_url.value)
      }
    },
    infrastructure: (.infrastructure // {}) + {
      resource_identifiers: {
        cluster_name: (inputjson.cluster_name.value),
        service_name: (inputjson.service_name.value),
        endpoint_url: (inputjson.endpoint_url.value)
      }
    }
  }
' docs/examples/jobs/acme/mysql_customers_to_s3_infrastructure.yaml \
   .terraform-runtime/acme/mysql_customers_to_s3.json \
   > rendered_jobs/acme/mysql_customers_to_s3.yaml
```

The rendered YAML can then be committed, deployed, or passed directly to `dativo_ingest.cli`.

## Tagging Best Practices

- **AWS**: Follow [AWS Tagging Strategies](https://docs.aws.amazon.com/whitepapers/latest/tagging-best-practices/tagging-strategy.html). Replicate required organization-level tags via `var.default_tags` and merge job-specific metadata.
- **Azure**: Align with [Azure resource tagging design area](https://learn.microsoft.com/azure/cloud-adoption-framework/ready/landing-zone/design-area/resource-tagging). Enforce Azure Policy to block resources missing the mandatory keys.
- **GCP**: Respect [label key restrictions](https://cloud.google.com/resource-manager/docs/creating-managing-labels). The Cloud Run module normalises keys, but standardise on lowercase, hyphen/underscore-delimited names.

## Validating Metadata in Dativo

When `JobConfig.from_yaml` loads a job:

- Provider/runtime combinations are validated (`aws`/`aws_fargate`, `azure`/`azure_container_apps`, `gcp`/`gcp_cloud_run`).
- All required tags must be present and non-empty.
- `resource_identifiers` must reference Terraform outputs.
- `infrastructure.tags.environment` must match the job-level `environment`.
- `validate_infrastructure(job_config)` cross-checks Terraform placeholders and emits warnings if the infrastructure block is missing.

## Optional CI/CD Automation (GitHub Actions)

See [CI/CD Automation](#cicd-automation) for a full example that ties these pieces together.

## CI/CD Automation

The workflow below shows one way to orchestrate Terraform and Dativo using GitHub Actions. It extracts job metadata, applies the Terraform module, captures outputs, renders the job definition, and triggers the Dativo CLI.

> Requirements: `hashicorp/setup-terraform` action, `yq` and `jq` CLIs (pre-installed on `ubuntu-latest`), and Dativo CLI on the PATH.

```yaml
name: Deploy Dativo Job

on:
  workflow_dispatch:
  push:
    paths:
      - terraform/**
      - docs/examples/jobs/acme/*.yaml

jobs:
  deploy-runtime:
    runs-on: ubuntu-latest
    env:
      JOB_FILE: docs/examples/jobs/acme/mysql_customers_to_s3_infrastructure.yaml
      TF_WORKDIR: terraform/environments/prod/aws_fargate_runtime
      OUTPUT_FILE: .terraform-runtime/acme/mysql_customers_to_s3.json

    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v2

      - name: Extract job metadata
        id: metadata
        run: |
          job_file="${JOB_FILE}"
          echo "region=$(yq -r '.infrastructure.region' \"$job_file\")" >> "$GITHUB_OUTPUT"
          echo "runtime_type=$(yq -r '.infrastructure.runtime.type' \"$job_file\")" >> "$GITHUB_OUTPUT"
          echo "tags=$(yq -o=json '.infrastructure.tags' \"$job_file\")" >> "$GITHUB_OUTPUT"

      - name: Generate tfvars.json from job metadata
        run: |
          mkdir -p "$TF_WORKDIR"
          cat <<EOF > "$TF_WORKDIR/runtime.auto.tfvars.json"
{
  "region": "${{ steps.metadata.outputs.region }}",
  "runtime_type": "${{ steps.metadata.outputs.runtime_type }}",
  "tags": ${{ steps.metadata.outputs.tags }}
}
EOF

      - name: Terraform apply
        working-directory: ${{ env.TF_WORKDIR }}
        env:
          TF_IN_AUTOMATION: "true"
        run: |
          terraform init
          terraform apply -auto-approve

      - name: Capture Terraform outputs
        working-directory: ${{ env.TF_WORKDIR }}
        run: |
          mkdir -p "$(dirname "$OUTPUT_FILE")"
          terraform output -json > "$OUTPUT_FILE"

      - name: Render job definition with Terraform outputs
        run: |
          outputs_json=$(cat "$TF_WORKDIR/$OUTPUT_FILE")
          mkdir -p rendered_jobs/acme
          yq -y --argjson outputs "$outputs_json" '
            .target.connection.runtime_endpoint = $outputs.endpoint_url.value |
            .infrastructure.resource_identifiers.cluster_name = $outputs.cluster_name.value |
            .infrastructure.resource_identifiers.service_name = $outputs.service_name.value |
            .infrastructure.resource_identifiers.endpoint_url = $outputs.endpoint_url.value
          ' "$JOB_FILE" > rendered_jobs/acme/mysql_customers_to_s3.yaml

      - name: Deploy job via Dativo CLI
        run: |
          dativo-ingest run \
            --config rendered_jobs/acme/mysql_customers_to_s3.yaml \
            --mode self_hosted
```

Adapt the matrix, directories, and deployment command to your environment. The key pattern is:

1. Derive Terraform variables from `infrastructure` metadata.
2. Merge tags inside Terraform (`merge(var.default_tags, var.tags)`).
3. Capture outputs and project them back into the job definition.
4. Keep rendered job files under source control or artifact storage for auditing.
