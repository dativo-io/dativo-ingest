#!/bin/bash
# Generate a minimal job configuration template

set -e

TENANT_ID="${1:-mytenant}"
JOB_NAME="${2:-my_job}"
SOURCE="${3:-csv}"
TARGET="${4:-iceberg}"

JOB_DIR="jobs/${TENANT_ID}"
JOB_FILE="${JOB_DIR}/${JOB_NAME}.yaml"

# Create directory if it doesn't exist
mkdir -p "${JOB_DIR}"

# Generate template
cat > "${JOB_FILE}" << EOF
# ${JOB_NAME} - Generated job template
tenant_id: ${TENANT_ID}
environment: prod

# Source connector
source_connector: ${SOURCE}
source_connector_path: connectors/${SOURCE}.yaml

# Target connector
target_connector: ${TARGET}
target_connector_path: connectors/${TARGET}.yaml

# Asset definition
asset: ${JOB_NAME}
asset_path: assets/${SOURCE}/v1.0/${JOB_NAME}.yaml

# Source configuration
source:
  files:
    - path: data/your_file.csv
      object: ${JOB_NAME}

# Target configuration
target:
  connection:
    s3:
      bucket: "\${S3_BUCKET}"
      prefix: "raw/${TENANT_ID}/${JOB_NAME}"

# Infrastructure runtime metadata (Terraform-managed)
infrastructure:
  provider: aws
  region: us-east-1
  runtime:
    type: aws_fargate
  resource_identifiers:
    cluster_name: "{{terraform_outputs.cluster_name}}"
    service_name: "{{terraform_outputs.service_name}}"
  tags:
    job_name: ${JOB_NAME}
    team: data_platform
    pipeline_type: ingestion
    environment: prod
    cost_center: FINOPS-DEFAULT

# Schema validation mode
schema_validation_mode: strict  # or 'warn'

# Logging
logging:
  redaction: true
  level: INFO
EOF

echo "✅ Job template created: ${JOB_FILE}"
echo ""
echo "📝 Next steps:"
echo "   1. Create asset definition: assets/${SOURCE}/v1.0/${JOB_NAME}.yaml"
echo "   2. Set up secrets: secrets/${TENANT_ID}/iceberg.env"
echo "   3. Update source file path in job config"
echo "   4. Run: dativo run --config ${JOB_FILE} --mode self_hosted"

