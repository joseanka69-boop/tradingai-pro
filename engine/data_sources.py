"""
Fuentes de datos de mercado:
- Futuros NQ/MNQ  -> IBKR (ib_insync), con fallback a yfinance
- Acciones        -> yfinance
- Crypto BTC/ETH  -> API pública de Binance (sin API key)

Todas las funciones devuelven un dict con arrays numpy:
{"open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}
o None si no se pudieron obtener datos.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import numpy as np
import pandas as pd
import requests

logger = logging.getLogger("tradingai.data_sources")

# Símbolos soportados y su configuración de mercado
SYMBOLS = {
    "NQ":   {"class": "future", "yf_ticker": "NQ=F",   "multiplier": 20, "tv": "CME_MINI:NQ1!"},
    "MNQ":  {"class": "future", "yf_ticker": "MNQ=F",  "multiplier": 2,  "tv": "CME_MINI:MNQ1!"},
    "AMD":  {"class": "stock",  "yf_ticker": "AMD",    "multiplier": 1,  "tv": "NASDAQ:AMD"},
    "NVDA": {"class": "stock",  "yf_ticker": "NVDA",   "multiplier": 1,  "tv": "NASDAQ:NVDA"},
    "AAPL": {"class": "stock",  "yf_ticker": "AAPL",   "multiplier": 1,  "tv": "NASDAQ:AAPL"},
    "TSLA": {"class": "stock",  "yf_ticker": "TSLA",   "multiplier": 1,  "tv": "NASDAQ:TSLA"},
    "BTC":  {"class": "crypto", "binance": "BTCUSDT",  "multiplier": 1,  "tv": "BITSTAMP:BTCUSD"},
    "ETH":  {"class": "crypto", "binance": "ETHUSDT",  "multiplier": 1,  "tv": "BITSTAMP:ETHUSD"},
}

BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"

_ib_connection = None  # Conexión IBKR reutilizable (ib_insync.IB)


def _bars_from_df(df: "pd.DataFrame") -> Optional[dict]:
    if df is None or df.empty:
        return None
    df = df.dropna()
    if df.empty:
        return None
    return {
        "open": df["Open"].to_numpy(dtype=float),
        "high": df["High"].to_numpy(dtype=float),
        "low": df["Low"].to_numpy(dtype=float),
        "close": df["Close"].to_numpy(dtype=float),
        "volume": df["Volume"].to_numpy(dtype=float) if "Volume" in df else np.zeros(len(df)),
    }


def fetch_yfinance_bars(ticker: str, period: str = "1d", interval: str = "5m") -> Optional[dict]:
    """Descarga barras desde yfinance. Usado para acciones y como fallback de futuros."""
    try:
        import yfinance as yf

        df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=False)
        # yfinance a veces devuelve columnas multi-índice cuando se pasa un solo ticker
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return _bars_from_df(df)
    except Exception as exc:  # noqa: BLE001 - queremos degradar sin tumbar el scanner
        logger.warning("yfinance falló para %s: %s", ticker, exc)
        return None


def fetch_binance_bars(symbol_pair: str, interval: str = "5m", limit: int = 60) -> Optional[dict]:
    """Descarga velas (klines) públicas de Binance para crypto, sin necesidad de API key."""
    try:
        params = {"symbol": symbol_pair, "interval": interval, "limit": limit}
        resp = requests.get(BINANCE_KLINES_URL, params=params, timeout=10)
        resp.raise_for_status()
        klines = resp.json()
        if not klines:
            return None

        opens = np.array([float(k[1]) for k in klines])
        highs = np.array([float(k[2]) for k in klines])
        lows = np.array([float(k[3]) for k in klines])
        closes = np.array([float(k[4]) for k in klines])
        volumes = np.array([float(k[5]) for k in klines])

        return {"open": opens, "high": highs, "low": lows, "close": closes, "volume": volumes}
    except Exception as exc:  # noqa: BLE001
        logger.warning("Binance falló para %s: %s", symbol_pair, exc)
        return None


def _get_ib_connection():
    """Conecta (una sola vez) a TWS/IB Gateway Paper (puerto configurable vía IBKR_PORT)."""
    global _ib_connection
    if _ib_connection is not None and _ib_connection.isConnected():
        return _ib_connection

    try:
        from ib_insync import IB

        ib = IB()
        host = os.getenv("IBKR_HOST", "127.0.0.1")
        port = int(os.getenv("IBKR_PORT", "7497"))
        client_id = int(os.getenv("IBKR_CLIENT_ID", "1"))
        ib.connect(host, port, clientId=client_id, timeout=4)
        _ib_connection = ib
        return ib
    except Exception as exc:  # noqa: BLE001
        logger.info("IBKR no disponible (%s) — se usará fallback yfinance", exc)
        return None


def fetch_ibkr_future_bars(root_symbol: str, duration: str = "1 D", bar_size: str = "5 mins") -> Optional[dict]:
    """Descarga barras históricas de un futuro (NQ/MNQ) vía IBKR, con reqHistoricalData."""
    ib = _get_ib_connection()
    if ib is None:
        return None

    try:
        from ib_insync import ContFuture

        contract = ContFuture(root_symbol, exchange="CME")
        ib.qualifyContracts(contract)
        bars = ib.reqHistoricalData(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=False,
        )
        if not bars:
            return None

        df = pd.DataFrame([{
            "Open": b.open, "High": b.high, "Low": b.low, "Close": b.close, "Volume": b.volume,
        } for b in bars])
        return _bars_from_df(df)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Descarga IBKR falló para %s: %s", root_symbol, exc)
        return None


def get_bars(symbol: str) -> Optional[dict]:
    """Punto de entrada único: obtiene barras de 5min según la clase del símbolo."""
    cfg = SYMBOLS.get(symbol)
    if cfg is None:
        return None

    if cfg["class"] == "future":
        bars = fetch_ibkr_future_bars(symbol)
        if bars is not None:
            return bars
        # Fallback a yfinance si IBKR no está disponible
        return fetch_yfinance_bars(cfg["yf_ticker"])

    if cfg["class"] == "stock":
        return fetch_yfinance_bars(cfg["yf_ticker"])

    if cfg["class"] == "crypto":
        return fetch_binance_bars(cfg["binance"])

    return None


def get_multiplier(symbol: str) -> float:
    return SYMBOLS.get(symbol, {}).get("multiplier", 1)


def get_tv_symbol(symbol: str) -> str:
    return SYMBOLS.get(symbol, {}).get("tv", symbol)
