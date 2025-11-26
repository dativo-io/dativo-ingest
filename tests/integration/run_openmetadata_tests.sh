#!/bin/bash
# Run OpenMetadata integration tests with Docker Compose setup

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMPOSE_FILE="${SCRIPT_DIR}/docker-compose-openmetadata.yml"

echo -e "${GREEN}Starting OpenMetadata integration tests...${NC}"

# Function to check if a service is healthy
check_service_health() {
    local service=$1
    local max_attempts=30
    local attempt=1
    
    echo -e "${YELLOW}Waiting for $service to be healthy...${NC}"
    
    while [ $attempt -le $max_attempts ]; do
        if docker-compose -f "$COMPOSE_FILE" ps | grep "$service" | grep -q "healthy"; then
            echo -e "${GREEN}$service is healthy!${NC}"
            return 0
        fi
        
        echo "Attempt $attempt/$max_attempts: $service not ready yet..."
        sleep 5
        attempt=$((attempt + 1))
    done
    
    echo -e "${RED}$service failed to become healthy${NC}"
    return 1
}

# Function to cleanup
cleanup() {
    echo -e "${YELLOW}Cleaning up...${NC}"
    cd "$SCRIPT_DIR"
    docker-compose -f "$COMPOSE_FILE" down
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Start services
echo -e "${GREEN}Starting OpenMetadata services...${NC}"
cd "$SCRIPT_DIR"
docker-compose -f "$COMPOSE_FILE" up -d

# Wait for PostgreSQL
check_service_health "postgresql" || exit 1

# Wait for Elasticsearch
check_service_health "elasticsearch" || exit 1

# Wait for OpenMetadata Server
check_service_health "openmetadata-server" || exit 1

# Verify OpenMetadata API is accessible
echo -e "${YELLOW}Verifying OpenMetadata API...${NC}"
max_retries=10
retry=0
while [ $retry -lt $max_retries ]; do
    if curl -s -f http://localhost:8585/api/v1/system/version > /dev/null; then
        echo -e "${GREEN}OpenMetadata API is accessible!${NC}"
        break
    fi
    echo "Waiting for OpenMetadata API... ($((retry + 1))/$max_retries)"
    sleep 5
    retry=$((retry + 1))
done

if [ $retry -eq $max_retries ]; then
    echo -e "${RED}OpenMetadata API not accessible${NC}"
    exit 1
fi

# Run tests
echo -e "${GREEN}Running OpenMetadata integration tests...${NC}"
cd "$(dirname "$SCRIPT_DIR")" # Go to workspace root
export RUN_OPENMETADATA_TESTS=1
export OPENMETADATA_HOST_PORT=http://localhost:8585/api

if pytest tests/integration/test_openmetadata_smoke.py -v; then
    echo -e "${GREEN}All OpenMetadata integration tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some OpenMetadata integration tests failed${NC}"
    exit 1
fi
