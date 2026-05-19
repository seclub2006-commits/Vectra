# web/websocket_manager.py
"""
WebSocket менеджер и обработчики для стриминга свечей и обновлений.
"""

import asyncio
import logging
from typing import List, Dict, Any

from fastapi import WebSocket, WebSocketDisconnect
from jose import jwt, JWTError

from web.config import JWT_SECRET_KEY, JWT_ALGORITHM
from web.grpc_client import GrpcCoreClient
import core_pb2

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Управляет активными WebSocket соединениями для широковещательных обновлений."""
    
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """Отправить сообщение всем подключённым клиентам."""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")


async def verify_websocket_token(token: str) -> bool:
    """Проверяет JWT токен из WebSocket query-параметра."""
    if not token:
        return False
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        # Проверяем, что в токене есть поле 'sub' (как при создании в auth.py)
        return payload.get("sub") is not None
    except JWTError as e:
        logger.warning(f"JWT verification failed: {e}")
        return False


async def websocket_candles_handler(
    websocket: WebSocket,
    connector: str,
    symbol: str,
    timeframe: str,
    market_data_source: str,
    market_data_source_config: str,
    grpc_client: GrpcCoreClient
):
    """
    Обработчик WebSocket-соединения для стриминга свечей.
    """
    token = websocket.query_params.get("token")
    if not token or not await verify_websocket_token(token):
        logger.warning(f"Candles WebSocket rejected: invalid token")
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await websocket.accept()
    try:
        request = core_pb2.SubscribeCandlesRequest(
            connector=connector,
            symbol=symbol,
            timeframe=timeframe,
            market_data_source=market_data_source,
            market_data_source_config=market_data_source_config
        )
        async for candle_pb in grpc_client.subscribe_candles_stream(request):
            await websocket.send_json({
                "timestamp": candle_pb.timestamp,
                "open": candle_pb.open,
                "high": candle_pb.high,
                "low": candle_pb.low,
                "close": candle_pb.close,
                "volume": candle_pb.volume
            })
    except WebSocketDisconnect:
        logger.info("Candles WebSocket disconnected")
    except Exception as e:
        logger.error(f"Candles WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except Exception:
            pass


async def websocket_updates_handler(websocket: WebSocket, manager: ConnectionManager):
    """
    Обработчик WebSocket-соединения для широковещательных обновлений (статусы ботов).
    """
    token = websocket.query_params.get("token")
    if not token or not await verify_websocket_token(token):
        logger.warning(f"Updates WebSocket rejected: invalid token")
        await websocket.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(websocket)
    try:
        while True:
            # Ожидаем любые сообщения от клиента (heartbeat)
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)