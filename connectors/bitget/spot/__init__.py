# connectors/bitget/spot/__init__.py
"""
Спотовый коннектор Bitget.
Объединяет миксины: MarketMixin, AccountMixin, OrderMixin, TriggerMixin, WebSocketMixin.
"""

import logging
import traceback
from typing import Dict, List, Optional, Any, Callable

from connectors.bitget.common import BitgetBaseConnector
from .market import MarketMixin
from .account import AccountMixin
from .orders import OrderMixin
from .trigger import TriggerMixin
from .websocket import WebSocketMixin

logger = logging.getLogger(__name__)


class BitgetSpotConnector(
    MarketMixin,
    AccountMixin,
    OrderMixin,
    TriggerMixin,
    WebSocketMixin,
    BitgetBaseConnector
):
    """Коннектор для спотовой торговли на Bitget."""

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.product_type = 'SPOT'
        self.logger = logging.getLogger(f"connector.spot.{name}")

    async def connect(self) -> bool:
        try:
            self.logger.info("Connecting to Bitget Spot (demo mode) ...")
            balances = await self.get_balance()
            self.logger.info(f"Balance fetched: {len(balances)} coins")
            self.status = 'online'
            self.logger.info(f"Spot connector {self.name} connected")
            return True
        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"Spot connector {self.name} connection failed: {type(e).__name__} - {e}")
            self.status = 'offline'
            return False

    async def get_markets(self) -> List[str]:
        tickers = await self.get_tickers()
        return [t['symbol'] for t in tickers]

    async def disconnect(self):
        if hasattr(self, '_ws_manager') and self._ws_manager is not None:
            try:
                await self._ws_manager.stop()
                self.logger.info("WebSocket manager stopped")
            except Exception as e:
                self.logger.error(f"Error stopping WebSocket manager: {e}")
        await super().disconnect()

    # ==================== НЕПОДДЕРЖИВАЕМЫЕ МЕТОДЫ ====================
    async def get_contracts(self, product_type: str, symbol: str = None) -> List[Dict]:
        raise NotImplementedError("Spot connector does not support contracts")

    async def get_positions(self, symbol: str = None) -> List[Dict]:
        return []

    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'crossed',
                           hold_side: str = None) -> Dict:
        raise NotImplementedError("Spot connector does not support leverage")

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Dict:
        raise NotImplementedError

    async def add_margin(self, symbol: str, amount: float, hold_side: str) -> Dict:
        raise NotImplementedError

    async def set_tpsl(self, symbol: str, hold_side: str, trigger_price: float,
                       execute_price: float, tpsl_type: str, size: float = 0) -> Dict:
        raise NotImplementedError

    async def cancel_tpsl(self, symbol: str, order_id: str) -> Dict:
        raise NotImplementedError

    async def close_position(self, symbol: str, hold_side: str = '') -> Dict:
        raise NotImplementedError

    async def get_funding_rate(self, symbol: str) -> Dict:
        raise NotImplementedError

    async def get_funding_history(self, symbol: str, limit: int = 20) -> List[Dict]:
        raise NotImplementedError

    async def get_interest_rate_history(self, coin: str) -> Dict:
        raise NotImplementedError