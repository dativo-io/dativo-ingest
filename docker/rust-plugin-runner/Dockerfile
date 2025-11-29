# Multi-stage build for Rust plugin runner
# Using rust:slim (latest stable) to support Cargo.lock v4 format
FROM rust:slim as builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy Cargo files
COPY Cargo.toml Cargo.lock* ./

# Copy source
COPY src ./src

# Build release binary
RUN cargo build --release

# Runtime stage
FROM debian:bookworm-slim

# Install runtime dependencies
RUN apt-get update && apt-get install -y \
    libc6 \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Copy runner binary from builder
COPY --from=builder /build/target/release/rust-plugin-runner /usr/local/bin/rust-plugin-runner

# Create non-root user and plugin directory
# Use /usr/local/plugins (FHS-compliant, matches Python sandbox)
RUN useradd -m -u 1000 plugin && \
    mkdir -p /usr/local/plugins && \
    chown -R plugin:plugin /usr/local/plugins

USER plugin

WORKDIR /usr/local/plugins

ENTRYPOINT ["/usr/local/bin/rust-plugin-runner"]

