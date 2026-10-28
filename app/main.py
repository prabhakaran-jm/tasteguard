from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"

app = FastAPI(title="TasteGuard", version="0.1.0")

# API first — static mount registered after so /api/* always wins.
app.include_router(api_router)

if DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="spa")
