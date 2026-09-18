"""
Broker IBKR (Interactive Brokers) vía ib_insync.

- Modo Paper: TWS/IB Gateway en el puerto IBKR_PORT (por defecto 7497).
- Modo Real:  TWS/IB Gateway en el puerto 7496.

El modo efectivo lo decide AUTOTRADE_MODE en el .env (gating global de
seguridad); este broker solo se instancia cuando ese modo ya es "real".
"""
from __future__ import annotations

import logging
import os

from engine.brokers import BaseBroker

logger = logging.getLogger("tradingai.brokers.ibkr")

REAL_PORT = 7496


class IBKRBroker(BaseBroker):
    name = "ibkr"

    def __init__(self):
        self.host = os.getenv("IBKR_HOST", "127.0.0.1")
        self.client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))
        # AUTOTRADE_MODE ya está en "real" cuando este broker se usa para operar en vivo;
        # el puerto de datos (paper) se controla por separado en engine/data_sources.py
        self.port = REAL_PORT

    def _connect(self):
        from ib_insync import IB

        ib = IB()
        ib.connect(self.host, self.port, clientId=self.client_id, timeout=4)
        return ib

    @staticmethod
    def _get_contract(symbol: str):
        from ib_insync import ContFuture, Stock

        if symbol in ("NQ", "MNQ"):
            return ContFuture(symbol, exchange="CME")
        # BTC/ETH no se operan vía IBKR en este proyecto (usar Alpaca para crypto)
        return Stock(symbol, "SMART", "USD")

    def place_order(self, symbol: str, direction: str, qty: int, sl: float, tp: float) -> dict:
        """Bracket order manual: entrada a mercado + Take Profit (LMT) + Stop Loss (STP)."""
        try:
            from ib_insync import LimitOrder, MarketOrder, StopOrder

            ib = self._connect()
            contract = self._get_contract(symbol)
            ib.qualifyContracts(contract)

            action = "BUY" if direction == "LONG" else "SELL"
            reverse_action = "SELL" if direction == "LONG" else "BUY"

            parent = MarketOrder(action, qty)
            parent.orderId = ib.client.getReqId()
            parent.transmit = False

            take_profit = LimitOrder(reverse_action, qty, tp)
            take_profit.orderId = ib.client.getReqId()
            take_profit.parentId = parent.orderId
            take_profit.transmit = False

            stop_loss = StopOrder(reverse_action, qty, sl)
            stop_loss.orderId = ib.client.getReqId()
            stop_loss.parentId = parent.orderId
            stop_loss.transmit = True

            for order in (parent, take_profit, stop_loss):
                ib.placeOrder(contract, order)

            ib.disconnect()
            return {"status": "submitted", "broker": self.name, "symbol": symbol, "qty": qty}
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al colocar bracket order IBKR para %s: %s", symbol, exc)
            return {"status": "error", "broker": self.name, "error": str(exc)}

    def close_position(self, symbol: str, qty: int, direction: str) -> dict:
        try:
            from ib_insync import MarketOrder

            ib = self._connect()
            positions = [p for p in ib.positions() if p.contract.symbol == symbol]

            if not positions:
                ib.disconnect()
                return {"status": "no_position", "broker": self.name, "symbol": symbol}

            action = "SELL" if direction == "LONG" else "BUY"
            for p in positions:
                ib.placeOrder(p.contract, MarketOrder(action, min(qty, abs(p.position))))

            ib.disconnect()
            return {"status": "submitted", "broker": self.name, "symbol": symbol}
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al cerrar posición IBKR de %s: %s", symbol, exc)
            return {"status": "error", "broker": self.name, "error": str(exc)}

    def get_positions(self) -> list[dict]:
        try:
            ib = self._connect()
            positions = [
                {
                    "symbol": p.contract.symbol,
                    "qty": p.position,
                    "avg_cost": p.avgCost,
                }
                for p in ib.positions()
            ]
            ib.disconnect()
            return positions
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al obtener posiciones IBKR: %s", exc)
            return []

    def get_account(self) -> dict:
        try:
            ib = self._connect()
            summary = {item.tag: item.value for item in ib.accountSummary()}
            ib.disconnect()
            return {
                "broker": self.name,
                "equity": summary.get("NetLiquidation"),
                "cash": summary.get("TotalCashValue"),
                "buying_power": summary.get("BuyingPower"),
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al obtener cuenta IBKR: %s", exc)
            return {"broker": self.name, "error": str(exc)}
