"""
Motor de señales algorítmicas (Scanner).

Recorre todos los símbolos soportados, calcula los indicadores técnicos
y aplica la lógica de "triple certificación" para detectar señales LONG,
SHORT o EXIT. Funciona aunque IBKR no esté conectado (fallback a yfinance
para NQ/MNQ).
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

if __name__ == "__main__":
    # Permite ejecutar `python engine/scanner.py` directamente desde la raíz del proyecto
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import indicators as ind
from engine.data_sources import SYMBOLS, get_bars, get_multiplier, get_tv_symbol

logger = logging.getLogger("tradingai.scanner")

# Parámetros configurables del motor de señales
PARAMS = {
    "period": 20,
    "z_threshold_long": -2.0,
    "z_threshold_short": 2.0,
    "rsi_period": 14,
    "bb_period": 20,
    "bb_mult": 2.0,
    "adx_period": 14,
    "adx_max": 30.0,
    "atr_period": 14,
    "atr_mult": 2.5,
    "scan_interval": 60,  # segundos
}


@dataclass
class Signal:
    symbol: str
    tv_symbol: str
    price: float
    direction: str          # "LONG" | "SHORT" | "NEUTRAL"
    zscore: float
    rsi: float
    adx: float
    atr: float
    bb_upper: float
    bb_mid: float
    bb_lower: float
    stop_loss: Optional[float]
    take_profit: Optional[float]
    multiplier: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_symbol(symbol: str, params: dict = PARAMS) -> Optional[Signal]:
    """Calcula los indicadores de un símbolo y determina si hay señal LONG/SHORT."""
    bars = get_bars(symbol)
    if bars is None or len(bars["close"]) < max(params["period"], params["rsi_period"], params["adx_period"]) + 1:
        return None

    closes = bars["close"]
    highs = bars["high"]
    lows = bars["low"]

    price = float(closes[-1])
    zscore = ind.calc_zscore(closes, params["period"])
    rsi = ind.calc_rsi(closes, params["rsi_period"])
    bb_upper, bb_mid, bb_lower = ind.calc_bollinger(closes, params["bb_period"], params["bb_mult"])
    adx = ind.calc_adx(highs, lows, closes, params["adx_period"])
    atr = ind.calc_atr(highs, lows, closes, params["atr_period"])

    direction = "NEUTRAL"
    stop_loss = None
    take_profit = None

    # LONG: triple certificación (Z-Score, RSI, precio bajo banda inferior, ADX bajo)
    if (
        zscore <= params["z_threshold_long"]
        and rsi <= 30
        and price <= bb_lower
        and adx < params["adx_max"]
    ):
        direction = "LONG"
        stop_loss = price - params["atr_mult"] * atr
        take_profit = bb_mid  # Salida objetivo: reversión a la media (Z-Score cruza 0)

    # SHORT: triple certificación inversa
    elif (
        zscore >= params["z_threshold_short"]
        and rsi >= 70
        and price >= bb_upper
        and adx < params["adx_max"]
    ):
        direction = "SHORT"
        stop_loss = price + params["atr_mult"] * atr
        take_profit = bb_mid

    return Signal(
        symbol=symbol,
        tv_symbol=get_tv_symbol(symbol),
        price=price,
        direction=direction,
        zscore=round(zscore, 3),
        rsi=round(rsi, 2),
        adx=round(adx, 2),
        atr=round(atr, 4),
        bb_upper=round(bb_upper, 4),
        bb_mid=round(bb_mid, 4),
        bb_lower=round(bb_lower, 4),
        stop_loss=round(stop_loss, 4) if stop_loss is not None else None,
        take_profit=round(take_profit, 4) if take_profit is not None else None,
        multiplier=get_multiplier(symbol),
    )


def should_exit(zscore_prev: float, zscore_now: float) -> bool:
    """Señal de salida: el Z-Score cruza cero (reversión a la media)."""
    return (zscore_prev < 0 <= zscore_now) or (zscore_prev > 0 >= zscore_now)


class SignalScanner:
    """Escanea todos los símbolos en un ciclo continuo y mantiene el último estado."""

    def __init__(self, params: dict = None):
        self.params = params or PARAMS
        self.latest_signals: dict[str, Signal] = {}
        self._on_signal_callbacks = []
        self._running = False

    def on_signal(self, callback):
        """Registra un callback async(signal: Signal) llamado en cada nueva señal LONG/SHORT."""
        self._on_signal_callbacks.append(callback)

    def scan_once(self) -> dict[str, Signal]:
        results: dict[str, Signal] = {}
        for symbol in SYMBOLS:
            try:
                signal = evaluate_symbol(symbol, self.params)
            except Exception as exc:  # noqa: BLE001 - un símbolo caído no debe tumbar el scanner
                logger.exception("Error evaluando %s: %s", symbol, exc)
                signal = None

            if signal is not None:
                results[symbol] = signal

        self.latest_signals = results
        return results

    async def run_forever(self):
        """Bucle principal: escanea, dispara callbacks en señales nuevas, y espera el intervalo."""
        self._running = True
        previous_directions: dict[str, str] = {}

        while self._running:
            results = await asyncio.to_thread(self.scan_once)

            for symbol, signal in results.items():
                prev_dir = previous_directions.get(symbol, "NEUTRAL")
                if signal.direction != "NEUTRAL" and signal.direction != prev_dir:
                    for callback in self._on_signal_callbacks:
                        try:
                            await callback(signal)
                        except Exception:  # noqa: BLE001
                            logger.exception("Error en callback de señal para %s", symbol)
                previous_directions[symbol] = signal.direction

            await asyncio.sleep(self.params["scan_interval"])

    def stop(self):
        self._running = False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    scanner = SignalScanner()
    print("Escaneando símbolos:", list(SYMBOLS.keys()))
    signals = scanner.scan_once()
    for sym, sig in signals.items():
        print(f"{sym}: {sig.direction} @ {sig.price} | Z={sig.zscore} RSI={sig.rsi} ADX={sig.adx}")
    if not signals:
        print("No se pudieron obtener datos para ningún símbolo (revisa conexión a internet/IBKR).")
