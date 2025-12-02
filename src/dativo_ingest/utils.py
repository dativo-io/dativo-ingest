"""Utility functions for Dativo ingestion."""

import os
import re
from typing import Optional


def expand_env_variable(value: Optional[str]) -> Optional[str]:
    """Expand environment variable references in a string value.

    Supports both ${VAR} and ${VAR:-default} syntax.

    Args:
        value: String value that may contain environment variable references

    Returns:
        Expanded string value, or None if value is None or variable is unset

    Examples:
        >>> expand_env_variable("${HOME}")
        '/home/user'
        >>> expand_env_variable("${MISSING:-default}")
        'default'
        >>> expand_env_variable(None)
        None
    """
    if not isinstance(value, str):
        return value

    # Handle bash-style ${VAR:-default} syntax
    # Replace all occurrences of ${VAR:-default} with the resolved value
    bash_default_pattern = r"\$\{([^:}]+):-([^}]+)\}"

    def replace_with_default(match):
        env_var = match.group(1)
        default_value = match.group(2)
        return os.getenv(env_var, default_value)

    value = re.sub(bash_default_pattern, replace_with_default, value)

    # Handle simple ${VAR} syntax
    if "${" in value:
        expanded = os.path.expandvars(value)
        if "${" in expanded:
            # Variable not set, extract var name and try to get from env
            var_match = re.search(r"\$\{([^}]+)\}", expanded)
            if var_match:
                var_name = var_match.group(1)
                return os.getenv(var_name, None)
        return expanded

    return value
