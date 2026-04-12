from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def score_label(score: int) -> str:
    if score <= 39:
        return "Poor"
    if score <= 69:
        return "Needs Work"
    if score <= 84:
        return "Good"
    return "Strong"


class AnalysisRequest(BaseModel):
    title: str = Field(min_length=3, max_length=280)
    description: str = Field(min_length=20, max_length=15000)
    category: str = Field(default="", max_length=120)
    target_keyword: str = Field(default="", max_length=120)

    @field_validator("title", "description", "category", "target_keyword", mode="before")
    @classmethod
    def strip_strings(cls, value: Any) -> Any:
        return value.strip() if isinstance(value, str) else value


class AnalysisResult(BaseModel):
    seo_score: int = Field(ge=0, le=100)
    issues_found: list[str] = Field(default_factory=list)
    optimized_title: str = Field(min_length=3, max_length=280)
    optimized_description: str = Field(min_length=20, max_length=15000)
    suggested_tags: list[str] = Field(default_factory=list, max_length=13)
    keyword_focus: str = Field(default="", max_length=160)
    explanation: str = Field(default="", max_length=2000)

    model_config = ConfigDict(extra="forbid")

    @field_validator("issues_found", "suggested_tags")
    @classmethod
    def strip_list_items(cls, values: list[str]) -> list[str]:
        return [item.strip() for item in values if isinstance(item, str) and item.strip()]

    @field_validator("suggested_tags")
    @classmethod
    def normalize_tags(cls, values: list[str]) -> list[str]:
        unique_tags: list[str] = []
        for value in values:
            trimmed = value[:32]
            if trimmed not in unique_tags:
                unique_tags.append(trimmed)
        return unique_tags[:13]

    @model_validator(mode="after")
    def ensure_content(self) -> "AnalysisResult":
        if not self.suggested_tags:
            raise ValueError("suggested_tags must include at least one item")
        return self


class AnalysisResponse(AnalysisResult):
    score_label: str
    used_mock: bool = False

    @classmethod
    def from_result(cls, result: AnalysisResult, *, used_mock: bool) -> "AnalysisResponse":
        payload = result.model_dump()
        payload["score_label"] = score_label(result.seo_score)
        payload["used_mock"] = used_mock
        return cls.model_validate(payload)
