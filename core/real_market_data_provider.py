# core/real_market_data_provider.py
import asyncio
from typing import List, Optional, Callable, Dict
import logging
from core.market_data_provider import MarketDataProvider, Interval, Candle, Ticker, OrderBook, OrderBookLevel
from connectors.base.exchange_connector import ExchangeConnector

logger = logging.getLogger(__name__)

class RealMarketDataProvider(MarketDataProvider):
    def __init__(self, connector: ExchangeConnector, mode: str = 'websocket', polling_interval: int = 5):
        self.connector = connector
        self.mode = mode          # 'websocket' или 'rest_polling'
        self.polling_interval = polling_interval
        self._polling_task: Optional[asyncio.Task] = None
        self._subscribed = set()
        self._callbacks: Dict[str, Callable] = {}

    async def connect(self) -> bool:
        return await self.connector.connect()

    async def disconnect(self):
        if self._polling_task:
            self._polling_task.cancel()
        await self.connector.disconnect()

    def is_connected(self) -> bool:
        return self.connector.status == 'online'

    async def get_candles(self, symbol: str, interval: Interval,
                          limit: int = 100,
                          start_time: Optional[int] = None,
                          end_time: Optional[int] = None) -> List[Candle]:
        interval_str = interval.value
        data = await self.connector.get_klines(symbol, interval_str, limit, start_time, end_time)
        return [Candle(
            timestamp=d['timestamp'],
            open=d['open'],
            high=d['high'],
            low=d['low'],
            close=d['close'],
            volume=d['volume']
        ) for d in data]

    async def get_ticker(self, symbol: str) -> Ticker:
        data = await self.connector.get_ticker(symbol)
        return Ticker(
            symbol=data['symbol'], last=data['last'], bid=data['bid'], ask=data['ask'],
            high=data['high'], low=data['low'], volume=data['volume'],
            quote_volume=data.get('quote_volume', 0), timestamp=data['timestamp']
        )

    async def get_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        data = await self.connector.get_order_book(symbol, depth)
        bids = [OrderBookLevel(price=p, amount=a) for p, a in data['bids']]
        asks = [OrderBookLevel(price=p, amount=a) for p, a in data['asks']]
        return OrderBook(symbol=symbol, bids=bids, asks=asks, timestamp=data['timestamp'])

    async def get_symbols(self, product_type: str = "") -> List[str]:
        return await self.connector.get_markets()

    async def subscribe_candles(self, symbol: str, interval: Interval,
                                callback: Callable[[Candle], None]):
        key = f"{symbol}_{interval.value}"
        self._callbacks[key] = callback
        if self.mode == 'websocket':
            async def ws_callback(data):
                # Ожидаем, что data — это список свечей или одна свеча
                if isinstance(data, list):
                    for candle_list in data:
                        if isinstance(candle_list, dict):
                            # Некоторые коннекторы могут давать словарь
                            candle = Candle(
                                timestamp=int(candle_list.get('timestamp', 0)),
                                open=float(candle_list.get('open', 0)),
                                high=float(candle_list.get('high', 0)),
                                low=float(candle_list.get('low', 0)),
                                close=float(candle_list.get('close', 0)),
                                volume=float(candle_list.get('volume', 0))
                            )
                        else:
                            # Ожидаем список [ts, open, high, low, close, volume]
                            candle = Candle(
                                timestamp=int(candle_list[0]),
                                open=float(candle_list[1]),
                                high=float(candle_list[2]),
                                low=float(candle_list[3]),
                                close=float(candle_list[4]),
                                volume=float(candle_list[5])
                            )
                        if asyncio.iscoroutinefunction(callback):
                            await callback(candle)
                        else:
                            callback(candle)
                else:
                    # Единичная свеча
                    candle = Candle(
                        timestamp=int(data[0]), open=float(data[1]),
                        high=float(data[2]), low=float(data[3]),
                        close=float(data[4]), volume=float(data[5])
                    )
                    if asyncio.iscoroutinefunction(callback):
                        await callback(candle)
                    else:
                        callback(candle)
            if hasattr(self.connector, 'subscribe_candles'):
                await self.connector.subscribe_candles(symbol, interval.value, ws_callback)
        else:
            # REST polling mode
            if not self._polling_task or self._polling_task.done():
                self._polling_task = asyncio.create_task(self._poll_candles_loop())
            self._subscribed.add((symbol, interval.value))

    async def _poll_candles_loop(self):
        last_timestamps = {}
        while True:
            await asyncio.sleep(self.polling_interval)
            for (symbol, interval_str) in list(self._subscribed):
                candles = await self.get_candles(symbol, Interval(interval_str), limit=1)
                if not candles:
                    continue
                new_candle = candles[0]
                last_ts = last_timestamps.get((symbol, interval_str))
                if last_ts is None or new_candle.timestamp > last_ts:
                    last_timestamps[(symbol, interval_str)] = new_candle.timestamp
                    callback = self._callbacks.get(f"{symbol}_{interval_str}")
                    if callback:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(new_candle)
                        else:
                            callback(new_candle)

    async def subscribe_ticker(self, symbol: str, callback: Callable[[Ticker], None]):
        if self.mode == 'websocket' and hasattr(self.connector, 'subscribe_ticker'):
            await self.connector.subscribe_ticker(symbol, callback)
        else:
            logger.warning("Ticker subscription not supported in polling mode")

    async def subscribe_order_book(self, symbol: str, depth: int,
                                   callback: Callable[[OrderBook], None]):
        if self.mode == 'websocket' and hasattr(self.connector, 'subscribe_orderbook'):
            await self.connector.subscribe_orderbook(symbol, callback)
        else:
            logger.warning("OrderBook subscription not supported in polling mode")

    async def subscribe_trades(self, symbol: str, callback: Callable[[Dict], None]):
        if self.mode == 'websocket' and hasattr(self.connector, 'subscribe_trades'):
            await self.connector.subscribe_trades(symbol, callback)
        else:
            logger.warning("Trades subscription not supported in polling mode")

    async def unsubscribe_all(self, symbol: str = None):
        if self.mode == 'websocket' and hasattr(self.connector, 'unsubscribe_all'):
            await self.connector.unsubscribe_all(symbol)
        else:
            self._subscribed.clear()