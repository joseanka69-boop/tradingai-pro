"""Endpoint GET /api/news/{symbol} — noticias en vivo por instrumento (NewsAPI)."""
from __future__ import annotations

import os

import httpx
from fastapi import APIRouter

router = APIRouter(prefix="/api/news", tags=["news"])

# Nombre de búsqueda amigable por símbolo, para mejores resultados en NewsAPI
SEARCH_TERMS = {
    "NQ": "Nasdaq 100 futures",
    "MNQ": "Nasdaq 100 futures",
    "AMD": "AMD stock",
    "NVDA": "Nvidia stock",
    "AAPL": "Apple stock",
    "TSLA": "Tesla stock",
    "BTC": "Bitcoin",
    "ETH": "Ethereum",
}

NEWS_API_URL = "https://newsapi.org/v2/everything"


@router.get("/{symbol}")
async def get_news(symbol: str):
    symbol = symbol.upper()
    api_key = os.getenv("NEWS_API_KEY")
    query = SEARCH_TERMS.get(symbol, symbol)

    if not api_key:
        return {"symbol": symbol, "articles": [], "error": "NEWS_API_KEY no configurada"}

    params = {
        "q": query,
        "language": "es",
        "sortBy": "publishedAt",
        "pageSize": 10,
        "apiKey": api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(NEWS_API_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:  # noqa: BLE001
        return {"symbol": symbol, "articles": [], "error": str(exc)}

    articles = [
        {
            "title": a.get("title"),
            "source": (a.get("source") or {}).get("name"),
            "url": a.get("url"),
            "published_at": a.get("publishedAt"),
            "description": a.get("description"),
        }
        for a in data.get("articles", [])
    ]
    return {"symbol": symbol, "articles": articles}
