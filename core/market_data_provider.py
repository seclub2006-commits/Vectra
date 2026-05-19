# core/market_data_provider.py
"""
Абстрактный провайдер рыночных данных.
Отделяет получение данных от конкретного источника (REST, WebSocket, база данных, симулятор).
Боты и индикаторы должны работать через этот интерфейс, а не напрямую с коннектором.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable, Any
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import pandas as pd 


class Interval(Enum):
    """Поддерживаемые таймфреймы."""
    M1 = "1m"
    M5 = "5m"
    M15 = "15m"
    M30 = "30m"
    H1 = "1H"
    H4 = "4H"
    D1 = "1D"
    W1 = "1W"


@dataclass
class Candle:
    """Свеча OHLCV."""
    timestamp: int      # milliseconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume
        }


@dataclass
class Ticker:
    """Тикер (текущая рыночная информация)."""
    symbol: str
    last: float
    bid: float
    ask: float
    high: float
    low: float
    volume: float
    quote_volume: float
    timestamp: int


@dataclass
class OrderBookLevel:
    """Уровень стакана."""
    price: float
    amount: float


@dataclass
class OrderBook:
    """Стакан ордеров."""
    symbol: str
    bids: List[OrderBookLevel]   # отсортированы по убыванию цены
    asks: List[OrderBookLevel]   # отсортированы по возрастанию цены
    timestamp: int


class MarketDataProvider(ABC):
    """
    Абстрактный провайдер рыночных данных.
    Реализации: RealMarketDataProvider (через коннектор), HistoricalDataProvider (из БД/файлов),
    SimulatedDataProvider (для бэктестов).
    """

    # ==================== 1. Получение исторических данных ====================

    @abstractmethod
    async def get_candles(self, symbol: str, interval: Interval,
                          limit: int = 100,
                          start_time: Optional[int] = None,
                          end_time: Optional[int] = None) -> List[Candle]:
        """
        Получить историю свечей.
        :param symbol: торговая пара (например, 'BTCUSDT')
        :param interval: таймфрейм
        :param limit: максимальное количество свечей
        :param start_time: начальная метка времени в мс (опционально)
        :param end_time: конечная метка времени в мс (опционально)
        :return: список свечей (от старых к новым)
        """
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Ticker:
        """Получить текущий тикер."""
        pass

    @abstractmethod
    async def get_order_book(self, symbol: str, depth: int = 20) -> OrderBook:
        """Получить текущий стакан ордеров."""
        pass

    @abstractmethod
    async def get_symbols(self, product_type: str = "") -> List[str]:
        """Получить список доступных торговых пар (опционально фильтр по типу продукта)."""
        pass

    # ==================== 2. Подписка на реальное время (WebSocket) ====================

    @abstractmethod
    async def subscribe_candles(self, symbol: str, interval: Interval,
                                callback: Callable[[Candle], None]):
        """
        Подписаться на обновления свечей в реальном времени.
        :param callback: асинхронная функция, принимающая Candle
        """
        pass

    @abstractmethod
    async def subscribe_ticker(self, symbol: str, callback: Callable[[Ticker], None]):
        """Подписаться на обновления тикера."""
        pass

    @abstractmethod
    async def subscribe_order_book(self, symbol: str, depth: int,
                                   callback: Callable[[OrderBook], None]):
        """Подписаться на обновления стакана."""
        pass

    @abstractmethod
    async def subscribe_trades(self, symbol: str, callback: Callable[[Dict], None]):
        """Подписаться на последние сделки (trades)."""
        pass

    @abstractmethod
    async def unsubscribe_all(self, symbol: str = None):
        """Отписаться от всех каналов (опционально по символу)."""
        pass

    # ==================== 3. Управление провайдером ====================

    @abstractmethod
    async def connect(self) -> bool:
        """Установить соединение с источником данных."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Закрыть соединения."""
        pass

    @abstractmethod
    def is_connected(self) -> bool:
        """Проверить статус соединения."""
        pass

    # ==================== 4. Вспомогательные методы ====================

    async def get_candles_dataframe(self, symbol: str, interval: Interval,
                                    limit: int = 100) -> 'pd.DataFrame':
        """
        Удобный метод: получить свечи в виде pandas DataFrame.
        Требует импорта pandas (не делаем его в абстрактном классе, но реализация может его использовать).
        """
        candles = await self.get_candles(symbol, interval, limit)
        if not candles:
            return None
        import pandas as pd
        df = pd.DataFrame([c.to_dict() for c in candles])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    async def get_current_price(self, symbol: str) -> float:
        """Вернуть последнюю цену (из тикера)."""
        ticker = await self.get_ticker(symbol)
        return ticker.last