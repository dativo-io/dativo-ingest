"""LLM-powered metadata generation for ingestion jobs."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from typing import Any, Dict, Optional

import requests
import yaml

from .config import AssetDefinition, MetadataGenerationConfig, SourceConfig
from .logging import get_logger


class MetadataGenerator:
    """Generate enriched metadata for an asset using an LLM."""

    DEFAULT_SYSTEM_PROMPT = (
        "You are an expert data product architect. Given a source API definition and job context, "
        "produce concise metadata that helps data teams understand the dataset. "
        "Respond in JSON with keys: summary (string), recommended_tags (list of strings), "
        "field_insights (list of objects with 'field' and 'description'), "
        "and data_quality_notes (string). Keep responses under 800 characters per field."
    )

    DEFAULT_USER_TEMPLATE = textwrap.dedent(
        """
        Dataset name: {asset_name}
        Domain: {domain}
        Tenant: {tenant}
        Source type: {source_type}
        Source objects: {source_objects}
        Target platform: {target}

        Source API definition (truncated):
        {api_definition}
        """
    ).strip()

    def __init__(
        self,
        config: MetadataGenerationConfig,
        asset_definition: AssetDefinition,
        source_config: SourceConfig,
        logger=None,
    ) -> None:
        if not config.enabled:
            raise ValueError("MetadataGenerationConfig must be enabled to use MetadataGenerator")

        self.config = config
        self.asset_definition = asset_definition
        self.source_config = source_config
        self.logger = logger or get_logger()

    def generate(self) -> Dict[str, Any]:
        """Generate enriched metadata dictionary."""
        api_definition = self._load_api_definition()
        prompt = self._build_prompt(api_definition)
        raw_response = self._invoke_llm(prompt)
        structured = self._parse_response(raw_response)

        # Attach context for downstream consumers
        structured.setdefault("source_type", self.source_config.type)
        structured.setdefault("asset_name", self.asset_definition.name)
        structured.setdefault("tenant_id", self.asset_definition.tenant)

        return structured

    def _load_api_definition(self) -> str:
        """Load API definition content as a trimmed string."""
        path_str = self.config.source_api_definition_path
        if not path_str:
            raise ValueError("Source API definition path is required for metadata generation")

        path = Path(path_str)
        if not path.exists():
            raise FileNotFoundError(f"Source API definition not found: {path}")

        content: Any
        if path.suffix.lower() in {".yaml", ".yml"}:
            content = yaml.safe_load(path.read_text())
            serialized = yaml.safe_dump(content, sort_keys=False)
        elif path.suffix.lower() == ".json":
            content = json.loads(path.read_text())
            serialized = json.dumps(content, indent=2)
        else:
            serialized = path.read_text()

        max_chars = self.config.max_api_chars or 5000
        if len(serialized) > max_chars:
            truncated = serialized[:max_chars]
            return f"{truncated}\n... (truncated {len(serialized) - max_chars} characters)"

        return serialized

    def _build_prompt(self, api_definition: str) -> Dict[str, str]:
        """Build system and user prompts for the LLM."""
        template = self.config.prompt_template or self.DEFAULT_USER_TEMPLATE
        source_objects = self._stringify_objects()
        target = getattr(self.asset_definition, "dataProduct", None) or self.source_config.type

        user_prompt = template.format(
            asset_name=self.asset_definition.name,
            domain=self.asset_definition.domain or "default",
            tenant=self.asset_definition.tenant or "unknown",
            source_type=self.source_config.type,
            source_objects=source_objects,
            target=target,
            api_definition=api_definition,
        )

        return {
            "system": self.DEFAULT_SYSTEM_PROMPT,
            "user": user_prompt,
        }

    def _stringify_objects(self) -> str:
        """Convert configured source objects to a string."""
        objects = getattr(self.source_config, "objects", None)
        if not objects and isinstance(self.source_config, dict):
            objects = self.source_config.get("objects")

        if not objects:
            return "unspecified"
        if isinstance(objects, (list, tuple)):
            return ", ".join(str(obj) for obj in objects)
        return str(objects)

    def _invoke_llm(self, prompt: Dict[str, str]) -> str:
        """Invoke the configured LLM provider."""
        if not self.config.llm:
            raise ValueError("LLM configuration missing")

        provider = (self.config.llm.provider or "openai").lower()
        if provider == "openai":
            return self._call_openai(prompt)

        raise ValueError(f"Unsupported LLM provider: {provider}")

    def _call_openai(self, prompt: Dict[str, str]) -> str:
        """Call OpenAI chat completion API via HTTP."""
        llm = self.config.llm
        assert llm is not None

        api_key = llm.resolve_api_key()
        base_url = llm.api_base or "https://api.openai.com/v1/chat/completions"

        payload = {
            "model": llm.model,
            "messages": [
                {"role": "system", "content": prompt["system"]},
                {"role": "user", "content": prompt["user"]},
            ],
            "temperature": llm.temperature,
            "max_tokens": llm.max_tokens,
        }

        response = requests.post(
            base_url,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=llm.timeout_seconds,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"LLM request failed with status {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        choices = data.get("choices")
        if not choices:
            raise ValueError("LLM response did not include choices")

        message = choices[0].get("message", {})
        content = message.get("content")
        if not content:
            raise ValueError("LLM response content was empty")

        return content

    def _parse_response(self, response_text: str) -> Dict[str, Any]:
        """Parse LLM response into a structured dictionary."""
        text = response_text.strip()
        if not text:
            return {}

        candidate = self._extract_json_block(text)
        if candidate:
            try:
                parsed = json.loads(candidate)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        # Fallback to raw text blob
        return {"raw_response": text}

    @staticmethod
    def _extract_json_block(text: str) -> Optional[str]:
        """Extract the first JSON object from text."""
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        candidate = text[start : end + 1]
        return candidate

