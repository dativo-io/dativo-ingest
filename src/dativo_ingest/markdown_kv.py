"""Markdown-KV parser and transformer for LLM-optimized data storage."""

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional


def extract_yaml_front_matter(content: str) -> tuple[Optional[Dict[str, Any]], str]:
    """Extract YAML front matter from Markdown content.

    Args:
        content: Markdown content with optional YAML front matter

    Returns:
        Tuple of (front_matter_dict, content_without_front_matter)
    """
    front_matter_pattern = r"^---\s*\n(.*?)\n---\s*\n"
    match = re.match(front_matter_pattern, content, re.DOTALL)

    if match:
        import yaml

        try:
            front_matter = yaml.safe_load(match.group(1))
            remaining_content = content[match.end() :]
            return front_matter, remaining_content
        except yaml.YAMLError:
            return None, content

    return None, content


def extract_sections(content: str) -> List[Dict[str, Any]]:
    """Extract sections from Markdown content based on headers.

    Args:
        content: Markdown content

    Returns:
        List of section dictionaries with 'name', 'level', 'content', 'start_line'
    """
    sections = []
    lines = content.split("\n")
    current_section = None
    current_content = []
    current_level = 0
    current_start_line = 1
    line_num = 0

    for line in lines:
        line_num += 1
        # Check for header (starts with #)
        header_match = re.match(r"^(#{1,6})\s+(.+)$", line)

        if header_match:
            # Save previous section if exists
            if current_section:
                sections.append(
                    {
                        "name": current_section,
                        "level": current_level,
                        "content": "\n".join(current_content).strip(),
                        "start_line": current_start_line,
                    }
                )

            # Start new section
            current_level = len(header_match.group(1))
            current_section = header_match.group(2).strip()
            current_content = []
            current_start_line = line_num
        else:
            current_content.append(line)

    # Add last section
    if current_section:
        sections.append(
            {
                "name": current_section,
                "level": current_level,
                "content": "\n".join(current_content).strip(),
                "start_line": current_start_line,
            }
        )

    # If no sections found, create a default section
    if not sections:
        sections.append(
            {
                "name": "_default",
                "level": 0,
                "content": content.strip(),
                "start_line": 1,
            }
        )

    return sections


def parse_key_value_pairs(content: str) -> List[Dict[str, Any]]:
    """Parse key-value pairs from Markdown-KV format.

    Format: key:: value
    Supports multi-line values (indented lines after key::)

    Args:
        content: Section content with key-value pairs

    Returns:
        List of dictionaries with 'key', 'value', 'value_json', 'ord'
    """
    kv_pairs = []
    lines = content.split("\n")
    current_key = None
    current_value = []
    ord_counter = 0

    for line in lines:
        # Check for key:: value pattern
        kv_match = re.match(r"^([^:]+)::\s*(.*)$", line)

        if kv_match:
            # Save previous key-value if exists
            if current_key:
                value_str = "\n".join(current_value).strip()
                value_json = None

                # Try to parse as JSON
                try:
                    json.loads(value_str)
                    value_json = value_str
                except (json.JSONDecodeError, ValueError):
                    pass

                kv_pairs.append(
                    {
                        "key": current_key.strip(),
                        "value": value_str,
                        "value_json": value_json,
                        "ord": ord_counter,
                    }
                )
                ord_counter += 1

            # Start new key-value
            current_key = kv_match.group(1).strip()
            current_value = (
                [kv_match.group(2).strip()] if kv_match.group(2).strip() else []
            )
        elif current_key and (line.startswith(" ") or line.startswith("\t")):
            # Continuation of multi-line value (indented)
            current_value.append(line)
        elif current_key and not line.strip():
            # Empty line - continue collecting value
            current_value.append(line)
        elif current_key:
            # Non-indented line after key-value - save and reset
            value_str = "\n".join(current_value).strip()
            value_json = None

            try:
                json.loads(value_str)
                value_json = value_str
            except (json.JSONDecodeError, ValueError):
                pass

            kv_pairs.append(
                {
                    "key": current_key.strip(),
                    "value": value_str,
                    "value_json": value_json,
                    "ord": ord_counter,
                }
            )
            ord_counter += 1
            current_key = None
            current_value = []

    # Save last key-value if exists
    if current_key:
        value_str = "\n".join(current_value).strip()
        value_json = None

        try:
            json.loads(value_str)
            value_json = value_str
        except (json.JSONDecodeError, ValueError):
            pass

        kv_pairs.append(
            {
                "key": current_key.strip(),
                "value": value_str,
                "value_json": value_json,
                "ord": ord_counter,
            }
        )

    return kv_pairs


def parse_to_row_per_kv(
    content: str, doc_id: str, extracted_at: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Parse Markdown-KV content into row-per-KV format (flattened, query-friendly).

    Args:
        content: Markdown-KV content
        doc_id: Document identifier
        extracted_at: Extraction timestamp (defaults to now)

    Returns:
        List of row dictionaries, one per key-value pair
    """
    if extracted_at is None:
        extracted_at = datetime.utcnow()

    # Extract YAML front matter
    front_matter, content_body = extract_yaml_front_matter(content)

    # Extract sections
    sections = extract_sections(content_body)

    rows = []

    # Process front matter as a special section
    if front_matter:
        for key, value in front_matter.items():
            value_str = str(value)
            value_json = None

            if isinstance(value, (dict, list)):
                value_json = json.dumps(value)

            rows.append(
                {
                    "doc_id": doc_id,
                    "section": "_front_matter",
                    "key": key,
                    "value": value_str,
                    "value_json": value_json,
                    "ord": len(rows),
                    "extracted_at": extracted_at.isoformat(),
                }
            )

    # Process each section
    for section in sections:
        section_name = section["name"]
        section_content = section["content"]

        # Parse key-value pairs in this section
        kv_pairs = parse_key_value_pairs(section_content)

        for kv in kv_pairs:
            rows.append(
                {
                    "doc_id": doc_id,
                    "section": section_name,
                    "key": kv["key"],
                    "value": kv["value"],
                    "value_json": kv["value_json"],
                    "ord": len(rows),
                    "extracted_at": extracted_at.isoformat(),
                }
            )

    return rows


def parse_to_document_level(
    content: str, doc_id: str, extracted_at: Optional[datetime] = None
) -> Dict[str, Any]:
    """Parse Markdown-KV content into document-level format (compact, nested).

    Args:
        content: Markdown-KV content
        doc_id: Document identifier
        extracted_at: Extraction timestamp (defaults to now)

    Returns:
        Dictionary with doc_id, title, sections (nested), raw_md, extracted_at
    """
    if extracted_at is None:
        extracted_at = datetime.utcnow()

    # Extract YAML front matter
    front_matter, content_body = extract_yaml_front_matter(content)

    # Extract title from front matter or first header
    title = None
    if front_matter and "title" in front_matter:
        title = str(front_matter["title"])

    # Extract sections
    sections_data = extract_sections(content_body)

    # Build nested sections structure
    sections = []

    # Add front matter as a section
    if front_matter:
        front_matter_kv = []
        for key, value in front_matter.items():
            if key != "title":  # Title is already extracted
                value_str = str(value)
                value_json = None
                if isinstance(value, (dict, list)):
                    value_json = json.dumps(value)

                front_matter_kv.append(
                    {
                        "key": key,
                        "value": value_str,
                        "value_json": value_json,
                        "ord": len(front_matter_kv),
                    }
                )

        if front_matter_kv:
            sections.append(
                {
                    "section": "_front_matter",
                    "level": 0,
                    "kv": front_matter_kv,
                }
            )

    # Process each section
    for section in sections_data:
        section_name = section["name"]
        section_content = section["content"]
        section_level = section["level"]

        # Parse key-value pairs
        kv_pairs = parse_key_value_pairs(section_content)

        if kv_pairs:
            sections.append(
                {
                    "section": section_name,
                    "level": section_level,
                    "kv": [
                        {
                            "key": kv["key"],
                            "value": kv["value"],
                            "value_json": kv["value_json"],
                            "ord": kv["ord"],
                        }
                        for kv in kv_pairs
                    ],
                }
            )

    # If no title found, use first section name
    if not title and sections_data:
        title = sections_data[0]["name"]

    return {
        "doc_id": doc_id,
        "title": title or doc_id,
        "sections": sections,
        "raw_md": content,  # Store original for reparse
        "extracted_at": extracted_at.isoformat(),
    }


def parse_markdown_kv(
    content: str,
    doc_id: str,
    pattern: str = "row_per_kv",
    extracted_at: Optional[datetime] = None,
) -> Any:
    """Parse Markdown-KV content into structured format.

    Args:
        content: Markdown-KV content
        doc_id: Document identifier
        pattern: Storage pattern - "row_per_kv" or "document_level"
        extracted_at: Extraction timestamp (defaults to now)

    Returns:
        Parsed data in the requested format
    """
    if pattern == "row_per_kv":
        return parse_to_row_per_kv(content, doc_id, extracted_at)
    elif pattern == "document_level":
        return parse_to_document_level(content, doc_id, extracted_at)
    else:
        raise ValueError(
            f"Unknown pattern: {pattern}. Must be 'row_per_kv' or 'document_level'"
        )


def transform_to_markdown_kv(
    data: Dict[str, Any], format: str = "compact", doc_id: Optional[str] = None
) -> str:
    """Transform structured data to Markdown-KV format.

    Args:
        data: Structured data dictionary
        format: Output format - "compact" or "verbose"
        doc_id: Optional document ID (if not provided, will be generated)

    Returns:
        Markdown-KV formatted string
    """
    if doc_id is None:
        doc_id = data.get("id") or data.get("doc_id") or "unknown"

    lines = []

    # Add YAML front matter if title or metadata exists
    front_matter = {}
    if "title" in data:
        front_matter["title"] = data["title"]
    if "id" in data:
        front_matter["id"] = data["id"]
    if "doc_id" in data:
        front_matter["doc_id"] = data["doc_id"]

    if front_matter:
        import yaml

        lines.append("---")
        lines.append(yaml.dump(front_matter, default_flow_style=False).strip())
        lines.append("---")
        lines.append("")

    # Add main content section
    if format == "verbose":
        lines.append("# Document")
        lines.append("")

    # Convert data fields to key-value pairs
    for key, value in data.items():
        if key in ["id", "doc_id", "title"] and front_matter:
            continue  # Already in front matter

        if isinstance(value, (dict, list)):
            # Complex types - serialize as JSON
            value_str = json.dumps(value, indent=2 if format == "verbose" else None)
        elif value is None:
            value_str = ""
        else:
            value_str = str(value)

        lines.append(f"{key}:: {value_str}")

    return "\n".join(lines)
