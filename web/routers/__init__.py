# web/routers/__init__.py
"""
Инициализация и экспорт всех роутеров API.
"""

from web.routers.bots import router as bots_router
from web.routers.connectors import router as connectors_router
from web.routers.market import router as market_router
from web.routers.trading import router as trading_router
from web.routers.logs import router as logs_router
from web.routers.manual import router as manual_router
from web.routers.auth import router as auth_router   # <-- добавить

__all__ = [
    "bots_router",
    "connectors_router",
    "market_router",
    "trading_router",
    "logs_router",
    "manual_router",
    "auth_router",   # <-- добавить
]