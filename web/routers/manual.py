# web/routers/manual.py
"""
Эндпоинты для ручного управления ботами: вызов методов, получение описания стратегии.
"""

from typing import Dict, Any

from fastapi import APIRouter, Depends, Query

from web.dependencies import get_current_user, get_grpc_client
from web.grpc_client import GrpcCoreClient
from web.models import CallManualBotRequest, CallBotMethodRequest

router = APIRouter(prefix="/api", tags=["manual"])


@router.post("/manual/call")
async def call_manual_bot(
    request: CallManualBotRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Вызвать метод ручного бота (например, manual_open_position)."""
    result = await client.call_manual_bot(request.bot_id, request.method, request.params)
    return {"status": "ok" if result["success"] else "error", "data": result.get("result"), "error": result.get("error")}


@router.post("/bot/method")
async def call_bot_method(
    request: CallBotMethodRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Вызвать произвольный метод любого бота (универсальный)."""
    result = await client.call_bot_method(request.bot_id, request.method_name, request.params)
    return {"status": "ok" if result["success"] else "error", "data": result.get("result"), "error": result.get("error")}


@router.get("/bot/strategy")
async def get_bot_strategy_description(
    bot_id: int = Query(..., description="ID бота"),
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить описание стратегии бота (индикаторы, уровни, условия)."""
    description = await client.get_bot_strategy_description(bot_id)
    return {"status": "ok", "data": description}