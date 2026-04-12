from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

from app.config import get_settings
from app.schemas.extraction import ExtractionResponse

logger = logging.getLogger(__name__)

TITLE_SELECTORS = [
    "h1[data-buy-box-listing-title='true']",
    "h1.wt-text-body-03",
    "h1[data-listing-page-title]",
    "main h1",
]

DESCRIPTION_SELECTORS = [
    'div[data-id="description-text"]',
    '[data-selector="expanded-content"]',
    '[data-component="listing-description-body"]',
    "#description-text",
    "section[aria-label*='Description'] p",
]

GENERIC_TITLE_PATTERNS = [
    "etsy",
    "shopping",
    "find things you'll love",
]

ANTI_BOT_PATTERNS = [
    "please enable js and disable any ad blocker",
    "datadome captcha",
    "captcha-delivery.com",
    "geo.captcha-delivery.com",
]

TITLE_KEYS = {"name", "headline", "title"}
DESCRIPTION_KEYS = {"description", "listing_description"}


@dataclass
class FetchResult:
    html: str = ""
    source: str = ""
    status_code: int | None = None
    blocked: bool = False
    notes: list[str] = field(default_factory=list)


class ExtractionServiceError(Exception):
    """Raised when public page extraction cannot complete."""


def extract_listing_content(url: str) -> ExtractionResponse:
    settings = get_settings()
    normalized_url = _normalize_listing_url(url)
    logger.info("Extracting Etsy listing content from %s", normalized_url)

    notes: list[str] = []
    fetch_result = _fetch_listing_page(normalized_url)
    title = ""
    description = ""
    title_source: str | None = None
    description_source: str | None = None
    structured_data: dict[str, Any] = {}

    if settings.etsy_api_key:
        api_title, api_description, api_notes = _fetch_from_etsy_api(normalized_url, settings.etsy_api_key)
        notes.extend(api_notes)
        if api_title:
            title = api_title
            title_source = "Etsy API"
        if api_description:
            description = api_description
            description_source = "Etsy API"
    else:
        notes.append("ETSY_API_KEY is not configured, so official Etsy API extraction was skipped.")

    notes.extend(fetch_result.notes)

    if (not title or not description) and fetch_result.html and not fetch_result.blocked:
        soup = BeautifulSoup(fetch_result.html, "html.parser")
        structured_data = _extract_json_ld(soup)
        html_title, html_title_source = _extract_title(soup, structured_data)
        html_description, html_description_source = _extract_description(soup, structured_data)

        if not title and html_title:
            title = html_title
            title_source = html_title_source
        if not description and html_description:
            description = html_description
            description_source = html_description_source

        if html_title_source:
            notes.append(f"Title extracted from {html_title_source}.")
        else:
            notes.append("Could not find a reliable title in the fetched listing content.")

        if html_description_source:
            notes.append(f"Description extracted from {html_description_source}.")
        else:
            notes.append("Could not find a reliable description in the fetched listing content.")

        if structured_data:
            notes.append("Structured data was present in the listing HTML.")
    else:
        notes.append(
            "Etsy blocked automated access to the public listing page, so extraction fell back to URL-based hints."
        )

    if not title:
        inferred_title = _infer_title_from_url(normalized_url)
        if inferred_title:
            title = inferred_title
            title_source = "URL slug"
            notes.append("Title was inferred from the Etsy URL slug.")

    if not description:
        notes.append("Description still needs manual input.")

    confidence = _calculate_confidence(title, description, title_source, description_source)

    if fetch_result.blocked:
        confidence = min(confidence, 0.35)

    if _looks_suspicious(title, description):
        notes.append("Content looks incomplete or generic, so confidence was reduced.")
        confidence = max(0.0, confidence - 0.2)

    if description and len(description) < 80:
        notes.append("Description is quite short; manual review is recommended.")

    return ExtractionResponse(
        success=bool(title or description),
        confidence=round(confidence, 2),
        extracted_title=title,
        extracted_description=description,
        fallback_required=confidence < 0.6,
        extraction_notes=_dedupe_notes(notes),
    )


def _fetch_listing_page(url: str) -> FetchResult:
    direct_result = _fetch_with_requests(url)
    if direct_result.html and not direct_result.blocked:
        return direct_result

    settings = get_settings()
    if not settings.browser_extraction_enabled:
        direct_result.notes.append("Browser fallback is disabled.")
        return direct_result

    browser_result = _fetch_with_browser(url)
    merged_notes = direct_result.notes + browser_result.notes

    if browser_result.html and not browser_result.blocked:
        browser_result.notes = merged_notes
        return browser_result

    fallback = browser_result if browser_result.html else direct_result
    fallback.notes = merged_notes
    fallback.blocked = direct_result.blocked or browser_result.blocked
    return fallback


def _fetch_from_etsy_api(url: str, api_key: str) -> tuple[str, str, list[str]]:
    listing_id = _extract_listing_id(url)
    if not listing_id:
        return "", "", ["Could not extract a listing ID from the Etsy URL, so API lookup was skipped."]

    endpoint = f"https://openapi.etsy.com/v3/application/listings/{listing_id}"
    headers = {
        "x-api-key": api_key,
        "Accept": "application/json",
        "User-Agent": get_settings().user_agent,
    }

    try:
        response = requests.get(endpoint, headers=headers, timeout=get_settings().extraction_timeout)
    except requests.RequestException as exc:
        return "", "", [f"Etsy API lookup failed: {exc}"]

    if response.status_code >= 400:
        return "", "", [f"Etsy API lookup returned HTTP {response.status_code} for listing {listing_id}."]

    try:
        payload = response.json()
    except ValueError:
        return "", "", ["Etsy API lookup returned a non-JSON response."]

    title = _clean_text(str(payload.get("title", "")))
    description = _clean_text(str(payload.get("description", "")))
    notes = [f"Etsy API lookup succeeded for listing {listing_id}."]
    return title, description, notes


def _fetch_with_requests(url: str) -> FetchResult:
    settings = get_settings()
    try:
        response = requests.get(
            url,
            timeout=settings.extraction_timeout,
            headers={
                "User-Agent": settings.user_agent,
                "Accept-Language": "en-US,en;q=0.9",
                "Cache-Control": "no-cache",
            },
        )
    except requests.RequestException as exc:
        return FetchResult(notes=[f"Direct fetch failed: {exc}"])

    html = response.text or ""
    blocked = response.status_code >= 400 or _is_anti_bot_html(html)
    note = (
        f"Direct fetch returned {response.status_code} and appears to be blocked by Etsy."
        if blocked
        else f"Direct fetch succeeded with HTTP {response.status_code}."
    )
    return FetchResult(
        html=html,
        source="direct request",
        status_code=response.status_code,
        blocked=blocked,
        notes=[note],
    )


def _fetch_with_browser(url: str) -> FetchResult:
    settings = get_settings()
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError:
        return FetchResult(notes=["Browser fallback is unavailable because Playwright is not installed."])

    channels = ["msedge", "chrome"]
    for channel in channels:
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel=channel, headless=True)
                page = browser.new_page(
                    locale="en-US",
                    user_agent=settings.user_agent,
                    viewport={"width": 1440, "height": 1100},
                )
                page.goto(url, wait_until="domcontentloaded", timeout=int(settings.browser_extraction_timeout * 1000))
                page.wait_for_timeout(2500)
                html = page.content()
                browser.close()

            blocked = _is_anti_bot_html(html)
            note = (
                f"Browser fallback via {channel} still hit Etsy's anti-bot challenge."
                if blocked
                else f"Browser fallback via {channel} loaded the listing page."
            )
            return FetchResult(
                html=html,
                source=f"browser fallback ({channel})",
                status_code=200,
                blocked=blocked,
                notes=[note],
            )
        except PlaywrightTimeoutError:
            return FetchResult(notes=[f"Browser fallback via {channel} timed out."])
        except Exception as exc:
            logger.debug("Browser fallback failed with %s: %s", channel, exc)

    return FetchResult(notes=["Browser fallback could not launch a supported local browser."])


def _extract_title(soup: BeautifulSoup, structured_data: dict[str, Any]) -> tuple[str, str | None]:
    structured_title = _structured_lookup(structured_data, TITLE_KEYS)
    if _is_valid_title(structured_title):
        return _normalize_title(structured_title), "JSON-LD"

    og_title = _clean_text(_meta_content(soup, "property", "og:title"))
    if _is_valid_title(og_title):
        return _normalize_title(og_title), "og:title"

    title_tag = soup.title.string if soup.title and soup.title.string else ""
    title_value = _normalize_title(_clean_text(title_tag))
    if _is_valid_title(title_value):
        return title_value, "<title>"

    for selector in TITLE_SELECTORS:
        node = soup.select_one(selector)
        text = _normalize_title(_clean_text(node.get_text(" ", strip=True) if node else ""))
        if _is_valid_title(text):
            return text, selector

    return "", None


def _extract_description(
    soup: BeautifulSoup,
    structured_data: dict[str, Any],
) -> tuple[str, str | None]:
    description_value = _structured_lookup(structured_data, DESCRIPTION_KEYS)
    if _is_valid_description(description_value):
        return description_value, "JSON-LD"

    meta_description = _clean_text(_meta_content(soup, "name", "description"))
    if _is_valid_description(meta_description):
        return meta_description, "meta description"

    og_description = _clean_text(_meta_content(soup, "property", "og:description"))
    if _is_valid_description(og_description):
        return og_description, "og:description"

    for selector in DESCRIPTION_SELECTORS:
        nodes = soup.select(selector)
        combined = _clean_text(" ".join(node.get_text(" ", strip=True) for node in nodes))
        if _is_valid_description(combined):
            return combined, selector

    return "", None


def _extract_json_ld(soup: BeautifulSoup) -> dict[str, Any]:
    for node in soup.select("script[type='application/ld+json']"):
        raw_text = node.string or node.get_text(strip=True)
        if not raw_text:
            continue
        try:
            parsed = json.loads(raw_text)
        except json.JSONDecodeError:
            continue

        candidates = parsed if isinstance(parsed, list) else [parsed]
        for candidate in candidates:
            match = _find_product_like_node(candidate)
            if match:
                return match
    return {}


def _find_product_like_node(candidate: Any) -> dict[str, Any] | None:
    if isinstance(candidate, dict):
        node_type = candidate.get("@type")
        node_types = [str(item).lower() for item in node_type] if isinstance(node_type, list) else [str(node_type).lower()]
        if any(item in {"product", "listing", "productmodel"} for item in node_types):
            return candidate

        for value in candidate.values():
            match = _find_product_like_node(value)
            if match:
                return match

    if isinstance(candidate, list):
        for item in candidate:
            match = _find_product_like_node(item)
            if match:
                return match

    return None


def _structured_lookup(structured_data: dict[str, Any], keys: set[str]) -> str:
    for key in keys:
        value = structured_data.get(key, "")
        if isinstance(value, list):
            value = " ".join(str(item) for item in value)
        cleaned = _clean_text(str(value))
        if cleaned:
            return cleaned
    return ""


def _meta_content(soup: BeautifulSoup, attr: str, value: str) -> str:
    node = soup.find("meta", attrs={attr: value})
    return node.get("content", "") if node else ""


def _normalize_listing_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if not parsed.scheme:
        parsed = parsed._replace(scheme="https")
    if not parsed.netloc:
        parsed = parsed._replace(netloc="www.etsy.com")

    path = re.sub(r"/+$", "", parsed.path)
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def _extract_listing_id(url: str) -> str:
    match = re.search(r"/listing/(\d+)", url)
    return match.group(1) if match else ""


def _infer_title_from_url(url: str) -> str:
    parsed = urlparse(url)
    slug = parsed.path.rsplit("/", 1)[-1]
    if not slug or slug.isdigit():
        return ""

    normalized = re.sub(r"[-_]+", " ", slug).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    words = [word for word in normalized.split() if word]
    if len(words) < 2:
        return ""
    return " ".join(word.capitalize() if word.islower() else word for word in words)


def _normalize_title(title: str) -> str:
    cleaned = re.sub(r"\s+[|\-]\s+Etsy.*$", "", title, flags=re.IGNORECASE)
    return cleaned.strip(" -|")


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def _is_valid_title(value: str) -> bool:
    lowered = value.lower()
    return len(value) >= 6 and lowered not in GENERIC_TITLE_PATTERNS and lowered != "etsy.com"


def _is_valid_description(value: str) -> bool:
    lowered = value.lower()
    return len(value) >= 40 and "captcha" not in lowered and "enable js" not in lowered


def _is_anti_bot_html(html: str) -> bool:
    lowered = html.lower()
    return any(pattern in lowered for pattern in ANTI_BOT_PATTERNS)


def _looks_suspicious(title: str, description: str) -> bool:
    title_lower = title.lower()
    description_lower = description.lower()
    if any(pattern in title_lower for pattern in GENERIC_TITLE_PATTERNS):
        return True
    if title_lower.startswith("etsy") or "sign in" in description_lower:
        return True
    return len(title) < 10 or (description != "" and len(description) < 40)


def _calculate_confidence(
    title: str,
    description: str,
    title_source: str | None,
    description_source: str | None,
) -> float:
    confidence = 0.0

    if title:
        confidence += 0.2
        if len(title) >= 20:
            confidence += 0.1

    if description:
        confidence += 0.25
        if len(description) >= 120:
            confidence += 0.15
        elif len(description) >= 60:
            confidence += 0.05

    if title_source == "JSON-LD":
        confidence += 0.15
    elif title_source == "URL slug":
        confidence += 0.02
    elif title_source:
        confidence += 0.05

    if description_source == "JSON-LD":
        confidence += 0.1
    elif description_source and description_source not in {"meta description", "og:description"}:
        confidence += 0.05

    return min(confidence, 1.0)


def _dedupe_notes(notes: list[str]) -> list[str]:
    unique_notes: list[str] = []
    for note in notes:
        cleaned = _clean_text(note)
        if cleaned and cleaned not in unique_notes:
            unique_notes.append(cleaned)
    return unique_notes
