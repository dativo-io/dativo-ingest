# Direct AJV CLI usage

# Validate the main registry
yq -o=json '. ' /registry/connectors.yaml \
| npx ajv validate -s /schemas/connectors.schema.json -d /dev/stdin --strict=false

