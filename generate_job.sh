#!/bin/bash
# Convenience wrapper for the Dativo job/asset generator

set -e

# Change to workspace directory
cd "$(dirname "$0")"

# Run the generator
python3 -m src.dativo_ingest.cli generate "$@"
