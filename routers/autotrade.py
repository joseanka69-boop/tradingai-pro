"""Endpoints de Auto Trade: registro de usuarios, estado y cierre manual de posiciones."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from engine.brokers import list_brokers

router = APIRouter(prefix="/api/autotrade", tags=["autotrade"])


class RegisterRequest(BaseModel):
    phone: str          # formato E.164, ej: +15551234567
    plan: str = "trial"
    qty: int = 1
    symbols: list[str]
    broker: str = "ibkr"  # "ibkr" | "alpaca"

    @field_validator("broker")
    @classmethod
    def validate_broker(cls, value: str) -> str:
        if value not in list_brokers():
            raise ValueError(f"Broker no soportado: '{value}'. Válidos: {list_brokers()}")
        return value


class CloseRequest(BaseModel):
    user_id: str
    symbol: str
    exit_price: float


@router.post("/register")
async def register(payload: RegisterRequest, request: Request):
    manager = request.app.state.autotrade_manager
    user = manager.register_user(payload.phone, payload.plan, payload.qty, payload.symbols, payload.broker)
    return user


@router.get("/user/{user_id}")
async def get_user(user_id: str, request: Request):
    manager = request.app.state.autotrade_manager
    user = manager.get_user(user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user


@router.post("/close")
async def close_position(payload: CloseRequest, request: Request):
    manager = request.app.state.autotrade_manager
    trade = manager.close_position_manual(payload.user_id, payload.symbol, payload.exit_price)
    if not trade:
        raise HTTPException(status_code=404, detail="No hay posición abierta para ese símbolo/usuario")
    return trade
