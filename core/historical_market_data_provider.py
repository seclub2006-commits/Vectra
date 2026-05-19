# core/historical_market_data_provider.py
import asyncio
from typing import List, Optional, Callable, Dict
import logging
from core.market_data_provider import MarketDataProvider, Interval, Candle, Ticker, OrderBook, OrderBookLevel
from connectors.base.exchange_connector import ExchangeConnector
from core.database import Database
from core.models import CachedCandle
from sqlalchemy import select, and_, desc

logger = logging.getLogger(__name__)

class HistoricalMarketDataProvider(MarketDataProvider):
    """Провайдер с кэшированием свечей в SQLite. Подписки не поддерживает, возвращает только историю."""

    def __init__(self, connector: ExchangeConnector, db: Database):
        self.connector = connector
        self.db = db

    async def connect(self) -> bool:
        return await self.connector.connect()

    async def disconnect(self):
        await self.connector.disconnect()

    def is_connected(self) -> bool:
        return self.connector.status == 'online'

    async def get_candles(self, symbol: str, interval: Interval,
                          limit: int = 100,
                          start_time: Optional[int] = None,
                          end_time: Optional[int] = None) -> List[Candle]:
        # Сначала пробуем достать из кэша
        async with self.db.session_maker() as session:
            query = select(CachedCandle).where(
                CachedCandle.symbol == symbol,
                CachedCandle.interval == interval.value
            )
            if start_time:
                query = query.where(CachedCandle.timestamp >= start_time)
            if end_time:
                query = query.where(CachedCandle.timestamp <= end_time)
            query = query.order_by(desc(CachedCandle.timestamp)).limit(limit)
            result = await session.execute(query)
            candles_db = result.scalars().all()
            if len(candles_db) >= limit:
                # достаточно данных в кэше
                return [Candle(timestamp=c.timestamp, open=c.open, high=c.high,
                               low=c.low, close=c.close, volume=c.volume)
                        for c in reversed(candles_db)]
        # Не хватает – подгружаем с биржи и сохраняем
        interval_str = interval.value
        data = await self.connector.get_klines(symbol, interval_str, limit, start_time, end_time)
        candles = []
        async with self.db.session_maker() as session:
            for d in data:
                candle = Candle(timestamp=d['timestamp'], open=d['open'], high=d['high'],
                                low=d['low'], close=d['close'], volume=d['volume'])
                candles.append(candle)
                # Сохраняем в БД (проверяем уникальность)
                existing = await session.execute(
                    select(CachedCandle).where(
                        CachedCandle.symbol == symbol,
                        CachedCandle.interval == interval.value,
                        CachedCandle.timestamp == candle.timestamp
                    )
                )
                if not existing.scalar_one_or_none():
                    cached = CachedCandle(
                        symbol=symbol, interval=interval.value, timestamp=candle.timestamp,
                        open=candle.open, high=candle.high, low=candle.low,
                        close=candle.close, volume=candle.volume
                    )
                    session.add(cached)
            await session.commit()
        return candles

    async def get_ticker(self, symbol: str) -> Ticker:
        # Прокси к реальному коннектору
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

    # Подписки не поддерживаем
    async def subscribe_candles(self, symbol: str, interval: Interval, callback):
        raise NotImplementedError("Historical provider does not support live subscriptions")

    async def subscribe_ticker(self, symbol: str, callback): pass
    async def subscribe_order_book(self, symbol: str, depth: int, callback): pass
    async def subscribe_trades(self, symbol: str, callback): pass
    async def unsubscribe_all(self, symbol: str = None): pass