"""LLM-powered metadata generation utilities for Dativo ingestion jobs."""

from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, Optional

import requests
from requests import Response

from .config import AssetDefinition, LLMMetadataConfig, SourceConfig

DEFAULT_SYSTEM_PROMPT = """You are a data product metadata assistant.
- Read the source API definition and ODCS data contract context.
- Summarize what the dataset represents, how it should be used, and any governance concerns.
- Recommend data quality checks that would increase trust in downstream analytics and AI workloads.
- Identify important columns and propose semantic descriptions / business terms for each.
- Call out PII / sensitive data handling expectations explicitly."""

OPENAI_CHAT_ENDPOINT = "https://api.openai.com/v1/chat/completions"


class SourceMetadataGenerator:
    """Generate enriched metadata for a job using an LLM provider."""

    def __init__(self, config: LLMMetadataConfig, logger: Optional[logging.Logger] = None) -> None:
        if not config.enabled:
            raise ValueError("SourceMetadataGenerator requires llm_metadata.enabled=true")
        self.config = config
        self.logger = logger or logging.getLogger(__name__)
        self._instructions = self._load_instructions()
        self._session = requests.Session()

    def generate(
        self,
        asset_definition: AssetDefinition,
        source_config: SourceConfig,
    ) -> Optional[Dict[str, Any]]:
        """Generate metadata for the provided asset/source context."""
        try:
            prompt = self._build_user_prompt(asset_definition, source_config)
            response = self._call_llm(prompt)
            metadata = self._parse_response(response)
            if not metadata:
                self.logger.warning(
                    "LLM metadata generation returned no parsable content",
                    extra={"event_type": "llm_metadata_empty_response"},
                )
                return None

            artifact_path = self._persist_metadata(asset_definition, metadata)
            return {
                "metadata": metadata,
                "artifact_path": str(artifact_path) if artifact_path else None,
            }
        except Exception as exc:  # pragma: no cover - logged upstream
            self.logger.warning(
                f"LLM metadata generation failed: {exc}",
                extra={"event_type": "llm_metadata_failure"},
            )
            raise

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------
    def _load_instructions(self) -> str:
        """Load system prompt instructions from file or default template."""
        if self.config.prompt_template_path:
            template_path = Path(self.config.prompt_template_path)
            if not template_path.exists():
                raise FileNotFoundError(
                    f"LLM prompt template not found: {template_path}"
                )
            return template_path.read_text(encoding="utf-8").strip()
        return DEFAULT_SYSTEM_PROMPT.strip()

    def _build_user_prompt(
        self, asset_definition: AssetDefinition, source_config: SourceConfig
    ) -> str:
        """Build user prompt context from source API definition and schema."""
        schema_lines = []
        for field in asset_definition.schema:
            name = field.get("name")
            dtype = field.get("type", "string")
            required = field.get("required", False)
            description = field.get("description")
            line = f"- {name} ({dtype}) | required={required}"
            if description:
                line += f" | description={description}"
            schema_lines.append(line)
        schema_section = "\n".join(schema_lines)

        asset_context = asset_definition.model_dump(
            include={
                "name",
                "version",
                "domain",
                "dataProduct",
                "description",
                "tags",
                "team",
                "compliance",
            },
            exclude_none=True,
        )

        source_context = self._sanitize_source_config(source_config)

        prompt = (
            "Source API definition (redacted credentials):\n"
            f"{json.dumps(source_context, indent=2)}\n\n"
            "Asset contract context:\n"
            f"{json.dumps(asset_context, indent=2)}\n\n"
            "Schema fields:\n"
            f"{schema_section}\n\n"
            "Respond with JSON shaped as:\n"
            '{\n'
            '  "dataset_summary": "<overview>",\n'
            '  "pii_risk_assessment": "<risk level>",\n'
            '  "data_quality_recommendations": ["list", "of", "checks"],\n'
            '  "semantic_columns": [\n'
            '      {"name": "<column>", "description": "<short text>", "business_term": "<term>"}\n'
            "  ]\n"
            "}\n"
            "Summaries should be concise and refer to the context provided."
        )
        return prompt

    def _sanitize_source_config(self, source_config: SourceConfig) -> Dict[str, Any]:
        """Remove sensitive information before sharing configs with the LLM."""
        data = source_config.model_dump(exclude_none=True)
        for sensitive_key in ("credentials", "connection", "dsn"):
            if sensitive_key in data:
                data[sensitive_key] = "[REDACTED]"
        return data

    def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """Invoke the configured LLM provider."""
        endpoint = self.config.endpoint or self._default_endpoint()
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        if self.config.organization:
            headers["OpenAI-Organization"] = self.config.organization
        if self.config.project:
            headers["OpenAI-Project"] = self.config.project

        payload = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_output_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": self._instructions},
                {"role": "user", "content": prompt},
            ],
        }

        response: Response = self._session.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        return response.json()

    def _default_endpoint(self) -> str:
        """Resolve endpoint for supported providers."""
        if self.config.provider.lower() == "openai":
            return OPENAI_CHAT_ENDPOINT
        raise ValueError(f"Unsupported LLM provider: {self.config.provider}")

    def _parse_response(self, response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parse JSON metadata payload from LLM response."""
        try:
            content = response["choices"][0]["message"]["content"]
            if not content:
                return None
            metadata = json.loads(content)
        except (KeyError, IndexError, json.JSONDecodeError):
            return None

        metadata.setdefault("dataset_summary", "")
        metadata.setdefault("pii_risk_assessment", "not_provided")
        metadata.setdefault("data_quality_recommendations", [])
        metadata.setdefault("semantic_columns", [])
        return metadata

    def _persist_metadata(
        self, asset_definition: AssetDefinition, metadata: Dict[str, Any]
    ) -> Optional[Path]:
        """Persist generated metadata to disk for auditability."""
        if not self.config.persist_artifact:
            return None

        output_dir = Path(
            self.config.output_dir or os.getenv("LLM_METADATA_OUTPUT_DIR", ".local/metadata")
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{asset_definition.name}_llm_metadata.json"
        output_path = output_dir / filename

        payload = {
            "asset": asset_definition.name,
            "generated_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "provider": self.config.provider,
            "model": self.config.model,
            "metadata": metadata,
        }

        output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return output_path

