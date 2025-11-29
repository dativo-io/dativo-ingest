#!/bin/bash
# Setup infrastructure services for smoke tests
# These are dependencies (Postgres, MySQL, MinIO, Nessie), NOT the dativo-ingest service
# The dativo-ingest CLI runs locally and connects to these services
# This script automatically detects if services are running and starts them if needed
#
# Usage: setup_smoke_test_infrastructure.sh [--no-teardown]
#   --no-teardown: Don't register cleanup trap (for manual cleanup)

set +e  # Don't exit on error - we want to continue even if some checks fail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Use docker compose v2 (modern approach)
DOCKER_COMPOSE="docker compose -f $PROJECT_ROOT/docker-compose.dev.yml"

# Check if Docker is available
if ! command -v docker >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker is required for smoke tests but not found.${NC}"
    echo ""
    echo "   Smoke tests require infrastructure services (Postgres, MySQL, MinIO, Nessie)"
    echo "   which are managed via Docker Compose."
    echo ""
    echo "   Please install Docker:"
    echo "   - macOS: Install Docker Desktop from https://www.docker.com/products/docker-desktop"
    echo "   - Linux: sudo apt-get install docker.io docker-compose"
    echo ""
    exit 1
fi

# Check if Docker daemon is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running. This is required for smoke tests.${NC}"
    echo ""
    echo "   Smoke tests require infrastructure services (Postgres, MySQL, MinIO, Nessie)"
    echo "   which need Docker to be running."
    echo ""
    echo "   Please start Docker:"
    echo "   - Docker Desktop: Open Docker Desktop application"
    echo "   - Linux: sudo systemctl start docker"
    echo "   - Or: docker info (to verify Docker is running)"
    echo ""
    exit 1
fi

# Check if services are already running
check_service() {
    local service_name=$1
    local port=$2
    
    # Check if container is running
    if docker ps --format '{{.Names}}' | grep -q "^${service_name}$"; then
        # Check container health status if available
        local health_status=$(docker inspect --format='{{.State.Health.Status}}' "$service_name" 2>/dev/null || echo "none")
        if [ "$health_status" = "healthy" ]; then
            return 0  # Container is healthy
        elif [ "$health_status" = "starting" ]; then
            return 2  # Container is starting (will be ready soon)
        fi
        
        # If no health check, check if container is running (not just created)
        local container_status=$(docker inspect --format='{{.State.Status}}' "$service_name" 2>/dev/null || echo "none")
        if [ "$container_status" = "running" ]; then
            # Try to check port accessibility (but don't fail if tools aren't available)
            if command -v nc >/dev/null 2>&1 && nc -z localhost "$port" 2>/dev/null; then
                return 0  # Service is running and accessible
            elif command -v curl >/dev/null 2>&1 && curl -sf "http://localhost:$port" >/dev/null 2>&1; then
                return 0  # Service is running and accessible
            else
                # Container is running but we can't verify port - assume it's OK
                return 0
            fi
        fi
    fi
    return 1  # Service is not running
}

# Check if ports are in use by other containers/services
check_port_conflict() {
    local port=$1
    local service_name=$2
    
    # Check if port is in use
    if lsof -i ":$port" >/dev/null 2>&1 || nc -z localhost "$port" 2>/dev/null; then
        # Check if it's our container
        if docker ps --format '{{.Names}}' | grep -q "^${service_name}$"; then
            return 0  # Port is used by our container (good)
        else
            # Port is used by something else
            local conflicting_container=$(docker ps --format '{{.Names}}' --filter "publish=$port" 2>/dev/null | head -1)
            if [ -n "$conflicting_container" ]; then
                echo -e "${YELLOW}⚠️  Port $port is in use by container: $conflicting_container${NC}"
            else
                echo -e "${YELLOW}⚠️  Port $port is already in use (not by our containers)${NC}"
            fi
            return 1  # Port conflict
        fi
    fi
    return 0  # Port is free
}

# Check all services
POSTGRES_RUNNING=0
MYSQL_RUNNING=0
MINIO_RUNNING=0
NESSIE_RUNNING=0
POSTGRES_STARTING=0
MYSQL_STARTING=0
MINIO_STARTING=0
NESSIE_STARTING=0

if check_service "dativo-postgres" 5432; then
    POSTGRES_RUNNING=1
else
    check_result=$?
    if [ $check_result -eq 2 ]; then
        POSTGRES_STARTING=1
    fi
fi

# MySQL port can be overridden via MYSQL_PORT env var (default 3307 to avoid conflict with openmetadata_mysql)
MYSQL_PORT=${MYSQL_PORT:-3307}
if check_service "dativo-mysql" "$MYSQL_PORT"; then
    MYSQL_RUNNING=1
else
    check_result=$?
    if [ $check_result -eq 2 ]; then
        MYSQL_STARTING=1
    fi
fi

if check_service "dativo-minio" 9000; then
    MINIO_RUNNING=1
else
    check_result=$?
    if [ $check_result -eq 2 ]; then
        MINIO_STARTING=1
    fi
fi

if check_service "dativo-nessie" 19120; then
    NESSIE_RUNNING=1
else
    check_result=$?
    if [ $check_result -eq 2 ]; then
        NESSIE_STARTING=1
    fi
fi

ALL_RUNNING=$((POSTGRES_RUNNING + MYSQL_RUNNING + MINIO_RUNNING + NESSIE_RUNNING))
ALL_STARTING=$((POSTGRES_STARTING + MYSQL_STARTING + MINIO_STARTING + NESSIE_STARTING))

if [ $ALL_RUNNING -eq 4 ]; then
    echo -e "${GREEN}✅ Infrastructure services already running${NC}"
    exit 0
fi

# Some services are running or starting, some are not
if [ $ALL_RUNNING -gt 0 ] || [ $ALL_STARTING -gt 0 ]; then
    if [ $ALL_STARTING -gt 0 ]; then
        echo -e "${BLUE}ℹ️  $ALL_RUNNING/4 services running, $ALL_STARTING/4 starting, starting remaining services...${NC}"
    else
        echo -e "${BLUE}ℹ️  $ALL_RUNNING/4 services already running, starting remaining services...${NC}"
    fi
    echo ""
fi

# Check for port conflicts before trying to start
PORT_CONFLICTS=0
CONFLICT_MESSAGES=()

if ! check_port_conflict 5432 "dativo-postgres" >/tmp/port_check_5432 2>&1; then
    PORT_CONFLICTS=$((PORT_CONFLICTS + 1))
    CONFLICT_MESSAGES+=("Postgres (5432)")
fi

if ! check_port_conflict "$MYSQL_PORT" "dativo-mysql" >/tmp/port_check_${MYSQL_PORT} 2>&1; then
    PORT_CONFLICTS=$((PORT_CONFLICTS + 1))
    CONFLICT_MESSAGES+=("MySQL ($MYSQL_PORT)")
fi

if ! check_port_conflict 9000 "dativo-minio" >/tmp/port_check_9000 2>&1; then
    PORT_CONFLICTS=$((PORT_CONFLICTS + 1))
    CONFLICT_MESSAGES+=("MinIO (9000)")
fi

if ! check_port_conflict 19120 "dativo-nessie" >/tmp/port_check_19120 2>&1; then
    PORT_CONFLICTS=$((PORT_CONFLICTS + 1))
    CONFLICT_MESSAGES+=("Nessie (19120)")
fi

# Show port conflict warnings but don't fail yet - try to start anyway
if [ $PORT_CONFLICTS -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Port conflicts detected for: ${CONFLICT_MESSAGES[*]}${NC}"
    echo "   Attempting to start services anyway (docker-compose will handle conflicts)..."
    echo ""
fi

# Some services are not running, start them
echo -e "${BLUE}🐳 Starting infrastructure services...${NC}"
echo "   Services: Postgres, MySQL, MinIO, Nessie (dependencies for testing)"
echo "   Note: dativo-ingest CLI runs locally and connects to these services"
echo ""

cd "$PROJECT_ROOT"

# Try to start services - docker-compose will handle already-running containers gracefully
# It will start only the containers that aren't running
STARTUP_OUTPUT=$($DOCKER_COMPOSE up -d 2>&1)
STARTUP_EXIT=$?

# Wait for services to be ready before checking
echo ""
echo "⏳ Waiting for services to be ready (this may take a moment)..."
sleep 3

# Check what's actually running after startup attempt and waiting
echo ""
echo "🔍 Verifying services..."
RUNNING_COUNT=0

if check_service "dativo-postgres" 5432; then
    echo -e "${GREEN}   ✅ Postgres is running${NC}"
    RUNNING_COUNT=$((RUNNING_COUNT + 1))
else
    check_result=$?
    if [ $check_result -eq 2 ]; then
        echo -e "${YELLOW}   ⚠️  Postgres is starting (waiting...)${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Postgres is not accessible${NC}"
    fi
fi

if check_service "dativo-mysql" "$MYSQL_PORT"; then
    echo -e "${GREEN}   ✅ MySQL is running${NC}"
    RUNNING_COUNT=$((RUNNING_COUNT + 1))
else
    check_result=$?
    if [ $check_result -eq 2 ]; then
        echo -e "${YELLOW}   ⚠️  MySQL is starting (waiting...)${NC}"
    else
        echo -e "${YELLOW}   ⚠️  MySQL is not accessible${NC}"
    fi
fi

if check_service "dativo-minio" 9000; then
    echo -e "${GREEN}   ✅ MinIO is running${NC}"
    RUNNING_COUNT=$((RUNNING_COUNT + 1))
else
    check_result=$?
    if [ $check_result -eq 2 ]; then
        echo -e "${YELLOW}   ⚠️  MinIO is starting (waiting...)${NC}"
    else
        echo -e "${YELLOW}   ⚠️  MinIO is not accessible${NC}"
    fi
fi

if check_service "dativo-nessie" 19120; then
    echo -e "${GREEN}   ✅ Nessie is running${NC}"
    RUNNING_COUNT=$((RUNNING_COUNT + 1))
else
    check_result=$?
    if [ $check_result -eq 2 ]; then
        echo -e "${YELLOW}   ⚠️  Nessie is starting (waiting...)${NC}"
    else
        echo -e "${YELLOW}   ⚠️  Nessie is not accessible${NC}"
    fi
fi

echo ""

# Wait a bit more for services that are starting
if [ $RUNNING_COUNT -lt 4 ]; then
    echo "⏳ Waiting additional time for services to become ready..."
    sleep 5
fi

# Re-check services after additional wait
FINAL_RUNNING_COUNT=0
check_service "dativo-postgres" 5432 && FINAL_RUNNING_COUNT=$((FINAL_RUNNING_COUNT + 1))
check_service "dativo-mysql" "$MYSQL_PORT" && FINAL_RUNNING_COUNT=$((FINAL_RUNNING_COUNT + 1))
check_service "dativo-minio" 9000 && FINAL_RUNNING_COUNT=$((FINAL_RUNNING_COUNT + 1))
check_service "dativo-nessie" 19120 && FINAL_RUNNING_COUNT=$((FINAL_RUNNING_COUNT + 1))

# Check if containers exist (even if we can't verify ports)
CONTAINER_COUNT=0
docker ps --format '{{.Names}}' | grep -q "^dativo-postgres$" && CONTAINER_COUNT=$((CONTAINER_COUNT + 1))
docker ps --format '{{.Names}}' | grep -q "^dativo-mysql$" && CONTAINER_COUNT=$((CONTAINER_COUNT + 1))
docker ps --format '{{.Names}}' | grep -q "^dativo-minio$" && CONTAINER_COUNT=$((CONTAINER_COUNT + 1))
docker ps --format '{{.Names}}' | grep -q "^dativo-nessie$" && CONTAINER_COUNT=$((CONTAINER_COUNT + 1))

# Evaluate final state - use container count if we can't verify ports
if [ $FINAL_RUNNING_COUNT -eq 4 ] || [ $CONTAINER_COUNT -eq 4 ]; then
    if [ $FINAL_RUNNING_COUNT -eq 4 ]; then
        echo -e "${GREEN}✅ All infrastructure services are running and accessible${NC}"
    else
        echo -e "${GREEN}✅ All infrastructure containers are running${NC}"
        echo -e "${YELLOW}   (Port accessibility checks may have failed, but containers are running)${NC}"
    fi
    # Show any warnings from startup but don't fail
    if [ $STARTUP_EXIT -ne 0 ]; then
        echo -e "${YELLOW}   (Some containers were already running - this is fine)${NC}"
    fi
elif [ $CONTAINER_COUNT -gt 0 ]; then
    echo -e "${YELLOW}⚠️  Only $CONTAINER_COUNT/4 containers are running${NC}"
    echo ""
    echo "   This may be due to:"
    echo "   - Port conflicts (ports already in use by other services)"
    echo "   - Container startup failures"
    echo ""
    echo "   To diagnose:"
    echo "   - Check port conflicts: lsof -i :5432 -i :${MYSQL_PORT} -i :9000 -i :19120"
    echo "   - Check Docker logs: docker-compose -f docker-compose.dev.yml logs"
    echo "   - Check running containers: docker ps"
    echo ""
    echo -e "${YELLOW}   Some tests may fail. Continuing anyway...${NC}"
else
    echo -e "${RED}❌ No infrastructure containers are running${NC}"
    echo ""
    echo "   Check Docker logs for errors:"
    echo "   docker-compose -f docker-compose.dev.yml logs"
    echo ""
    echo "   Common issues:"
    echo "   - Port conflicts: Stop other services using ports 5432, ${MYSQL_PORT}, 9000, 19120"
    echo "   - Docker daemon issues: Restart Docker"
    echo ""
    exit 1
fi

echo ""
echo "⏳ Waiting for services to be fully ready..."
sleep 2

# Wait for services with timeout
wait_for_service() {
    local name=$1
    local check_cmd=$2
    local max_wait=60
    local elapsed=0
    
    echo -n "   Waiting for $name... "
    while [ $elapsed -lt $max_wait ]; do
        if eval "$check_cmd" >/dev/null 2>&1; then
            echo -e "${GREEN}✅${NC}"
            return 0
        fi
        sleep 2
        elapsed=$((elapsed + 2))
    done
    echo -e "${YELLOW}⚠️  (timeout)${NC}"
    return 1
}

# Wait for each service (only if container exists)
if docker ps --format '{{.Names}}' | grep -q "^dativo-postgres$"; then
    if command -v pg_isready >/dev/null 2>&1; then
        wait_for_service "Postgres" "pg_isready -h localhost -p 5432 -U postgres" || true
    else
        echo -e "   Waiting for Postgres... ${GREEN}✅${NC} (container running, pg_isready not available)"
    fi
fi

if docker ps --format '{{.Names}}' | grep -q "^dativo-mysql$"; then
    if command -v mysqladmin >/dev/null 2>&1; then
        wait_for_service "MySQL" "mysqladmin ping -h 127.0.0.1 -P $MYSQL_PORT -u root -proot --silent" || true
    else
        echo -e "   Waiting for MySQL... ${GREEN}✅${NC} (container running, mysqladmin not available)"
    fi
fi

if docker ps --format '{{.Names}}' | grep -q "^dativo-minio$"; then
    if command -v curl >/dev/null 2>&1; then
        wait_for_service "MinIO" "curl -sf http://localhost:9000/minio/health/live" || true
    else
        echo -e "   Waiting for MinIO... ${GREEN}✅${NC} (container running, curl not available)"
    fi
fi

if docker ps --format '{{.Names}}' | grep -q "^dativo-nessie$"; then
    if command -v curl >/dev/null 2>&1; then
        wait_for_service "Nessie" "curl -sf http://localhost:19120/api/v1/config" || true
    else
        echo -e "   Waiting for Nessie... ${GREEN}✅${NC} (container running, curl not available)"
    fi
fi

echo ""
echo -e "${GREEN}✅ Infrastructure services started${NC}"
echo "   Postgres: localhost:5432 | MySQL: localhost:$MYSQL_PORT"
echo "   MinIO: http://localhost:9000 | Nessie: http://localhost:19120/api/v1"

# Register cleanup function if not disabled
if [[ "$*" != *"--no-teardown"* ]]; then
    # Create a cleanup function
    cleanup_infrastructure() {
        echo ""
        echo -e "${BLUE}🧹 Cleaning up infrastructure services...${NC}"
        cd "$PROJECT_ROOT"
        $DOCKER_COMPOSE down >/dev/null 2>&1
        echo -e "${GREEN}✅ Infrastructure services stopped${NC}"
    }
    
    # Register cleanup on script exit (if called from run_all_smoke_tests.sh)
    # The actual cleanup will be handled by run_all_smoke_tests.sh
    export INFRASTRUCTURE_STARTED=1
fi

exit 0

