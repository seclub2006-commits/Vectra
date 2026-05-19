# core/data_manager.py
import asyncio
from collections import deque
from typing import Dict, List, Optional
import pandas as pd
import logging

from core.market_data_provider import MarketDataProvider, Interval, Candle

logger = logging.getLogger(__name__)


class DataManager:
    def __init__(self, market_data_provider: MarketDataProvider, max_history: int = 1000):
        self.provider = market_data_provider
        self.max_history = max_history
        self._buffers: Dict[str, deque] = {}
        self._running = False

    async def start(self):
        self._running = True
        logger.info("DataManager started")

    async def stop(self):
        self._running = False

    async def update_candle(self, symbol: str, candle: Candle):
        if symbol not in self._buffers:
            self._buffers[symbol] = deque(maxlen=self.max_history)
        buf = self._buffers[symbol]
        if buf and buf[-1].timestamp == candle.timestamp:
            buf[-1] = candle
        else:
            buf.append(candle)

    async def fetch_candles(self, symbol: str, interval: Interval, limit: int = 100,
                            start_time: Optional[int] = None,
                            end_time: Optional[int] = None) -> List[Candle]:
        candles = await self.provider.get_candles(symbol, interval, limit, start_time, end_time)
        for candle in candles:
            await self.update_candle(symbol, candle)
        return candles

    def get_candles(self, symbol: str, limit: int = 100) -> List[Dict]:
        buf = self._buffers.get(symbol, deque())
        candles = list(buf)[-limit:]
        return [c.to_dict() for c in candles]

    def get_dataframe(self, symbol: str, limit: int = 100) -> pd.DataFrame:
        candles = self.get_candles(symbol, limit)
        if not candles:
            return pd.DataFrame()
        df = pd.DataFrame(candles)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        return df