# connectors/base/exchange_connector.py
"""
Базовый класс для всех коннекторов к биржам.
Содержит ВСЕ возможные методы для спота, маржи, фьючерсов, опционов.
Новые коннекторы переопределяют только то, что поддерживают.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable


class ExchangeConnector(ABC):
    """
    Абстрактный коннектор к бирже. Определяет единый интерфейс для всех торговых операций.
    Боты используют только этот интерфейс и не зависят от конкретной биржи.
    """

    def __init__(self, name: str, config: dict):
        """
        :param name: Уникальное имя коннектора (например, "bitget_futures")
        :param config: Словарь с настройками: api_key, api_secret, api_passphrase,
                       testnet (демо-режим), product_type и другие параметры.
        """
        self.name = name
        self.config = config
        self.status = "offline"       # offline, online, error
        self.logger = None  # будет установлен в наследнике

    # ==================== 1. ПОДКЛЮЧЕНИЕ И СТАТУС (абстрактные, обязательные) ====================

    @abstractmethod
    async def connect(self) -> bool:
        """Установить соединение с биржей, выполнить авторизацию (если требуются ключи)."""
        pass

    @abstractmethod
    async def disconnect(self):
        """Закрыть все активные соединения (REST-сессии, WebSocket-сокеты)."""
        pass

    @abstractmethod
    async def check_connection(self) -> bool:
        """Проверить, активно ли соединение с биржей (например, запрос тикера)."""
        pass

    # ==================== 2. РЫНОЧНЫЕ ДАННЫЕ ====================

    @abstractmethod
    async def get_server_time(self) -> int:
        """Серверное время в миллисекундах."""
        pass

    @abstractmethod
    async def get_ticker(self, symbol: str) -> Dict:
        """
        Получить текущий тикер по символу.
        :return: { 'symbol', 'last', 'bid', 'ask', 'high', 'low', 'volume', 'quote_volume', 'timestamp' }
        """
        pass

    @abstractmethod
    async def get_tickers(self, product_type: str = None) -> List[Dict]:
        """Получить тикеры для всех символов (опционально фильтр по типу продукта)."""
        pass

    @abstractmethod
    async def get_klines(self, symbol: str, interval: str, limit: int = 100,
                         start_time: Optional[int] = None,
                         end_time: Optional[int] = None) -> List[Dict]:
        """
        Получить историю свечей OHLCV.
        :return: список { 'timestamp', 'open', 'high', 'low', 'close', 'volume' }
        """
        pass

    @abstractmethod
    async def get_order_book(self, symbol: str, limit: int = 20, merge_scale: str = 'scale0') -> Dict:
        """
        Получить стакан ордеров (объединённый с заданной точностью).
        :return: { 'bids': [[price, amount], ...], 'asks': [[price, amount], ...], 'timestamp': int }
        """
        pass

    @abstractmethod
    async def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Получить последние сделки по символу."""
        pass

    @abstractmethod
    async def get_contracts(self, product_type: str, symbol: str = None) -> List[Dict]:
        """Получить конфигурацию контрактов (для фьючерсов)."""
        pass

    # ==================== 3. ТОРГОВЫЕ ОРДЕРА ====================

    @abstractmethod
    async def create_order(self, symbol: str, side: str, order_type: str,
                           quantity: float, price: Optional[float] = None,
                           reduce_only: bool = False, client_oid: str = None,
                           preset_tp: float = None, preset_sl: float = None,
                           stp_mode: str = 'none') -> Dict:
        """
        Создать ордер.
        :param side: 'buy' или 'sell'
        :param order_type: 'limit', 'market', 'stop_limit', 'stop_market' и т.д.
        :param reduce_only: только уменьшение позиции (для фьючерсов)
        :param client_oid: пользовательский ID ордера
        :param preset_tp: предустановленная цена тейк-профита
        :param preset_sl: предустановленная цена стоп-лосса
        :param stp_mode: режим самоторговли ('none', 'cancel_taker', 'cancel_maker', 'cancel_both')
        :return: { 'orderId', 'clientOid', 'symbol', 'status' }
        """
        pass

    @abstractmethod
    async def cancel_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        """Отменить ордер по ID или clientOid."""
        pass

    @abstractmethod
    async def cancel_all_orders(self, symbol: str = None, product_type: str = None) -> List[Dict]:
        """Отменить все активные ордера (опционально по символу или типу продукта)."""
        pass

    @abstractmethod
    async def get_open_orders(self, symbol: str = None, product_type: str = None) -> List[Dict]:
        """Получить список открытых ордеров."""
        pass

    @abstractmethod
    async def get_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        """Получить информацию об ордере по ID или clientOid."""
        pass

    @abstractmethod
    async def get_order_history(self, symbol: str = None, product_type: str = None,
                                start_time: int = None, end_time: int = None,
                                limit: int = 100) -> List[Dict]:
        """История ордеров (за 90 дней)."""
        pass

    @abstractmethod
    async def get_fills(self, symbol: str = None, product_type: str = None,
                        start_time: int = None, end_time: int = None,
                        limit: int = 100) -> List[Dict]:
        """История сделок (fills)."""
        pass

    # ==================== 4. БАЛАНСЫ И ПОЗИЦИИ ====================

    @abstractmethod
    async def get_balance(self, currency: str = None) -> List[Dict]:
        """
        Получить баланс кошелька (спот или фьючерсный).
        :return: [{ 'currency', 'available', 'frozen', 'total' }]
        """
        pass

    @abstractmethod
    async def get_positions(self, symbol: str = None) -> List[Dict]:
        """
        Получить открытые позиции (фьючерсы/маржа).
        :return: [{ 'symbol', 'side', 'size', 'entry_price', 'mark_price', 'pnl', 'leverage', 'margin', 'liquidation_price', 'margin_mode' }]
        """
        pass

    # ==================== 5. УПРАВЛЕНИЕ РИСКАМИ (SL/TP, плечо) ====================

    @abstractmethod
    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'crossed',
                           hold_side: str = None) -> Dict:
        """Установить плечо и режим маржи."""
        pass

    @abstractmethod
    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Dict:
        """Переключить режим маржи (isolated / crossed)."""
        pass

    @abstractmethod
    async def add_margin(self, symbol: str, amount: float, hold_side: str) -> Dict:
        """Добавить маржу к позиции (для изолированной маржи)."""
        pass

    @abstractmethod
    async def set_tpsl(self, symbol: str, hold_side: str, trigger_price: float,
                       execute_price: float, tpsl_type: str, size: float = 0) -> Dict:
        """
        Установить TP/SL плановый ордер.
        tpsl_type: 'profit_plan', 'loss_plan', 'moving_plan', 'pos_profit', 'pos_loss'
        """
        pass

    @abstractmethod
    async def cancel_tpsl(self, symbol: str, order_id: str) -> Dict:
        """Отменить TP/SL ордер."""
        pass

    @abstractmethod
    async def close_position(self, symbol: str, hold_side: str = '') -> Dict:
        """Закрыть позицию по рыночной цене."""
        pass

    # ==================== 6. ФЬЮЧЕРСНЫЕ СПЕЦИФИЧЕСКИЕ МЕТОДЫ ====================

    @abstractmethod
    async def get_funding_rate(self, symbol: str) -> Dict:
        """Текущая ставка финансирования."""
        pass

    @abstractmethod
    async def get_funding_history(self, symbol: str, limit: int = 20) -> List[Dict]:
        """История ставок финансирования."""
        pass

    @abstractmethod
    async def get_interest_rate_history(self, coin: str) -> Dict:
        """История процентных ставок."""
        pass

    # ==================== 7. WEBSOCKET И ПОТОКИ ДАННЫХ ====================

    @abstractmethod
    async def subscribe(self, channel: str, symbol: str = None, callback: Callable = None, private: bool = False):
        """Подписаться на WebSocket-канал (ticker, trades, depth, kline, user_data)."""
        pass

    @abstractmethod
    async def unsubscribe_all(self, symbol: str = None):
        """Отписаться от всех каналов (опционально по символу)."""
        pass

    # ==================== 8. ВСПОМОГАТЕЛЬНЫЕ МЕТОДЫ ====================

    async def get_markets(self) -> List[str]:
        """Получить список всех доступных торговых пар (по умолчанию через get_contracts)."""
        try:
            contracts = await self.get_contracts(self.config.get('product_type', 'USDT-FUTURES'))
            return [c['symbol'] for c in contracts]
        except:
            return []

    def normalize_symbol(self, symbol: str) -> str:
        """Привести символ к формату, понятному бирже."""
        return symbol.upper()