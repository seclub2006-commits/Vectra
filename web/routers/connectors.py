# web/routers/connectors.py
"""
Эндпоинты для управления коннекторами к биржам.
"""

from typing import Dict, Any

from fastapi import APIRouter, Depends

from web.dependencies import get_current_user, get_grpc_client
from web.grpc_client import GrpcCoreClient
from web.models import (
    CreateConnectorRequest, UpdateConnectorRequest,
    SetConnectorStatusRequest
)

router = APIRouter(prefix="/api/connectors", tags=["connectors"])


@router.get("")
async def get_connectors(
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить список всех коннекторов."""
    connectors = await client.get_connectors_list()
    return {"status": "ok", "data": connectors}


@router.post("/create")
async def create_connector(
    request: CreateConnectorRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Создать новый коннектор."""
    settings = request.dict()
    result = await client.create_connector(settings)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


@router.get("/{name}/settings")
async def get_connector_settings(
    name: str,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить настройки коннектора (включая зашифрованные ключи)."""
    settings = await client.get_connector_settings(name)
    return {"status": "ok", "data": settings}


@router.put("/{name}/settings")
async def update_connector_settings(
    name: str,
    request: UpdateConnectorRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Обновить настройки коннектора (API ключи, параметры)."""
    result = await client.update_connector_settings(name, request.settings)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


@router.delete("/{name}/delete")
async def delete_connector(
    name: str,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Удалить коннектор (только если он не используется ботами)."""
    result = await client.delete_connector(name)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}


@router.post("/{name}/status")
async def set_connector_status(
    name: str,
    request: SetConnectorStatusRequest,
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Изменить статус коннектора (online/offline)."""
    result = await client.set_connector_status(name, request.status)
    return {"status": "ok" if result["success"] else "error", "message": result["message"]}