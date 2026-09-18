"""
Alertas por WhatsApp usando la API de Twilio.

El envío es asíncrono (se ejecuta en un hilo aparte con asyncio.to_thread)
para no bloquear el ciclo del scanner ni el bucle de eventos de FastAPI.
"""
from __future__ import annotations

import asyncio
import logging
import os

logger = logging.getLogger("tradingai.whatsapp")

ENTRY_TEMPLATE = """🟢 TradingAI AutoTrade — {arrow} {direction}
📋 {mode_label}
━━━━━━━━━━━━━━━━
📊 {symbol} · {hora} ET
📦 Contratos: {qty}
💵 Entrada: {entry}
⛔ Stop Loss: {sl}
✅ Take Profit: {tp}
━━━━━━━━━━━━━━━━
Z: {z} | RSI: {rsi} | ADX: {adx}"""

EXIT_TEMPLATE = """✅ TradingAI AutoTrade — CERRADO
📋 {mode_label}
📊 {symbol} {direction}
💵 Entrada: {entry}
🏁 Salida: {exit}
💰 P&L: {pnl_sign}${pnl}
📈 Ver stats: tradingai.com/dashboard"""


def _get_twilio_client():
    """Crea el cliente de Twilio a partir de las variables de entorno."""
    try:
        from twilio.rest import Client

        sid = os.getenv("TWILIO_ACCOUNT_SID")
        token = os.getenv("TWILIO_AUTH_TOKEN")
        if not sid or not token:
            logger.warning("Credenciales de Twilio no configuradas — alerta de WhatsApp omitida")
            return None
        return Client(sid, token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("No se pudo inicializar Twilio: %s", exc)
        return None


def _send_sync(to_phone: str, body: str) -> bool:
    client = _get_twilio_client()
    if client is None:
        return False

    from_whatsapp = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
    try:
        client.messages.create(from_=from_whatsapp, to=to_phone, body=body)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Fallo al enviar WhatsApp a %s: %s", to_phone, exc)
        return False


async def send_whatsapp(to_phone: str, body: str) -> bool:
    """Envía un mensaje de WhatsApp sin bloquear el event loop."""
    return await asyncio.to_thread(_send_sync, to_phone, body)


async def send_entry_alert(to_phone: str, *, symbol: str, direction: str, mode: str, hora: str,
                            qty: int, entry: float, sl: float, tp: float,
                            z: float, rsi: float, adx: float) -> bool:
    arrow = "▲" if direction == "LONG" else "▼"
    mode_label = "SIMULADO" if mode == "paper" else "REAL"
    body = ENTRY_TEMPLATE.format(
        arrow=arrow, direction=direction, mode_label=mode_label, symbol=symbol, hora=hora,
        qty=qty, entry=entry, sl=sl, tp=tp, z=z, rsi=rsi, adx=adx,
    )
    return await send_whatsapp(to_phone, body)


async def send_exit_alert(to_phone: str, *, symbol: str, direction: str, mode: str,
                           entry: float, exit_price: float, pnl: float) -> bool:
    mode_label = "SIMULADO" if mode == "paper" else "REAL"
    pnl_sign = "+" if pnl >= 0 else "-"
    body = EXIT_TEMPLATE.format(
        mode_label=mode_label, symbol=symbol, direction=direction, entry=entry,
        exit=exit_price, pnl_sign=pnl_sign, pnl=abs(round(pnl, 2)),
    )
    return await send_whatsapp(to_phone, body)
