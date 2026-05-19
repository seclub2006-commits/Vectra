# connectors/bitget/futures/websocket.py
from typing import Callable

class WebSocketMixin:
    """Миксин для WebSocket подписок (фьючерсы)."""

    async def _ensure_ws_manager(self):
        if not hasattr(self, '_ws_manager') or self._ws_manager is None:
            from connectors.bitget.websocket_manager import BitgetWebSocketManager
            ws_config = {
                'ping_interval': self.ws_ping_interval,
                'reconnect_delay': self.ws_reconnect_delay,
            }
            self._ws_manager = BitgetWebSocketManager(
                self.api_key, self.api_secret, self.api_passphrase, self.demo, ws_config
            )
            await self._ws_manager.start()

    async def subscribe_ticker(self, symbol: str, callback: Callable):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_ticker(symbol, callback, product_type=self.product_type)

    async def subscribe_candles(self, symbol: str, interval: str, callback: Callable):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_candles(symbol, interval, callback, product_type=self.product_type)

    async def subscribe_depth(self, symbol: str, callback: Callable, limit: int = 20):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_depth(symbol, callback, limit=limit, product_type=self.product_type)

    async def subscribe_trades(self, symbol: str, callback: Callable):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_trades(symbol, callback, product_type=self.product_type)

    async def subscribe_orders(self, symbol: str = "default", callback: Callable = None):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_orders(symbol, callback, product_type=self.product_type)

    async def subscribe_positions(self, symbol: str = "default", callback: Callable = None):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_positions(symbol, callback, product_type=self.product_type)

    async def subscribe_account(self, callback: Callable = None):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_account(callback, product_type=self.product_type)

    async def subscribe_fills(self, callback: Callable = None):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_fills(callback, product_type=self.product_type)

    async def subscribe_orders_algo(self, callback: Callable = None):
        await self._ensure_ws_manager()
        await self._ws_manager.subscribe_orders_algo(callback, product_type=self.product_type)

    async def subscribe(self, channel: str, symbol: str = None, callback: Callable = None, private: bool = False):
        await self._ensure_ws_manager()
        if private:
            await self._ws_manager._subscribe_private(channel, symbol or 'default', callback, product_type=self.product_type)
        else:
            await self._ws_manager._subscribe_public(channel, symbol or 'default', callback, product_type=self.product_type)

    async def unsubscribe_all(self, symbol: str = None):
        if hasattr(self, '_ws_manager') and self._ws_manager:
            await self._ws_manager.unsubscribe_all(symbol)

    async def disconnect(self):
        if hasattr(self, '_ws_manager') and self._ws_manager:
            await self._ws_manager.stop()
        await super().disconnect()