"""
Paquete de brokers de TradingAI Pro.

Define la interfaz común (`BaseBroker`) que implementan todos los brokers
soportados y la factoría `get_broker(name)` que instancia el broker
correcto según lo que el usuario eligió al registrarse.
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class BaseBroker(ABC):
    """Interfaz que debe implementar cualquier broker soportado por Auto Trade."""

    name: str = "base"

    @abstractmethod
    def place_order(self, symbol: str, direction: str, qty: int, sl: float, tp: float) -> dict:
        """Abre una posición con Stop Loss y Take Profit (bracket order cuando el broker lo soporta)."""
        raise NotImplementedError

    @abstractmethod
    def close_position(self, symbol: str, qty: int, direction: str) -> dict:
        """Cierra (total o parcialmente) una posición abierta."""
        raise NotImplementedError

    @abstractmethod
    def get_positions(self) -> list[dict]:
        """Devuelve las posiciones abiertas actuales en la cuenta del broker."""
        raise NotImplementedError

    @abstractmethod
    def get_account(self) -> dict:
        """Devuelve balance/equity/buying power de la cuenta."""
        raise NotImplementedError


_SUPPORTED_BROKERS = ("ibkr", "alpaca")


def get_broker(name: str) -> BaseBroker:
    """Instancia el broker solicitado. Soporta: "ibkr" | "alpaca"."""
    key = (name or "ibkr").strip().lower()

    if key == "ibkr":
        from engine.brokers.ibkr_broker import IBKRBroker
        return IBKRBroker()

    if key == "alpaca":
        from engine.brokers.alpaca_broker import AlpacaBroker
        return AlpacaBroker()

    raise ValueError(f"Broker no soportado: '{name}'. Brokers disponibles: {_SUPPORTED_BROKERS}")


def list_brokers() -> tuple[str, ...]:
    return _SUPPORTED_BROKERS
