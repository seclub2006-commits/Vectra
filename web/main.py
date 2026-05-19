# web/main.py
"""
Главный модуль веб-сервера.
Подключает роутеры, WebSocket обработчики, раздаёт статику.
Добавлен маршрут /manual-terminal для нового ручного терминала.
"""

import os
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from web.config import WEB_HOST, WEB_PORT, CORS_ORIGINS, CORE_HOST, CORE_PORT
from web.dependencies import set_grpc_client, get_grpc_client, get_current_user
from web.websocket_manager import ConnectionManager, websocket_candles_handler, websocket_updates_handler
from web.routers import (
    bots_router,
    connectors_router,
    market_router,
    trading_router,
    logs_router,
    manual_router,
    auth_router,
)

logger = logging.getLogger("web.main")

# Глобальный менеджер WebSocket соединений
ws_manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом: подключение к gRPC ядру и фоновые задачи."""
    logger.info("Starting Vectra Web Server...")
    
    # Устанавливаем глобальный grpc_client в dependencies
    from web.grpc_client import GrpcCoreClient
    client = GrpcCoreClient(host=CORE_HOST, port=CORE_PORT, password=os.getenv("CORE_PASSWORD", ""))
    set_grpc_client(client)
    
    # Запускаем фоновую задачу широковещательных обновлений
    broadcast_task = None
    try:
        await client.ensure_connection()
        logger.info("Initial connection to gRPC core established")
        
        from web.services.broadcast_service import start_broadcast_service
        broadcast_task = await start_broadcast_service(client, ws_manager)
        
    except Exception as e:
        logger.warning(f"Could not establish initial connection to core: {e}")
    
    yield
    
    # Shutdown
    if broadcast_task:
        broadcast_task.cancel()
        try:
            await broadcast_task
        except asyncio.CancelledError:
            pass
    await client.disconnect()
    logger.info("Web Server shut down")


# Создаём приложение FastAPI
app = FastAPI(
    title="Vectra Trading API",
    description="REST и WebSocket API для управления торговыми ботами",
    version="2.0.0",
    lifespan=lifespan
)

# Добавляем CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Подключаем роутеры
app.include_router(bots_router)
app.include_router(connectors_router)
app.include_router(market_router)
app.include_router(trading_router)
app.include_router(logs_router)
app.include_router(manual_router)
app.include_router(auth_router)


# ==================== ПУБЛИЧНЫЕ ЭНДПОИНТЫ ====================
@app.get("/api/health")
async def health_check():
    """Проверка работоспособности сервера."""
    return {"status": "ok", "message": "Vectra Web Server is running"}


@app.get("/api/strategy/params_schema")
async def get_strategy_params_schema(
    strategy_name: str = Query(..., description="Полное имя стратегии, например 'trend.ema_bot.EmaBot'"),
    client = Depends(get_grpc_client),
    _ = Depends(get_current_user)
):
    """Получить схему параметров стратегии по её имени (без запуска бота)."""
    try:
        schema = await client.get_strategy_params_schema(strategy_name)
        return {"status": "ok", "data": schema}
    except Exception as e:
        logger.error(f"Error getting strategy params schema for {strategy_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== WEBSOCKЕТ ЭНДПОИНТЫ ====================
@app.websocket("/ws/candles")
async def ws_candles(
    websocket,
    connector: str,
    symbol: str,
    timeframe: str,
    market_data_source: str = "websocket",
    market_data_source_config: str = ""
):
    """Стриминг свечей в реальном времени."""
    client = get_grpc_client()
    if client is None:
        await websocket.close(code=1011, reason="gRPC client not ready")
        return
    await websocket_candles_handler(
        websocket, connector, symbol, timeframe,
        market_data_source, market_data_source_config,
        client
    )


@app.websocket("/ws/updates")
async def ws_updates(websocket):
    """Широковещательные обновления (статусы ботов)."""
    await websocket_updates_handler(websocket, ws_manager)


# ==================== СТАТИКА И SPA ====================
app.mount("/static", StaticFiles(directory="web/static", html=False), name="static")

# ---- НОВЫЙ МАРШРУТ ДЛЯ РУЧНОГО ТЕРМИНАЛА ----
@app.get("/manual-terminal")
async def get_manual_terminal():
    """Отдаёт HTML нового ручного терминала."""
    terminal_path = os.path.join("web", "static", "manual_terminal.html")
    if os.path.exists(terminal_path):
        return FileResponse(terminal_path)
    raise HTTPException(status_code=404, detail="Manual terminal page not found")

# ---- ОСНОВНОЙ SPA МАРШРУТ ----
@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Отдаём index.html для всех остальных маршрутов (SPA)."""
    if full_path.startswith("api/") or full_path.startswith("ws/") or full_path.startswith("static/"):
        raise HTTPException(status_code=404)
    index_path = os.path.join("web", "static", "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    raise HTTPException(status_code=404)


# ==================== ЗАПУСК ====================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "web.main:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=True
    )