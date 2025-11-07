.PHONY: schema-validate schema-connectors test-unit test-smoke test clean clean-state clean-temp

schema-validate: schema-connectors

schema-connectors:
	@yq -o=json '. ' registry/connectors.yaml > /tmp/connectors.json && npx ajv-cli validate -s schemas/connectors.schema.json -d /tmp/connectors.json --strict=false && rm -f /tmp/connectors.json

# Unit tests: Test internal functions (config loading, validation, etc.)
test-unit:
	@pytest tests/test_*.py -v

# Smoke tests: Run actual CLI commands with test fixtures (true E2E)
# Users can also run: dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets
test-smoke:
	@python -m dativo_ingest.cli run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted

# Run all tests
test: test-unit test-smoke

# Clean up state files (development)
clean-state:
	@echo "🧹 Cleaning up state files..."
	@rm -rf .local/state
	@rm -rf state
	@echo "✅ State files cleaned"

# Clean up temporary files (Parquet files, logs, etc.)
clean-temp:
	@echo "🧹 Cleaning up temporary files..."
	@rm -rf /tmp/dativo_ingest* 2>/dev/null || true
	@rm -rf /tmp/dativo-state 2>/dev/null || true
	@rm -f *.log 2>/dev/null || true
	@find . -maxdepth 1 -name "*.tmp" -type f -delete 2>/dev/null || true
	@find . -maxdepth 1 -name "*.temp" -type f -delete 2>/dev/null || true
	@echo "✅ Temporary files cleaned"

# Clean up everything (state + temp files)
clean: clean-state clean-temp
	@echo "✅ All cleanup complete"


