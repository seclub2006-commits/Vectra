# web/routers/logs.py
"""
Эндпоинты для получения системных логов.
"""

from typing import Dict, Any, List

from fastapi import APIRouter, Depends, Query

from web.dependencies import get_current_user, get_grpc_client
from web.grpc_client import GrpcCoreClient

router = APIRouter(prefix="/api", tags=["logs"])


@router.get("/logs")
async def get_logs_since(
    since_timestamp: int = Query(..., description="Начальная метка времени в мс"),
    limit: int = Query(1000, description="Максимальное количество записей"),
    client: GrpcCoreClient = Depends(get_grpc_client),
    _=Depends(get_current_user)
) -> Dict[str, Any]:
    """Получить логи с указанного времени."""
    logs = await client.get_logs_since(since_timestamp, limit)
    return {"status": "ok", "data": logs}