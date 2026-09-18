"""
TradingAI Pro — punto de entrada de la aplicación FastAPI.

- Inicializa el SignalScanner y el AutoTradeManager al arrancar (lifespan).
- Expone un WebSocket en /ws que emite el estado de todas las señales
  cada 30 segundos.
- Sirve el frontend estático (HTML/CSS/JS puro) desde /frontend.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from engine.autotrade import AutoTradeManager
from engine.scanner import SignalScanner
from routers import ai, alerts, autotrade, news, signals

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("tradingai.main")


class ConnectionManager:
    """Mantiene la lista de clientes WebSocket conectados y difunde mensajes."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        stale = []
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:  # noqa: BLE001
                stale.append(connection)
        for connection in stale:
            self.disconnect(connection)


async def _broadcast_loop(app: FastAPI):
    """Emite el estado de todas las señales por WebSocket cada 30 segundos."""
    while True:
        signals_dict = {
            symbol: signal.to_dict()
            for symbol, signal in app.state.scanner.latest_signals.items()
        }
        await app.state.ws_manager.broadcast({"type": "signals", "data": signals_dict})
        await asyncio.sleep(30)


async def _autotrade_bridge(app: FastAPI, signal):
    """Callback del scanner: reenvía cada nueva señal LONG/SHORT al AutoTradeManager."""
    prev_zscore = app.state.prev_zscores.get(signal.symbol)
    await app.state.autotrade_manager.process_signal(signal, prev_zscore)
    app.state.prev_zscores[signal.symbol] = signal.zscore


@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup ---
    app.state.scanner = SignalScanner()
    app.state.autotrade_manager = AutoTradeManager()
    app.state.ws_manager = ConnectionManager()
    app.state.prev_zscores = {}

    app.state.scanner.on_signal(lambda signal: _autotrade_bridge(app, signal))

    scanner_task = asyncio.create_task(app.state.scanner.run_forever())
    broadcast_task = asyncio.create_task(_broadcast_loop(app))

    logger.info("TradingAI Pro iniciado — motor de señales corriendo en segundo plano")
    yield

    # --- Shutdown ---
    app.state.scanner.stop()
    scanner_task.cancel()
    broadcast_task.cancel()
    logger.info("TradingAI Pro detenido")


app = FastAPI(title="TradingAI Pro", lifespan=lifespan)

# CORS abierto en desarrollo
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(signals.router)
app.include_router(news.router)
app.include_router(ai.router)
app.include_router(autotrade.router)
app.include_router(alerts.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await app.state.ws_manager.connect(websocket)
    try:
        # Envía el estado actual inmediatamente al conectar
        signals_dict = {
            symbol: signal.to_dict()
            for symbol, signal in app.state.scanner.latest_signals.items()
        }
        await websocket.send_json({"type": "signals", "data": signals_dict})

        while True:
            # Mantiene la conexión viva; el broadcast periódico lo hace _broadcast_loop
            await websocket.receive_text()
    except WebSocketDisconnect:
        app.state.ws_manager.disconnect(websocket)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Sirve el frontend estático (HTML/CSS/JS puro)
app.mount("/frontend", StaticFiles(directory="frontend", html=True), name="frontend")
