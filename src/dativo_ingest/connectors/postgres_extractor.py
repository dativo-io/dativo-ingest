"""Native Postgres extractor using psycopg2."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ..config import SourceConfig
from ..validator import IncrementalStateManager


class PostgresExtractor:
    """Extracts data from PostgreSQL databases."""

    def __init__(self, source_config: SourceConfig):
        """Initialize Postgres extractor.

        Args:
            source_config: Source configuration with tables and connection details
        """
        self.source_config = source_config
        self.engine_options = self._get_engine_options()
        self.connection = self._build_connection()

    def _get_engine_options(self) -> Dict[str, Any]:
        """Get engine options from source config.

        Returns:
            Dictionary of engine options
        """
        if self.source_config.engine:
            native_opts = self.source_config.engine.get("options", {}).get("native", {})
            if native_opts:
                return native_opts

            meltano_opts = self.source_config.engine.get("options", {}).get(
                "meltano", {}
            )
            if meltano_opts:
                return meltano_opts

        # Default options
        return {
            "batch_size": 10000,
            "fetch_size": 10000,
        }

    def _build_connection(self) -> Dict[str, Any]:
        """Build connection parameters from source config.

        Returns:
            Dictionary of connection parameters
        """
        connection = {}

        # Get connection from source config (already has env vars expanded)
        if self.source_config.connection:
            connection.update(self.source_config.connection)

        # Also check credentials if available (for .env file loading)
        if self.source_config.credentials:
            # Credentials might contain connection details
            if isinstance(self.source_config.credentials, dict):
                # If credentials is a dict, it might have connection params
                for key in [
                    "host",
                    "port",
                    "database",
                    "user",
                    "password",
                    "PGHOST",
                    "PGPORT",
                    "PGDATABASE",
                    "PGUSER",
                    "PGPASSWORD",
                ]:
                    if key in self.source_config.credentials and key not in connection:
                        value = self.source_config.credentials[key]
                        # Map PG* env vars to connection keys
                        if key == "PGHOST":
                            connection.setdefault("host", value)
                        elif key == "PGPORT":
                            connection.setdefault(
                                "port", int(value) if isinstance(value, str) else value
                            )
                        elif key == "PGDATABASE":
                            connection.setdefault("database", value)
                        elif key == "PGUSER":
                            connection.setdefault("user", value)
                        elif key == "PGPASSWORD":
                            connection.setdefault("password", value)
                        else:
                            connection.setdefault(key, value)

        # Expand environment variables in connection values
        import re

        for key, value in connection.items():
            if isinstance(value, str):
                # Handle bash-style ${VAR:-default} syntax
                bash_default_pattern = r"\$\{([^:}]+):-([^}]+)\}"
                match = re.search(bash_default_pattern, value)
                if match:
                    env_var = match.group(1)
                    default_value = match.group(2)
                    connection[key] = os.getenv(env_var, default_value)
                elif value.startswith("${") and value.endswith("}"):
                    # Simple ${VAR} syntax
                    env_var = value[2:-1]
                    connection[key] = os.getenv(env_var, value)

        # Override with environment variables if not in config
        connection.setdefault("host", os.getenv("PGHOST", "localhost"))
        port = connection.get("port")
        if port is None:
            port = os.getenv("PGPORT", "5432")
        elif isinstance(port, str):
            # Try to expand if it's a string
            if port.startswith("${") and port.endswith("}"):
                env_var = port[2:-1]
                port = os.getenv(env_var, port)
            # Convert to int if it's a numeric string
            try:
                port = int(port)
            except ValueError:
                # If it's not numeric, try to get from env
                port = os.getenv("PGPORT", "5432")
        connection.setdefault("port", int(port) if isinstance(port, str) else port)
        connection.setdefault("database", os.getenv("PGDATABASE", "postgres"))
        connection.setdefault(
            "user", os.getenv("PGUSER", os.getenv("USER", "postgres"))
        )
        connection.setdefault("password", os.getenv("PGPASSWORD", ""))

        return connection

    def _get_cursor_field(self, table_config: Dict[str, Any]) -> Optional[str]:
        """Get cursor field for incremental sync.

        Args:
            table_config: Table configuration

        Returns:
            Cursor field name or None
        """
        # Check table-specific cursor field
        if "cursor_field" in table_config:
            return table_config["cursor_field"]

        # Check incremental config
        if self.source_config.incremental:
            return self.source_config.incremental.get("cursor_field")

        return None

    def _build_query(
        self,
        table_name: str,
        cursor_field: Optional[str] = None,
        cursor_value: Optional[Any] = None,
        lookback_days: int = 0,
    ) -> Tuple[str, List[Any]]:
        """Build SQL query for table extraction.

        Args:
            table_name: Fully qualified table name (schema.table)
            cursor_field: Optional cursor field for incremental sync
            cursor_value: Optional cursor value for incremental sync
            lookback_days: Number of days to look back for incremental sync

        Returns:
            Tuple of (SQL query string, parameter list)
        """
        # Escape table name properly (handle schema.table)
        if "." in table_name:
            schema, table = table_name.split(".", 1)
            quoted_table = f'"{schema}"."{table}"'
        else:
            quoted_table = f'"{table_name}"'

        # Base SELECT query
        query = f"SELECT * FROM {quoted_table}"
        params: List[Any] = []

        # Add WHERE clause for incremental sync
        if cursor_field:
            # Escape column name
            quoted_cursor = f'"{cursor_field}"'

            if cursor_value is not None:
                # Use cursor value (parameterized for safety)
                query += f" WHERE {quoted_cursor} >= %s"
                params.append(cursor_value)
            elif lookback_days > 0:
                # Use lookback days
                query += f" WHERE {quoted_cursor} >= CURRENT_DATE - INTERVAL %s"
                params.append(f"{lookback_days} days")

        # Add ORDER BY for consistent results
        if cursor_field:
            quoted_cursor = f'"{cursor_field}"'
            query += f" ORDER BY {quoted_cursor}"

        return query, params

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Postgres tables.

        Args:
            state_manager: Optional incremental state manager for tracking cursor state

        Yields:
            Batches of records as dictionaries
        """
        if not self.source_config.tables:
            raise ValueError("Postgres source requires 'tables' configuration")

        try:
            import psycopg2
            from psycopg2.extras import RealDictCursor
        except ImportError:
            raise ImportError(
                "psycopg2 is required for Postgres extraction. Install with: pip install psycopg2-binary"
            )

        # Get incremental configuration
        incremental = self.source_config.incremental or {}
        strategy = incremental.get("strategy", "updated_at")
        cursor_field_default = incremental.get("cursor_field")
        lookback_days = incremental.get("lookback_days", 0)
        state_path_str = incremental.get("state_path", "")
        state_path = Path(state_path_str) if state_path_str else None

        batch_size = self.engine_options.get("batch_size", 10000)

        # Connect to database
        try:
            conn = psycopg2.connect(
                host=self.connection["host"],
                port=self.connection["port"],
                database=self.connection["database"],
                user=self.connection["user"],
                password=self.connection["password"],
            )
            conn.set_session(autocommit=False)
        except Exception as e:
            raise RuntimeError(
                f"Failed to connect to Postgres database: {str(e)}"
            ) from e

        try:
            # Process each table
            for table_config in self.source_config.tables:
                table_name = table_config.get("name")
                if not table_name:
                    raise ValueError("Table configuration must include 'name' field")

                object_name = table_config.get("object", table_name.split(".")[-1])

                # Get cursor field for this table
                cursor_field = (
                    self._get_cursor_field(table_config) or cursor_field_default
                )

                # Get cursor value from state if available
                cursor_value = None
                if state_path and cursor_field:
                    state_data = IncrementalStateManager.read_state(state_path)
                    state_key = f"{object_name}.{cursor_field}"
                    if state_key in state_data:
                        cursor_value = state_data[state_key].get("last_value")

                # Build query
                query, params = self._build_query(
                    table_name=table_name,
                    cursor_field=cursor_field,
                    cursor_value=cursor_value,
                    lookback_days=lookback_days,
                )

                # Track last cursor value for state update
                last_cursor_value = None
                records_processed = 0

                # Execute query with server-side cursor for large datasets
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(query, params)

                    # Fetch in batches
                    while True:
                        records = cursor.fetchmany(batch_size)
                        if not records:
                            break

                        # Convert to list of dictionaries
                        batch = [dict(record) for record in records]

                        # Convert any datetime/date objects to ISO format strings
                        for record in batch:
                            for key, value in record.items():
                                if isinstance(value, (datetime,)):
                                    record[key] = value.isoformat()
                                elif hasattr(value, "isoformat"):  # date objects
                                    record[key] = value.isoformat()

                        # Track last cursor value
                        if cursor_field and batch:
                            last_record = batch[-1]
                            if cursor_field in last_record:
                                last_cursor_value = last_record[cursor_field]

                        records_processed += len(batch)
                        yield batch

                    # Update state after successful processing
                    if state_path and cursor_field and last_cursor_value is not None:
                        state_key = f"{object_name}.{cursor_field}"
                        # Read current state
                        state_data = IncrementalStateManager.read_state(state_path)
                        # Update cursor value
                        if state_key not in state_data:
                            state_data[state_key] = {}
                        state_data[state_key]["last_value"] = last_cursor_value
                        state_data[state_key]["updated_at"] = datetime.now().isoformat()
                        # Write updated state
                        IncrementalStateManager.write_state(state_path, state_data)

        finally:
            conn.close()

    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records across all tables.

        Returns:
            Estimated record count or None if cannot estimate
        """
        if not self.source_config.tables:
            return None

        try:
            import psycopg2
        except ImportError:
            return None

        try:
            conn = psycopg2.connect(
                host=self.connection["host"],
                port=self.connection["port"],
                database=self.connection["database"],
                user=self.connection["user"],
                password=self.connection["password"],
            )

            total = 0
            try:
                with conn.cursor() as cursor:
                    for table_config in self.source_config.tables:
                        table_name = table_config.get("name")
                        if not table_name:
                            continue

                        # Get approximate row count
                        cursor.execute(
                            f"SELECT reltuples::BIGINT AS estimate "
                            f"FROM pg_class WHERE relname = '{table_name.split('.')[-1]}'"
                        )
                        result = cursor.fetchone()
                        if result and result[0]:
                            total += result[0]
            finally:
                conn.close()

            return int(total) if total > 0 else None
        except Exception:
            return None

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract naturally available metadata from PostgreSQL.

        Extracts metadata that is naturally available in PostgreSQL:
        - Security labels (from row-level security policies)
        - Column types and constraints
        - Column comments (if set by DBA)
        - NOT NULL constraints
        - Primary key, foreign key information

        Returns:
            Dictionary with "tags" key containing field_name -> metadata mapping
            e.g., {"tags": {"email": "security_label_value", "id": "primary_key"}}
        """
        if not self.source_config.tables:
            return {"tags": {}}

        try:
            import psycopg2
        except ImportError:
            return {"tags": {}}

        source_tags = {}

        try:
            conn = psycopg2.connect(
                host=self.connection["host"],
                port=self.connection["port"],
                database=self.connection["database"],
                user=self.connection["user"],
                password=self.connection["password"],
            )

            try:
                with conn.cursor() as cursor:
                    # Process each table
                    for table_config in self.source_config.tables:
                        table_name = table_config.get("name")
                        if not table_name:
                            continue

                        # Parse schema.table format
                        if "." in table_name:
                            schema, table = table_name.split(".", 1)
                        else:
                            schema = "public"
                            table = table_name

                        # Query comprehensive metadata from pg_catalog
                        query = """
                            SELECT 
                                a.attname as column_name,
                                pg_catalog.col_description(c.oid, a.attnum) as column_comment,
                                t.typname as data_type,
                                a.attnotnull as is_not_null,
                                CASE WHEN pk.attname IS NOT NULL THEN 'primary_key' ELSE NULL END as is_primary_key,
                                CASE WHEN fk.attname IS NOT NULL THEN 'foreign_key' ELSE NULL END as is_foreign_key
                            FROM pg_catalog.pg_attribute a
                            JOIN pg_catalog.pg_class c ON a.attrelid = c.oid
                            JOIN pg_catalog.pg_namespace n ON c.relnamespace = n.oid
                            JOIN pg_catalog.pg_type t ON a.atttypid = t.oid
                            LEFT JOIN (
                                SELECT kcu.column_name as attname
                                FROM information_schema.table_constraints tc
                                JOIN information_schema.key_column_usage kcu 
                                    ON tc.constraint_name = kcu.constraint_name
                                WHERE tc.table_schema = %s 
                                  AND tc.table_name = %s
                                  AND tc.constraint_type = 'PRIMARY KEY'
                            ) pk ON a.attname = pk.attname
                            LEFT JOIN (
                                SELECT kcu.column_name as attname
                                FROM information_schema.table_constraints tc
                                JOIN information_schema.key_column_usage kcu 
                                    ON tc.constraint_name = kcu.constraint_name
                                WHERE tc.table_schema = %s 
                                  AND tc.table_name = %s
                                  AND tc.constraint_type = 'FOREIGN KEY'
                            ) fk ON a.attname = fk.attname
                            WHERE n.nspname = %s 
                              AND c.relname = %s
                              AND a.attnum > 0
                              AND NOT a.attisdropped
                            ORDER BY a.attnum
                        """

                        cursor.execute(
                            query, (schema, table, schema, table, schema, table)
                        )
                        results = cursor.fetchall()

                        for row in results:
                            (
                                column_name,
                                comment,
                                data_type,
                                is_not_null,
                                is_primary_key,
                                is_foreign_key,
                            ) = row

                            # Collect naturally available metadata
                            metadata_parts = []

                            # Column comment (if set by DBA)
                            if comment:
                                metadata_parts.append(comment.strip())

                            # Primary key constraint
                            if is_primary_key:
                                metadata_parts.append("primary_key")

                            # Foreign key constraint
                            if is_foreign_key:
                                metadata_parts.append("foreign_key")

                            # NOT NULL constraint
                            if is_not_null:
                                metadata_parts.append("not_null")

                            # Data type as metadata
                            if data_type:
                                metadata_parts.append(f"type:{data_type}")

                            # Combine metadata parts
                            if metadata_parts:
                                source_tags[column_name] = ",".join(metadata_parts)

            finally:
                conn.close()

        except Exception:
            # If extraction fails, return empty tags (non-critical)
            return {"tags": {}}

        return {"tags": source_tags}
