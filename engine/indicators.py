"""
Indicadores técnicos implementados desde cero con numpy (sin ta-lib).
Todas las funciones reciben arrays de numpy y devuelven el último valor
del indicador (o una tupla de valores para Bollinger).
"""
from __future__ import annotations

import numpy as np


def calc_rsi(closes: np.ndarray, period: int = 14) -> float:
    """RSI clásico de Wilder sobre el cierre."""
    if len(closes) < period + 1:
        return 50.0

    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    # Suavizado de Wilder para el resto de la serie
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def calc_zscore(closes: np.ndarray, period: int = 20) -> float:
    """Z-Score del último precio respecto a la media/desviación de la ventana."""
    if len(closes) < period:
        return 0.0

    window = closes[-period:]
    mean = np.mean(window)
    std = np.std(window)

    if std == 0:
        return 0.0
    return float((closes[-1] - mean) / std)


def calc_bollinger(closes: np.ndarray, period: int = 20, mult: float = 2.0) -> tuple[float, float, float]:
    """Devuelve (banda_superior, media_movil, banda_inferior)."""
    if len(closes) < period:
        price = float(closes[-1]) if len(closes) else 0.0
        return price, price, price

    window = closes[-period:]
    mid = float(np.mean(window))
    std = float(np.std(window))
    upper = mid + mult * std
    lower = mid - mult * std
    return upper, mid, lower


def calc_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Average True Range (suavizado de Wilder)."""
    if len(closes) < 2:
        return 0.0

    prev_closes = closes[:-1]
    highs_r = highs[1:]
    lows_r = lows[1:]

    tr = np.maximum.reduce([
        highs_r - lows_r,
        np.abs(highs_r - prev_closes),
        np.abs(lows_r - prev_closes),
    ])

    if len(tr) < period:
        return float(np.mean(tr)) if len(tr) else 0.0

    atr = np.mean(tr[:period])
    for i in range(period, len(tr)):
        atr = (atr * (period - 1) + tr[i]) / period
    return float(atr)


def calc_adx(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
    """Average Directional Index."""
    n = len(closes)
    if n < period + 1:
        return 0.0

    up_move = highs[1:] - highs[:-1]
    down_move = lows[:-1] - lows[1:]

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    prev_closes = closes[:-1]
    highs_r = highs[1:]
    lows_r = lows[1:]
    tr = np.maximum.reduce([
        highs_r - lows_r,
        np.abs(highs_r - prev_closes),
        np.abs(lows_r - prev_closes),
    ])

    def wilder_smooth(values: np.ndarray, period: int) -> np.ndarray:
        smoothed = np.zeros_like(values)
        smoothed[period - 1] = np.sum(values[:period])
        for i in range(period, len(values)):
            smoothed[i] = smoothed[i - 1] - (smoothed[i - 1] / period) + values[i]
        return smoothed

    if len(tr) < period:
        return 0.0

    tr_smooth = wilder_smooth(tr, period)
    plus_dm_smooth = wilder_smooth(plus_dm, period)
    minus_dm_smooth = wilder_smooth(minus_dm, period)

    with np.errstate(divide="ignore", invalid="ignore"):
        plus_di = 100.0 * np.divide(plus_dm_smooth, tr_smooth, out=np.zeros_like(tr_smooth), where=tr_smooth != 0)
        minus_di = 100.0 * np.divide(minus_dm_smooth, tr_smooth, out=np.zeros_like(tr_smooth), where=tr_smooth != 0)
        dx = 100.0 * np.divide(
            np.abs(plus_di - minus_di), (plus_di + minus_di),
            out=np.zeros_like(tr_smooth), where=(plus_di + minus_di) != 0,
        )

    valid_dx = dx[period - 1:]
    if len(valid_dx) < period:
        return float(np.mean(valid_dx)) if len(valid_dx) else 0.0
    return float(np.mean(valid_dx[-period:]))


def calc_slope(closes: np.ndarray, period: int = 20) -> float:
    """Pendiente de la regresión lineal sobre la ventana de cierres."""
    if len(closes) < period:
        period = len(closes)
    if period < 2:
        return 0.0

    window = closes[-period:]
    x = np.arange(period)
    slope, _ = np.polyfit(x, window, 1)
    return float(slope)
