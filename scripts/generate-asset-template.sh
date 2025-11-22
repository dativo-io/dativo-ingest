#!/bin/bash
# Generate a minimal asset definition template

set -e

SOURCE_TYPE="${1:-csv}"
ASSET_NAME="${2:-my_asset}"
OWNER_EMAIL="${3:-your-email@company.com}"

ASSET_DIR="assets/${SOURCE_TYPE}/v1.0"
ASSET_FILE="${ASSET_DIR}/${ASSET_NAME}.yaml"

# Create directory if it doesn't exist
mkdir -p "${ASSET_DIR}"

# Generate template
cat > "${ASSET_FILE}" << EOF
# Minimal asset definition for ${ASSET_NAME}
\$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: ${ASSET_NAME}
version: "1.0"
source_type: ${SOURCE_TYPE}
object: ${ASSET_NAME}

# Schema definition - add your fields here
schema:
  - name: id
    type: integer
    required: true
  - name: name
    type: string
    required: true
  # Add more fields as needed

# Target configuration
target:
  file_format: parquet
  partitioning: [ingest_date]

# Governance (required)
team:
  owner: ${OWNER_EMAIL}

compliance:
  classification: []  # Add [PII], [SENSITIVE], etc. as needed
EOF

echo "✅ Asset template created: ${ASSET_FILE}"
echo ""
echo "📝 Next steps:"
echo "   1. Update schema fields to match your data"
echo "   2. Add field classifications if needed (PII, SENSITIVE)"
echo "   3. Add compliance details (regulations, retention_days)"
echo "   4. Validate: make schema-validate"
echo ""
echo "📖 See docs/MINIMAL_ASSET_EXAMPLE.md for more details"

