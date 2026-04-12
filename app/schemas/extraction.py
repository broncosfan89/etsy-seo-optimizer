from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, Field


class ExtractionRequest(BaseModel):
    url: AnyHttpUrl


class ExtractionResponse(BaseModel):
    success: bool
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_title: str = ""
    extracted_description: str = ""
    fallback_required: bool
    extraction_notes: list[str] = Field(default_factory=list)
