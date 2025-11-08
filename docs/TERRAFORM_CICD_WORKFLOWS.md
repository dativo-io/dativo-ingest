# CI/CD Workflows for Terraform Infrastructure Integration

This document provides CI/CD workflow examples for automating the Terraform infrastructure provisioning and Dativo job deployment process.

## Table of Contents

- [Overview](#overview)
- [GitHub Actions Workflows](#github-actions-workflows)
- [GitLab CI/CD](#gitlab-cicd)
- [Azure DevOps](#azure-devops)
- [Workflow Components](#workflow-components)
- [Best Practices](#best-practices)

## Overview

The CI/CD workflow automates the following steps:

1. **Extract job metadata** from Dativo job configuration
2. **Generate Terraform variables** from job metadata (tags)
3. **Run Terraform** to provision infrastructure
4. **Capture Terraform outputs** (resource identifiers)
5. **Update job configuration** with Terraform outputs (replace placeholders)
6. **Validate job configuration** against schema
7. **Deploy Dativo job** to runtime environment

## GitHub Actions Workflows

### Complete Workflow: Infrastructure + Job Deployment

Create `.github/workflows/dativo-infrastructure-deploy.yml`:

```yaml
name: Dativo Infrastructure and Job Deployment

on:
  push:
    branches:
      - main
    paths:
      - 'jobs/**/*.yaml'
      - 'terraform/dativo_jobs/**/*.tf'
  pull_request:
    branches:
      - main
    paths:
      - 'jobs/**/*.yaml'
      - 'terraform/dativo_jobs/**/*.tf'

env:
  TERRAFORM_VERSION: 1.5.0
  PYTHON_VERSION: 3.10

jobs:
  detect-changes:
    name: Detect Changed Jobs
    runs-on: ubuntu-latest
    outputs:
      job_configs: ${{ steps.detect.outputs.job_configs }}
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
        with:
          fetch-depth: 0

      - name: Detect changed job configs
        id: detect
        run: |
          # Get list of changed job config files
          CHANGED_FILES=$(git diff --name-only ${{ github.event.before }} ${{ github.sha }} | grep '^jobs/.*\.yaml$' || true)
          
          if [ -z "$CHANGED_FILES" ]; then
            echo "No job config changes detected"
            echo "job_configs=[]" >> $GITHUB_OUTPUT
          else
            # Convert to JSON array
            JOB_CONFIGS=$(echo "$CHANGED_FILES" | jq -R -s -c 'split("\n") | map(select(length > 0))')
            echo "job_configs=$JOB_CONFIGS" >> $GITHUB_OUTPUT
            echo "Changed job configs: $JOB_CONFIGS"
          fi

  provision-infrastructure:
    name: Provision Infrastructure
    runs-on: ubuntu-latest
    needs: detect-changes
    if: needs.detect-changes.outputs.job_configs != '[]'
    strategy:
      matrix:
        job_config: ${{ fromJson(needs.detect-changes.outputs.job_configs) }}
    outputs:
      terraform_outputs: ${{ steps.terraform-output.outputs.outputs }}
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install dependencies
        run: |
          pip install pyyaml jinja2

      - name: Extract job metadata from config
        id: extract-metadata
        run: |
          python - <<'EOF'
          import yaml
          import json
          import sys
          
          # Read job config
          with open("${{ matrix.job_config }}", "r") as f:
              config = yaml.safe_load(f)
          
          # Extract infrastructure metadata
          if "infrastructure" not in config:
              print("No infrastructure section found")
              sys.exit(0)
          
          infra = config["infrastructure"]
          
          # Extract tags
          tags = infra.get("tags", {})
          
          # Extract provider and runtime info
          provider = infra.get("provider")
          runtime_type = infra.get("runtime", {}).get("type")
          region = infra.get("region")
          
          # Output as JSON for Terraform variables
          metadata = {
              "job_name": tags.get("job_name"),
              "team": tags.get("team"),
              "pipeline_type": tags.get("pipeline_type"),
              "environment": tags.get("environment"),
              "cost_center": tags.get("cost_center"),
              "provider": provider,
              "runtime_type": runtime_type,
              "region": region
          }
          
          print(json.dumps(metadata))
          
          # Write to GITHUB_OUTPUT
          with open("$GITHUB_OUTPUT", "a") as f:
              f.write(f"metadata={json.dumps(metadata)}\n")
          EOF

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v2
        with:
          terraform_version: ${{ env.TERRAFORM_VERSION }}
          terraform_wrapper: false

      - name: Configure cloud credentials
        run: |
          # Configure based on provider
          PROVIDER=$(echo '${{ steps.extract-metadata.outputs.metadata }}' | jq -r '.provider')
          
          if [ "$PROVIDER" == "aws" ]; then
            # AWS credentials from secrets
            echo "AWS_ACCESS_KEY_ID=${{ secrets.AWS_ACCESS_KEY_ID }}" >> $GITHUB_ENV
            echo "AWS_SECRET_ACCESS_KEY=${{ secrets.AWS_SECRET_ACCESS_KEY }}" >> $GITHUB_ENV
            echo "AWS_REGION=${{ steps.extract-metadata.outputs.metadata.region }}" >> $GITHUB_ENV
          elif [ "$PROVIDER" == "azure" ]; then
            # Azure credentials
            echo "ARM_CLIENT_ID=${{ secrets.AZURE_CLIENT_ID }}" >> $GITHUB_ENV
            echo "ARM_CLIENT_SECRET=${{ secrets.AZURE_CLIENT_SECRET }}" >> $GITHUB_ENV
            echo "ARM_SUBSCRIPTION_ID=${{ secrets.AZURE_SUBSCRIPTION_ID }}" >> $GITHUB_ENV
            echo "ARM_TENANT_ID=${{ secrets.AZURE_TENANT_ID }}" >> $GITHUB_ENV
          elif [ "$PROVIDER" == "gcp" ]; then
            # GCP credentials
            echo '${{ secrets.GCP_SA_KEY }}' > gcp-key.json
            echo "GOOGLE_APPLICATION_CREDENTIALS=gcp-key.json" >> $GITHUB_ENV
          fi

      - name: Generate Terraform variables
        run: |
          METADATA='${{ steps.extract-metadata.outputs.metadata }}'
          
          cat > terraform/dativo_jobs/auto.tfvars.json <<EOF
          {
            "job_metadata": {
              "job_name": $(echo $METADATA | jq -r '.job_name'),
              "team": $(echo $METADATA | jq -r '.team'),
              "pipeline_type": $(echo $METADATA | jq -r '.pipeline_type'),
              "environment": $(echo $METADATA | jq -r '.environment'),
              "cost_center": $(echo $METADATA | jq -r '.cost_center')
            },
            "region": $(echo $METADATA | jq -r '.region')
          }
          EOF

      - name: Terraform Init
        working-directory: terraform/dativo_jobs
        run: terraform init

      - name: Terraform Plan
        working-directory: terraform/dativo_jobs
        run: terraform plan -out=tfplan

      - name: Terraform Apply
        working-directory: terraform/dativo_jobs
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: terraform apply -auto-approve tfplan

      - name: Capture Terraform Outputs
        id: terraform-output
        working-directory: terraform/dativo_jobs
        run: |
          terraform output -json > outputs.json
          cat outputs.json
          
          # Write to GITHUB_OUTPUT
          echo "outputs=$(cat outputs.json)" >> $GITHUB_OUTPUT

      - name: Upload Terraform outputs
        uses: actions/upload-artifact@v3
        with:
          name: terraform-outputs-${{ matrix.job_config }}
          path: terraform/dativo_jobs/outputs.json

  update-job-configs:
    name: Update Job Configs with Terraform Outputs
    runs-on: ubuntu-latest
    needs: [detect-changes, provision-infrastructure]
    if: needs.detect-changes.outputs.job_configs != '[]'
    strategy:
      matrix:
        job_config: ${{ fromJson(needs.detect-changes.outputs.job_configs) }}
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Download Terraform outputs
        uses: actions/download-artifact@v3
        with:
          name: terraform-outputs-${{ matrix.job_config }}
          path: ./

      - name: Update job config with Terraform outputs
        run: |
          python - <<'EOF'
          import yaml
          import json
          import re
          
          # Read Terraform outputs
          with open("outputs.json", "r") as f:
              outputs = json.load(f)
          
          # Read job config
          with open("${{ matrix.job_config }}", "r") as f:
              config = yaml.safe_load(f)
          
          # Replace placeholders
          def replace_placeholders(obj):
              if isinstance(obj, dict):
                  return {k: replace_placeholders(v) for k, v in obj.items()}
              elif isinstance(obj, list):
                  return [replace_placeholders(item) for item in obj]
              elif isinstance(obj, str):
                  # Match {{terraform_outputs.<key>}}
                  pattern = r'\{\{terraform_outputs\.([a-zA-Z0-9_]+)\}\}'
                  def replacer(match):
                      key = match.group(1)
                      if key in outputs:
                          return outputs[key]["value"]
                      return match.group(0)
                  return re.sub(pattern, replacer, obj)
              return obj
          
          # Update resource_identifiers
          if "infrastructure" in config and "resource_identifiers" in config["infrastructure"]:
              config["infrastructure"]["resource_identifiers"] = replace_placeholders(
                  config["infrastructure"]["resource_identifiers"]
              )
          
          # Write updated config
          with open("${{ matrix.job_config }}", "w") as f:
              yaml.dump(config, f, default_flow_style=False, sort_keys=False)
          
          print(f"Updated {('${{ matrix.job_config }}')} with Terraform outputs")
          EOF

      - name: Commit updated job configs
        if: github.ref == 'refs/heads/main' && github.event_name == 'push'
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add ${{ matrix.job_config }}
          git commit -m "chore: update job config with Terraform outputs [skip ci]" || echo "No changes to commit"
          git push

  deploy-dativo-jobs:
    name: Deploy Dativo Jobs
    runs-on: ubuntu-latest
    needs: [detect-changes, update-job-configs]
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    strategy:
      matrix:
        job_config: ${{ fromJson(needs.detect-changes.outputs.job_configs) }}
    steps:
      - name: Checkout code
        uses: actions/checkout@v3
        with:
          ref: main  # Get latest with updated configs

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: ${{ env.PYTHON_VERSION }}

      - name: Install Dativo CLI
        run: |
          pip install -e .

      - name: Validate job configuration
        run: |
          dativo_ingest run --config ${{ matrix.job_config }} --mode cloud --validate-only

      - name: Deploy Dativo job
        run: |
          # Actual deployment logic depends on your setup
          # This is a placeholder for job registration/deployment
          echo "Deploying job: ${{ matrix.job_config }}"
          
          # Example: Register with orchestrator
          # dativo_ingest register --config ${{ matrix.job_config }}
          
          # Or: Deploy to cloud scheduler
          # ./scripts/deploy-to-scheduler.sh ${{ matrix.job_config }}

      - name: Notify success
        if: success()
        run: |
          echo "✅ Successfully deployed job: ${{ matrix.job_config }}"
```

### Simplified Workflow: Single Job

For deploying a single job (not change-detection based):

Create `.github/workflows/deploy-single-job.yml`:

```yaml
name: Deploy Single Dativo Job with Infrastructure

on:
  workflow_dispatch:
    inputs:
      job_config_path:
        description: 'Path to job config file'
        required: true
        type: string
      environment:
        description: 'Target environment'
        required: true
        type: choice
        options:
          - dev
          - staging
          - prod

jobs:
  deploy:
    name: Deploy Job with Infrastructure
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Extract and provision
        run: |
          # Extract metadata
          python scripts/extract_job_metadata.py ${{ inputs.job_config_path }} > metadata.json
          
          # Setup Terraform
          cd terraform/dativo_jobs
          terraform init
          terraform apply -auto-approve -var-file=<(cat ../../metadata.json)
          
          # Capture outputs
          terraform output -json > outputs.json
          
          # Update job config
          python ../../scripts/update_job_config.py ${{ inputs.job_config_path }} outputs.json
          
          # Validate
          dativo_ingest run --config ../../${{ inputs.job_config_path }} --validate-only
          
          # Deploy
          echo "Job deployed successfully"
```

## GitLab CI/CD

Create `.gitlab-ci.yml`:

```yaml
stages:
  - validate
  - provision
  - deploy

variables:
  TERRAFORM_VERSION: "1.5.0"
  PYTHON_VERSION: "3.10"

.terraform_base:
  image: hashicorp/terraform:$TERRAFORM_VERSION
  before_script:
    - cd terraform/dativo_jobs
    - terraform init

extract_metadata:
  stage: validate
  image: python:$PYTHON_VERSION
  script:
    - pip install pyyaml
    - python scripts/extract_all_job_metadata.py > job_metadata.json
  artifacts:
    paths:
      - job_metadata.json
    expire_in: 1 hour

terraform_plan:
  stage: validate
  extends: .terraform_base
  script:
    - terraform plan -out=tfplan
  artifacts:
    paths:
      - terraform/dativo_jobs/tfplan
    expire_in: 1 hour

terraform_apply:
  stage: provision
  extends: .terraform_base
  script:
    - terraform apply -auto-approve tfplan
    - terraform output -json > outputs.json
  artifacts:
    paths:
      - terraform/dativo_jobs/outputs.json
    expire_in: 1 hour
  only:
    - main

update_configs:
  stage: provision
  image: python:$PYTHON_VERSION
  dependencies:
    - terraform_apply
  script:
    - pip install pyyaml
    - python scripts/update_all_job_configs.py terraform/dativo_jobs/outputs.json
  artifacts:
    paths:
      - jobs/**/*.yaml
    expire_in: 1 hour
  only:
    - main

deploy_jobs:
  stage: deploy
  image: python:$PYTHON_VERSION
  dependencies:
    - update_configs
  script:
    - pip install -e .
    - |
      for job in jobs/**/*.yaml; do
        echo "Deploying $job"
        dativo_ingest run --config "$job" --mode cloud --validate-only
      done
  only:
    - main
```

## Azure DevOps

Create `azure-pipelines.yml`:

```yaml
trigger:
  branches:
    include:
      - main
  paths:
    include:
      - jobs/**/*.yaml
      - terraform/dativo_jobs/**

pool:
  vmImage: 'ubuntu-latest'

variables:
  - name: TERRAFORM_VERSION
    value: '1.5.0'
  - name: PYTHON_VERSION
    value: '3.10'

stages:
  - stage: Provision
    displayName: 'Provision Infrastructure'
    jobs:
      - job: Terraform
        displayName: 'Terraform Apply'
        steps:
          - task: UsePythonVersion@0
            inputs:
              versionSpec: '$(PYTHON_VERSION)'

          - script: |
              pip install pyyaml
              python scripts/extract_job_metadata.py jobs/**/*.yaml > metadata.json
            displayName: 'Extract Job Metadata'

          - task: TerraformInstaller@0
            inputs:
              terraformVersion: '$(TERRAFORM_VERSION)'

          - task: TerraformTaskV2@2
            displayName: 'Terraform Init'
            inputs:
              provider: 'azurerm'
              command: 'init'
              workingDirectory: '$(System.DefaultWorkingDirectory)/terraform/dativo_jobs'

          - task: TerraformTaskV2@2
            displayName: 'Terraform Apply'
            inputs:
              provider: 'azurerm'
              command: 'apply'
              workingDirectory: '$(System.DefaultWorkingDirectory)/terraform/dativo_jobs'
              environmentServiceNameAzureRM: 'AzureServiceConnection'

          - script: |
              cd terraform/dativo_jobs
              terraform output -json > outputs.json
            displayName: 'Capture Terraform Outputs'

          - publish: terraform/dativo_jobs/outputs.json
            artifact: terraform-outputs
            displayName: 'Publish Terraform Outputs'

  - stage: Deploy
    displayName: 'Deploy Dativo Jobs'
    dependsOn: Provision
    jobs:
      - job: DeployJobs
        displayName: 'Deploy Jobs'
        steps:
          - download: current
            artifact: terraform-outputs

          - task: UsePythonVersion@0
            inputs:
              versionSpec: '$(PYTHON_VERSION)'

          - script: |
              pip install -e .
              pip install pyyaml
            displayName: 'Install Dependencies'

          - script: |
              python scripts/update_all_job_configs.py $(Pipeline.Workspace)/terraform-outputs/outputs.json
            displayName: 'Update Job Configs'

          - script: |
              for job in jobs/**/*.yaml; do
                echo "Validating $job"
                dativo_ingest run --config "$job" --mode cloud --validate-only
              done
            displayName: 'Validate Jobs'

          - script: |
              for job in jobs/**/*.yaml; do
                echo "Deploying $job"
                # Add actual deployment logic
              done
            displayName: 'Deploy Jobs'
```

## Workflow Components

### 1. Extract Job Metadata Script

Create `scripts/extract_job_metadata.py`:

```python
#!/usr/bin/env python3
"""Extract job metadata from Dativo job configuration."""

import sys
import yaml
import json

def extract_metadata(job_config_path):
    """Extract infrastructure metadata from job config."""
    with open(job_config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    if 'infrastructure' not in config:
        print("No infrastructure section found", file=sys.stderr)
        return None
    
    infra = config['infrastructure']
    tags = infra.get('tags', {})
    
    metadata = {
        'job_name': tags.get('job_name'),
        'team': tags.get('team'),
        'pipeline_type': tags.get('pipeline_type'),
        'environment': tags.get('environment'),
        'cost_center': tags.get('cost_center'),
        'provider': infra.get('provider'),
        'runtime_type': infra.get('runtime', {}).get('type'),
        'region': infra.get('region')
    }
    
    return metadata

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: extract_job_metadata.py <job_config_path>", file=sys.stderr)
        sys.exit(1)
    
    metadata = extract_metadata(sys.argv[1])
    if metadata:
        print(json.dumps(metadata, indent=2))
```

### 2. Update Job Config Script

Create `scripts/update_job_config.py`:

```python
#!/usr/bin/env python3
"""Update job config with Terraform outputs."""

import sys
import yaml
import json
import re

def update_job_config(job_config_path, terraform_outputs_path):
    """Replace Terraform output placeholders in job config."""
    # Read Terraform outputs
    with open(terraform_outputs_path, 'r') as f:
        outputs = json.load(f)
    
    # Read job config
    with open(job_config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Replace placeholders
    def replace_placeholders(obj):
        if isinstance(obj, dict):
            return {k: replace_placeholders(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [replace_placeholders(item) for item in obj]
        elif isinstance(obj, str):
            pattern = r'\{\{terraform_outputs\.([a-zA-Z0-9_]+)\}\}'
            def replacer(match):
                key = match.group(1)
                if key in outputs:
                    return str(outputs[key]['value'])
                return match.group(0)
            return re.sub(pattern, replacer, obj)
        return obj
    
    # Update resource_identifiers
    if 'infrastructure' in config and 'resource_identifiers' in config['infrastructure']:
        config['infrastructure']['resource_identifiers'] = replace_placeholders(
            config['infrastructure']['resource_identifiers']
        )
    
    # Write updated config
    with open(job_config_path, 'w') as f:
        yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    
    print(f"Updated {job_config_path} with Terraform outputs")

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print("Usage: update_job_config.py <job_config_path> <terraform_outputs_path>", file=sys.stderr)
        sys.exit(1)
    
    update_job_config(sys.argv[1], sys.argv[2])
```

## Best Practices

### 1. Secure Secrets Management

✅ **DO:**
- Store cloud credentials in CI/CD secrets
- Use OIDC/Workload Identity when possible
- Rotate credentials regularly
- Use separate credentials per environment

❌ **DON'T:**
- Commit credentials to git
- Share credentials across environments
- Use long-lived access keys

### 2. Terraform State Management

✅ **DO:**
- Use remote state backend (S3, Azure Storage, GCS)
- Enable state locking
- Use separate state per environment
- Back up state files

❌ **DON'T:**
- Store state in git
- Use local state in CI/CD
- Share state across environments

### 3. Workflow Optimization

✅ **DO:**
- Cache dependencies (Terraform, Python packages)
- Use matrix builds for parallel execution
- Implement change detection to avoid unnecessary runs
- Use artifacts to pass data between jobs

❌ **DON'T:**
- Run full workflows on every commit
- Repeat expensive operations unnecessarily
- Deploy to production without approval gates

### 4. Error Handling

✅ **DO:**
- Implement retry logic for transient failures
- Send notifications on failures
- Capture logs and artifacts
- Implement rollback mechanisms

❌ **DON'T:**
- Ignore validation errors
- Deploy without testing
- Skip error notifications

### 5. Testing

✅ **DO:**
- Validate Terraform plans before apply
- Test job configs before deployment
- Use separate environments for testing
- Implement smoke tests

❌ **DON'T:**
- Deploy directly to production
- Skip validation steps
- Test in production

## Additional Resources

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [GitLab CI/CD Documentation](https://docs.gitlab.com/ee/ci/)
- [Azure DevOps Pipelines](https://learn.microsoft.com/en-us/azure/devops/pipelines/)
- [Terraform Automation](https://developer.hashicorp.com/terraform/tutorials/automation)
- [Main Integration Guide](./TERRAFORM_INFRASTRUCTURE_INTEGRATION.md)
