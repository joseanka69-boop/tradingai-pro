"""Endpoint POST /api/ai/analyze — análisis de mercado con Claude AI."""
from __future__ import annotations

import os

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/api/ai", tags=["ai"])

CLAUDE_MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = (
    "Eres un analista de trading cuantitativo de TradingAI Pro. Recibes el estado "
    "actual de los indicadores técnicos (Z-Score, RSI, Bandas de Bollinger, ADX, ATR) "
    "de un instrumento financiero. Da un análisis breve, claro y en español sobre el "
    "sesgo del mercado (alcista/bajista/neutral), el riesgo actual y qué señalaría "
    "confirmación o invalidación del escenario. No des consejos financieros personalizados, "
    "aclara que es solo información educativa."
)


class AnalyzeRequest(BaseModel):
    symbol: str
    question: str | None = None


@router.post("/analyze")
async def analyze(payload: AnalyzeRequest, request: Request):
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY no configurada"}

    scanner = request.app.state.scanner
    signal = scanner.latest_signals.get(payload.symbol.upper())

    if signal is None:
        market_context = f"No hay datos recientes disponibles para {payload.symbol.upper()}."
    else:
        s = signal.to_dict()
        market_context = (
            f"Símbolo: {s['symbol']}\n"
            f"Precio actual: {s['price']}\n"
            f"Dirección de señal: {s['direction']}\n"
            f"Z-Score: {s['zscore']}\n"
            f"RSI: {s['rsi']}\n"
            f"ADX: {s['adx']}\n"
            f"ATR: {s['atr']}\n"
            f"Banda superior: {s['bb_upper']} | Media: {s['bb_mid']} | Banda inferior: {s['bb_lower']}\n"
            f"Stop Loss sugerido: {s['stop_loss']} | Take Profit sugerido: {s['take_profit']}"
        )

    user_question = payload.question or "Dame un análisis rápido del estado actual de este instrumento."

    try:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": f"Datos de mercado:\n{market_context}\n\nPregunta: {user_question}"}
            ],
        )
        text = "".join(block.text for block in response.content if block.type == "text")
        return {"symbol": payload.symbol.upper(), "analysis": text}
    except Exception as exc:  # noqa: BLE001
        return {"error": f"Fallo al consultar Claude AI: {exc}"}
