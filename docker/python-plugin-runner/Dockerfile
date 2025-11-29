# Docker image for Python plugin sandbox execution
# This image includes common dependencies needed by plugins
FROM python:3.10-slim

# Install common dependencies that plugins may need
# These are required for dativo_ingest to import and work correctly
RUN pip install --no-cache-dir \
    jsonschema>=4.0.0 \
    pyyaml>=6.0 \
    pydantic>=2.0.0 \
    && rm -rf /root/.cache/pip

# Create non-root user for security
RUN useradd -m -u 1000 plugin && \
    mkdir -p /usr/local/plugins && \
    chown -R plugin:plugin /usr/local/plugins

# Set working directory
WORKDIR /usr/local/plugins

# Note: We don't set USER here because some Docker environments
# (e.g., colima) may not support user namespaces properly.
# The sandbox code can set the user if needed.

