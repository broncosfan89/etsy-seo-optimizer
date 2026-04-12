from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.routes.api import router as api_router
from app.routes.web import router as web_router


def configure_logging() -> None:
    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level, logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


configure_logging()
settings = get_settings()
BASE_DIR = Path(__file__).resolve().parent

app = FastAPI(title=settings.app_name, debug=settings.debug)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

app.include_router(web_router)
app.include_router(api_router)
