# Test Data Seeds

This directory contains seed data files used to initialize test databases for both integration tests and the testing playbook.

## Unified Seed Approach

We use **unified seed data** across PostgreSQL and MySQL to ensure consistency between:
- Integration tests
- Testing playbook test cases
- Cross-database compatibility

## Seed Files

### PostgreSQL

- **`postgres_employees_setup.sql`**: Creates a simple `employees` table with schema:
  - `emp_id` (SERIAL PRIMARY KEY)
  - `first_name`, `last_name`, `email`
  - `hire_date`, `salary`, `department`
  - `updated_at` (TIMESTAMP)
  
  Used in:
  - Test cases 7, 8, and 9 in `TESTING_PLAYBOOK.md`
  - PostgreSQL integration tests
  - Setup script: `scripts/testing-playbook-setup-postgres-employees.sh`

### MySQL

- **`mysql_employees_setup.sql`**: Creates the same `employees` table schema (MySQL-compatible):
  - `emp_id` (AUTO_INCREMENT PRIMARY KEY)
  - `first_name`, `last_name`, `email`
  - `hire_date`, `salary`, `department`
  - `updated_at` (TIMESTAMP)
  
  Used in:
  - Testing playbook (when using MySQL)
  - Setup script: `scripts/testing-playbook-setup-mysql-employees.sh`
  
- **`test_db/`**: Full MySQL employees sample database (comprehensive testing)
  - Used by MySQL integration tests for more complex scenarios
  - Contains multiple tables: `employees`, `departments`, `salaries`, `titles`, etc.
  - This is the standard MySQL sample database

## Usage

### Automatic Setup (Docker Compose)

Both seed files are automatically loaded when containers are first created:

```bash
docker compose -f docker-compose.dev.yml up -d
```

- PostgreSQL: `postgres_employees_setup.sql` runs automatically
- MySQL: Both `test_db/` and `mysql_employees_setup.sql` run automatically

### Manual Setup

For existing containers or manual setup:

**PostgreSQL:**
```bash
./scripts/testing-playbook-setup-postgres-employees.sh
```

**MySQL:**
```bash
./scripts/testing-playbook-setup-mysql-employees.sh
```

## Schema Consistency

The `postgres_employees_setup.sql` and `mysql_employees_setup.sql` files create **identical schemas** (with database-specific syntax differences):

| Field | PostgreSQL | MySQL |
|-------|-----------|-------|
| Primary Key | `SERIAL` | `AUTO_INCREMENT` |
| Insert Conflict | `ON CONFLICT DO NOTHING` | `INSERT IGNORE` |
| Timestamp | `DEFAULT CURRENT_TIMESTAMP` | `DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP` |

Both create the same 5 test records:
- Alice Johnson (Engineering)
- Bob Smith (Marketing)
- Carol Williams (Engineering)
- David Brown (Sales)
- Eve Davis (Operations)

## Test Data

The unified seed provides consistent test data across databases:

```sql
-- All databases have the same 5 employees
emp_id | first_name | last_name | email              | hire_date  | salary  | department
-------|------------|-----------|--------------------|------------|---------|------------
1      | Alice      | Johnson   | alice@example.com | 2023-01-15 | 95000.00| Engineering
2      | Bob        | Smith     | bob@example.com   | 2023-02-20 | 87000.00| Marketing
3      | Carol      | Williams  | carol@example.com | 2023-03-10 | 92000.00| Engineering
4      | David      | Brown     | david@example.com | 2023-04-05 | 78000.00| Sales
5      | Eve        | Davis     | eve@example.com   | 2023-05-01 | 89000.00| Operations
```

## Other Seeds

- **`AdventureWorks-oltp-install-script/`**: Full AdventureWorks database for PostgreSQL (comprehensive testing)
- **`adventureworks/`**: AdventureWorks CSV data files
- **`test_db/`**: Full MySQL employees sample database (comprehensive testing)
- **`music_listening/`**: Sample music listening history data
- **`markdown_kv/`**: Sample Markdown-KV documents

## Best Practices

1. **Use unified seeds** for simple test cases (test cases 7, 8, 9)
2. **Use comprehensive seeds** (AdventureWorks, test_db) for complex integration tests
3. **Keep schemas consistent** when creating new seed files
4. **Document schema differences** between database-specific versions
5. **Use setup scripts** for manual setup to ensure consistency

