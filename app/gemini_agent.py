from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from app.config import Settings, get_settings
from app.models import Alternative, CandidateInput

logger = logging.getLogger(__name__)

SYSTEM = (
    "You are a dining concierge. Recommend real restaurants only. "
    "Return strict JSON with key 'recommendations' as a list of objects: "
    "name, neighbourhood, address, notes. No markdown."
)


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


class GeminiConcierge:
    """Gemini Flash baseline: no tools. Repair picks only from a closed Qloo pool."""

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return bool(self.settings.gemini_api_key)

    def _generate(self, prompt: str) -> str:
        """Call Gemini via the supported ``google.genai`` SDK."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self.settings.gemini_api_key)
        resp = client.models.generate_content(
            model=self.settings.gemini_model,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                response_mime_type="application/json",
            ),
        )
        return resp.text or ""

    async def recommend(
        self,
        *,
        city: str,
        persona_description: str,
        n: int = 5,
    ) -> list[CandidateInput]:
        if not self.enabled:
            raise RuntimeError("GEMINI_API_KEY is not configured")

        prompt = (
            f"{SYSTEM}\n\n"
            f"City: {city}\n"
            f"Diner taste profile: {persona_description}\n"
            f"Recommend {n} dinner restaurants only (no museums, viewpoints, or shops). "
            f"Include neighbourhood."
        )
        text = await asyncio.to_thread(self._generate, prompt)
        data = _extract_json(text)
        items = data.get("recommendations") or data.get("restaurants") or []
        out: list[CandidateInput] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            out.append(
                CandidateInput(
                    name=name,
                    neighbourhood=item.get("neighbourhood")
                    or item.get("neighborhood"),
                    address=item.get("address"),
                    notes=item.get("notes"),
                )
            )
        if not out:
            raise RuntimeError("Gemini returned no parseable recommendations")
        return out

    async def repair_from_pool(
        self,
        *,
        city: str,
        persona_description: str,
        fail_reasons: list[str],
        alternatives: list[Alternative],
        n: int = 5,
    ) -> list[str]:
        """Return entity_ids chosen ONLY from the provided alternatives pool."""
        if not alternatives:
            return []

        target_n = min(max(n, 1), len(alternatives))

        if not self.enabled:
            ranked = sorted(
                alternatives,
                key=lambda a: (a.affinity is not None, a.affinity or 0.0),
                reverse=True,
            )
            return [a.entity_id for a in ranked[:target_n]]

        pool = [
            {
                "entity_id": a.entity_id,
                "name": a.name,
                "affinity": a.affinity,
                "locality": a.locality,
                "reason": a.replacement_reason,
            }
            for a in alternatives
        ]
        prompt = (
            f"{SYSTEM}\n\n"
            f"City: {city}\nTaste profile: {persona_description}\n"
            f"Previous list FAILED TasteGuard for: {fail_reasons}\n"
            f"You MUST choose exactly {target_n} restaurants from this pool by entity_id only.\n"
            f"Do not invent places. Do not return names that are not in the pool.\n"
            f"Prefer real dining venues; the pool should already be restaurants only.\n"
            f"Pool JSON: {json.dumps(pool)}\n"
            'Return JSON: {"chosen_entity_ids": ["..."]}'
        )
        text = await asyncio.to_thread(self._generate, prompt)
        data = _extract_json(text)
        chosen = data.get("chosen_entity_ids") or data.get("entity_ids") or []
        allowed = {a.entity_id for a in alternatives}
        cleaned = [str(x) for x in chosen if str(x) in allowed]
        # Dedupe preserve order
        seen: set[str] = set()
        uniq: list[str] = []
        for eid in cleaned:
            if eid not in seen:
                seen.add(eid)
                uniq.append(eid)
        if len(uniq) < target_n:
            ranked = sorted(
                alternatives,
                key=lambda a: (a.affinity is not None, a.affinity or 0.0),
                reverse=True,
            )
            for a in ranked:
                if a.entity_id not in seen:
                    uniq.append(a.entity_id)
                    seen.add(a.entity_id)
                if len(uniq) >= target_n:
                    break
        return uniq[:target_n]
