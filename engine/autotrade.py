"""
Gestión de Auto Trade: modo Paper (simulado) y modo Real (IBKR).

- Modo PAPER: no requiere IBKR. Simula la ejecución con los precios reales
  que entrega el scanner y calcula el P&L usando el multiplicador correcto
  de cada instrumento (NQ=$20/pt, MNQ=$2/pt, acciones=$1/acción, crypto=$1/u).
- Modo REAL: solo se activa si AUTOTRADE_MODE=real en el .env. Envía
  bracket orders (entrada + Stop Loss + Take Profit en una sola orden) a
  IBKR real (puerto 7496).

Los usuarios se guardan en data/autotrade_users.json. Cada usuario nuevo
arranca con un trial gratuito de 30 días en modo Paper.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from engine import whatsapp
from engine.scanner import Signal, should_exit

logger = logging.getLogger("tradingai.autotrade")

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
USERS_FILE = DATA_DIR / "autotrade_users.json"

TRIAL_DAYS = 30


@dataclass
class Position:
    symbol: str
    direction: str  # LONG | SHORT
    qty: int
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_zscore: float
    opened_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class User:
    user_id: str
    phone: str
    plan: str
    qty: int
    symbols: list[str]
    mode: str  # "paper" | "real"
    created_at: str
    trial_ends_at: str
    open_positions: dict = field(default_factory=dict)   # symbol -> Position.to_dict()
    closed_trades: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load_users() -> dict[str, dict]:
    if not USERS_FILE.exists():
        return {}
    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def _save_users(users: dict[str, dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=2, ensure_ascii=False)


class AutoTradeManager:
    """Administra usuarios de Auto Trade y procesa señales del scanner."""

    def __init__(self):
        self.users: dict[str, dict] = _load_users()
        self.mode_default = os.getenv("AUTOTRADE_MODE", "paper")

    # ------------------------------------------------------------------ #
    # Gestión de usuarios
    # ------------------------------------------------------------------ #
    def register_user(self, phone: str, plan: str, qty: int, symbols: list[str]) -> dict:
        user_id = str(uuid.uuid4())
        now = _now()
        user = User(
            user_id=user_id,
            phone=phone,
            plan=plan,
            qty=qty,
            symbols=symbols,
            mode="paper",  # el trial siempre arranca en paper
            created_at=now.isoformat(),
            trial_ends_at=(now + timedelta(days=TRIAL_DAYS)).isoformat(),
        )
        self.users[user_id] = user.to_dict()
        _save_users(self.users)
        return self.users[user_id]

    def get_user(self, user_id: str) -> Optional[dict]:
        return self.users.get(user_id)

    def list_users(self) -> list[dict]:
        return list(self.users.values())

    def _effective_mode(self, user: dict) -> str:
        """El modo real solo se activa si el usuario lo tiene Y el sistema lo permite."""
        if user["mode"] == "real" and self.mode_default == "real":
            return "real"
        return "paper"

    def check_trial_expirations(self) -> None:
        """Marca a los usuarios cuyo trial expiró y dispara notificación de upgrade."""
        now = _now()
        for user in self.users.values():
            trial_end = datetime.fromisoformat(user["trial_ends_at"])
            if user["plan"] == "trial" and now > trial_end and not user.get("trial_notified"):
                user["trial_notified"] = True
                _save_users(self.users)
                # El envío real se dispara de forma asíncrona desde el router/scheduler

    # ------------------------------------------------------------------ #
    # Procesamiento de señales
    # ------------------------------------------------------------------ #
    async def process_signal(self, signal: Signal, prev_zscore: Optional[float] = None) -> None:
        """Evalúa la señal contra todos los usuarios suscritos a ese símbolo."""
        for user_id, user in self.users.items():
            if signal.symbol not in user.get("symbols", []):
                continue

            open_pos = user["open_positions"].get(signal.symbol)

            if open_pos is None:
                if signal.direction in ("LONG", "SHORT"):
                    await self._open_position(user, signal)
            else:
                await self._check_exit(user, signal, open_pos, prev_zscore)

        _save_users(self.users)

    async def _open_position(self, user: dict, signal: Signal) -> None:
        mode = self._effective_mode(user)
        qty = user["qty"]

        position = Position(
            symbol=signal.symbol,
            direction=signal.direction,
            qty=qty,
            entry_price=signal.price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            entry_zscore=signal.zscore,
        )

        if mode == "real":
            self._place_ibkr_bracket_order(signal, qty)

        user["open_positions"][signal.symbol] = position.to_dict()

        hora = datetime.now(timezone.utc).strftime("%H:%M")
        await whatsapp.send_entry_alert(
            user["phone"], symbol=signal.symbol, direction=signal.direction, mode=mode, hora=hora,
            qty=qty, entry=signal.price, sl=signal.stop_loss, tp=signal.take_profit,
            z=signal.zscore, rsi=signal.rsi, adx=signal.adx,
        )

    async def _check_exit(self, user: dict, signal: Signal, open_pos: dict, prev_zscore: Optional[float]) -> None:
        exit_reason = None

        if prev_zscore is not None and should_exit(prev_zscore, signal.zscore):
            exit_reason = "zscore_reversion"
        elif open_pos["direction"] == "LONG" and signal.price <= open_pos["stop_loss"]:
            exit_reason = "stop_loss"
        elif open_pos["direction"] == "SHORT" and signal.price >= open_pos["stop_loss"]:
            exit_reason = "stop_loss"

        if exit_reason is None:
            return

        await self._close_position(user, signal.symbol, signal.price, exit_reason)

    async def _close_position(self, user: dict, symbol: str, exit_price: float, reason: str) -> dict:
        open_pos = user["open_positions"].pop(symbol, None)
        if open_pos is None:
            return {}

        pnl = self._calc_pnl(open_pos, exit_price)
        mode = self._effective_mode(user)

        trade_record = {
            **open_pos,
            "exit_price": exit_price,
            "closed_at": _now().isoformat(),
            "reason": reason,
            "pnl": round(pnl, 2),
            "mode": mode,
        }
        user["closed_trades"].append(trade_record)

        if mode == "real":
            self._close_ibkr_position(symbol)

        await whatsapp.send_exit_alert(
            user["phone"], symbol=symbol, direction=open_pos["direction"], mode=mode,
            entry=open_pos["entry_price"], exit_price=exit_price, pnl=pnl,
        )
        return trade_record

    def close_position_manual(self, user_id: str, symbol: str, exit_price: float) -> dict:
        """Cierre manual solicitado desde el panel (POST /api/autotrade/close)."""
        user = self.users.get(user_id)
        if user is None or symbol not in user["open_positions"]:
            return {}

        import asyncio
        return asyncio.run(self._close_position(user, symbol, exit_price, "manual"))

    @staticmethod
    def _calc_pnl(position: dict, exit_price: float) -> float:
        from engine.data_sources import get_multiplier

        multiplier = get_multiplier(position["symbol"])
        qty = position["qty"]
        diff = exit_price - position["entry_price"]
        if position["direction"] == "SHORT":
            diff = -diff
        return diff * multiplier * qty

    # ------------------------------------------------------------------ #
    # Ejecución real vía IBKR (bracket orders)
    # ------------------------------------------------------------------ #
    def _place_ibkr_bracket_order(self, signal: Signal, qty: int) -> None:
        try:
            from ib_insync import IB, MarketOrder, Stock, ContFuture

            ib = IB()
            ib.connect(
                os.getenv("IBKR_HOST", "127.0.0.1"),
                7496,  # puerto de cuenta real
                clientId=int(os.getenv("IBKR_CLIENT_ID", "1")),
                timeout=4,
            )

            if signal.symbol in ("NQ", "MNQ"):
                contract = ContFuture(signal.symbol, exchange="CME")
            else:
                contract = Stock(signal.symbol, "SMART", "USD")
            ib.qualifyContracts(contract)

            action = "BUY" if signal.direction == "LONG" else "SELL"
            bracket = ib.bracketOrder(
                action, qty,
                limitPrice=signal.price,
                takeProfitPrice=signal.take_profit,
                stopLossPrice=signal.stop_loss,
            )
            for order in bracket:
                ib.placeOrder(contract, order)

            ib.disconnect()
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al colocar bracket order real para %s: %s", signal.symbol, exc)

    def _close_ibkr_position(self, symbol: str) -> None:
        try:
            from ib_insync import IB, MarketOrder, Stock, ContFuture

            ib = IB()
            ib.connect(
                os.getenv("IBKR_HOST", "127.0.0.1"), 7496,
                clientId=int(os.getenv("IBKR_CLIENT_ID", "1")), timeout=4,
            )
            positions = [p for p in ib.positions() if p.contract.symbol == symbol]
            for p in positions:
                action = "SELL" if p.position > 0 else "BUY"
                ib.placeOrder(p.contract, MarketOrder(action, abs(p.position)))
            ib.disconnect()
        except Exception as exc:  # noqa: BLE001
            logger.error("Fallo al cerrar posición real de %s: %s", symbol, exc)
