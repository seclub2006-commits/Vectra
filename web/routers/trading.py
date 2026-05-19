# web/routers/trading.py
"""
Эндпоинты для торговых операций: баланс, ордера, позиции, риск-менеджмент.
"""

from typing import Dict, Any, List

from fastapi import APIRouter, Depends, Query

from web.dependencies import get_current_user, get_grpc_client
from web.grpc_client import GrpcCoreClient
from web.models import (
    CreateOrderRequest, CancelOrderRequest,
    SetLeverageRequest, SetTPSLRequest, ClosePositionRequest
)

router = APIRouter(prefix="/api", tags=["trading"])


# ==================== БАЛАНС ====================
@router.get("/balance")
async def get_balance(
    connector_name: str = Query(..., description="Имя коннектора"),
    currency: str = Query("", description="Валюта (например USDT), пусто - все"),
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить баланс счёта."""
    balances = await client.get_balance(connector_name, currency)
    return {"status": "ok", "data": balances}


# ==================== ОРДЕРА ====================
@router.get("/orders")
async def get_open_orders(
    connector_name: str = Query(..., description="Имя коннектора"),
    symbol: str = Query("", description="Торговая пара (опционально)"),
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить список открытых ордеров."""
    orders = await client.get_open_orders(connector_name, symbol)
    return {"status": "ok", "data": orders}


@router.post("/order/create")
async def create_order(
    request: CreateOrderRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Создать новый ордер (лимитный, рыночный, с TP/SL)."""
    result = await client.create_order(
        connector_name=request.connector_name,
        symbol=request.symbol,
        side=request.side,
        order_type=request.order_type,
        quantity=request.quantity,
        price=request.price,
        preset_tp=request.preset_tp,
        preset_sl=request.preset_sl
    )
    if result["success"]:
        return {"status": "ok", "data": {"order_id": result["order_id"], "client_oid": result.get("client_oid")}}
    else:
        return {"status": "error", "error": result["error"]}


@router.post("/order/cancel")
async def cancel_order(
    request: CancelOrderRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Отменить открытый ордер по ID."""
    result = await client.cancel_order(request.connector_name, request.symbol, request.order_id)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


# ==================== ПОЗИЦИИ ====================
@router.get("/positions")
async def get_positions(
    connector_name: str = Query(..., description="Имя коннектора"),
    symbol: str = Query("", description="Торговая пара (опционально)"),
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить открытые позиции."""
    positions = await client.get_position(connector_name, symbol)
    return {"status": "ok", "data": positions}


@router.post("/position/close")
async def close_position(
    request: ClosePositionRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Закрыть позицию по символу (опционально указать сторону)."""
    result = await client.close_position(request.connector_name, request.symbol, request.hold_side)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


# ==================== РИСК-МЕНЕДЖМЕНТ ====================
@router.post("/leverage")
async def set_leverage(
    request: SetLeverageRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Установить плечо и режим маржи для символа."""
    result = await client.set_leverage(request.connector_name, request.symbol, request.leverage, request.margin_mode)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


@router.post("/tpsl")
async def set_tpsl(
    request: SetTPSLRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Установить тейк-профит или стоп-лосс (плановый ордер)."""
    result = await client.set_tpsl(
        request.connector_name, request.symbol, request.hold_side,
        request.trigger_price, request.execute_price, request.tpsl_type, request.size
    )
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}