"""Utilities for parsing secret payloads in various formats."""

import json
import os
from typing import Any, Dict, Optional


def parse_env_blob(blob: str) -> Dict[str, str]:
    """Parse a .env-style blob into a dictionary.

    Args:
        blob: Multiline string with KEY=VALUE pairs

    Returns:
        Dictionary of environment variables
    """
    env_vars: Dict[str, str] = {}
    for raw_line in blob.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        env_vars[key.strip()] = os.path.expandvars(value.strip().strip('"').strip("'"))
    return env_vars


def expand_env_vars_in_dict(data: Any) -> Any:
    """Recursively expand environment variables in dictionary values.

    Args:
        data: Data structure (dict, list, or str) to expand

    Returns:
        Data structure with environment variables expanded
    """
    if isinstance(data, dict):
        return {k: expand_env_vars_in_dict(v) for k, v in data.items()}
    if isinstance(data, list):
        return [expand_env_vars_in_dict(item) for item in data]
    if isinstance(data, str):
        return os.path.expandvars(data)
    return data


def parse_secret_payload(payload: Any, format_hint: Optional[str] = None) -> Any:
    """Parse a secret payload based on format hint or auto-detection.

    Args:
        payload: Raw secret payload (string, dict, list, etc.)
        format_hint: Optional format hint (json, env, text, raw, auto)

    Returns:
        Parsed secret value
    """
    if isinstance(payload, (dict, list)):
        return expand_env_vars_in_dict(payload)

    if payload is None:
        return payload

    if not isinstance(payload, str):
        return payload

    text = payload.strip()
    hint = (format_hint or "auto").lower()

    if hint == "json" or (hint == "auto" and text.startswith(("{", "["))):
        try:
            return expand_env_vars_in_dict(json.loads(text))
        except json.JSONDecodeError:
            if hint == "json":
                raise
    if hint == "env" or (hint == "auto" and "\n" in text and "=" in text):
        return parse_env_blob(text)
    if hint == "text" or hint == "raw":
        return os.path.expandvars(text)

    # auto fallback
    return os.path.expandvars(text)
