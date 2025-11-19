# Markdown-KV Storage Guide

## Overview

Markdown-KV is an LLM-optimized data format that combines the readability of Markdown with structured key-value pairs. Dativo supports three storage options for Markdown-KV data, allowing you to choose the best pattern for your use case.

## Storage Options

### Option 1: Store as STRING in Iceberg (Parquet)

Store Markdown-KV content as a STRING column in existing Iceberg Parquet tables. This preserves the original format and is ideal for document-level queries.

**When to use:**
- You need to preserve the original Markdown-KV format
- You primarily query by document ID
- You want simple storage without parsing overhead

**Configuration:**
```yaml
target:
  file_format: parquet
  markdown_kv_storage:
    mode: "string"
```

**Asset Definition:**
Your asset definition should include a STRING column for the Markdown-KV content:
```yaml
schema:
  - name: doc_id
    type: string
    required: true
  - name: markdown_kv_content
    type: string
    required: false
```

### Option 2: Store Raw Files in S3/MinIO

Store Markdown-KV files directly in S3/MinIO buckets for direct LLM consumption. Files are stored with `.md` or `.mdkv` extensions.

**When to use:**
- You need direct file access for LLM ingestion
- You want to preserve files in their original format
- You're using S3/MinIO as your primary storage

**Configuration:**
```yaml
target:
  type: s3  # or minio
  connection:
    bucket: "llm-data"
  markdown_kv_storage:
    mode: "raw_file"
    file_extension: ".mdkv"  # or ".md"
    path_pattern: "docs/{doc_id}.mdkv"  # Optional: specify file path pattern
```

**Path Patterns:**
- `{doc_id}` - Document identifier
- `{date}` - Current date (YYYY-MM-DD)
- `{timestamp}` - Current timestamp

### Option 3: Parse and Store as Structured Data in Iceberg

Parse Markdown-KV into structured format and store in Iceberg tables. This option provides three patterns:

#### Pattern 3a: Row-per-KV (Flattened, Query-Friendly)

One row per key-value pair. Ideal for filtering and joining operations.

**When to use:**
- You need to filter by key-value pairs (e.g., "all docs where model:: gpt-4")
- You want to join across documents
- You're building RAG (Retrieval-Augmented Generation) filters

**Configuration:**
```yaml
target:
  file_format: parquet
  markdown_kv_storage:
    mode: "structured"
    structured_pattern: "row_per_kv"
```

**Asset Definition:**
Use `assets/markdown_kv/v1.0/kv_lines.yaml`:
```yaml
asset_path: assets/markdown_kv/v1.0/kv_lines.yaml
```

**Schema:**
- `doc_id` (string, required) - Document identifier
- `section` (string) - Section name (from Markdown headers or '_front_matter')
- `key` (string, required) - Key from key-value pair
- `value` (string) - Value from key-value pair
- `value_json` (string) - JSON-serialized value for complex types
- `ord` (integer) - Display order within section
- `extracted_at` (timestamp) - Extraction timestamp

#### Pattern 3b: Document-Level with Nested Types (Compact)

One row per document with nested sections. Ideal for document reconstruction.

**When to use:**
- You need to reconstruct full documents
- You want compact storage (fewer rows)
- You primarily retrieve documents by ID

**Configuration:**
```yaml
target:
  file_format: parquet
  markdown_kv_storage:
    mode: "structured"
    structured_pattern: "document_level"
```

**Asset Definition:**
Use `assets/markdown_kv/v1.0/docs.yaml`:
```yaml
asset_path: assets/markdown_kv/v1.0/docs.yaml
```

**Schema:**
- `doc_id` (string, required) - Document identifier
- `title` (string) - Document title
- `sections` (array) - Array of section structs with nested KV arrays
- `raw_md` (string) - Original Markdown-KV content (optional)
- `extracted_at` (timestamp) - Extraction timestamp

**Iceberg Nested Type:**
The `sections` field uses Iceberg nested types:
```
ARRAY<STRUCT<
  section: string,
  level: int,
  kv: ARRAY<STRUCT<
    key: string,
    value: string,
    value_json: string,
    ord: int
  >>
>>
```

#### Pattern 3c: Hybrid (Both Patterns)

Maintain both row-per-KV and document-level tables. Provides the best of both worlds.

**When to use:**
- You need both filtering capabilities and document reconstruction
- You can afford maintaining two tables
- You want maximum flexibility

**Implementation Options:**

**Option A: Dual-Write (Recommended)**
Write to both tables in the same job. Requires two asset definitions or dual-write logic in the ingestion engine.

**Option B: Materialized View**
Write to docs table, then create a "silver" job that materializes kv_lines from docs.

**Option C: Two Separate Jobs**
Run separate jobs for each pattern.

**Configuration:**
```yaml
target:
  file_format: parquet
  markdown_kv_storage:
    mode: "structured"
    structured_pattern: "hybrid"
```

See `assets/markdown_kv/v1.0/hybrid_example.yaml` for detailed implementation guidance.

## Markdown-KV Format

### Basic Syntax

```
key:: value
```

### Multi-line Values

```
key:: This is a multi-line value
     that continues on the next line
     with indentation
```

### Sections

```
# Section Title

key1:: value1
key2:: value2

## Subsection

key3:: value3
```

### YAML Front Matter

```yaml
---
title: Document Title
author: John Doe
tags: [markdown, kv, llm]
---

# Main Content

key:: value
```

### JSON Values

Complex values can be stored as JSON:

```
config:: {"model": "gpt-4", "temperature": 0.7}
```

The parser will automatically detect JSON and store it in the `value_json` field.

## Source Connector

Dativo includes a `markdown_kv` source connector for reading Markdown-KV files:

```yaml
source_connector_path: connectors/sources/markdown_kv.yaml
source:
  files:
    - file_path: "data/docs/doc1.mdkv"
      object: "doc1"
```

## Transformation

You can transform structured data (CSV, JSON, etc.) to Markdown-KV format before storage:

```python
from dativo_ingest.markdown_kv import transform_to_markdown_kv

data = {
    "id": "doc1",
    "title": "Example Document",
    "content": "This is the content",
    "metadata": {"author": "John", "tags": ["example"]}
}

markdown_kv = transform_to_markdown_kv(data, format="compact")
```

## Complete Job Examples

### Example 1: Store as STRING in Iceberg

```yaml
tenant_id: acme
source_connector_path: connectors/sources/markdown_kv.yaml
target_connector_path: connectors/targets/iceberg.yaml
asset_path: assets/markdown_kv/v1.0/string_storage.yaml

source:
  files:
    - file_path: "data/docs/doc1.mdkv"
      object: "doc1"

target:
  branch: acme
  warehouse: s3://lake/acme/markdown_kv/
  file_format: parquet
  markdown_kv_storage:
    mode: "string"
  connection:
    nessie:
      uri: "${NESSIE_URI}"
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: acme-bucket
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      region: "${AWS_REGION}"
```

### Example 2: Store Raw Files in S3

```yaml
tenant_id: acme
source_connector_path: connectors/sources/markdown_kv.yaml
target_connector_path: connectors/targets/s3.yaml
asset_path: assets/markdown_kv/v1.0/raw_files.yaml

source:
  files:
    - file_path: "data/docs/doc1.mdkv"
      object: "doc1"

target:
  connection:
    bucket: "llm-data"
    endpoint: "s3.amazonaws.com"
    access_key_id: "${AWS_ACCESS_KEY_ID}"
    secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
    region: "${AWS_REGION}"
  markdown_kv_storage:
    mode: "raw_file"
    file_extension: ".mdkv"
    path_pattern: "docs/{doc_id}.mdkv"
```

### Example 3: Structured Storage (Row-per-KV)

```yaml
tenant_id: acme
source_connector_path: connectors/sources/markdown_kv.yaml
target_connector_path: connectors/targets/iceberg.yaml
asset_path: assets/markdown_kv/v1.0/kv_lines.yaml

source:
  files:
    - file_path: "data/docs/doc1.mdkv"
      object: "doc1"

target:
  branch: acme
  warehouse: s3://lake/acme/markdown_kv/
  file_format: parquet
  markdown_kv_storage:
    mode: "structured"
    structured_pattern: "row_per_kv"
  connection:
    nessie:
      uri: "${NESSIE_URI}"
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: acme-bucket
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      region: "${AWS_REGION}"
```

### Example 4: Structured Storage (Document-Level)

```yaml
tenant_id: acme
source_connector_path: connectors/sources/markdown_kv.yaml
target_connector_path: connectors/targets/iceberg.yaml
asset_path: assets/markdown_kv/v1.0/docs.yaml

source:
  files:
    - file_path: "data/docs/doc1.mdkv"
      object: "doc1"

target:
  branch: acme
  warehouse: s3://lake/acme/markdown_kv/
  file_format: parquet
  markdown_kv_storage:
    mode: "structured"
    structured_pattern: "document_level"
  connection:
    nessie:
      uri: "${NESSIE_URI}"
    s3:
      endpoint: "${S3_ENDPOINT}"
      bucket: acme-bucket
      access_key_id: "${AWS_ACCESS_KEY_ID}"
      secret_access_key: "${AWS_SECRET_ACCESS_KEY}"
      region: "${AWS_REGION}"
```

## Performance Considerations

### Row-per-KV Pattern
- **Pros:** Excellent for filtering and joining, easy to index
- **Cons:** More rows, larger storage footprint, requires grouping to reconstruct documents

### Document-Level Pattern
- **Pros:** Compact storage, easy document retrieval, fewer rows
- **Cons:** More complex nested queries, less efficient for filtering by key-value pairs

### Hybrid Pattern
- **Pros:** Best of both worlds, maximum flexibility
- **Cons:** Requires maintaining two tables, more storage overhead

## Best Practices

1. **Choose the right pattern:**
   - Use row-per-KV for analytics and filtering
   - Use document-level for document retrieval
   - Use hybrid when you need both capabilities

2. **Partition by ingest_date:**
   - All patterns support partitioning by `ingest_date`
   - This improves query performance and enables efficient data retention

3. **Preserve order:**
   - The `ord` field preserves the original order of key-value pairs
   - Use this when order matters for your use case

4. **Store raw Markdown-KV:**
   - Consider storing `raw_md` in document-level pattern for reparse capability
   - This allows you to reprocess documents if the schema changes

5. **Use JSON for complex values:**
   - Store complex types (dicts, arrays) in `value_json` field
   - This preserves type information and enables proper deserialization

## Troubleshooting

### Issue: Parser not detecting key-value pairs
**Solution:** Ensure keys are followed by `::` (double colon) with a space before the value.

### Issue: Multi-line values not working
**Solution:** Ensure continuation lines are indented (start with space or tab).

### Issue: Sections not being extracted
**Solution:** Ensure section headers start with `#` followed by a space.

### Issue: YAML front matter not parsed
**Solution:** Ensure front matter is wrapped in `---` delimiters and is valid YAML.

## Additional Resources

- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Comprehensive setup and onboarding guide
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Configuration reference
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Execution flow documentation
- [README.md](../README.md) - Project overview

## External References

- [Markdown-KV Format Specification](https://www.improvingagents.com/blog/best-input-data-format-for-llms)
- [Iceberg Nested Types Documentation](https://iceberg.apache.org/docs/latest/spec/#nested-types)

