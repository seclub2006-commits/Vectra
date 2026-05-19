# web/services/broadcast_service.py
"""
Фоновый сервис для широковещательной рассылки статусов ботов.
"""

import asyncio
import logging
from typing import Optional

from web.grpc_client import GrpcCoreClient
from web.websocket_manager import ConnectionManager

logger = logging.getLogger("web.broadcast")


async def broadcast_updates_loop(
    client: GrpcCoreClient,
    ws_manager: ConnectionManager,
    interval_seconds: int = 2
) -> None:
    """
    Фоновая задача: каждые interval_seconds секунд получает статусы всех ботов
    и рассылает их всем подключённым WebSocket-клиентам.
    """
    while True:
        await asyncio.sleep(interval_seconds)
        
        if not ws_manager.active_connections:
            continue
        
        try:
            # Получаем всех ботов
            bots = await client.get_bots_list()
            updates = []
            
            for bot in bots:
                try:
                    status = await client.get_bot_status(bot["id"])
                    trades = await client.get_bot_trades(bot["id"], limit=1000)
                    
                    closed_count = len([t for t in trades if t.get("close_time", 0) > 0])
                    total_pnl = sum(t.get("pnl", 0) for t in trades)
                    
                    updates.append({
                        "id": bot["id"],
                        "running": status.get("running", False),
                        "position_open": status.get("position_open", False),
                        "side": status.get("side", ""),
                        "entry_price": status.get("entry_price", 0.0),
                        "symbol": status.get("symbol", ""),
                        "closed_trades": closed_count,
                        "pnl": total_pnl
                    })
                except Exception as e:
                    logger.error(f"Error getting status for bot {bot['id']}: {e}")
                    updates.append({
                        "id": bot["id"],
                        "running": False,
                        "position_open": False,
                        "side": "",
                        "entry_price": 0.0,
                        "symbol": "",
                        "closed_trades": 0,
                        "pnl": 0.0
                    })
            
            await ws_manager.broadcast({
                "type": "bots_status",
                "data": updates
            })
            
        except Exception as e:
            logger.error(f"Broadcast error: {e}")


async def start_broadcast_service(
    client: GrpcCoreClient,
    ws_manager: ConnectionManager,
    interval_seconds: int = 2
) -> Optional[asyncio.Task]:
    """
    Запускает фоновую задачу широковещательных обновлений.
    Возвращает объект Task для последующей отмены.
    """
    task = asyncio.create_task(broadcast_updates_loop(client, ws_manager, interval_seconds))
    logger.info("Broadcast service started")
    return task