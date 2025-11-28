# Multi-stage build for Rust plugin runner
FROM rust:1.75-slim as builder

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

# Create non-root user
RUN useradd -m -u 1000 plugin && \
    mkdir -p /app/plugins && \
    chown -R plugin:plugin /app

USER plugin

WORKDIR /app

ENTRYPOINT ["/usr/local/bin/rust-plugin-runner"]

