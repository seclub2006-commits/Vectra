# bots/base_bot.py
"""
Абстрактный базовый класс для всех торговых ботов.
Содержит ВСЕ возможные методы, которые могут понадобиться в любом типе бота.
Добавлена поддержка ручного управления (manual override) и описания стратегии для визуализации.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from enum import Enum
import asyncio
import logging


class BotTradeSide(Enum):
    LONG = "long"
    SHORT = "short"
    NONE = "none"


class BotOrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP_MARKET = "stop_market"
    STOP_LIMIT = "stop_limit"
    TAKE_PROFIT_MARKET = "take_profit_market"
    TAKE_PROFIT_LIMIT = "take_profit_limit"


class BotStatus(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"


class BaseBot(ABC):
    """
    Абстрактный бот. Все конкретные стратегии должны наследовать этот класс.
    """

    def __init__(self, name: str, connector, market_data, time_provider, config: Dict[str, Any]):
        self.name = name
        self.connector = connector
        self.market_data = market_data
        self.time_provider = time_provider
        self.config = config
        self._status = BotStatus.STOPPED
        self._logger = logging.getLogger(f"bot.{name}")
        self._error_message: Optional[str] = None
        self._cancel_event: Optional[asyncio.Event] = None
        self._manual_override: bool = False

    def set_cancel_event(self, event: asyncio.Event):
        """Устанавливает событие отмены, которое бот должен периодически проверять."""
        self._cancel_event = event

    async def check_cancelled(self):
        """Проверить, не был ли вызван cancel. Если был – поднять исключение для выхода."""
        if self._cancel_event and self._cancel_event.is_set():
            self._logger.info(f"Bot {self.name} received cancel signal")
            raise asyncio.CancelledError(f"Bot {self.name} cancelled")

    # ==================== Ручное управление ====================
    @abstractmethod
    async def manual_open_position(self, side: str, size_usdt: float, **kwargs) -> Dict:
        """
        Открыть позицию вручную (через интерфейс ручного бота).
        При этом бот переходит в режим ручного управления (manual_override = True)
        и не будет совершать автоматических действий, пока не будет вызван release_manual_control.
        """
        pass

    @abstractmethod
    async def manual_close_position(self, price: float = None) -> Dict:
        """
        Закрыть текущую позицию вручную.
        После закрытия бот остаётся в ручном режиме (не открывает новую позицию автоматически).
        """
        pass

    async def set_manual_override(self, enabled: bool):
        """
        Включить/выключить режим ручного управления.
        Если enabled=True – бот прекращает любые автоматические торговые действия.
        Если enabled=False – бот возвращается к нормальной работе (но не открывает позицию мгновенно,
        а ждёт следующего сигнала).
        """
        self._manual_override = enabled
        self._logger.info(f"Manual override set to {enabled} for bot {self.name}")

    async def release_manual_control(self):
        """
        Полностью выйти из режима ручного управления и сбросить флаги.
        """
        self._manual_override = False
        self._logger.info(f"Manual control released for bot {self.name}")

    # ==================== Описание стратегии для визуализации ====================
    @abstractmethod
    def get_strategy_description(self) -> Dict[str, Any]:
        pass

    # ==================== Вспомогательный метод для преобразования булевых параметров ====================
    @staticmethod
    def _parse_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() == 'true'
        return bool(value)

    # ==================== 1. Жизненный цикл ====================
    @abstractmethod
    async def start(self):
        pass

    @abstractmethod
    async def stop(self):
        pass

    @abstractmethod
    def get_status(self) -> Dict[str, Any]:
        pass

    async def pause(self):
        if self._status == BotStatus.RUNNING:
            self._status = BotStatus.PAUSED
            self._logger.info(f"Bot {self.name} paused")

    async def resume(self):
        if self._status == BotStatus.PAUSED:
            self._status = BotStatus.RUNNING
            self._logger.info(f"Bot {self.name} resumed")

    # ==================== 2. Обработка рыночных событий ====================
    async def on_tick(self, symbol: str, price: float):
        pass

    async def on_candle(self, symbol: str, candle: Dict):
        pass

    async def on_order_book_update(self, symbol: str, bids: List, asks: List):
        pass

    async def on_trade(self, trade: Dict):
        pass

    async def on_balance_update(self, balances: Dict[str, float]):
        pass

    async def on_position_update(self, positions: List[Dict]):
        pass

    async def on_order_filled(self, order_data: Dict):
        pass

    # ==================== 3. Управление параметрами ====================
    @classmethod
    def get_params_schema(cls) -> Dict[str, Any]:
        return {}

    async def set_parameter(self, name: str, value: Any):
        if name in self.config:
            self.config[name] = value
            self._logger.info(f"Parameter {name} updated to {value}")
            await self.on_parameters_changed({name: value})

    async def set_parameters(self, params: Dict[str, Any]):
        for name, value in params.items():
            if name in self.config:
                self.config[name] = value
        self._logger.info(f"Parameters updated: {params}")
        await self.on_parameters_changed(params)

    async def on_parameters_changed(self, changed_params: Dict[str, Any]):
        pass

    # ==================== 4. Управление позициями и ордерами (ИСПРАВЛЕНО) ====================
    async def open_position(self, side: BotTradeSide, price: float = None,
                            order_type: BotOrderType = BotOrderType.MARKET,
                            size_usdt: float = None, manual: bool = False) -> Optional[Dict]:
        """
        Открыть позицию.
        Если manual=False и _manual_override=True, операция блокируется.
        При manual=True флаг игнорируется.
        """
        if not manual and self._manual_override:
            self._logger.warning(f"Bot {self.name} is under manual override, cannot open position automatically")
            return None

        if size_usdt is None:
            size_usdt = self.config.get("position_size", 10.0)
        try:
            size_usdt = float(size_usdt)
        except (TypeError, ValueError):
            self._logger.error(f"Invalid size_usdt: {size_usdt}")
            return None

        if price is None:
            ticker = await self.connector.get_ticker(self.config["symbol"])
            try:
                price = float(ticker.get("last", 0))
            except (TypeError, ValueError):
                self._logger.error(f"Invalid price from ticker: {ticker.get('last')}")
                return None
        else:
            try:
                price = float(price)
            except (TypeError, ValueError):
                self._logger.error(f"Invalid price argument: {price}")
                return None

        if price <= 0:
            self._logger.error(f"Cannot open position: invalid price {price}")
            return None

        quantity = size_usdt / price
        order = await self.connector.create_order(
            symbol=self.config["symbol"],
            side="buy" if side == BotTradeSide.LONG else "sell",
            order_type=order_type.value,
            quantity=quantity,
            price=price if order_type == BotOrderType.LIMIT else None
        )
        return order

    async def close_position(self, side: BotTradeSide = None, price: float = None,
                             manual: bool = False) -> Optional[Dict]:
        """
        Закрыть позицию.
        Если manual=False и _manual_override=True, блокируется.
        """
        if not manual and self._manual_override:
            self._logger.warning(f"Bot {self.name} is under manual override, cannot close position automatically")
            return None
        hold_side = "" if side is None else side.value
        return await self.connector.close_position(self.config["symbol"], hold_side)

    # ==================== 5. Метрики и статистика ====================
    async def get_metrics(self) -> Dict[str, Any]:
        return {
            "total_trades": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "total_pnl": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
        }

    async def reset_metrics(self):
        pass

    # ==================== 6. Валидация ====================
    def validate_config(self) -> bool:
        if not self.config.get("symbol"):
            self._logger.error("Symbol is required in config")
            return False
        if self.config.get("position_size", 0) <= 0:
            self._logger.error("Position size must be positive")
            return False
        if not self.connector:
            self._logger.error("Connector is not set")
            return False
        return True

    # ==================== 7. Вспомогательные свойства ====================
    @property
    def is_running(self) -> bool:
        return self._status == BotStatus.RUNNING

    @property
    def is_paused(self) -> bool:
        return self._status == BotStatus.PAUSED

    @property
    def status(self) -> BotStatus:
        return self._status

    @property
    def last_error(self) -> Optional[str]:
        return self._error_message