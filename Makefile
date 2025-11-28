.PHONY: schema-validate schema-connectors schema-odcs test-unit test-integration test-smoke test-workflows test-plugin test format format-check lint clean clean-state clean-temp build-plugin-images

schema-validate: schema-connectors schema-odcs

schema-connectors:
	@echo "🔍 Validating connector registry schema..."
	@if [ -d venv ]; then \
		. venv/bin/activate && PYTHONPATH=src python -c "import yaml, json, sys; data = yaml.safe_load(open('registry/connectors.yaml')); json.dump(data, open('/tmp/connectors.json', 'w'), indent=2)"; \
	else \
		PYTHONPATH=src python3 -c "import yaml, json, sys; data = yaml.safe_load(open('registry/connectors.yaml')); json.dump(data, open('/tmp/connectors.json', 'w'), indent=2)"; \
	fi
	@npx ajv-cli validate -s schemas/connectors.schema.json -d /tmp/connectors.json --strict=false && rm -f /tmp/connectors.json || (rm -f /tmp/connectors.json && exit 1)

schema-odcs:
	@echo "🔍 Validating ODCS compliance..."
	@if [ -d venv ]; then \
		. venv/bin/activate && PYTHONPATH=src python tests/integration/test_odcs_compliance.py; \
	else \
		PYTHONPATH=src python3 tests/integration/test_odcs_compliance.py; \
	fi

# Unit tests: Test internal functions (config loading, validation, etc.)
test-unit:
	@PYTHONPATH=src pytest tests/test_*.py tests/secrets/ -v --ignore=tests/integration

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
# REQUIRES: Infrastructure services (Postgres, MySQL, MinIO, Nessie) - automatically set up and torn down
# Note: Infrastructure services are dependencies for testing, NOT the dativo-ingest service
# The dativo-ingest CLI runs locally and connects to these services
# Docker configuration is checked before tests run
# Infrastructure is automatically stopped after tests complete
# Uses run_all_smoke_tests.sh which runs both original and custom plugin smoke tests
# Users can also run: dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets
test-smoke:
	@echo "🧪 Running smoke tests..."
	@bash tests/run_all_smoke_tests.sh

# Plugin tests: Test plugin system (unit, integration, Rust)
test-plugin:
	@echo "🔌 Running plugin tests..."
	@bash tests/run_all_plugin_tests.sh

# Validate GitHub Actions workflows
test-workflows:
	@echo "🔍 Validating GitHub Actions workflows..."
	@if command -v actionlint >/dev/null 2>&1; then \
		if [ -d .github/workflows ]; then \
			actionlint .github/workflows/*.yml 2>&1 | grep -v "too old to run" || true; \
			if actionlint .github/workflows/*.yml 2>&1 | grep -qE "(error|hashFiles.*failed)"; then \
				echo "❌ Workflow validation failed"; \
				actionlint .github/workflows/*.yml 2>&1 | grep -E "(error|hashFiles.*failed)" || true; \
				exit 1; \
			else \
				echo "✅ All workflows validated successfully"; \
			fi; \
		else \
			echo "⚠️  No .github/workflows directory found"; \
		fi; \
	else \
		echo "⚠️  actionlint not found. Skipping workflow validation."; \
		echo "   Install with: brew install actionlint"; \
	fi

# Run all tests
test: test-unit test-integration test-smoke test-workflows

# Format code with black and isort
format:
	@echo "🎨 Formatting code with black and isort..."
	@if command -v black >/dev/null 2>&1; then \
		black src/ tests/; \
	else \
		echo "⚠️  black not found. Install with: pip install black"; \
	fi
	@if command -v isort >/dev/null 2>&1; then \
		isort src/ tests/; \
	else \
		echo "⚠️  isort not found. Install with: pip install isort"; \
	fi
	@echo "✅ Code formatted"

# Check code formatting (for CI)
format-check:
	@echo "🔍 Checking code formatting..."
	@if command -v black >/dev/null 2>&1; then \
		black --check src/ tests/ || (echo "❌ Code formatting issues found. Run 'make format' to fix." && exit 1); \
	else \
		echo "⚠️  black not found. Install with: pip install black"; \
		exit 1; \
	fi
	@if command -v isort >/dev/null 2>&1; then \
		isort --check-only src/ tests/ || (echo "❌ Import sorting issues found. Run 'make format' to fix." && exit 1); \
	else \
		echo "⚠️  isort not found. Install with: pip install isort"; \
		exit 1; \
	fi
	@echo "✅ Code formatting is correct"

# Lint code (format check + flake8)
lint: format-check
	@echo "🔍 Linting code with flake8..."
	@if command -v flake8 >/dev/null 2>&1; then \
		flake8 src/ tests/ --count --select=E9,F63,F7,F82 --show-source --statistics || exit 1; \
	else \
		echo "⚠️  flake8 not found. Install with: pip install flake8"; \
		exit 1; \
	fi
	@echo "✅ Linting passed"

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

# Build Docker images for plugin sandboxes
build-plugin-images:
	@echo "🐳 Building plugin sandbox Docker images..."
	@if command -v docker >/dev/null 2>&1; then \
		echo "Building Python plugin runner image..."; \
		docker build -t dativo/python-plugin-runner:latest -f docker/python-plugin-runner/Dockerfile .; \
		echo "Building Rust plugin runner image..."; \
		docker build -t dativo/rust-plugin-runner:latest -f docker/rust-plugin-runner/Dockerfile docker/rust-plugin-runner/; \
		echo "✅ Plugin images built successfully"; \
	else \
		echo "❌ Docker not found. Please install Docker to build plugin images."; \
		exit 1; \
	fi


