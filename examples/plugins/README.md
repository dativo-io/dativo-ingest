# Custom Plugin Examples

This directory contains example implementations of custom readers and writers for the Dativo ETL platform.

## Available Examples

### Readers

#### 1. JSON API Reader (`json_api_reader.py`)

A custom reader for paginated JSON APIs with authentication support.

**Features:**
- Pagination handling
- Bearer token authentication
- Configurable page size
- Error handling
- Timeout support

**Usage:**
```yaml
source:
  custom_reader: "examples/plugins/json_api_reader.py:JSONAPIReader"
  connection:
    base_url: "https://api.example.com/v1"
    timeout: 30
  credentials:
    token: "${API_TOKEN}"
  engine:
    options:
      page_size: 100
      max_pages: null
  objects: ["users", "orders"]
```

**Test Locally:**
```bash
cd examples/plugins
python json_api_reader.py
```

### Writers

#### 1. JSON File Writer (`json_file_writer.py`)

A custom writer for JSON and JSONL files with S3 upload support.

**Features:**
- JSON and JSONL formats
- Optional compression (gzip)
- S3 upload support
- Local file writing fallback
- Manifest file generation

**Usage:**
```yaml
target:
  custom_writer: "examples/plugins/json_file_writer.py:JSONFileWriter"
  connection:
    s3:
      bucket: "my-data-lake"
      region: "us-east-1"
      access_key: "${AWS_ACCESS_KEY_ID}"
      secret_key: "${AWS_SECRET_ACCESS_KEY}"
  engine:
    options:
      format: "jsonl"
      indent: null
      compress: false
```

**Test Locally:**
```bash
cd examples/plugins
python json_file_writer.py
```

## Creating Your Own Plugins

### Step 1: Copy an Example

Start with an example that's closest to your use case:

```bash
cp json_api_reader.py my_custom_reader.py
```

### Step 2: Modify the Class

Update the class name and implementation:

```python
class MyCustomReader(BaseReader):
    """Your custom reader implementation."""
    
    def extract(self, state_manager=None):
        # Your extraction logic
        pass
```

### Step 3: Configure Your Job

Update your job configuration to use the custom plugin:

```yaml
source:
  custom_reader: "examples/plugins/my_custom_reader.py:MyCustomReader"
  # ... your configuration
```

### Step 4: Test

Run your job to test the custom plugin:

```bash
dativo run --config /app/jobs/my_job.yaml --mode self_hosted
```

## Plugin Development Guidelines

### Best Practices

1. **Inherit from Base Classes**: Always inherit from `BaseReader` or `BaseWriter`
2. **Handle Errors**: Implement robust error handling and provide clear error messages
3. **Use Configuration**: Access connection details from `source_config` or `target_config`
4. **Batch Processing**: Process data in batches for efficiency
5. **Documentation**: Document your plugin's configuration options and behavior

### Testing

1. **Unit Tests**: Create unit tests for your plugin logic
2. **Integration Tests**: Test with real connections (in dev/staging)
3. **Local Testing**: Use the `main()` function for quick local testing
4. **Error Cases**: Test error scenarios and edge cases

### Configuration Access

#### For Readers

```python
# Connection details
self.source_config.connection.get("endpoint")

# Credentials
self.source_config.credentials.get("api_key")

# Engine options
self.source_config.engine.get("options", {})

# Objects to extract
self.source_config.objects
```

#### For Writers

```python
# Connection details
self.target_config.connection.get("s3", {})

# Asset schema
self.asset_definition.schema

# Output path
self.output_base

# Engine options
self.target_config.engine.get("options", {})
```

## Dependencies

Install required dependencies for the examples:

```bash
pip install requests boto3
```

## Additional Resources

- [Custom Plugins Documentation](/workspace/docs/CUSTOM_PLUGINS.md)
- [Plugin API Reference](/workspace/src/dativo_ingest/plugins.py)
- [Base Reader Class](/workspace/src/dativo_ingest/plugins.py#BaseReader)
- [Base Writer Class](/workspace/src/dativo_ingest/plugins.py#BaseWriter)

## Contributing

To contribute new example plugins:

1. Create your plugin in this directory
2. Add documentation and usage examples
3. Include a `main()` function for testing
4. Update this README with your example
5. Submit a pull request

## Support

For questions or issues:
- Check the [main documentation](/workspace/docs/CUSTOM_PLUGINS.md)
- Review other example implementations
- Open an issue with your question
