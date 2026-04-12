from __future__ import annotations

import logging
import re

from app.schemas.analysis import AnalysisRequest, AnalysisResponse, AnalysisResult
from app.services.llm import LLMClient, LLMServiceError, extract_json_object

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an Etsy SEO copy assistant.

Your job is to evaluate and improve an Etsy product listing.

Return valid JSON only with this exact schema:
{
  "seo_score": 0,
  "issues_found": ["short issue"],
  "optimized_title": "",
  "optimized_description": "",
  "suggested_tags": ["tag1"],
  "keyword_focus": "",
  "explanation": ""
}

Rules:
- Preserve the product’s actual meaning
- Do not invent materials, sizes, or features
- Make the title clearer and more searchable
- Improve readability and keyword placement
- Keep the tone natural, not spammy
- Focus on buyer search intent
- suggested_tags must contain no more than 13 items
- Each tag must be concise and realistic for Etsy
- Output valid JSON only"""

USER_PROMPT_TEMPLATE = """Analyze and improve this Etsy listing.

Title: {title}
Description: {description}
Category: {category}
Target Keyword: {target_keyword}"""


class AnalysisError(Exception):
    """Raised when listing analysis cannot be completed."""


def analyze_listing(request: AnalysisRequest) -> AnalysisResponse:
    client = LLMClient()

    if client.use_mock:
        logger.info("Using mock analysis mode")
        result = _mock_analysis(request)
        return AnalysisResponse.from_result(result, used_mock=True)

    messages = _build_messages(request)

    try:
        raw_content = client.create_chat_completion(messages)
        parsed = _parse_and_validate(raw_content)
    except (LLMServiceError, ValueError) as first_error:
        logger.warning("First model response was invalid: %s", first_error)
        retry_messages = messages + [
            {
                "role": "user",
                "content": (
                    "Your previous response was invalid. "
                    "Return valid JSON only that matches the required schema."
                ),
            }
        ]
        try:
            raw_content = client.create_chat_completion(retry_messages)
            parsed = _parse_and_validate(raw_content)
        except (LLMServiceError, ValueError) as second_error:
            raise AnalysisError(
                f"Unable to parse a valid JSON response from the model: {second_error}"
            ) from second_error

    return AnalysisResponse.from_result(parsed, used_mock=False)


def _build_messages(request: AnalysisRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_PROMPT_TEMPLATE.format(
                title=request.title,
                description=request.description,
                category=request.category or "Not provided",
                target_keyword=request.target_keyword or "Not provided",
            ),
        },
    ]


def _parse_and_validate(raw_content: str) -> AnalysisResult:
    payload = extract_json_object(raw_content)
    return AnalysisResult.model_validate(payload)


def _mock_analysis(request: AnalysisRequest) -> AnalysisResult:
    title = request.title.strip()
    description = request.description.strip()
    keyword = (request.target_keyword or _derive_keyword(title, request.category)).strip()

    issues: list[str] = []
    score = 82

    if len(title) < 45:
        issues.append("Title is shorter than many high-performing Etsy titles.")
        score -= 12
    elif len(title) > 140:
        issues.append("Title is too long and may feel cluttered in search results.")
        score -= 10

    if keyword and keyword.lower() not in title.lower():
        issues.append("Primary keyword is not clearly placed in the title.")
        score -= 10

    if len(description) < 180:
        issues.append("Description is brief and may not answer buyer questions well.")
        score -= 14

    if not re.search(r"[.!?]", description):
        issues.append("Description needs clearer sentence structure for readability.")
        score -= 6

    if not issues:
        issues.append("Listing is solid overall, but the copy can be tighter for search intent.")

    return AnalysisResult(
        seo_score=max(0, min(score, 100)),
        issues_found=issues,
        optimized_title=_optimize_title(title, keyword),
        optimized_description=_optimize_description(description, keyword, request.category),
        suggested_tags=_generate_tags(title, keyword, request.category),
        keyword_focus=keyword or request.category or "Etsy buyer intent",
        explanation=(
            "The mock analysis tightened keyword placement, improved scanability, "
            "and kept the copy aligned with the original listing details."
        ),
    )


def _derive_keyword(title: str, category: str) -> str:
    if category:
        return category.strip()
    words = [word for word in re.split(r"[^a-zA-Z0-9]+", title) if len(word) > 2]
    return " ".join(words[:3]).strip()


def _optimize_title(title: str, keyword: str) -> str:
    candidate = f"{keyword} - {title}" if keyword and keyword.lower() not in title.lower() else title
    candidate = re.sub(r"\s+", " ", candidate).strip(" -")
    return candidate[:140]


def _optimize_description(description: str, keyword: str, category: str) -> str:
    opener_parts = [part for part in [keyword, category] if part]
    intro = f"{' | '.join(opener_parts)}\n\n" if opener_parts else ""
    body = (
        f"{intro}{description}\n\n"
        "Why this listing works better:\n"
        "- Clearer keyword placement for Etsy search\n"
        "- Easier to scan for shoppers comparing options\n"
        "- Natural wording that keeps the original product meaning"
    )
    return body[:3000]


def _generate_tags(title: str, keyword: str, category: str) -> list[str]:
    tags: list[str] = []
    for phrase in [keyword, category, title]:
        for candidate in _phrase_variants(phrase):
            if candidate not in tags:
                tags.append(candidate)
            if len(tags) == 13:
                return tags

    while len(tags) < 13:
        tags.append(f"etsy seo tag {len(tags) + 1}")
    return tags[:13]


def _phrase_variants(phrase: str) -> list[str]:
    cleaned = re.sub(r"\s+", " ", phrase or "").strip()
    if not cleaned:
        return []

    tokens = [token for token in re.split(r"[^a-zA-Z0-9]+", cleaned.lower()) if token]
    phrases: list[str] = [cleaned[:20]]

    for size in (2, 3):
        for index in range(0, max(0, len(tokens) - size + 1)):
            variant = " ".join(tokens[index : index + size])[:20]
            if len(variant) >= 4 and variant not in phrases:
                phrases.append(variant)

    return phrases
