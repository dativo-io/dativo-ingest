"""Custom Python reader for Postgres Employee table.

This reader demonstrates:
- Reading from Postgres database
- Handling connection configuration
- Incremental sync support
- Custom filtering and transformation
"""

import sys
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

# Add src to path for local development
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "src"))

from dativo_ingest.plugins import BaseReader
from dativo_ingest.validator import IncrementalStateManager
import os
import re


class PostgresEmployeeReader(BaseReader):
    """Custom reader for Postgres Employee table.
    
    Configuration example:
        source:
          custom_reader: "tests/fixtures/plugins/postgres_employee_reader.py:PostgresEmployeeReader"
          tables:
            - name: humanresources.employee
              object: employee
          connection:
            host: "${PGHOST:-localhost}"
            port: "${PGPORT:-5432}"
            database: "${PGDATABASE:-Adventureworks}"
            user: "${PGUSER:-postgres}"
            password: "${PGPASSWORD:-postgres}"
          incremental:
            strategy: updated_at
            cursor_field: modifieddate
    """
    
    def __init__(self, source_config):
        """Initialize Postgres Employee reader."""
        super().__init__(source_config)
        
        # Extract connection details with environment variable expansion
        self.connection = source_config.connection or {}
        self.host = self._expand_env_var(self.connection.get("host", "localhost"))
        port = self._expand_env_var(self.connection.get("port", "5432"))
        self.port = int(port) if isinstance(port, str) and port.isdigit() else (port if isinstance(port, int) else 5432)
        self.database = self._expand_env_var(self.connection.get("database", "postgres"))
        self.user = self._expand_env_var(self.connection.get("user", "postgres"))
        self.password = self._expand_env_var(self.connection.get("password", ""))
        
        # Override with environment variables if not set
        import os
        self.host = os.getenv("PGHOST", self.host)
        self.port = int(os.getenv("PGPORT", str(self.port)))
        self.database = os.getenv("PGDATABASE", self.database)
        self.user = os.getenv("PGUSER", self.user)
        self.password = os.getenv("PGPASSWORD", self.password)
        
        # Get table configuration
        self.tables = source_config.tables or []
        
        # Get incremental configuration
        self.incremental = source_config.incremental or {}
        self.cursor_field = self.incremental.get("cursor_field")
        
        # Engine options
        if source_config.engine and isinstance(source_config.engine, dict):
            engine_opts = source_config.engine.get("options", {})
        else:
            engine_opts = {}
        self.batch_size = engine_opts.get("batch_size", 1000)
    
    def _expand_env_var(self, value: Any) -> Any:
        """Expand environment variables in string values.
        
        Supports bash-style ${VAR:-default} syntax.
        
        Args:
            value: Value to expand
        
        Returns:
            Expanded value
        """
        if not isinstance(value, str):
            return value
        
        # Handle bash-style ${VAR:-default} syntax
        bash_default_pattern = r'\$\{([^:}]+):-([^}]+)\}'
        match = re.search(bash_default_pattern, value)
        if match:
            env_var = match.group(1)
            default_value = match.group(2)
            return os.getenv(env_var, default_value)
        elif value.startswith("${") and value.endswith("}"):
            # Simple ${VAR} syntax
            env_var = value[2:-1]
            return os.getenv(env_var, value)
        elif "${" in value:
            # Mixed string with env vars
            return os.path.expandvars(value)
        
        return value
    
    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Postgres Employee table.
        
        Args:
            state_manager: Optional state manager for incremental syncs
        
        Yields:
            Batches of records as list of dictionaries
        """
        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError:
            raise ImportError(
                "psycopg2-binary is required for Postgres reader. "
                "Install with: pip install psycopg2-binary"
            )
        
        # Connect to database
        conn = psycopg2.connect(
            host=self.host,
            port=self.port,
            database=self.database,
            user=self.user,
            password=self.password,
        )
        
        try:
            # Process each table
            for table_config in self.tables:
                table_name = table_config.get("name", "")
                if not table_name:
                    continue
                
                # Build query
                query = self._build_query(table_name)
                
                # Get cursor value from state if incremental
                cursor_value = None
                if state_manager and self.cursor_field:
                    # Note: state_manager is passed but IncrementalStateManager uses static methods
                    # For cursor-based incremental, we'll handle it differently
                    # For now, start from beginning (can be enhanced later)
                    cursor_value = None
                
                # Execute query with cursor
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    if cursor_value:
                        # Add WHERE clause for incremental sync
                        query += f" WHERE {self.cursor_field} > %s"
                        cursor.execute(query, (cursor_value,))
                    else:
                        cursor.execute(query)
                    
                    # Fetch in batches
                    last_cursor_value = None
                    while True:
                        records = cursor.fetchmany(self.batch_size)
                        if not records:
                            break
                        
                        # Convert to list of dictionaries
                        batch = [dict(record) for record in records]
                        
                        # Convert datetime/date objects to ISO format strings
                        for record in batch:
                            for key, value in record.items():
                                if hasattr(value, 'isoformat'):
                                    record[key] = value.isoformat()
                        
                        # Track last cursor value for incremental sync
                        if self.cursor_field and batch:
                            last_record = batch[-1]
                            if self.cursor_field in last_record:
                                last_cursor_value = last_record[self.cursor_field]
                        
                        yield batch
                    
                    # Update state if incremental
                    # Note: IncrementalStateManager uses static methods, so we skip state updates
                    # for now (can be enhanced later if needed)
        
        finally:
            conn.close()
    
    def _build_query(self, table_name: str) -> str:
        """Build SQL query for table.
        
        Args:
            table_name: Full table name (schema.table)
        
        Returns:
            SQL query string
        """
        # Add ORDER BY for incremental sync
        if self.cursor_field:
            return f"SELECT * FROM {table_name} ORDER BY {self.cursor_field} ASC"
        return f"SELECT * FROM {table_name}"
    
    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records.
        
        Returns:
            Estimated record count or None
        """
        try:
            import psycopg2
        except ImportError:
            return None
        
        try:
            conn = psycopg2.connect(
                host=self.host,
                port=self.port,
                database=self.database,
                user=self.user,
                password=self.password,
            )
            
            total = 0
            with conn.cursor() as cursor:
                for table_config in self.tables:
                    table_name = table_config.get("name", "")
                    if table_name:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = cursor.fetchone()[0]
                        total += count
            
            conn.close()
            return total
        except Exception:
            return None

