"""Native MySQL extractor using mysql-connector-python."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

from ..config import SourceConfig
from ..validator import IncrementalStateManager


class MySQLExtractor:
    """Extracts data from MySQL databases."""

    def __init__(self, source_config: SourceConfig):
        """Initialize MySQL extractor.

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
                    "MYSQL_HOST",
                    "MYSQL_PORT",
                    "MYSQL_DATABASE",
                    "MYSQL_USER",
                    "MYSQL_PASSWORD",
                    "charset",
                    "ssl_ca",
                    "ssl_cert",
                    "ssl_key",
                ]:
                    if key in self.source_config.credentials and key not in connection:
                        value = self.source_config.credentials[key]
                        # Map MYSQL_* env vars to connection keys
                        if key == "MYSQL_HOST":
                            connection.setdefault("host", value)
                        elif key == "MYSQL_PORT":
                            connection.setdefault(
                                "port", int(value) if isinstance(value, str) else value
                            )
                        elif key == "MYSQL_DATABASE":
                            connection.setdefault("database", value)
                        elif key == "MYSQL_USER":
                            connection.setdefault("user", value)
                        elif key == "MYSQL_PASSWORD":
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
        connection.setdefault("host", os.getenv("MYSQL_HOST", "localhost"))
        port = connection.get("port")
        if port is None:
            port = os.getenv("MYSQL_PORT", "3306")
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
                port = os.getenv("MYSQL_PORT", "3306")
        connection.setdefault("port", int(port) if isinstance(port, str) else port)
        connection.setdefault(
            "database", os.getenv("MYSQL_DATABASE", os.getenv("MYSQL_DB", ""))
        )
        connection.setdefault(
            "user", os.getenv("MYSQL_USER", os.getenv("USER", "root"))
        )
        connection.setdefault("password", os.getenv("MYSQL_PASSWORD", ""))

        # MySQL-specific defaults
        connection.setdefault("charset", "utf8mb4")
        connection.setdefault("autocommit", False)

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
            table_name: Fully qualified table name (schema.table or just table)
            cursor_field: Optional cursor field for incremental sync
            cursor_value: Optional cursor value for incremental sync
            lookback_days: Number of days to look back for incremental sync

        Returns:
            Tuple of (SQL query string, parameter list)
        """
        # Escape table name properly (handle schema.table)
        # MySQL uses backticks for identifiers
        if "." in table_name:
            schema, table = table_name.split(".", 1)
            quoted_table = f"`{schema}`.`{table}`"
        else:
            quoted_table = f"`{table_name}`"

        # Base SELECT query
        query = f"SELECT * FROM {quoted_table}"
        params: List[Any] = []

        # Add WHERE clause for incremental sync
        if cursor_field:
            # Escape column name with backticks
            quoted_cursor = f"`{cursor_field}`"

            if cursor_value is not None:
                # Use cursor value (parameterized for safety)
                query += f" WHERE {quoted_cursor} >= %s"
                params.append(cursor_value)
            elif lookback_days > 0:
                # Use lookback days (MySQL date arithmetic)
                query += (
                    f" WHERE {quoted_cursor} >= DATE_SUB(CURDATE(), INTERVAL %s DAY)"
                )
                params.append(lookback_days)

        # Add ORDER BY for consistent results
        if cursor_field:
            quoted_cursor = f"`{cursor_field}`"
            query += f" ORDER BY {quoted_cursor}"

        return query, params

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from MySQL tables.

        Args:
            state_manager: Optional incremental state manager for tracking cursor state

        Yields:
            Batches of records as dictionaries
        """
        if not self.source_config.tables:
            raise ValueError("MySQL source requires 'tables' configuration")

        try:
            import mysql.connector
        except ImportError:
            raise ImportError(
                "mysql-connector-python is required for MySQL extraction. Install with: pip install mysql-connector-python"
            )

        # Get incremental configuration
        incremental = self.source_config.incremental or {}
        strategy = incremental.get("strategy", "updated_at")
        cursor_field_default = incremental.get("cursor_field")
        lookback_days = incremental.get("lookback_days", 0)
        state_path_str = incremental.get("state_path", "")
        state_path = Path(state_path_str) if state_path_str else None

        batch_size = self.engine_options.get("batch_size", 10000)

        # Build connection config (mysql.connector.connect expects specific parameter names)
        connect_config = {
            "host": self.connection["host"],
            "port": self.connection["port"],
            "database": self.connection["database"],
            "user": self.connection["user"],
            "password": self.connection["password"],
            "charset": self.connection.get("charset", "utf8mb4"),
            "autocommit": self.connection.get("autocommit", False),
        }

        # Add authentication plugin if specified (for MySQL 8.0 compatibility)
        if "auth_plugin" in self.connection:
            connect_config["auth_plugin"] = self.connection["auth_plugin"]
        elif self.connection.get("use_native_auth", False):
            # Use mysql_native_password for compatibility with older clients
            connect_config["auth_plugin"] = "mysql_native_password"

        # Add SSL options if provided
        if "ssl_ca" in self.connection:
            connect_config["ssl_ca"] = self.connection["ssl_ca"]
        if "ssl_cert" in self.connection:
            connect_config["ssl_cert"] = self.connection["ssl_cert"]
        if "ssl_key" in self.connection:
            connect_config["ssl_key"] = self.connection["ssl_key"]

        # Connect to database
        try:
            conn = mysql.connector.connect(**connect_config)
        except Exception as e:
            raise RuntimeError(f"Failed to connect to MySQL database: {str(e)}") from e

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

                # Execute query with dictionary cursor (returns dicts directly)
                cursor = conn.cursor(dictionary=True)
                try:
                    cursor.execute(query, params)

                    # Fetch in batches
                    while True:
                        records = cursor.fetchmany(batch_size)
                        if not records:
                            break

                        # Records are already dictionaries when using dictionary=True
                        batch = list(records)

                        # Convert any datetime/date objects to ISO format strings
                        for record in batch:
                            for key, value in record.items():
                                if isinstance(value, (datetime,)):
                                    record[key] = value.isoformat()
                                elif hasattr(value, "isoformat"):  # date objects
                                    record[key] = value.isoformat()
                                elif isinstance(value, (bytes,)):
                                    # Handle BLOB types - convert to base64 or string
                                    try:
                                        record[key] = value.decode("utf-8")
                                    except UnicodeDecodeError:
                                        # If can't decode, skip or use base64
                                        import base64

                                        record[key] = base64.b64encode(value).decode(
                                            "ascii"
                                        )

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
                    cursor.close()

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
            import mysql.connector
        except ImportError:
            return None

        # Build connection config
        connect_config = {
            "host": self.connection["host"],
            "port": self.connection["port"],
            "database": self.connection["database"],
            "user": self.connection["user"],
            "password": self.connection["password"],
            "charset": self.connection.get("charset", "utf8mb4"),
        }

        try:
            conn = mysql.connector.connect(**connect_config)

            total = 0
            try:
                cursor = conn.cursor()
                for table_config in self.source_config.tables:
                    table_name = table_config.get("name")
                    if not table_name:
                        continue

                    # Get table name without schema for query
                    if "." in table_name:
                        schema, table = table_name.split(".", 1)
                        # MySQL uses information_schema
                        cursor.execute(
                            """
                            SELECT table_rows 
                            FROM information_schema.tables 
                            WHERE table_schema = %s AND table_name = %s
                            """,
                            (schema, table),
                        )
                    else:
                        cursor.execute(
                            """
                            SELECT table_rows 
                            FROM information_schema.tables 
                            WHERE table_schema = DATABASE() AND table_name = %s
                            """,
                            (table_name,),
                        )
                    result = cursor.fetchone()
                    if result and result[0]:
                        total += result[0]
                cursor.close()
            finally:
                conn.close()

            return int(total) if total > 0 else None
        except Exception:
            return None

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract naturally available metadata from MySQL.

        Extracts metadata that is naturally available in MySQL:
        - Column types and constraints
        - Column comments (if set by DBA)
        - NOT NULL constraints
        - Primary key, foreign key information
        - Column default values

        Returns:
            Dictionary with "tags" key containing field_name -> metadata mapping
            e.g., {"tags": {"email": "varchar,not_null", "id": "int,primary_key"}}
        """
        if not self.source_config.tables:
            return {"tags": {}}

        try:
            import mysql.connector
        except ImportError:
            return {"tags": {}}

        source_tags = {}

        # Build connection config
        connect_config = {
            "host": self.connection["host"],
            "port": self.connection["port"],
            "database": self.connection["database"],
            "user": self.connection["user"],
            "password": self.connection["password"],
            "charset": self.connection.get("charset", "utf8mb4"),
        }

        try:
            conn = mysql.connector.connect(**connect_config)

            try:
                cursor = conn.cursor()
                # Process each table
                for table_config in self.source_config.tables:
                    table_name = table_config.get("name")
                    if not table_name:
                        continue

                    # Parse schema.table format
                    if "." in table_name:
                        schema, table = table_name.split(".", 1)
                    else:
                        # Use current database as schema
                        schema = self.connection["database"]
                        table = table_name

                    # Query comprehensive metadata from information_schema
                    query = """
                        SELECT 
                            column_name,
                            column_type,
                            is_nullable,
                            column_key,
                            column_comment,
                            column_default
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position
                    """

                    cursor.execute(query, (schema, table))
                    results = cursor.fetchall()

                    for row in results:
                        (
                            column_name,
                            column_type,
                            is_nullable,
                            column_key,
                            comment,
                            default_value,
                        ) = row

                        # Collect naturally available metadata
                        metadata_parts = []

                        # Column type
                        if column_type:
                            metadata_parts.append(f"type:{column_type}")

                        # Column comment (if set by DBA)
                        if comment:
                            metadata_parts.append(comment.strip())

                        # NOT NULL constraint
                        if is_nullable == "NO":
                            metadata_parts.append("not_null")

                        # Primary key
                        if column_key == "PRI":
                            metadata_parts.append("primary_key")

                        # Foreign key
                        if column_key == "MUL":
                            metadata_parts.append("foreign_key")

                        # Default value
                        if default_value is not None:
                            metadata_parts.append(f"default:{default_value}")

                        # Combine metadata parts
                        if metadata_parts:
                            source_tags[column_name] = ",".join(metadata_parts)

                cursor.close()
            finally:
                conn.close()

        except Exception:
            # If extraction fails, return empty tags (non-critical)
            return {"tags": {}}

        return {"tags": source_tags}
