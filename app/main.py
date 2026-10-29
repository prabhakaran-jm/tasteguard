from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api import router as api_router
from app.mcp_server import mcp_sse_app

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "web" / "dist"

app = FastAPI(title="TasteGuard", version="0.1.0")

# API + MCP before the SPA catch-all so /api/* and /mcp/* always win.
app.include_router(api_router)
app.mount("/mcp", mcp_sse_app())

if DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST), html=True), name="spa")
