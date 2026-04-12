from __future__ import annotations

import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic import BaseModel, Field


class Settings(BaseModel):
    app_name: str = "Etsy Listing Optimizer"
    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    debug: bool = False
    log_level: str = "INFO"
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
    )
    extraction_timeout: float = 12.0
    browser_extraction_enabled: bool = True
    browser_extraction_timeout: float = 30.0
    etsy_api_key: str | None = None
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    llm_request_timeout: float = 45.0
    llm_mock_mode: bool = Field(default=False)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_name=os.getenv("APP_NAME", "Etsy Listing Optimizer"),
        app_env=os.getenv("APP_ENV", "development"),
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        debug=os.getenv("DEBUG", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        user_agent=os.getenv(
            "USER_AGENT",
            (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0 Safari/537.36"
            ),
        ),
        extraction_timeout=float(os.getenv("EXTRACTION_TIMEOUT", "12")),
        browser_extraction_enabled=os.getenv("BROWSER_EXTRACTION_ENABLED", "true").lower() == "true",
        browser_extraction_timeout=float(os.getenv("BROWSER_EXTRACTION_TIMEOUT", "30")),
        etsy_api_key=os.getenv("ETSY_API_KEY"),
        llm_base_url=os.getenv("LLM_BASE_URL"),
        llm_api_key=os.getenv("LLM_API_KEY"),
        llm_model=os.getenv("LLM_MODEL"),
        llm_request_timeout=float(os.getenv("LLM_REQUEST_TIMEOUT", "45")),
        llm_mock_mode=os.getenv("LLM_MOCK_MODE", "false").lower() == "true",
    )
