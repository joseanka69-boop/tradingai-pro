"""Endpoint POST /api/alerts/subscribe — suscripción a alertas de WhatsApp (sin Auto Trade)."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SUBSCRIBERS_FILE = DATA_DIR / "subscribers.json"


class SubscribeRequest(BaseModel):
    phone: str
    symbols: list[str]


def _load_subscribers() -> list[dict]:
    if not SUBSCRIBERS_FILE.exists():
        return []
    try:
        with open(SUBSCRIBERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_subscribers(subscribers: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(SUBSCRIBERS_FILE, "w", encoding="utf-8") as f:
        json.dump(subscribers, f, indent=2, ensure_ascii=False)


@router.post("/subscribe")
async def subscribe(payload: SubscribeRequest):
    subscribers = _load_subscribers()

    for sub in subscribers:
        if sub["phone"] == payload.phone:
            sub["symbols"] = payload.symbols
            _save_subscribers(subscribers)
            return {"status": "updated", "subscriber": sub}

    new_sub = {"phone": payload.phone, "symbols": payload.symbols}
    subscribers.append(new_sub)
    _save_subscribers(subscribers)
    return {"status": "created", "subscriber": new_sub}
