"""LLM-based metadata generation for data assets.

This module provides functionality to enhance asset metadata using Large Language Models (LLMs).
Inspired by the Intelligence Lake concept, it generates rich semantic metadata from source
API definitions, schema information, and sample data to improve data discoverability and governance.
"""

import json
import os
from typing import Any, Dict, List, Optional

from .config import AssetDefinition, SourceConfig
from .logging import get_logger


class LLMMetadataGenerator:
    """Generate enhanced metadata for data assets using LLMs.
    
    Supports multiple LLM providers:
    - OpenAI (GPT-3.5, GPT-4)
    - Anthropic (Claude)
    - AWS Bedrock (various models)
    - Azure OpenAI
    """
    
    def __init__(self, llm_config: Dict[str, Any]):
        """Initialize LLM metadata generator.
        
        Args:
            llm_config: LLM configuration dictionary containing:
                - provider: LLM provider (openai, anthropic, bedrock, azure)
                - model: Model identifier
                - api_key: API key (can be env var reference)
                - endpoint: Optional custom endpoint
                - temperature: Optional temperature setting (default: 0.3)
                - max_tokens: Optional max tokens (default: 2000)
        
        Raises:
            ValueError: If configuration is invalid
        """
        self.logger = get_logger()
        self.config = llm_config
        
        # Validate required fields
        if not llm_config.get("provider"):
            raise ValueError("LLM provider is required")
        if not llm_config.get("model"):
            raise ValueError("LLM model is required")
        
        # Resolve credentials
        self.provider = llm_config["provider"]
        self.model = llm_config["model"]
        self.api_key = self._resolve_credential(llm_config.get("api_key", ""))
        self.endpoint = llm_config.get("endpoint")
        self.temperature = llm_config.get("temperature", 0.3)
        self.max_tokens = llm_config.get("max_tokens", 2000)
        
        # Validate provider-specific requirements
        self._validate_provider_config()
        
        self.logger.info(
            f"Initialized LLM metadata generator",
            extra={
                "provider": self.provider,
                "model": self.model,
                "event_type": "llm_generator_initialized",
            },
        )
    
    def _resolve_credential(self, credential: str) -> str:
        """Resolve credential from environment variable if needed.
        
        Args:
            credential: Credential string or env var reference
        
        Returns:
            Resolved credential value
        """
        if not credential:
            return ""
        
        # Check if it's an environment variable reference
        if credential.startswith("${") and credential.endswith("}"):
            env_var = credential[2:-1]
            return os.getenv(env_var, "")
        elif credential.startswith("$"):
            env_var = credential[1:]
            return os.getenv(env_var, "")
        
        return credential
    
    def _validate_provider_config(self) -> None:
        """Validate provider-specific configuration.
        
        Raises:
            ValueError: If configuration is invalid for the provider
        """
        if self.provider in ["openai", "azure"]:
            if not self.api_key:
                raise ValueError(f"{self.provider} provider requires api_key")
        elif self.provider == "anthropic":
            if not self.api_key:
                raise ValueError("Anthropic provider requires api_key")
        elif self.provider == "bedrock":
            # Bedrock uses AWS credentials from environment
            if not os.getenv("AWS_ACCESS_KEY_ID") and not os.getenv("AWS_PROFILE"):
                raise ValueError(
                    "Bedrock provider requires AWS credentials "
                    "(AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY or AWS_PROFILE)"
                )
    
    def _call_llm(self, prompt: str) -> str:
        """Call the configured LLM with the given prompt.
        
        Args:
            prompt: Prompt to send to the LLM
        
        Returns:
            LLM response text
        
        Raises:
            Exception: If LLM call fails
        """
        try:
            if self.provider == "openai":
                return self._call_openai(prompt)
            elif self.provider == "anthropic":
                return self._call_anthropic(prompt)
            elif self.provider == "bedrock":
                return self._call_bedrock(prompt)
            elif self.provider == "azure":
                return self._call_azure_openai(prompt)
            else:
                raise ValueError(f"Unsupported LLM provider: {self.provider}")
        except Exception as e:
            self.logger.error(
                f"LLM call failed: {e}",
                extra={
                    "provider": self.provider,
                    "model": self.model,
                    "event_type": "llm_call_failed",
                },
            )
            raise
    
    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API.
        
        Args:
            prompt: Prompt to send
        
        Returns:
            Response text
        """
        try:
            import openai
            
            client = openai.OpenAI(api_key=self.api_key)
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data catalog expert that generates high-quality metadata for data assets.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            return response.choices[0].message.content
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install openai"
            )
    
    def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Claude API.
        
        Args:
            prompt: Prompt to send
        
        Returns:
            Response text
        """
        try:
            import anthropic
            
            client = anthropic.Anthropic(api_key=self.api_key)
            
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                system="You are a data catalog expert that generates high-quality metadata for data assets.",
                messages=[{"role": "user", "content": prompt}],
            )
            
            return message.content[0].text
        except ImportError:
            raise ImportError(
                "Anthropic package not installed. Install with: pip install anthropic"
            )
    
    def _call_bedrock(self, prompt: str) -> str:
        """Call AWS Bedrock API.
        
        Args:
            prompt: Prompt to send
        
        Returns:
            Response text
        """
        try:
            import boto3
            
            bedrock_runtime = boto3.client(
                service_name="bedrock-runtime",
                region_name=os.getenv("AWS_REGION", "us-east-1"),
            )
            
            # Format varies by model - handle common ones
            if "anthropic.claude" in self.model:
                body = json.dumps({
                    "prompt": f"\n\nHuman: You are a data catalog expert. {prompt}\n\nAssistant:",
                    "max_tokens_to_sample": self.max_tokens,
                    "temperature": self.temperature,
                })
            elif "amazon.titan" in self.model:
                body = json.dumps({
                    "inputText": prompt,
                    "textGenerationConfig": {
                        "maxTokenCount": self.max_tokens,
                        "temperature": self.temperature,
                    },
                })
            else:
                raise ValueError(f"Unsupported Bedrock model: {self.model}")
            
            response = bedrock_runtime.invoke_model(
                modelId=self.model,
                body=body,
            )
            
            response_body = json.loads(response["body"].read())
            
            # Extract text based on model
            if "anthropic.claude" in self.model:
                return response_body.get("completion", "")
            elif "amazon.titan" in self.model:
                results = response_body.get("results", [])
                return results[0].get("outputText", "") if results else ""
            
            return ""
        except ImportError:
            raise ImportError(
                "Boto3 package not installed. Install with: pip install boto3"
            )
    
    def _call_azure_openai(self, prompt: str) -> str:
        """Call Azure OpenAI API.
        
        Args:
            prompt: Prompt to send
        
        Returns:
            Response text
        """
        try:
            import openai
            
            if not self.endpoint:
                raise ValueError("Azure OpenAI requires endpoint configuration")
            
            client = openai.AzureOpenAI(
                api_key=self.api_key,
                api_version="2024-02-01",
                azure_endpoint=self.endpoint,
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a data catalog expert that generates high-quality metadata for data assets.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=self.temperature,
                max_tokens=self.max_tokens,
            )
            
            return response.choices[0].message.content
        except ImportError:
            raise ImportError(
                "OpenAI package not installed. Install with: pip install openai"
            )
    
    def generate_metadata(
        self,
        asset_definition: AssetDefinition,
        source_config: SourceConfig,
        sample_records: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Generate enhanced metadata for a data asset using LLM.
        
        Args:
            asset_definition: Asset definition with schema
            source_config: Source connector configuration
            sample_records: Optional sample records for better context
        
        Returns:
            Dictionary containing generated metadata:
                - description_enhanced: Enhanced description
                - business_purpose: Business purpose and use cases
                - data_quality_expectations: Suggested quality rules
                - related_assets: Suggested related assets
                - semantic_tags: Semantic tags for discoverability
                - sample_queries: Example queries
                - lineage_hints: Data lineage information
        """
        self.logger.info(
            "Generating LLM-enhanced metadata",
            extra={
                "asset_name": asset_definition.name,
                "source_type": source_config.type,
                "event_type": "llm_generation_started",
            },
        )
        
        # Build comprehensive prompt
        prompt = self._build_metadata_prompt(
            asset_definition, source_config, sample_records
        )
        
        # Call LLM
        try:
            response_text = self._call_llm(prompt)
            
            # Parse JSON response
            metadata = self._parse_llm_response(response_text)
            
            self.logger.info(
                "LLM metadata generation completed",
                extra={
                    "asset_name": asset_definition.name,
                    "metadata_keys": list(metadata.keys()),
                    "event_type": "llm_generation_completed",
                },
            )
            
            return metadata
        except Exception as e:
            self.logger.error(
                f"Failed to generate LLM metadata: {e}",
                extra={
                    "asset_name": asset_definition.name,
                    "event_type": "llm_generation_failed",
                },
            )
            # Return empty metadata rather than failing the job
            return {}
    
    def _build_metadata_prompt(
        self,
        asset_definition: AssetDefinition,
        source_config: SourceConfig,
        sample_records: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """Build a comprehensive prompt for metadata generation.
        
        Args:
            asset_definition: Asset definition
            source_config: Source configuration
            sample_records: Optional sample records
        
        Returns:
            Formatted prompt string
        """
        # Extract schema information
        schema_summary = []
        for field in asset_definition.schema:
            field_info = f"- {field['name']}: {field.get('type', 'unknown')}"
            if field.get('required'):
                field_info += " (required)"
            if field.get('description'):
                field_info += f" - {field['description']}"
            schema_summary.append(field_info)
        
        schema_text = "\n".join(schema_summary)
        
        # Build sample data context
        sample_text = ""
        if sample_records and len(sample_records) > 0:
            # Take first 3 records as examples
            sample_text = "\n\nSample Records:\n"
            for i, record in enumerate(sample_records[:3], 1):
                sample_text += f"\nRecord {i}:\n"
                sample_text += json.dumps(record, indent=2, default=str)
        
        # Build existing metadata context
        existing_description = ""
        if asset_definition.description:
            if hasattr(asset_definition.description, 'purpose') and asset_definition.description.purpose:
                existing_description = f"\n\nExisting Description: {asset_definition.description.purpose}"
        
        # Build prompt
        prompt = f"""Analyze this data asset and generate comprehensive metadata to improve discoverability and governance.

Asset Information:
- Name: {asset_definition.name}
- Source Type: {source_config.type}
- Object: {asset_definition.object}
- Domain: {asset_definition.domain or 'Not specified'}
- Data Product: {getattr(asset_definition, 'dataProduct', 'Not specified')}
{existing_description}

Schema:
{schema_text}
{sample_text}

Generate a comprehensive metadata analysis in JSON format with the following structure:

{{
  "description_enhanced": "A clear, concise description of what this dataset contains and its primary purpose (2-3 sentences)",
  "business_purpose": "Business use cases and value this data provides to stakeholders",
  "data_quality_expectations": [
    "Expected quality rule 1 (e.g., 'Customer email should be valid format')",
    "Expected quality rule 2",
    "Expected quality rule 3"
  ],
  "semantic_tags": [
    "tag1",
    "tag2",
    "tag3"
  ],
  "sample_queries": [
    "Example analytical question 1 that can be answered with this data",
    "Example analytical question 2"
  ],
  "lineage_hints": "Upstream sources and downstream consumers (if inferable from context)",
  "related_assets_hints": [
    "Suggested related datasets or tables based on schema and purpose"
  ],
  "sensitive_fields": [
    "List of field names that appear to contain sensitive/PII data"
  ],
  "optimization_suggestions": "Recommendations for partitioning, indexing, or performance optimization"
}}

Important:
- Be specific and actionable in your recommendations
- Base suggestions on the schema and sample data provided
- If sample data is not available, infer from schema and field names
- Return ONLY valid JSON, no additional text
"""
        
        return prompt
    
    def _parse_llm_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM response into structured metadata.
        
        Args:
            response_text: Raw LLM response
        
        Returns:
            Parsed metadata dictionary
        
        Raises:
            ValueError: If response cannot be parsed
        """
        try:
            # Try to extract JSON from response (in case there's extra text)
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_text = response_text[json_start:json_end]
                metadata = json.loads(json_text)
                return metadata
            else:
                raise ValueError("No JSON found in response")
        except json.JSONDecodeError as e:
            self.logger.error(
                f"Failed to parse LLM response as JSON: {e}",
                extra={"response_preview": response_text[:200]},
            )
            raise ValueError(f"Invalid JSON in LLM response: {e}")
    
    def enrich_asset_definition(
        self,
        asset_definition: AssetDefinition,
        generated_metadata: Dict[str, Any],
    ) -> AssetDefinition:
        """Enrich asset definition with LLM-generated metadata.
        
        Args:
            asset_definition: Original asset definition
            generated_metadata: Metadata generated by LLM
        
        Returns:
            Enriched asset definition
        """
        # Update description if enhanced version is available
        if generated_metadata.get("description_enhanced"):
            if not asset_definition.description:
                from .config import DescriptionModel
                asset_definition.description = DescriptionModel()
            
            # Keep original purpose if exists, otherwise use enhanced
            if not asset_definition.description.purpose:
                asset_definition.description.purpose = generated_metadata["description_enhanced"]
            
            # Add business purpose to usage
            if generated_metadata.get("business_purpose"):
                asset_definition.description.usage = generated_metadata["business_purpose"]
        
        # Add semantic tags
        if generated_metadata.get("semantic_tags"):
            existing_tags = set(asset_definition.tags or [])
            new_tags = set(generated_metadata["semantic_tags"])
            asset_definition.tags = list(existing_tags | new_tags)
        
        # Add data quality expectations if available
        if generated_metadata.get("data_quality_expectations"):
            if not asset_definition.data_quality:
                from .config import DataQualityModel
                asset_definition.data_quality = DataQualityModel()
            
            # Convert expectations to Great Expectations format (simplified)
            if not asset_definition.data_quality.expectations:
                asset_definition.data_quality.expectations = []
            
            for expectation in generated_metadata["data_quality_expectations"]:
                asset_definition.data_quality.expectations.append({
                    "description": expectation,
                    "source": "llm_generated"
                })
        
        # Update compliance with sensitive fields
        if generated_metadata.get("sensitive_fields"):
            if not asset_definition.compliance:
                from .config import ComplianceModel
                asset_definition.compliance = ComplianceModel()
            
            # Mark classification if sensitive fields detected
            if not asset_definition.compliance.classification:
                asset_definition.compliance.classification = ["PII"]
        
        # Store full LLM metadata in target config for downstream use
        # This allows other systems to access the full generated metadata
        if not asset_definition.target:
            asset_definition.target = {}
        
        asset_definition.target["llm_metadata"] = {
            "generated_at": "timestamp",  # Will be set by caller
            "provider": self.provider,
            "model": self.model,
            **generated_metadata,
        }
        
        self.logger.info(
            "Asset definition enriched with LLM metadata",
            extra={
                "asset_name": asset_definition.name,
                "tags_added": len(generated_metadata.get("semantic_tags", [])),
                "event_type": "asset_enriched",
            },
        )
        
        return asset_definition
