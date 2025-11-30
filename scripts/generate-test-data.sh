#!/bin/bash
# Generate test data for dativo-ingest testing

set -e

echo "🎲 Generating test data for dativo-ingest..."

# Create data directory
mkdir -p data/test_data

# 1. Generate sample employees CSV
echo "📝 Generating employees.csv..."
cat > data/test_data/employees.csv << 'EOF'
id,name,email,department,salary,hire_date
1,John Doe,john.doe@example.com,Engineering,120000,2023-01-15
2,Jane Smith,jane.smith@example.com,Marketing,95000,2023-02-20
3,Bob Johnson,bob.johnson@example.com,Sales,85000,2023-03-10
4,Alice Williams,alice.williams@example.com,Engineering,115000,2023-04-05
5,Charlie Brown,charlie.brown@example.com,Operations,78000,2023-05-12
EOF

# 2. Generate sample orders CSV with timestamps for incremental testing
echo "📝 Generating orders.csv..."

# Detect OS for date command compatibility
if date --version >/dev/null 2>&1; then
    # GNU date (Linux)
    YESTERDAY=$(date -u -d '1 day ago' +%Y-%m-%dT%H:%M:%SZ)
    TODAY=$(date -u +%Y-%m-%dT%H:%M:%SZ)
else
    # BSD date (macOS)
    YESTERDAY=$(date -u -v-1d +%Y-%m-%dT%H:%M:%SZ)
    TODAY=$(date -u +%Y-%m-%dT%H:%M:%SZ)
fi

cat > data/test_data/orders.csv << EOF
order_id,customer_id,order_date,amount,updated_at,status
1001,501,2025-01-01,150.50,${YESTERDAY},completed
1002,502,2025-01-02,275.00,${YESTERDAY},completed
1003,503,2025-01-03,89.99,${YESTERDAY},pending
1004,504,2025-01-04,199.99,${TODAY},completed
1005,505,2025-01-05,325.50,${TODAY},pending
EOF

# 3. Generate sample products CSV
echo "📝 Generating products.csv..."
cat > data/test_data/products.csv << 'EOF'
product_id,product_name,price,category,in_stock,description
1,Widget A,29.99,Electronics,true,High-quality widget
2,Widget B,49.99,Electronics,true,Premium widget with features
3,Widget C,19.99,Home,false,Basic home widget
4,Widget D,39.99,Home,true,Deluxe home widget
5,Widget E,59.99,Electronics,true,Professional widget
EOF

# 4. Generate sample sales data for partitioning tests
echo "📝 Generating sales.csv..."
cat > data/test_data/sales.csv << 'EOF'
sale_id,product_id,customer_id,sale_date,region,amount,quantity
5001,1,501,2025-01-15,US-West,89.97,3
5002,2,502,2025-01-16,US-East,49.99,1
5003,3,503,2025-01-17,EU-North,39.98,2
5004,4,504,2025-01-18,US-West,119.97,3
5005,5,505,2025-01-19,EU-West,59.99,1
5006,1,506,2025-01-20,US-East,29.99,1
EOF

# 5. Generate large CSV for performance testing
echo "📝 Generating large_dataset.csv (100K rows)..."
{
  echo "id,name,email,created_at,value,category"
  for i in $(seq 1 100000); do
    echo "$i,User_$i,user$i@example.com,2025-01-$((i % 28 + 1))T10:00:00Z,$((RANDOM % 1000)).$((RANDOM % 100)),Category_$((i % 10))"
  done
} > data/test_data/large_dataset.csv

# 6. Generate malformed CSV for validation testing
echo "📝 Generating malformed_data.csv..."
cat > data/test_data/malformed_data.csv << 'EOF'
id,name,email,age,salary
1,John Doe,john@example.com,30,50000
2,Jane Smith,invalid_email,abc,60000
3,,missing@example.com,25,
4,Bob Johnson,bob@example.com,35,invalid_salary
EOF

# 7. Generate JSON file for custom plugin testing
echo "📝 Generating sample_api_response.json..."
cat > data/test_data/sample_api_response.json << 'EOF'
{
  "records": [
    {"id": 1, "name": "Product A", "price": 29.99, "available": true},
    {"id": 2, "name": "Product B", "price": 49.99, "available": true},
    {"id": 3, "name": "Product C", "price": 19.99, "available": false}
  ],
  "page": 1,
  "total": 3
}
EOF

# 8. Generate Markdown-KV sample
echo "📝 Generating sample_markdown_kv.md..."
cat > data/test_data/sample_markdown_kv.md << 'EOF'
id: 1
name: John Doe
email: john@example.com
department: Engineering
salary: 120000
---
id: 2
name: Jane Smith
email: jane@example.com
department: Marketing
salary: 95000
---
id: 3
name: Bob Johnson
email: bob@example.com
department: Sales
salary: 85000
EOF

# 9. Set up PostgreSQL test data
if command -v docker &> /dev/null; then
    echo "📝 Loading PostgreSQL test data..."
    
    # Find PostgreSQL container by name (more reliable than ID)
    POSTGRES_CONTAINER=$(docker ps --filter "name=postgres" --format "{{.Names}}" 2>/dev/null | head -1)
    
    if [ -n "$POSTGRES_CONTAINER" ]; then
        echo "   Using PostgreSQL container: $POSTGRES_CONTAINER"
        docker exec -i "$POSTGRES_CONTAINER" psql -U postgres << 'EOF' 2>/dev/null || echo "⚠️  PostgreSQL not ready, skipping DB setup"
-- Create test table
CREATE TABLE IF NOT EXISTS test_employees (
  emp_id SERIAL PRIMARY KEY,
  first_name VARCHAR(50),
  last_name VARCHAR(50),
  email VARCHAR(100),
  hire_date DATE,
  salary DECIMAL(10,2),
  department VARCHAR(50),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert test data
INSERT INTO test_employees (first_name, last_name, email, hire_date, salary, department) VALUES
('Alice', 'Johnson', 'alice@example.com', '2023-01-15', 95000.00, 'Engineering'),
('Bob', 'Smith', 'bob@example.com', '2023-02-20', 87000.00, 'Marketing'),
('Carol', 'Williams', 'carol@example.com', '2023-03-10', 92000.00, 'Engineering'),
('David', 'Brown', 'david@example.com', '2023-04-05', 78000.00, 'Sales'),
('Eve', 'Davis', 'eve@example.com', '2023-05-01', 89000.00, 'Operations')
ON CONFLICT DO NOTHING;

-- Create orders table for incremental testing
CREATE TABLE IF NOT EXISTS test_orders (
  order_id SERIAL PRIMARY KEY,
  customer_id INTEGER,
  order_date DATE,
  amount DECIMAL(10,2),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO test_orders (customer_id, order_date, amount) VALUES
(501, '2025-01-01', 150.50),
(502, '2025-01-02', 275.00),
(503, '2025-01-03', 89.99)
ON CONFLICT DO NOTHING;
EOF
        
        # Verify data was loaded
        if docker exec -i "$POSTGRES_CONTAINER" psql -U postgres -c "SELECT COUNT(*) FROM test_employees;" 2>/dev/null | grep -q "5"; then
            echo "   ✓ PostgreSQL test data loaded successfully"
        fi
    else
        echo "⚠️  PostgreSQL container not found, skipping DB setup"
        echo "   Run: docker-compose -f docker-compose.dev.yml up -d"
    fi
fi

# 10. Summary
echo ""
echo "✅ Test data generation complete!"
echo ""
echo "📁 Generated files:"
echo "  - data/test_data/employees.csv (5 rows)"
echo "  - data/test_data/orders.csv (5 rows with timestamps)"
echo "  - data/test_data/products.csv (5 rows)"
echo "  - data/test_data/sales.csv (6 rows)"
echo "  - data/test_data/large_dataset.csv (100K rows)"
echo "  - data/test_data/malformed_data.csv (validation testing)"
echo "  - data/test_data/sample_api_response.json (custom plugin testing)"
echo "  - data/test_data/sample_markdown_kv.md (Markdown-KV format)"
echo ""
if [ -n "$POSTGRES_CONTAINER" ]; then
    echo "  - PostgreSQL: test_employees table (5 rows)"
    echo "  - PostgreSQL: test_orders table (3 rows)"
fi
echo ""
echo "🚀 You can now run test cases from TESTING_PLAYBOOK.md"
echo ""
echo "Quick test:"
echo "  dativo run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted"
