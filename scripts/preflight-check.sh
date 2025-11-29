#!/bin/bash
# Pre-flight check for dativo-ingest testing environment

set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ISSUES=0

echo ""
echo -e "${BOLD}🔍 Dativo-Ingest Pre-flight Check${NC}"
echo ""
echo "This script verifies your environment is ready for testing."
echo ""

# Function to check command exists
check_command() {
    if command -v $1 &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} $1 is installed"
        return 0
    else
        echo -e "  ${RED}✗${NC} $1 is NOT installed"
        ISSUES=$((ISSUES+1))
        return 1
    fi
}

# Function to check service
check_service() {
    local service=$1
    local port=$2
    local url=$3
    
    if curl -s -o /dev/null -w "%{http_code}" --max-time 2 "$url" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} $service is running on port $port"
        return 0
    else
        echo -e "  ${RED}✗${NC} $service is NOT accessible on port $port"
        echo -e "     URL: $url"
        ISSUES=$((ISSUES+1))
        return 1
    fi
}

# Check Python and version
echo -e "${BOLD}1. Python Environment${NC}"
if check_command python3; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
    MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
    
    if [ "$MAJOR" -ge 3 ] && [ "$MINOR" -ge 10 ]; then
        echo -e "     Version: ${GREEN}$PYTHON_VERSION (OK)${NC}"
    else
        echo -e "     Version: ${RED}$PYTHON_VERSION (Need 3.10+)${NC}"
        echo -e "     ${YELLOW}Fix: Upgrade Python to 3.10 or higher${NC}"
        echo -e "     ${YELLOW}• Using Conda: conda create -n dativo python=3.10 && conda activate dativo${NC}"
        echo -e "     ${YELLOW}• Using Homebrew: brew install python@3.10${NC}"
        echo -e "     ${YELLOW}• Using pyenv: pyenv install 3.10.13 && pyenv local 3.10.13${NC}"
        ISSUES=$((ISSUES+1))
    fi
    
    # Check for alternative Python versions
    for version in python3.10 python3.11 python3.12; do
        if command -v $version &> /dev/null; then
            ALT_VERSION=$($version --version | cut -d' ' -f2)
            echo -e "  ${GREEN}✓${NC} $version is available (v$ALT_VERSION)"
            echo -e "     Use: $version -m venv venv && source venv/bin/activate"
            break
        fi
    done
fi

# Check pip
check_command pip3

# Check if dativo is installed
if python3 -c "import dativo_ingest" 2>/dev/null; then
    echo -e "  ${GREEN}✓${NC} dativo-ingest package installed"
    if command -v dativo &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} dativo CLI available"
    else
        echo -e "  ${YELLOW}⚠${NC}  dativo CLI not in PATH (use 'python -m dativo_ingest.cli')"
    fi
else
    echo -e "  ${RED}✗${NC} dativo-ingest package NOT installed"
    echo -e "     Run: pip install -e ."
    ISSUES=$((ISSUES+1))
fi

echo ""

# Check Docker
echo -e "${BOLD}2. Docker Environment${NC}"
if check_command docker; then
    if docker ps &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} Docker daemon is running"
        
        # Check for running containers
        NESSIE_RUNNING=$(docker ps --filter "name=nessie" --format "{{.Names}}" | wc -l)
        MINIO_RUNNING=$(docker ps --filter "name=minio" --format "{{.Names}}" | wc -l)
        POSTGRES_RUNNING=$(docker ps --filter "name=postgres" --format "{{.Names}}" | wc -l)
        
        if [ "$NESSIE_RUNNING" -gt 0 ]; then
            echo -e "  ${GREEN}✓${NC} Nessie container is running"
        else
            echo -e "  ${RED}✗${NC} Nessie container is NOT running"
            ISSUES=$((ISSUES+1))
        fi
        
        if [ "$MINIO_RUNNING" -gt 0 ]; then
            echo -e "  ${GREEN}✓${NC} MinIO container is running"
        else
            echo -e "  ${RED}✗${NC} MinIO container is NOT running"
            ISSUES=$((ISSUES+1))
        fi
        
        if [ "$POSTGRES_RUNNING" -gt 0 ]; then
            echo -e "  ${GREEN}✓${NC} PostgreSQL container is running"
        else
            echo -e "  ${YELLOW}⚠${NC}  PostgreSQL container is NOT running (optional)"
        fi
    else
        echo -e "  ${RED}✗${NC} Docker daemon is NOT running"
        ISSUES=$((ISSUES+1))
    fi
fi

check_command docker-compose || check_command "docker compose"

echo ""

# Check Services
echo -e "${BOLD}3. Infrastructure Services${NC}"
check_service "Nessie" "19120" "http://localhost:19120/api/v1/config"
check_service "MinIO API" "9000" "http://localhost:9000/minio/health/live"
check_service "MinIO Console" "9001" "http://localhost:9001"

if curl -s -o /dev/null -w "%{http_code}" --max-time 2 "http://localhost:5432" > /dev/null 2>&1 || \
   docker ps --filter "name=postgres" --format "{{.Names}}" | grep -q postgres; then
    echo -e "  ${GREEN}✓${NC} PostgreSQL is running on port 5432"
else
    echo -e "  ${YELLOW}⚠${NC}  PostgreSQL is NOT running (optional for some tests)"
fi

echo ""

# Check Environment Variables
echo -e "${BOLD}4. Environment Variables${NC}"
check_env() {
    if [ -n "${!1}" ]; then
        echo -e "  ${GREEN}✓${NC} $1 is set"
        return 0
    else
        echo -e "  ${YELLOW}⚠${NC}  $1 is NOT set"
        return 1
    fi
}

check_env "NESSIE_URI" || echo "     Suggested: export NESSIE_URI=http://localhost:19120/api/v1"
check_env "S3_ENDPOINT" || echo "     Suggested: export S3_ENDPOINT=http://localhost:9000"
check_env "AWS_ACCESS_KEY_ID" || echo "     Suggested: export AWS_ACCESS_KEY_ID=minioadmin"
check_env "AWS_SECRET_ACCESS_KEY" || echo "     Suggested: export AWS_SECRET_ACCESS_KEY=minioadmin"
check_env "AWS_REGION" || echo "     Suggested: export AWS_REGION=us-east-1"
check_env "S3_BUCKET" || echo "     Suggested: export S3_BUCKET=test-bucket"

if [ -f ".env" ]; then
    echo -e "  ${GREEN}✓${NC} .env file exists"
    echo -e "     Run: ${YELLOW}source .env${NC}"
else
    echo -e "  ${YELLOW}⚠${NC}  .env file does NOT exist"
fi

echo ""

# Check File Structure
echo -e "${BOLD}5. Project Structure${NC}"
check_dir() {
    if [ -d "$1" ]; then
        echo -e "  ${GREEN}✓${NC} $1/ exists"
        return 0
    else
        echo -e "  ${YELLOW}⚠${NC}  $1/ does NOT exist"
        return 1
    fi
}

check_dir "connectors"
check_dir "assets"
check_dir "jobs"
check_dir "schemas"

if check_dir "secrets"; then
    # Count tenant secret directories
    TENANT_COUNT=$(find secrets -mindepth 1 -maxdepth 1 -type d 2>/dev/null | wc -l)
    if [ "$TENANT_COUNT" -gt 0 ]; then
        echo -e "     Found $TENANT_COUNT tenant secret directories"
    else
        echo -e "     ${YELLOW}No tenant directories found${NC}"
    fi
fi

check_dir ".local/state" || mkdir -p .local/state

echo ""

# Check MinIO Bucket
echo -e "${BOLD}6. MinIO Configuration${NC}"
if command -v mc &> /dev/null; then
    echo -e "  ${GREEN}✓${NC} MinIO client (mc) is installed"
    
    # Check if alias is configured
    if mc alias list local &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} MinIO alias 'local' is configured"
        
        # Check if bucket exists
        if mc ls local/test-bucket &> /dev/null; then
            echo -e "  ${GREEN}✓${NC} Bucket 'test-bucket' exists"
            
            # Check file count
            FILE_COUNT=$(mc ls local/test-bucket --recursive 2>/dev/null | wc -l)
            echo -e "     Contains $FILE_COUNT files"
        else
            echo -e "  ${RED}✗${NC} Bucket 'test-bucket' does NOT exist"
            echo -e "     Run: mc mb local/test-bucket"
            ISSUES=$((ISSUES+1))
        fi
    else
        echo -e "  ${YELLOW}⚠${NC}  MinIO alias 'local' NOT configured"
        echo -e "     Run: mc alias set local http://localhost:9000 minioadmin minioadmin"
    fi
else
    echo -e "  ${YELLOW}⚠${NC}  MinIO client (mc) is NOT installed (optional)"
    echo -e "     Install: https://min.io/docs/minio/linux/reference/minio-mc.html"
fi

echo ""

# Check Python Dependencies
echo -e "${BOLD}7. Python Dependencies${NC}"
check_python_package() {
    if python3 -c "import $1" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "  ${RED}✗${NC} $1 is NOT installed"
        ISSUES=$((ISSUES+1))
        return 1
    fi
}

check_python_package "pydantic"
check_python_package "yaml"
check_python_package "pandas"
check_python_package "pyarrow"
check_python_package "pyiceberg"
check_python_package "boto3"
check_python_package "requests"

echo ""

# Check Test Data
echo -e "${BOLD}8. Test Data${NC}"
if [ -f "tests/fixtures/jobs/csv_employee_to_iceberg.yaml" ]; then
    echo -e "  ${GREEN}✓${NC} Test fixture jobs found"
else
    echo -e "  ${YELLOW}⚠${NC}  Test fixture jobs NOT found"
fi

if [ -d "tests/fixtures/seeds" ]; then
    SEED_COUNT=$(find tests/fixtures/seeds -name "*.csv" 2>/dev/null | wc -l)
    echo -e "  ${GREEN}✓${NC} Test seed data found ($SEED_COUNT CSV files)"
else
    echo -e "  ${YELLOW}⚠${NC}  Test seed data NOT found"
fi

if [ -d "data/test_data" ]; then
    TEST_DATA_COUNT=$(find data/test_data -type f 2>/dev/null | wc -l)
    echo -e "  ${GREEN}✓${NC} Generated test data found ($TEST_DATA_COUNT files)"
else
    echo -e "  ${YELLOW}⚠${NC}  Generated test data NOT found"
    echo -e "     Run: ./scripts/generate-test-data.sh"
fi

echo ""

# Summary
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
if [ $ISSUES -eq 0 ]; then
    echo -e "${GREEN}${BOLD}✓ ALL CHECKS PASSED!${NC}"
    echo ""
    echo "Your environment is ready for testing."
    echo ""
    echo "Next steps:"
    echo "  1. Source environment variables: ${YELLOW}source .env${NC}"
    echo "  2. Generate test data: ${YELLOW}./scripts/generate-test-data.sh${NC}"
    echo "  3. Run smoke test: ${YELLOW}dativo run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted${NC}"
    echo "  4. Follow test cases: ${YELLOW}TESTING_PLAYBOOK.md${NC}"
    echo ""
    exit 0
else
    echo -e "${RED}${BOLD}✗ FOUND $ISSUES ISSUE(S)${NC}"
    echo ""
    echo "Please fix the issues above before testing."
    echo ""
    echo "Common fixes:"
    echo ""
    echo "  ${BOLD}Python Version Issue:${NC}"
    echo "  • Using Conda: ${YELLOW}conda create -n dativo python=3.10 && conda activate dativo${NC}"
    echo "  • Using venv: ${YELLOW}python3.10 -m venv venv && source venv/bin/activate${NC}"
    echo "  • Then install: ${YELLOW}pip install -e .${NC}"
    echo ""
    echo "  ${BOLD}Docker Services:${NC}"
    echo "  • Start all services: ${YELLOW}docker-compose -f docker-compose.dev.yml up -d${NC}"
    echo "  • Or run full setup: ${YELLOW}./scripts/setup-dev.sh${NC}"
    echo ""
    echo "  ${BOLD}Environment Variables:${NC}"
    echo "  • Source variables: ${YELLOW}source .env${NC}"
    echo ""
    echo "For detailed setup instructions, see: ${YELLOW}QUICKSTART.md${NC}"
    echo ""
    exit 1
fi
