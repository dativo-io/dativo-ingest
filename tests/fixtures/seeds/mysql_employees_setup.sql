-- MySQL employees table setup for testing playbook and integration tests
-- This seed file creates the employees table matching the PostgreSQL schema
-- used in test cases 7, 8, and 9
-- 
-- IMPORTANT: This file creates a simple employees table that matches the
-- PostgreSQL schema for consistency between test environments.
--
-- The table is created in the 'employees' database

-- Create employees table matching the PostgreSQL schema
CREATE TABLE IF NOT EXISTS employees (
    emp_id INT AUTO_INCREMENT PRIMARY KEY,
    first_name VARCHAR(50),
    last_name VARCHAR(50),
    email VARCHAR(100),
    hire_date DATE,
    salary DECIMAL(10,2),
    department VARCHAR(50),
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- Insert test data (using INSERT IGNORE to allow re-running)
INSERT IGNORE INTO employees (emp_id, first_name, last_name, email, hire_date, salary, department, updated_at)
VALUES
(1, 'Alice', 'Johnson', 'alice@example.com', '2023-01-15', 95000.00, 'Engineering', CURRENT_TIMESTAMP),
(2, 'Bob', 'Smith', 'bob@example.com', '2023-02-20', 87000.00, 'Marketing', CURRENT_TIMESTAMP),
(3, 'Carol', 'Williams', 'carol@example.com', '2023-03-10', 92000.00, 'Engineering', CURRENT_TIMESTAMP),
(4, 'David', 'Brown', 'david@example.com', '2023-04-05', 78000.00, 'Sales', CURRENT_TIMESTAMP),
(5, 'Eve', 'Davis', 'eve@example.com', '2023-05-01', 89000.00, 'Operations', CURRENT_TIMESTAMP);

