# External Infrastructure Workflow

Dativo job definitions can now reference infrastructure that is provisioned and managed outside of the ingestion platform (for example, via Terraform modules owned by an infrastructure team). This document explains how job metadata flows from configuration files into Terraform, how outputs return to the job definition, and how to enforce consistent tagging across cloud providers.

## 1. Job Definition Schema Updates

Every job must include an `infrastructure` section:

```yaml
infrastructure:
  provider: aws | azure | gcp
  region: us-east-1
  runtime:
    type: aws_fargate | azure_container_apps | gcp_cloud_run
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    service_name: "{{terraform_outputs.service_name}}"
  tags:
    job_name: example_ingest_job
    team: data_platform
    pipeline_type: ingestion
    environment: prod
    cost_center: FINOPS-001
```

Validation rules enforced by `JobConfig` / `validate_infrastructure`:

- Provider/runtime combinations must be from the supported matrix (AWS Fargate, Azure Container Apps, GCP Cloud Run).
- `resource_identifiers` values must reference Terraform outputs using `{{terraform_outputs.<name>}}`.
- All required tags are present (`job_name`, `team`, `pipeline_type`, `environment`, `cost_center`) and the environment tag matches the job’s `environment` field.

## 2. Terraform Module Integration

Reference modules are available under `terraform/modules/`:

| Provider | Module Path | Outputs |
|----------|-------------|---------|
| AWS | `terraform/modules/aws_fargate` | `cluster_name`, `service_name`, `service_endpoint` |
| Azure | `terraform/modules/azure_container_apps` | `environment_name`, `container_app_name`, `ingress_url` |
| GCP | `terraform/modules/gcp_cloud_run` | `service_name`, `project_id`, `service_url` |

Each module:

1. Accepts `tags` (from the job definition) and `default_tags` (platform baseline).
2. Merges the maps so that every resource can set `tags = local.merged_tags` (AWS/Azure) or `labels = local.merged_labels` (GCP).
3. Exposes outputs that align with the placeholders defined in job YAML files.

> Tip: keep the module interface stable. When new metadata is required (for example, FinOps owner), extend the job schema, update the Terraform modules to accept the key, and rerun validation.

## 3. Tagging & Naming Best Practices

Recommendations inspired by official cloud guidance (AWS resource tagging best practices, Azure resource tagging strategies, Google Cloud labeling best practices):

- Enforce default provider-level tags/labels (`default_tags` / `default_labels`) and merge them with job metadata. This ensures auditability, cost allocation, and lineage back to the Dativo job.
- Apply the merged tags to **every resource** created by Terraform (clusters, services, log groups, load balancers, secrets, IAM roles, etc.). Leaving any resource untagged breaks FinOps reporting.
- Derive resource names from the job metadata (see module locals that normalise `job_name`): this supports traceability during incident response.
- Use consistent casing (lowercase-hyphenated) when generating names to avoid provider-specific restrictions.
- Surface ownership (`team`, `job_name`), runtime classification (`pipeline_type`), environment, and `cost_center` in the tags map to align with compliance and finance requirements.

## 4. End-to-End Workflow

1. **Author job metadata** – add the `infrastructure` block to the job YAML file with the required tags.
2. **Run Terraform** – the infrastructure team (or CI/CD pipeline) invokes the appropriate module and passes the job metadata map:

   ```hcl
   module "dativo_runtime" {
     source       = "git::ssh://example/terraform-modules.git//aws_fargate"
     region       = var.region
     runtime_type = "aws_fargate"
     tags         = var.job_metadata        # forwarded from job YAML
     default_tags = var.platform_defaults   # standard FinOps/ownership tags
   }
   ```

3. **Capture outputs** – serialise outputs to JSON so the deployment pipeline can resolve the job placeholders:

   ```bash
   terraform apply -auto-approve
   terraform output -json > runtime-outputs.json
   ```

4. **Update job definition** – substitute `{{terraform_outputs.<name>}}` in the YAML with the values from the JSON artifact when rendering the runtime configuration (handled automatically by the new job loader).
5. **Deploy job** – run the Dativo CLI/API deployment; validation ensures the infrastructure metadata is present and consistent.

The separation of duties remains intact: Terraform creates or updates infrastructure, Dativo simply consumes the outputs.

## 5. CI/CD Example (GitHub Actions)

```yaml
name: provision-runtime

on:
  workflow_dispatch:
    inputs:
      job_config_path:
        description: "Path to the job YAML that triggered this run"
        required: true

jobs:
  terraform:
    runs-on: ubuntu-latest
    env:
      TF_VAR_region: us-east-1
      TF_VAR_job_metadata: ${{ steps.extract_metadata.outputs.job_tags_json }}
    steps:
      - uses: actions/checkout@v4

      - name: Extract job tags
        id: extract_metadata
        run: |
          python scripts/render_job_tags.py "${{ github.event.inputs.job_config_path }}" > job-tags.json
          echo "job_tags_json=$(cat job-tags.json)" >> "$GITHUB_OUTPUT"

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: 1.8.5

      - name: Terraform Init
        working-directory: terraform/live/aws-fargate
        run: terraform init

      - name: Terraform Apply
        working-directory: terraform/live/aws-fargate
        run: terraform apply -auto-approve

      - name: Persist Terraform Outputs
        working-directory: terraform/live/aws-fargate
        run: terraform output -json > ../../artifacts/runtime-outputs.json

      - name: Deploy Dativo Job
        run: |
          dativo-cli jobs render \
            --config "${{ github.event.inputs.job_config_path }}" \
            --terraform-outputs terraform/artifacts/runtime-outputs.json \
            --out rendered-job.yaml
          dativo-cli jobs deploy --config rendered-job.yaml
```

Key points:

- The workflow extracts the job metadata (including infrastructure tags) and forwards it to Terraform as `var.job_metadata`.
- Terraform outputs are stored and then injected into the job definition during deployment.
- No Terraform provisioning logic lives inside Dativo; the CLI simply resolves placeholders using the JSON outputs.

## 6. Operational Checklist

- [ ] Job YAML includes the `infrastructure` block with required tags.
- [ ] Terraform module input `tags` map is populated from the job metadata.
- [ ] All Terraform resources apply the merged tags/labels.
- [ ] Module outputs are captured and referenced via `{{terraform_outputs.*}}`.
- [ ] Job validation (`dativo-ingest cli validate`) passes without infrastructure errors.

Following this workflow keeps infrastructure management in Terraform while guaranteeing that every runtime resource is traceable back to its originating Dativo job.
