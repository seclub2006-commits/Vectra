# connectors/bitget/websocket_manager.py
"""
Менеджер WebSocket для Bitget.
Поддерживает публичные (wss://ws.bitget.com/v2/ws/public) и приватные (wss://ws.bitget.com/v2/ws/private) каналы.
Автоматически переподключается при обрыве, отправляет ping каждые 30 секунд.
Восстанавливает подписки после переподключения.
Поддерживает разные типы продуктов: SPOT, USDT-FUTURES, COIN-FUTURES, USDC-FUTURES.
"""

import asyncio
import json
import logging
import time
from typing import Dict, List, Optional, Callable, Any, Union

import websockets

from connectors.bitget.signature import generate_ws_sign

logger = logging.getLogger(__name__)


class BitgetWebSocketManager:
    """
    Управляет WebSocket-соединениями для Bitget.
    """

    def __init__(self, api_key: str, secret: str, passphrase: str, demo: bool = False,
                 config: Optional[Dict] = None):
        self.api_key = api_key
        self.secret = secret
        self.passphrase = passphrase
        self.demo = demo
        
        # Извлекаем настройки из конфига, если он передан
        if config is None:
            config = {}
        self.ping_interval = int(config.get('ping_interval', 30))   # принудительно int
        self.reconnect_delay = int(config.get('reconnect_delay', 5))

        self._ws_public: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_private: Optional[websockets.WebSocketClientProtocol] = None
        self._public_task: Optional[asyncio.Task] = None
        self._private_task: Optional[asyncio.Task] = None

        # Хранилища подписок: {channel: [(instId, callback, extra_params)]}
        self._public_subscriptions: Dict[str, List[tuple]] = {}
        self._private_subscriptions: Dict[str, List[tuple]] = {}

        self._public_channel_params: Dict[str, Dict] = {}
        self._private_channel_params: Dict[str, Dict] = {}

        self._running = False
        self._reconnect_delay_current = 1

        # URL-ы
        if demo:
            self.ws_public_url = 'wss://wspap.bitget.com/v2/ws/public'
            self.ws_private_url = 'wss://wspap.bitget.com/v2/ws/private'
        else:
            self.ws_public_url = 'wss://ws.bitget.com/v2/ws/public'
            self.ws_private_url = 'wss://ws.bitget.com/v2/ws/private'

    async def start(self):
        """Запускает WebSocket-менеджеры."""
        if self._running:
            return
        self._running = True
        self._public_task = asyncio.create_task(self._run_ws_public())
        self._private_task = asyncio.create_task(self._run_ws_private())

    async def stop(self):
        """Останавливает WebSocket-менеджеры."""
        self._running = False
        if self._public_task:
            self._public_task.cancel()
        if self._private_task:
            self._private_task.cancel()
        if self._ws_public:
            await self._ws_public.close()
        if self._ws_private:
            await self._ws_private.close()

    # -------------------- Публичные методы для подписки --------------------

    async def subscribe_ticker(self, symbol: str, callback: Callable, product_type: str = "USDT-FUTURES"):
        await self._subscribe_public("ticker", symbol.upper(), callback, product_type=product_type)

    async def subscribe_candles(self, symbol: str, interval: str, callback: Callable, product_type: str = "USDT-FUTURES"):
        channel = f"candle{interval}"
        await self._subscribe_public(channel, symbol.upper(), callback, product_type=product_type)

    async def subscribe_depth(self, symbol: str, callback: Callable, limit: int = 20, product_type: str = "USDT-FUTURES"):
        if limit <= 5:
            channel = "books5"
        elif limit <= 15:
            channel = "books15"
        else:
            channel = "books"
        extra = {"limit": str(limit)} if channel == "books" else {}
        await self._subscribe_public(channel, symbol.upper(), callback, product_type=product_type, extra=extra)

    async def subscribe_trades(self, symbol: str, callback: Callable, product_type: str = "USDT-FUTURES"):
        await self._subscribe_public("trade", symbol.upper(), callback, product_type=product_type)

    async def subscribe_auction(self, symbol: str, callback: Callable, product_type: str = "SPOT"):
        await self._subscribe_public("auction", symbol.upper(), callback, product_type=product_type)

    async def subscribe_orders(self, inst_id: str = "default", callback: Callable = None, product_type: str = "USDT-FUTURES"):
        await self._subscribe_private("orders", inst_id, callback, product_type=product_type)

    async def subscribe_positions(self, inst_id: str = "default", callback: Callable = None, product_type: str = "USDT-FUTURES"):
        await self._subscribe_private("positions", inst_id, callback, product_type=product_type)

    async def subscribe_account(self, callback: Callable = None, product_type: str = "USDT-FUTURES"):
        await self._subscribe_private("account", "default", callback, product_type=product_type)

    async def subscribe_fills(self, callback: Callable = None, product_type: str = "USDT-FUTURES"):
        await self._subscribe_private("fill", "default", callback, product_type=product_type)

    async def subscribe_orders_algo(self, callback: Callable = None, product_type: str = "USDT-FUTURES"):
        await self._subscribe_private("orders-algo", "default", callback, product_type=product_type)

    async def unsubscribe_all(self, inst_id: str = None):
        """Отписывается от всех каналов (опционально по inst_id)."""
        for is_private, subs_dict in [(False, self._public_subscriptions), (True, self._private_subscriptions)]:
            for channel in list(subs_dict.keys()):
                if inst_id:
                    subs_dict[channel] = [(i, cb, params) for i, cb, params in subs_dict[channel] if i != inst_id]
                    if not subs_dict[channel]:
                        del subs_dict[channel]
                else:
                    del subs_dict[channel]

    # -------------------- Внутренние методы --------------------

    async def _subscribe_public(self, channel: str, inst_id: str, callback: Callable,
                                product_type: str = "USDT-FUTURES", extra: Dict = None):
        self._public_subscriptions.setdefault(channel, []).append((inst_id, callback, extra or {}))
        self._public_channel_params[channel] = {"product_type": product_type}
        if self._ws_public and self._ws_public.open:
            await self._send_subscribe(self._ws_public, channel, inst_id, product_type, extra)

    async def _subscribe_private(self, channel: str, inst_id: str, callback: Callable,
                                 product_type: str = "USDT-FUTURES", extra: Dict = None):
        self._private_subscriptions.setdefault(channel, []).append((inst_id, callback, extra or {}))
        self._private_channel_params[channel] = {"product_type": product_type}
        if self._ws_private and self._ws_private.open:
            await self._send_subscribe(self._ws_private, channel, inst_id, product_type, extra)

    async def _send_subscribe(self, ws, channel: str, inst_id: str, product_type: str, extra: Dict = None):
        args = {
            "instType": product_type,
            "channel": channel,
            "instId": inst_id
        }
        if extra:
            args.update(extra)
        msg = {
            "op": "subscribe",
            "args": [args]
        }
        await ws.send(json.dumps(msg))
        logger.debug(f"Subscribed to {channel}:{inst_id} on {product_type}")

    async def _send_unsubscribe(self, ws, channel: str, inst_id: str, product_type: str):
        args = {
            "instType": product_type,
            "channel": channel,
            "instId": inst_id
        }
        msg = {
            "op": "unsubscribe",
            "args": [args]
        }
        await ws.send(json.dumps(msg))

    # -------------------- Управление соединениями --------------------

    async def _run_ws_public(self):
        while self._running:
            try:
                self._ws_public = await self._connect_websocket(private=False)
                # Запускаем задачу пинга
                ping_task = asyncio.create_task(self._send_ping_loop(self._ws_public))
                # Восстанавливаем подписки
                for channel, subscriptions in self._public_subscriptions.items():
                    product_type = self._public_channel_params.get(channel, {}).get("product_type", "USDT-FUTURES")
                    for inst_id, _, extra in subscriptions:
                        await self._send_subscribe(self._ws_public, channel, inst_id, product_type, extra)
                await self._ws_listener(self._ws_public, is_private=False)
                ping_task.cancel()
            except Exception as e:
                if not self._running:
                    break
                logger.error(f"Public WebSocket error: {e}, reconnecting in {self._reconnect_delay_current}s")
                await asyncio.sleep(self._reconnect_delay_current)
                self._reconnect_delay_current = min(self._reconnect_delay_current * 2, self.reconnect_delay * 6)
            else:
                self._reconnect_delay_current = 1

    async def _run_ws_private(self):
        while self._running:
            try:
                self._ws_private = await self._connect_websocket(private=True)
                # Логинимся
                if not await self._login_websocket(self._ws_private):
                    raise Exception("WebSocket login failed")
                ping_task = asyncio.create_task(self._send_ping_loop(self._ws_private))
                # Восстанавливаем подписки
                for channel, subscriptions in self._private_subscriptions.items():
                    product_type = self._private_channel_params.get(channel, {}).get("product_type", "USDT-FUTURES")
                    for inst_id, _, extra in subscriptions:
                        await self._send_subscribe(self._ws_private, channel, inst_id, product_type, extra)
                await self._ws_listener(self._ws_private, is_private=True)
                ping_task.cancel()
            except Exception as e:
                if not self._running:
                    break
                logger.error(f"Private WebSocket error: {e}, reconnecting in {self._reconnect_delay_current}s")
                await asyncio.sleep(self._reconnect_delay_current)
                self._reconnect_delay_current = min(self._reconnect_delay_current * 2, self.reconnect_delay * 6)
            else:
                self._reconnect_delay_current = 1

    async def _connect_websocket(self, private: bool = False) -> websockets.WebSocketClientProtocol:
        url = self.ws_private_url if private else self.ws_public_url
        ws = await websockets.connect(
            url,
            ping_interval=None,
            ping_timeout=None,
            close_timeout=10,
            max_size=2**23
        )
        logger.info(f"WebSocket {'private' if private else 'public'} connected to {url}")
        return ws

    async def _login_websocket(self, ws) -> bool:
        timestamp = str(int(time.time()))
        sign = generate_ws_sign(self.secret, timestamp)
        login_msg = {
            "op": "login",
            "args": [{
                "apiKey": self.api_key,
                "passphrase": self.passphrase,
                "timestamp": timestamp,
                "sign": sign
            }]
        }
        await ws.send(json.dumps(login_msg))
        resp = await ws.recv()
        data = json.loads(resp)
        if data.get('code') == 0 and data.get('event') == 'login':
            logger.info("WebSocket login successful")
            return True
        else:
            logger.error(f"WebSocket login failed: {data}")
            return False

    async def _send_ping_loop(self, ws):
        """Отправляет ping с заданным интервалом."""
        try:
            while self._running:
                await asyncio.sleep(self.ping_interval)   # self.ping_interval теперь int
                if ws and ws.open:
                    try:
                        await ws.send("ping")
                        logger.debug("Sent ping")
                    except Exception as e:
                        logger.warning(f"Failed to send ping: {e}")
                        break
        except asyncio.CancelledError:
            pass

    async def _ws_listener(self, ws, is_private: bool):
        try:
            async for message in ws:
                if message == "pong":
                    logger.debug("Received pong")
                    continue
                data = json.loads(message)
                # Обработка событий subscribe/unsubscribe/login
                if 'event' in data and data['event'] in ('subscribe', 'unsubscribe', 'login'):
                    if data['event'] == 'subscribe':
                        logger.debug(f"Subscribe confirmed: {data.get('arg')}")
                    continue
                # Ошибки
                if 'code' in data and data['code'] != 0:
                    logger.error(f"WebSocket error: {data}")
                    continue
                # Данные по каналу
                arg = data.get('arg', {})
                channel = arg.get('channel')
                if not channel:
                    continue
                subscriptions = self._private_subscriptions if is_private else self._public_subscriptions
                for _, callback, _ in subscriptions.get(channel, []):
                    if callback:
                        try:
                            if asyncio.iscoroutinefunction(callback):
                                await callback(data['data'])
                            else:
                                callback(data['data'])
                        except Exception as e:
                            logger.error(f"Callback error for channel {channel}: {e}")
        except websockets.ConnectionClosed:
            logger.warning("WebSocket connection closed, will reconnect")
            raise
        except Exception as e:
            logger.error(f"WebSocket listener error: {e}")
            raise