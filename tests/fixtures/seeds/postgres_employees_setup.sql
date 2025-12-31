-- PostgreSQL employees table setup for testing playbook and integration tests
-- This seed file creates the employees table used in test cases 7, 8, and 9
-- 
-- IMPORTANT: This file is mounted in docker-compose.dev.yml and will run automatically
-- when the PostgreSQL container is FIRST created. For existing containers, use:
-- ./scripts/testing-playbook-setup-postgres-employees.sh
--
-- The table is created in the 'postgres' database (default database that always exists)

-- Create employees table matching the asset definition schema
CREATE TABLE IF NOT EXISTS employees (
    emp_id SERIAL PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    email VARCHAR(100),
    hire_date DATE,
    salary DECIMAL(10,2),
    department VARCHAR(50),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert test data (using ON CONFLICT to allow re-running)
INSERT INTO employees (first_name, last_name, email, hire_date, salary, department, updated_at)
VALUES
('Alice', 'Johnson', 'alice@example.com', '2023-01-15', 95000.00, 'Engineering', CURRENT_TIMESTAMP),
('Bob', 'Smith', 'bob@example.com', '2023-02-20', 87000.00, 'Marketing', CURRENT_TIMESTAMP),
('Carol', 'Williams', 'carol@example.com', '2023-03-10', 92000.00, 'Engineering', CURRENT_TIMESTAMP),
('David', 'Brown', 'david@example.com', '2023-04-05', 78000.00, 'Sales', CURRENT_TIMESTAMP),
('Eve', 'Davis', 'eve@example.com', '2023-05-01', 89000.00, 'Operations', CURRENT_TIMESTAMP)
ON CONFLICT (emp_id) DO NOTHING;

