"""Cloud plugin execution for running custom plugins in AWS Lambda and GCP Cloud Functions.

This module enables running custom Python and Rust plugins in cloud environments for:
- Better isolation and security
- Scalable execution
- Resource management
- Cost optimization for sporadic workloads

Supported Cloud Providers:
- AWS Lambda (Python and Rust via custom runtime)
- GCP Cloud Functions (Python and Rust via custom runtime)

Usage:
    Configure cloud execution in your job YAML:
    
    source:
      custom_reader: "path/to/plugin.py:MyReader"
      engine:
        cloud_execution:
          enabled: true
          provider: "aws"  # or "gcp"
          runtime: "python3.11"
          memory_mb: 512
          timeout_seconds: 300
          # AWS specific
          aws:
            role_arn: "arn:aws:iam::account:role/lambda-role"
            security_groups: ["sg-xxx"]
            subnets: ["subnet-xxx"]
          # GCP specific
          gcp:
            project_id: "my-project"
            region: "us-central1"
            service_account: "plugin-executor@my-project.iam.gserviceaccount.com"
"""

import base64
import hashlib
import io
import json
import logging
import os
import tempfile
import time
import zipfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Type

from .plugins import BaseReader, BaseWriter

logger = logging.getLogger(__name__)


class CloudExecutionConfig:
    """Configuration for cloud plugin execution."""

    def __init__(
        self,
        enabled: bool = False,
        provider: str = "aws",  # "aws" or "gcp"
        runtime: str = "python3.11",
        memory_mb: int = 512,
        timeout_seconds: int = 300,
        aws_config: Optional[Dict[str, Any]] = None,
        gcp_config: Optional[Dict[str, Any]] = None,
        environment_variables: Optional[Dict[str, str]] = None,
    ):
        """Initialize cloud execution configuration.

        Args:
            enabled: Whether cloud execution is enabled
            provider: Cloud provider ("aws" or "gcp")
            runtime: Runtime environment (e.g., "python3.11", "provided.al2")
            memory_mb: Memory allocation in MB
            timeout_seconds: Execution timeout in seconds
            aws_config: AWS-specific configuration
            gcp_config: GCP-specific configuration
            environment_variables: Environment variables to pass to function
        """
        self.enabled = enabled
        self.provider = provider.lower()
        self.runtime = runtime
        self.memory_mb = memory_mb
        self.timeout_seconds = timeout_seconds
        self.aws_config = aws_config or {}
        self.gcp_config = gcp_config or {}
        self.environment_variables = environment_variables or {}

    @classmethod
    def from_dict(cls, config: Dict[str, Any]) -> "CloudExecutionConfig":
        """Create configuration from dictionary.

        Args:
            config: Configuration dictionary

        Returns:
            CloudExecutionConfig instance
        """
        return cls(
            enabled=config.get("enabled", False),
            provider=config.get("provider", "aws"),
            runtime=config.get("runtime", "python3.11"),
            memory_mb=config.get("memory_mb", 512),
            timeout_seconds=config.get("timeout_seconds", 300),
            aws_config=config.get("aws", {}),
            gcp_config=config.get("gcp", {}),
            environment_variables=config.get("environment_variables", {}),
        )


class CloudPluginExecutor(ABC):
    """Abstract base class for cloud plugin executors."""

    def __init__(self, config: CloudExecutionConfig):
        """Initialize cloud plugin executor.

        Args:
            config: Cloud execution configuration
        """
        self.config = config

    @abstractmethod
    def deploy_plugin(
        self, plugin_path: str, plugin_type: str, function_name: str
    ) -> str:
        """Deploy plugin to cloud provider.

        Args:
            plugin_path: Path to plugin file
            plugin_type: Plugin type ("python" or "rust")
            function_name: Name for the cloud function

        Returns:
            Function ARN/URL for invocation
        """
        pass

    @abstractmethod
    def invoke_plugin(
        self, function_identifier: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Invoke deployed plugin.

        Args:
            function_identifier: Function ARN/URL
            payload: Payload to send to function

        Returns:
            Function response
        """
        pass

    @abstractmethod
    def cleanup_plugin(self, function_identifier: str) -> None:
        """Clean up deployed plugin.

        Args:
            function_identifier: Function ARN/URL to clean up
        """
        pass

    def _package_python_plugin(
        self, plugin_path: str, include_dependencies: bool = True
    ) -> bytes:
        """Package Python plugin into deployment package.

        Args:
            plugin_path: Path to Python plugin file
            include_dependencies: Whether to include dativo_ingest dependencies

        Returns:
            ZIP file bytes
        """
        plugin_file = Path(plugin_path)
        if not plugin_file.exists():
            raise ValueError(f"Plugin file not found: {plugin_path}")

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Add plugin file
            zipf.write(plugin_file, plugin_file.name)

            # Add handler wrapper
            handler_code = self._generate_python_handler(plugin_file.name)
            zipf.writestr("handler.py", handler_code)

            # Add minimal dativo_ingest dependencies if needed
            if include_dependencies:
                # Add base plugin classes
                dativo_ingest_path = Path(__file__).parent
                plugin_module = dativo_ingest_path / "plugins.py"
                config_module = dativo_ingest_path / "config.py"
                exceptions_module = dativo_ingest_path / "exceptions.py"
                validator_module = dativo_ingest_path / "validator.py"

                for module in [
                    plugin_module,
                    config_module,
                    exceptions_module,
                    validator_module,
                ]:
                    if module.exists():
                        zipf.write(
                            module, f"dativo_ingest/{module.name}"
                        )

                # Add __init__.py
                zipf.writestr("dativo_ingest/__init__.py", "")

        zip_buffer.seek(0)
        return zip_buffer.read()

    def _generate_python_handler(self, plugin_filename: str) -> str:
        """Generate Lambda/Cloud Function handler code.

        Args:
            plugin_filename: Name of the plugin file

        Returns:
            Handler code as string
        """
        handler_template = '''"""Auto-generated handler for cloud plugin execution."""

import json
import sys
from pathlib import Path

# Import plugin
plugin_module_name = "{plugin_module}"
plugin_class_name = "{plugin_class}"

# Import plugin module
import importlib.util
spec = importlib.util.spec_from_file_location(plugin_module_name, Path(__file__).parent / "{plugin_file}")
plugin_module = importlib.util.module_from_spec(spec)
sys.modules[plugin_module_name] = plugin_module
spec.loader.exec_module(plugin_module)

PluginClass = getattr(plugin_module, plugin_class_name)

def lambda_handler(event, context):
    """AWS Lambda handler."""
    return handle_request(event)

def handle_request(event):
    """Handle cloud function request."""
    try:
        operation = event.get("operation")
        config = event.get("config", {{}})
        
        if operation == "check_connection":
            # Instantiate plugin
            from dativo_ingest.config import SourceConfig
            source_config = SourceConfig(**config)
            plugin = PluginClass(source_config)
            
            # Check connection
            result = plugin.check_connection()
            return {{
                "statusCode": 200,
                "body": json.dumps(result.to_dict())
            }}
        
        elif operation == "discover":
            # Instantiate plugin
            from dativo_ingest.config import SourceConfig
            source_config = SourceConfig(** config)
            plugin = PluginClass(source_config)
            
            # Discover
            result = plugin.discover()
            return {{
                "statusCode": 200,
                "body": json.dumps(result.to_dict())
            }}
        
        elif operation == "extract":
            # Instantiate plugin
            from dativo_ingest.config import SourceConfig
            source_config = SourceConfig(**config)
            plugin = PluginClass(source_config)
            
            # Extract data (one batch at a time)
            batch_index = event.get("batch_index", 0)
            batches = []
            
            for i, batch in enumerate(plugin.extract()):
                if i == batch_index:
                    batches.append(batch)
                    break
            
            return {{
                "statusCode": 200,
                "body": json.dumps({{
                    "batch": batches[0] if batches else None,
                    "has_more": len(batches) > 0
                }})
            }}
        
        else:
            return {{
                "statusCode": 400,
                "body": json.dumps({{"error": f"Unknown operation: {{operation}}"}})
            }}
    
    except Exception as e:
        import traceback
        return {{
            "statusCode": 500,
            "body": json.dumps({{
                "error": str(e),
                "traceback": traceback.format_exc()
            }})
        }}

# GCP Cloud Functions entry point
def cloud_function_handler(request):
    """GCP Cloud Functions handler."""
    request_json = request.get_json()
    return handle_request(request_json)
'''
        # This will be populated when we know the class name
        return handler_template

    def _package_rust_plugin(self, plugin_path: str) -> bytes:
        """Package Rust plugin into deployment package.

        Args:
            plugin_path: Path to Rust plugin shared library

        Returns:
            ZIP file bytes
        """
        plugin_file = Path(plugin_path)
        if not plugin_file.exists():
            raise ValueError(f"Rust plugin file not found: {plugin_path}")

        # Create ZIP file in memory
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
            # Add Rust shared library
            zipf.write(plugin_file, f"lib/{plugin_file.name}")

            # Add bootstrap script for custom runtime
            bootstrap_code = self._generate_rust_bootstrap()
            zipf.writestr("bootstrap", bootstrap_code)

            # Make bootstrap executable (set file permissions)
            info = zipf.getinfo("bootstrap")
            info.external_attr = 0o755 << 16

        zip_buffer.seek(0)
        return zip_buffer.read()

    def _generate_rust_bootstrap(self) -> str:
        """Generate bootstrap script for Rust custom runtime.

        Returns:
            Bootstrap script as string
        """
        bootstrap_template = '''#!/bin/sh
set -euo pipefail

# Set up environment for Rust plugin
export LD_LIBRARY_PATH="${LD_LIBRARY_PATH}:${LAMBDA_TASK_ROOT}/lib"

# Start Lambda Runtime API handler
python3 handler.py
'''
        return bootstrap_template


class AWSLambdaExecutor(CloudPluginExecutor):
    """AWS Lambda plugin executor."""

    def __init__(self, config: CloudExecutionConfig):
        """Initialize AWS Lambda executor.

        Args:
            config: Cloud execution configuration
        """
        super().__init__(config)
        
        # Import boto3 (optional dependency)
        try:
            import boto3
            self.lambda_client = boto3.client("lambda")
            self.iam_client = boto3.client("iam")
        except ImportError:
            raise ImportError(
                "AWS Lambda support requires boto3. Install with: pip install boto3"
            )

    def deploy_plugin(
        self, plugin_path: str, plugin_type: str, function_name: str
    ) -> str:
        """Deploy plugin to AWS Lambda.

        Args:
            plugin_path: Path to plugin file
            plugin_type: Plugin type ("python" or "rust")
            function_name: Name for the Lambda function

        Returns:
            Lambda function ARN
        """
        logger.info(f"Deploying {plugin_type} plugin to AWS Lambda: {function_name}")

        # Package plugin
        if plugin_type == "python":
            zip_bytes = self._package_python_plugin(plugin_path)
            runtime = self.config.runtime
        elif plugin_type == "rust":
            zip_bytes = self._package_rust_plugin(plugin_path)
            runtime = "provided.al2"  # Custom runtime for Rust
        else:
            raise ValueError(f"Unsupported plugin type: {plugin_type}")

        # Get or create execution role
        role_arn = self.config.aws_config.get("role_arn")
        if not role_arn:
            role_arn = self._create_default_execution_role(function_name)

        # Create or update Lambda function
        try:
            # Try to update existing function
            response = self.lambda_client.update_function_code(
                FunctionName=function_name,
                ZipFile=zip_bytes,
            )
            logger.info(f"Updated existing Lambda function: {function_name}")
        except self.lambda_client.exceptions.ResourceNotFoundException:
            # Create new function
            vpc_config = {}
            if self.config.aws_config.get("security_groups") and self.config.aws_config.get("subnets"):
                vpc_config = {
                    "SecurityGroupIds": self.config.aws_config["security_groups"],
                    "SubnetIds": self.config.aws_config["subnets"],
                }

            response = self.lambda_client.create_function(
                FunctionName=function_name,
                Runtime=runtime,
                Role=role_arn,
                Handler="handler.lambda_handler" if plugin_type == "python" else "bootstrap",
                Code={"ZipFile": zip_bytes},
                Timeout=self.config.timeout_seconds,
                MemorySize=self.config.memory_mb,
                Environment={
                    "Variables": self.config.environment_variables,
                },
                **vpc_config,
            )
            logger.info(f"Created new Lambda function: {function_name}")

        return response["FunctionArn"]

    def invoke_plugin(
        self, function_identifier: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Invoke Lambda function.

        Args:
            function_identifier: Lambda function ARN or name
            payload: Payload to send to function

        Returns:
            Function response
        """
        logger.debug(f"Invoking Lambda function: {function_identifier}")

        response = self.lambda_client.invoke(
            FunctionName=function_identifier,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        # Parse response
        result_payload = json.loads(response["Payload"].read())
        
        if response.get("FunctionError"):
            raise RuntimeError(
                f"Lambda execution failed: {result_payload.get('errorMessage', 'Unknown error')}"
            )

        return result_payload

    def cleanup_plugin(self, function_identifier: str) -> None:
        """Clean up Lambda function.

        Args:
            function_identifier: Lambda function ARN or name
        """
        logger.info(f"Cleaning up Lambda function: {function_identifier}")
        
        try:
            self.lambda_client.delete_function(FunctionName=function_identifier)
        except Exception as e:
            logger.warning(f"Failed to delete Lambda function: {e}")

    def _create_default_execution_role(self, function_name: str) -> str:
        """Create default Lambda execution role.

        Args:
            function_name: Function name

        Returns:
            Role ARN
        """
        role_name = f"{function_name}-execution-role"
        
        assume_role_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"Service": "lambda.amazonaws.com"},
                    "Action": "sts:AssumeRole",
                }
            ],
        }

        try:
            response = self.iam_client.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(assume_role_policy),
                Description=f"Execution role for {function_name}",
            )
            role_arn = response["Role"]["Arn"]

            # Attach basic Lambda execution policy
            self.iam_client.attach_role_policy(
                RoleName=role_name,
                PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
            )

            # Wait for role to be available
            time.sleep(10)

            return role_arn
        except self.iam_client.exceptions.EntityAlreadyExistsException:
            response = self.iam_client.get_role(RoleName=role_name)
            return response["Role"]["Arn"]


class GCPCloudFunctionsExecutor(CloudPluginExecutor):
    """GCP Cloud Functions plugin executor."""

    def __init__(self, config: CloudExecutionConfig):
        """Initialize GCP Cloud Functions executor.

        Args:
            config: Cloud execution configuration
        """
        super().__init__(config)
        
        # Import google-cloud-functions (optional dependency)
        try:
            from google.cloud import functions_v2
            from google.cloud import storage
            
            self.project_id = config.gcp_config.get("project_id")
            if not self.project_id:
                raise ValueError("GCP project_id is required in gcp_config")
            
            self.region = config.gcp_config.get("region", "us-central1")
            
            self.functions_client = functions_v2.FunctionServiceClient()
            self.storage_client = storage.Client()
        except ImportError:
            raise ImportError(
                "GCP Cloud Functions support requires google-cloud-functions and google-cloud-storage. "
                "Install with: pip install google-cloud-functions google-cloud-storage"
            )

    def deploy_plugin(
        self, plugin_path: str, plugin_type: str, function_name: str
    ) -> str:
        """Deploy plugin to GCP Cloud Functions.

        Args:
            plugin_path: Path to plugin file
            plugin_type: Plugin type ("python" or "rust")
            function_name: Name for the Cloud Function

        Returns:
            Cloud Function URL
        """
        logger.info(f"Deploying {plugin_type} plugin to GCP Cloud Functions: {function_name}")

        # Package plugin
        if plugin_type == "python":
            zip_bytes = self._package_python_plugin(plugin_path)
            runtime = self.config.runtime
            entry_point = "cloud_function_handler"
        elif plugin_type == "rust":
            zip_bytes = self._package_rust_plugin(plugin_path)
            runtime = "python311"  # Use Python runtime with custom bootstrap
            entry_point = "cloud_function_handler"
        else:
            raise ValueError(f"Unsupported plugin type: {plugin_type}")

        # Upload to GCS
        bucket_name = f"{self.project_id}-plugin-packages"
        blob_name = f"{function_name}-{hashlib.md5(zip_bytes).hexdigest()}.zip"
        
        bucket = self._get_or_create_bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_string(zip_bytes)

        # Deploy Cloud Function
        from google.cloud import functions_v2
        
        parent = f"projects/{self.project_id}/locations/{self.region}"
        function_id = function_name
        
        function = functions_v2.Function()
        function.name = f"{parent}/functions/{function_id}"
        function.build_config = functions_v2.BuildConfig()
        function.build_config.runtime = runtime
        function.build_config.entry_point = entry_point
        function.build_config.source = functions_v2.Source()
        function.build_config.source.storage_source = functions_v2.StorageSource()
        function.build_config.source.storage_source.bucket = bucket_name
        function.build_config.source.storage_source.object_ = blob_name
        
        function.service_config = functions_v2.ServiceConfig()
        function.service_config.timeout_seconds = self.config.timeout_seconds
        function.service_config.available_memory = f"{self.config.memory_mb}M"
        function.service_config.environment_variables = self.config.environment_variables

        if self.config.gcp_config.get("service_account"):
            function.service_config.service_account_email = self.config.gcp_config["service_account"]

        request = functions_v2.CreateFunctionRequest()
        request.parent = parent
        request.function = function
        request.function_id = function_id

        try:
            operation = self.functions_client.create_function(request=request)
            response = operation.result()
            logger.info(f"Created Cloud Function: {function_name}")
            return response.service_config.uri
        except Exception as e:
            logger.error(f"Failed to create Cloud Function: {e}")
            raise

    def invoke_plugin(
        self, function_identifier: str, payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Invoke Cloud Function.

        Args:
            function_identifier: Cloud Function URL
            payload: Payload to send to function

        Returns:
            Function response
        """
        logger.debug(f"Invoking Cloud Function: {function_identifier}")

        import requests
        
        response = requests.post(
            function_identifier,
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        
        response.raise_for_status()
        return response.json()

    def cleanup_plugin(self, function_identifier: str) -> None:
        """Clean up Cloud Function.

        Args:
            function_identifier: Cloud Function name
        """
        logger.info(f"Cleaning up Cloud Function: {function_identifier}")
        
        try:
            from google.cloud import functions_v2
            
            request = functions_v2.DeleteFunctionRequest()
            request.name = function_identifier
            
            operation = self.functions_client.delete_function(request=request)
            operation.result()
        except Exception as e:
            logger.warning(f"Failed to delete Cloud Function: {e}")

    def _get_or_create_bucket(self, bucket_name: str):
        """Get or create GCS bucket.

        Args:
            bucket_name: Bucket name

        Returns:
            Bucket object
        """
        try:
            bucket = self.storage_client.get_bucket(bucket_name)
        except Exception:
            bucket = self.storage_client.create_bucket(bucket_name, location=self.region)
        
        return bucket


class CloudReaderWrapper(BaseReader):
    """Wrapper for cloud-executed reader plugins."""

    def __init__(
        self,
        source_config,
        plugin_path: str,
        plugin_type: str,
        executor: CloudPluginExecutor,
    ):
        """Initialize cloud reader wrapper.

        Args:
            source_config: Source configuration
            plugin_path: Path to plugin file
            plugin_type: Plugin type ("python" or "rust")
            executor: Cloud plugin executor
        """
        super().__init__(source_config)
        self.plugin_path = plugin_path
        self.plugin_type = plugin_type
        self.executor = executor
        self.function_identifier = None
        self._deployed = False

    def _ensure_deployed(self):
        """Ensure plugin is deployed to cloud."""
        if not self._deployed:
            # Generate function name
            plugin_hash = hashlib.md5(self.plugin_path.encode()).hexdigest()[:8]
            function_name = f"dativo-reader-{plugin_hash}"

            # Deploy plugin
            self.function_identifier = self.executor.deploy_plugin(
                self.plugin_path, self.plugin_type, function_name
            )
            self._deployed = True

    def check_connection(self):
        """Check connection via cloud function."""
        from .plugins import ConnectionTestResult
        
        self._ensure_deployed()

        try:
            # Prepare payload
            payload = {
                "operation": "check_connection",
                "config": {
                    "type": self.source_config.type,
                    "connection": self.source_config.connection or {},
                    "credentials": self.source_config.credentials or {},
                    "objects": self.source_config.objects or [],
                    "files": self.source_config.files or [],
                    "incremental": self.source_config.incremental or {},
                    "engine": self.source_config.engine or {},
                },
            }

            # Invoke cloud function
            response = self.executor.invoke_plugin(self.function_identifier, payload)
            
            # Parse response
            body = json.loads(response.get("body", "{}"))
            return ConnectionTestResult(**body)
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Cloud execution failed: {str(e)}",
                error_code="CLOUD_EXECUTION_ERROR",
            )

    def discover(self):
        """Discover via cloud function."""
        from .plugins import DiscoveryResult
        
        self._ensure_deployed()

        # Prepare payload
        payload = {
            "operation": "discover",
            "config": {
                "type": self.source_config.type,
                "connection": self.source_config.connection or {},
                "credentials": self.source_config.credentials or {},
                "objects": self.source_config.objects or [],
                "files": self.source_config.files or [],
                "incremental": self.source_config.incremental or {},
                "engine": self.source_config.engine or {},
            },
        }

        # Invoke cloud function
        response = self.executor.invoke_plugin(self.function_identifier, payload)
        
        # Parse response
        body = json.loads(response.get("body", "{}"))
        return DiscoveryResult(**body)

    def extract(self, state_manager=None) -> Iterator[List[Dict[str, Any]]]:
        """Extract data via cloud function."""
        self._ensure_deployed()

        batch_index = 0
        while True:
            # Prepare payload
            payload = {
                "operation": "extract",
                "batch_index": batch_index,
                "config": {
                    "type": self.source_config.type,
                    "connection": self.source_config.connection or {},
                    "credentials": self.source_config.credentials or {},
                    "objects": self.source_config.objects or [],
                    "files": self.source_config.files or [],
                    "incremental": self.source_config.incremental or {},
                    "engine": self.source_config.engine or {},
                },
            }

            # Invoke cloud function
            response = self.executor.invoke_plugin(self.function_identifier, payload)
            
            # Parse response
            body = json.loads(response.get("body", "{}"))
            batch = body.get("batch")
            has_more = body.get("has_more", False)

            if batch:
                yield batch
            
            if not has_more:
                break

            batch_index += 1

    def __del__(self):
        """Clean up cloud resources."""
        if self._deployed and self.function_identifier:
            try:
                self.executor.cleanup_plugin(self.function_identifier)
            except Exception as e:
                logger.warning(f"Failed to cleanup cloud plugin: {e}")


class CloudWriterWrapper(BaseWriter):
    """Wrapper for cloud-executed writer plugins."""

    def __init__(
        self,
        asset_definition,
        target_config,
        output_base: str,
        plugin_path: str,
        plugin_type: str,
        executor: CloudPluginExecutor,
    ):
        """Initialize cloud writer wrapper.

        Args:
            asset_definition: Asset definition
            target_config: Target configuration
            output_base: Base output path
            plugin_path: Path to plugin file
            plugin_type: Plugin type ("python" or "rust")
            executor: Cloud plugin executor
        """
        super().__init__(asset_definition, target_config, output_base)
        self.plugin_path = plugin_path
        self.plugin_type = plugin_type
        self.executor = executor
        self.function_identifier = None
        self._deployed = False

    def _ensure_deployed(self):
        """Ensure plugin is deployed to cloud."""
        if not self._deployed:
            # Generate function name
            plugin_hash = hashlib.md5(self.plugin_path.encode()).hexdigest()[:8]
            function_name = f"dativo-writer-{plugin_hash}"

            # Deploy plugin
            self.function_identifier = self.executor.deploy_plugin(
                self.plugin_path, self.plugin_type, function_name
            )
            self._deployed = True

    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write batch via cloud function."""
        self._ensure_deployed()

        # Prepare payload
        payload = {
            "operation": "write_batch",
            "records": records,
            "file_counter": file_counter,
            "config": {
                "asset_name": self.asset_definition.name,
                "schema": getattr(self.asset_definition, "schema", []),
                "output_base": self.output_base,
                "target_type": self.target_config.type,
                "connection": self.target_config.connection or {},
                "file_format": self.target_config.file_format,
                "engine": self.target_config.engine or {},
            },
        }

        # Invoke cloud function
        response = self.executor.invoke_plugin(self.function_identifier, payload)
        
        # Parse response
        body = json.loads(response.get("body", "{}"))
        return body.get("metadata", [])

    def __del__(self):
        """Clean up cloud resources."""
        if self._deployed and self.function_identifier:
            try:
                self.executor.cleanup_plugin(self.function_identifier)
            except Exception as e:
                logger.warning(f"Failed to cleanup cloud plugin: {e}")


def create_cloud_executor(config: CloudExecutionConfig) -> CloudPluginExecutor:
    """Create cloud plugin executor based on configuration.

    Args:
        config: Cloud execution configuration

    Returns:
        Cloud plugin executor

    Raises:
        ValueError: If provider is not supported
    """
    if config.provider == "aws":
        return AWSLambdaExecutor(config)
    elif config.provider == "gcp":
        return GCPCloudFunctionsExecutor(config)
    else:
        raise ValueError(f"Unsupported cloud provider: {config.provider}")


def create_cloud_reader_wrapper(
    plugin_path: str,
    plugin_type: str,
    config: CloudExecutionConfig,
) -> Type[BaseReader]:
    """Create cloud reader wrapper class.

    Args:
        plugin_path: Path to plugin file
        plugin_type: Plugin type ("python" or "rust")
        config: Cloud execution configuration

    Returns:
        Cloud reader wrapper class
    """
    executor = create_cloud_executor(config)

    class DynamicCloudReader(CloudReaderWrapper):
        def __init__(self, source_config):
            super().__init__(source_config, plugin_path, plugin_type, executor)

    return DynamicCloudReader


def create_cloud_writer_wrapper(
    plugin_path: str,
    plugin_type: str,
    config: CloudExecutionConfig,
) -> Type[BaseWriter]:
    """Create cloud writer wrapper class.

    Args:
        plugin_path: Path to plugin file
        plugin_type: Plugin type ("python" or "rust")
        config: Cloud execution configuration

    Returns:
        Cloud writer wrapper class
    """
    executor = create_cloud_executor(config)

    class DynamicCloudWriter(CloudWriterWrapper):
        def __init__(self, asset_definition, target_config, output_base):
            super().__init__(
                asset_definition, target_config, output_base, plugin_path, plugin_type, executor
            )

    return DynamicCloudWriter
