from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from app.schemas.analysis import AnalysisRequest, AnalysisResponse
from app.schemas.extraction import ExtractionRequest, ExtractionResponse
from app.services.analyzer import AnalysisError, analyze_listing
from app.services.extractor import ExtractionServiceError, extract_listing_content

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/extract", response_model=ExtractionResponse)
def extract_listing(request: ExtractionRequest) -> ExtractionResponse:
    try:
        return extract_listing_content(str(request.url))
    except ExtractionServiceError as exc:
        logger.warning("Extraction failed for %s: %s", request.url, exc)
        return ExtractionResponse(
            success=False,
            confidence=0.0,
            extracted_title="",
            extracted_description="",
            fallback_required=True,
            extraction_notes=[str(exc)],
        )


@router.post("/analyze", response_model=AnalysisResponse)
def analyze_listing_route(request: AnalysisRequest) -> AnalysisResponse:
    try:
        return analyze_listing(request)
    except AnalysisError as exc:
        logger.error("Analysis failed: %s", exc)
        raise HTTPException(status_code=502, detail={"message": str(exc)}) from exc
