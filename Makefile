.PHONY: schema-validate schema-connectors schema-templates

schema-validate: schema-connectors schema-templates

schema-connectors:
	@yq -o=json '. ' registry/connectors.yaml | npx ajv validate -s schemas/connectors.schema.json -d /dev/stdin --strict=false

schema-templates:
	@for f in registry/templates/*.yaml; do \
		echo "Validating $$f"; \
		yq -o=json '. ' $$f | npx ajv validate -s schemas/connector_template.schema.json -d /dev/stdin --strict=false; \
	done


