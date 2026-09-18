"""Endpoint GET /api/signals — devuelve el último estado del scanner."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("")
async def get_signals(request: Request):
    scanner = request.app.state.scanner
    return {
        symbol: signal.to_dict()
        for symbol, signal in scanner.latest_signals.items()
    }


@router.get("/{symbol}")
async def get_signal(symbol: str, request: Request):
    scanner = request.app.state.scanner
    signal = scanner.latest_signals.get(symbol.upper())
    if signal is None:
        return {"error": f"No hay señal disponible para {symbol.upper()} todavía"}
    return signal.to_dict()
