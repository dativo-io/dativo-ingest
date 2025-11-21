.PHONY: schema-validate schema-connectors schema-odcs test-unit test-integration test-smoke test clean clean-state clean-temp

schema-validate: schema-connectors schema-odcs

schema-connectors:
	@yq -o=json '. ' registry/connectors.yaml > /tmp/connectors.json && npx ajv-cli validate -s schemas/connectors.schema.json -d /tmp/connectors.json --strict=false && rm -f /tmp/connectors.json

schema-odcs:
	@echo "🔍 Validating ODCS compliance..."
	@if [ -d venv ]; then \
		. venv/bin/activate && PYTHONPATH=src python tests/integration/test_odcs_compliance.py; \
	else \
		PYTHONPATH=src python3 tests/integration/test_odcs_compliance.py; \
	fi

# Unit tests: Test internal functions (config loading, validation, etc.)
test-unit:
	@pytest tests/test_*.py -v --ignore=tests/integration

# Integration tests: Test module integration, tag derivation, and ODCS compliance
test-integration:
	@echo "🔍 Running integration tests..."
	@if [ -f venv/bin/python ]; then \
		PYTHONPATH=src venv/bin/python tests/integration/test_tag_derivation_integration.py; \
		PYTHONPATH=src venv/bin/python tests/integration/test_complete_integration.py; \
	else \
		PYTHONPATH=src python3 tests/integration/test_tag_derivation_integration.py; \
		PYTHONPATH=src python3 tests/integration/test_complete_integration.py; \
	fi
	@echo "✅ All integration tests passed"

# Smoke tests: Run actual CLI commands with test fixtures (true E2E)
# Includes tag propagation verification
# Automatically sets up infrastructure services (Postgres, MySQL, MinIO, Nessie) if needed
# Note: Infrastructure services are dependencies for testing, NOT the dativo-ingest service
# The dativo-ingest CLI runs locally and connects to these services
# Uses run_all_smoke_tests.sh which runs both original and custom plugin smoke tests
# Users can also run: dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets
test-smoke:
	@echo "🧪 Running smoke tests..."
	@bash tests/run_all_smoke_tests.sh

# Run all tests
test: test-unit test-integration test-smoke

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


