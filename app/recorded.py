"""Load checked recorded demo fixtures (no live Qloo/Gemini)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config import ROOT

REC_DIR = ROOT / "recorded"


def load_fixture(relative_path: str) -> dict[str, Any]:
    path = ROOT / relative_path
    if not path.is_file():
        raise FileNotFoundError(f"Recorded fixture missing: {relative_path}")
    return json.loads(path.read_text(encoding="utf-8"))
