# core/csv_market_data_provider.py
import asyncio
import csv
import pandas as pd
from pathlib import Path
from typing import List, Optional, Callable, Dict
import logging
from core.market_data_provider import MarketDataProvider, Interval, Candle, Ticker, OrderBook, OrderBookLevel

logger = logging.getLogger(__name__)

class CSVMarketDataProvider(MarketDataProvider):
    """Провайдер из CSV-файла. Подписка на свечи воспроизводит историю с заданной задержкой."""

    def __init__(self, csv_path: str, symbol: str, replay_delay_seconds: float = 60.0):
        self.csv_path = Path(csv_path)
        self.symbol = symbol.upper()
        self.replay_delay = replay_delay_seconds
        self._data: List[Candle] = []
        self._playback_task: Optional[asyncio.Task] = None
        self._callbacks = []
        self._load_csv()

    def _load_csv(self):
        """Загружает CSV с колонками: timestamp, open, high, low, close, volume"""
        if not self.csv_path.exists():
            raise FileNotFoundError(f"CSV file not found: {self.csv_path}")
        df = pd.read_csv(self.csv_path)
        required = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        for col in required:
            if col not in df.columns:
                raise ValueError(f"CSV must contain column: {col}")
        df['timestamp'] = pd.to_numeric(df['timestamp'])
        for col in required[1:]:
            df[col] = pd.to_numeric(df[col])
        self._data = [
            Candle(
                timestamp=int(row['timestamp']),
                open=row['open'],
                high=row['high'],
                low=row['low'],
                close=row['close'],
                volume=row['volume']
            )
            for _, row in df.iterrows()
        ]
        logger.info(f"Loaded {len(self._data)} candles from {self.csv_path}")

    async def connect(self) -> bool:
        return True

    async def disconnect(self):
        if self._playback_task:
            self._playback_task.cancel()

    def is_connected(self) -> bool:
        return True

    async def get_candles(self, symbol: str, interval: Interval,
                          limit: int = 100,
                          start_time: Optional[int] = None,
                          end_time: Optional[int] = None) -> List[Candle]:
        # Возвращает срез из загруженных данных
        if symbol != self.symbol:
            return []
        result = self._data
        if start_time:
            result = [c for c in result if c.timestamp >= start_time]
        if end_time:
            result = [c for c in result if c.timestamp <= end_time]
        return result[-limit:]

    async def subscribe_candles(self, symbol: str, interval: Interval,
                                callback: Callable[[Candle], None]):
        """Воспроизводит свечи из CSV по таймеру."""
        if symbol != self.symbol:
            return
        self._callbacks.append(callback)
        if not self._playback_task or self._playback_task.done():
            self._playback_task = asyncio.create_task(self._replay_candles())

    async def _replay_candles(self):
        """Последовательно передаёт свечи с задержкой."""
        for candle in self._data:
            await asyncio.sleep(self.replay_delay)
            for cb in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(candle)
                    else:
                        cb(candle)
                except Exception as e:
                    logger.error(f"Error in CSV replay callback: {e}")

    # Остальные методы – заглушки
    async def get_ticker(self, symbol: str) -> Ticker:
        raise NotImplementedError("CSV provider does not support live ticker")

    async def get_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        raise NotImplementedError("CSV provider does not support order book")

    async def get_symbols(self, product_type: str = "") -> List[str]:
        return [self.symbol] if self._data else []

    async def subscribe_ticker(self, symbol: str, callback): pass
    async def subscribe_order_book(self, symbol: str, depth: int, callback): pass
    async def subscribe_trades(self, symbol: str, callback): pass
    async def unsubscribe_all(self, symbol: str = None): pass