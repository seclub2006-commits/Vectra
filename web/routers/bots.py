# web/routers/bots.py
"""
Эндпоинты для управления торговыми ботами.
"""

from typing import List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException

from web.dependencies import get_current_user, get_grpc_client
from web.grpc_client import GrpcCoreClient
from web.models import (
    StartBotRequest, StopBotRequest, DeleteBotRequest,
    UpdateBotConfigRequest, SetBotParameterRequest,
    GetBotTradesRequest
)

router = APIRouter(prefix="/api/bots", tags=["bots"])


@router.get("")
async def get_bots_list(
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить список всех ботов."""
    bots = await client.get_bots_list()
    return {"status": "ok", "data": bots}


@router.post("/start")
async def start_bot(
    request: StartBotRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Запустить бота (создать нового или запустить существующего)."""
    result = await client.start_bot(
        bot_id=request.bot_id,
        name=request.name,
        strategy=request.strategy,
        connector_name=request.connector_name,
        symbol=request.symbol,
        timeframe=request.timeframe,
        position_size=request.position_size,
        params=request.params,
        market_data_source=request.market_data_source,
        market_data_source_config=request.market_data_source_config
    )
    status_str = "ok" if result["success"] else "error"
    return {"status": status_str, "message": result["message"], "bot_id": result["bot_id"]}


@router.post("/stop")
async def stop_bot(
    request: StopBotRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Остановить работающего бота."""
    result = await client.stop_bot(request.bot_id)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


@router.delete("/delete")
async def delete_bot(
    request: DeleteBotRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Удалить бота из базы данных (предварительно остановив)."""
    result = await client.delete_bot(request.bot_id)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


@router.get("/{bot_id}/status")
async def get_bot_status(
    bot_id: int,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить статус бота (running, позиция, цена входа и т.д.)."""
    status = await client.get_bot_status(bot_id)
    return {"status": "ok", "data": status}


@router.get("/{bot_id}/trades")
async def get_bot_trades(
    bot_id: int,
    limit: int = 100,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить историю сделок бота."""
    trades = await client.get_bot_trades(bot_id, limit)
    return {"status": "ok", "data": trades}


@router.post("/update_config")
async def update_bot_config(
    request: UpdateBotConfigRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Обновить конфигурацию бота (символ, таймфрейм, параметры и т.д.)."""
    result = await client.update_bot_config(
        bot_id=request.bot_id,
        connector_name=request.connector_name,
        symbol=request.symbol,
        timeframe=request.timeframe,
        position_size=request.position_size,
        params=request.params,
        emulator_enabled=request.emulator_enabled,
        market_data_source=request.market_data_source,
        market_data_source_config=request.market_data_source_config
    )
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


@router.get("/{bot_id}/params_schema")
async def get_bot_params_schema(
    bot_id: int,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить схему параметров стратегии бота."""
    schema = await client.get_bot_params_schema(bot_id)
    return {"status": "ok", "data": schema}


@router.post("/{bot_id}/set_parameter")
async def set_bot_parameter(
    bot_id: int,
    request: SetBotParameterRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Установить конкретный параметр бота (динамически)."""
    result = await client.set_bot_parameter(bot_id, request.param_name, request.param_value)
    return {"status": "ok" if result.get("success") else "error", "data": result.get("result")}


@router.get("/{bot_id}/market_data_source")
async def get_bot_market_data_source(
    bot_id: int,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить источник рыночных данных для бота."""
    source_info = await client.get_bot_market_data_source(bot_id)
    return {"status": "ok", "data": source_info}