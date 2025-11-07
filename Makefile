.PHONY: schema-validate schema-connectors

schema-validate: schema-connectors

schema-connectors:
	@yq -o=json '. ' registry/connectors.yaml | npx ajv validate -s schemas/connectors.schema.json -d /dev/stdin --strict=false


