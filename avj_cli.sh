# Direct AJV CLI usage

# Validate the main registry
yq -o=json '. ' /registry/connectors.yaml \
| npx ajv validate -s /schemas/connectors.schema.json -d /dev/stdin --strict=false

# Validate all templates
for f in /registry/templates/*.yaml; do
  echo "Validating $f"
  yq -o=json '. ' "$f" \
  | npx ajv validate -s /schemas/connector_template.schema.json -d /dev/stdin --strict=false
done
