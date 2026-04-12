from __future__ import annotations

import json
from typing import Any

import requests

from app.config import get_settings


class LLMServiceError(Exception):
    """Raised when the LLM request fails."""


class LLMClient:
    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.llm_base_url and self.settings.llm_model)

    @property
    def use_mock(self) -> bool:
        return self.settings.llm_mock_mode or not self.enabled

    def create_chat_completion(self, messages: list[dict[str, str]]) -> str:
        if not self.enabled:
            raise LLMServiceError("LLM is not configured. Set LLM_BASE_URL and LLM_MODEL.")

        endpoint = self._chat_completions_url()
        headers = {"Content-Type": "application/json"}
        if self.settings.llm_api_key:
            headers["Authorization"] = f"Bearer {self.settings.llm_api_key}"

        payload = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }

        try:
            response = requests.post(
                endpoint,
                headers=headers,
                json=payload,
                timeout=self.settings.llm_request_timeout,
            )
            response.raise_for_status()
        except requests.Timeout as exc:
            raise LLMServiceError("The LLM request timed out.") from exc
        except requests.RequestException as exc:
            raise LLMServiceError(f"Unable to reach the LLM endpoint: {exc}") from exc

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMServiceError("The LLM returned an unexpected response format.") from exc

        if isinstance(content, list):
            text_fragments = [item.get("text", "") for item in content if isinstance(item, dict)]
            content = "\n".join(fragment for fragment in text_fragments if fragment)

        if not isinstance(content, str) or not content.strip():
            raise LLMServiceError("The LLM returned an empty response.")

        return content.strip()

    def _chat_completions_url(self) -> str:
        base_url = (self.settings.llm_base_url or "").rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"


def extract_json_object(raw_content: str) -> dict[str, Any]:
    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        start = raw_content.find("{")
        end = raw_content.rfind("}")
        if start == -1 or end == -1 or start >= end:
            raise
        return json.loads(raw_content[start : end + 1])
