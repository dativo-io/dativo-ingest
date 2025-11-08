# Makefile for building Rust plugins

.PHONY: all build build-release test clean help install-rust

# Default target
all: build-release

# Build all plugins in debug mode
build:
	@echo "Building Rust plugins (debug mode)..."
	cargo build

# Build all plugins in release mode (optimized)
build-release:
	@echo "Building Rust plugins (release mode with optimizations)..."
	cargo build --release
	@echo ""
	@echo "✓ Build complete!"
	@echo "  CSV Reader: target/release/libcsv_reader_plugin.so"
	@echo "  Parquet Writer: target/release/libparquet_writer_plugin.so"

# Build with maximum optimization
build-optimized:
	@echo "Building with maximum optimization..."
	RUSTFLAGS="-C target-cpu=native" cargo build --release --config profile.release.lto=true

# Run tests for all plugins
test:
	@echo "Running tests..."
	cargo test

# Run tests with output
test-verbose:
	@echo "Running tests (verbose)..."
	cargo test -- --nocapture

# Run benchmarks (requires criterion)
bench:
	@echo "Running benchmarks..."
	cargo bench

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	cargo clean
	@echo "✓ Clean complete!"

# Check for Rust installation
check-rust:
	@command -v rustc >/dev/null 2>&1 || { echo "Error: Rust not installed. Run 'make install-rust' first."; exit 1; }
	@command -v cargo >/dev/null 2>&1 || { echo "Error: Cargo not installed. Run 'make install-rust' first."; exit 1; }
	@echo "✓ Rust toolchain found"
	@rustc --version
	@cargo --version

# Install Rust toolchain
install-rust:
	@echo "Installing Rust toolchain..."
	curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
	@echo ""
	@echo "✓ Rust installed!"
	@echo "  Run: source $$HOME/.cargo/env"
	@echo "  Then: make build-release"

# Format code
fmt:
	@echo "Formatting code..."
	cargo fmt --all

# Check code without building
check:
	@echo "Checking code..."
	cargo check --all-targets

# Run clippy linter
lint:
	@echo "Running clippy..."
	cargo clippy --all-targets -- -D warnings

# Show exported symbols (Linux)
symbols-reader:
	@echo "Exported symbols in CSV reader:"
	@nm -D target/release/libcsv_reader_plugin.so | grep -E "(create_reader|extract_batch|free_reader|free_string)"

symbols-writer:
	@echo "Exported symbols in Parquet writer:"
	@nm -D target/release/libparquet_writer_plugin.so | grep -E "(create_writer|write_batch|free_writer|free_string)"

# Help target
help:
	@echo "Rust Plugin Build System"
	@echo ""
	@echo "Targets:"
	@echo "  make build           - Build all plugins (debug mode)"
	@echo "  make build-release   - Build all plugins (release/optimized)"
	@echo "  make build-optimized - Build with maximum optimization"
	@echo "  make test            - Run all tests"
	@echo "  make test-verbose    - Run tests with output"
	@echo "  make bench           - Run benchmarks"
	@echo "  make clean           - Clean build artifacts"
	@echo "  make check-rust      - Check Rust installation"
	@echo "  make install-rust    - Install Rust toolchain"
	@echo "  make fmt             - Format code"
	@echo "  make check           - Check code without building"
	@echo "  make lint            - Run clippy linter"
	@echo "  make symbols-reader  - Show exported symbols (reader)"
	@echo "  make symbols-writer  - Show exported symbols (writer)"
	@echo "  make help            - Show this help"
	@echo ""
	@echo "Build outputs (release mode):"
	@echo "  target/release/libcsv_reader_plugin.so"
	@echo "  target/release/libparquet_writer_plugin.so"
	@echo ""
	@echo "Platform-specific:"
	@echo "  Linux:   .so files"
	@echo "  macOS:   .dylib files (can rename to .so)"
	@echo "  Windows: .dll files"
