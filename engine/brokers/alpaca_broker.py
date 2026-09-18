"""
Broker Alpaca (alpaca-py) — acciones (AMD, NVDA, AAPL, TSLA) y crypto (BTC, ETH).

- Modo Paper (gratis): https://paper-api.alpaca.markets
- Modo Real:           https://api.alpaca.markets

El modo se controla con ALPACA_MODE=paper|real en el .env, independiente
del gating global AUTOTRADE_MODE (que decide si Auto Trade opera en vivo
con cualquier broker).

Nota: las órdenes bracket (SL + TP automáticos) de Alpaca solo están
disponibles para acciones. Para crypto se envía una orden a mercado simple
y la salida la gestiona el propio motor de señales (reversión de Z-Score).
"""
from __future__ import annotations

import logging
import os

from engine.brokers import BaseBroker

logger = logging.getLogger("tradingai.brokers.alpaca")

PAPER_URL = "https://paper-api.alpaca.markets"
REAL_URL = "https://api.alpaca.markets"

STOCK_SYMBOLS = {"AMD", "NVDA", "AAPL", "TSLA"}
CRYPTO_SYMBOLS = {"BTC", "ETH"}
CRYPTO_PAIR_MAP = {"BTC": "BTC/USD", "ETH": "ETH/USD"}


class AlpacaBroker(BaseBroker):
    name = "alpaca"

    def __init__(self):
        self.api_key = os.getenv("ALPACA_API_KEY")
        self.secret_key = os.getenv("ALPACA_SECRET_KEY")
        self.mode = os.getenv("ALPACA_MODE", "paper")
        self.is_paper = self.mode != "real"
        self.base_url = PAPER_URL if self.is_paper else REAL_URL

    def _client(self):
        from alpaca.trading.client import TradingClient

        if not self.api_key or not self.secret_key:
            raise RuntimeError("ALPACA_API_KEY / ALPACA_SECRET_KEY no configuradas")

        return TradingClient(self.api_key, self.secret_key, paper=self.is_paper, url_override=self.base_url)

    @staticmethod
    def _resolve_symbol(symbol: str) -> tuple[str, bool]:
        """Devuelve (símbolo_alpaca, es_crypto)."""
        if symbol in CRYPTO_SYMBOLS:
            return CRYPTO_PAIR_MAP[symbol], True
        return symbol, False

    def place_order(self, symbol: str, direction: str, qty: int, sl: float, tp: float) -> dict:
        if symbol not in STOCK_SYMBOLS and symbol not in CRYPTO_SYMBOLS:
            return {"status": "unsupported_symbol", "broker": self.name, "symbol": symbol}

        try:
            from alpaca.trading.enums import OrderClass, OrderSide, TimeInForce
            from alpaca.trading.requests import (
                MarketOrderRequest,
                StopLossRequest,
                TakeProfitRequest,
            )

            client = self._client()
            alpaca_symbol, is_crypto = self._resolve_symbol(symbol)
            side = OrderSide.BUY if direction == "LONG" else OrderSide.SELL

            if is_crypto:
                # Alpaca no soporta bracket orders (OCO) para crypto todavía:
                # se envía la entrada a mercado y la salida la gestiona el scanner.
                order_data = MarketOrderRequest(
                    symbol=alpaca_symbol, qty=qty, side=side, time_in_force=TimeInForce.GTC,
                )
                logger.warning(
                    "Alpaca crypto no soporta bracket orders — SL=%s/TP=%s no se enviaron a %s, "
                    "la salida la gestionará el scanner.", sl, tp, symbol,
                )
            else:
                order_data = MarketOrderRequest(
                    symbol=alpaca_symbol, qty=qty, side=side, time_in_force=TimeInForce.GTC,
                    order_class=OrderClass.BRACKET,
                    take_profit=TakeProfitRequest(limit_price=round(tp, 2)),
                    stop_loss=StopLossRequest(stop_price=round(sl, 2)),
                )

            order = client.submit_order(order_data)
            return {"status": "submitted", "broker": self.name, "symbol": symbol, "order_id": str(order.id)}
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al colocar orden Alpaca para %s: %s", symbol, exc)
            return {"status": "error", "broker": self.name, "error": str(exc)}

    def close_position(self, symbol: str, qty: int, direction: str) -> dict:
        try:
            from alpaca.trading.enums import OrderSide, TimeInForce
            from alpaca.trading.requests import MarketOrderRequest

            client = self._client()
            alpaca_symbol, _ = self._resolve_symbol(symbol)
            reverse_side = OrderSide.SELL if direction == "LONG" else OrderSide.BUY

            order_data = MarketOrderRequest(
                symbol=alpaca_symbol, qty=qty, side=reverse_side, time_in_force=TimeInForce.GTC,
            )
            order = client.submit_order(order_data)
            return {"status": "submitted", "broker": self.name, "symbol": symbol, "order_id": str(order.id)}
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al cerrar posición Alpaca de %s: %s", symbol, exc)
            return {"status": "error", "broker": self.name, "error": str(exc)}

    def get_positions(self) -> list[dict]:
        try:
            client = self._client()
            positions = client.get_all_positions()
            return [
                {
                    "symbol": p.symbol,
                    "qty": float(p.qty),
                    "avg_cost": float(p.avg_entry_price),
                    "unrealized_pl": float(p.unrealized_pl),
                }
                for p in positions
            ]
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al obtener posiciones Alpaca: %s", exc)
            return []

    def get_account(self) -> dict:
        try:
            client = self._client()
            account = client.get_account()
            return {
                "broker": self.name,
                "equity": float(account.equity),
                "cash": float(account.cash),
                "buying_power": float(account.buying_power),
                "mode": self.mode,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al obtener cuenta Alpaca: %s", exc)
            return {"broker": self.name, "error": str(exc)}
