# bots/test/test_bot.py
import asyncio
import random
from typing import Dict, Any, Optional

from bots.base_bot import BaseBot, BotStatus


class TestBot(BaseBot):
    @classmethod
    def get_params_schema(cls):
        return {
            "test_param": {"type": "str", "default": "Hello World", "label": "Текстовая опция"},
            "dummy": {"type": "choice", "default": "Option A", "options": ["Option A", "Option B", "Option C"], "label": "Выпадающий список"},
            "emulator_enabled": {"type": "bool", "default": True, "label": "Режим эмуляции"},
            "timeframe": {"type": "str", "default": "1H", "label": "Таймфрейм для свечей"}
        }

    def __init__(self, name: str, connector, market_data, time_provider, config: Dict[str, Any]):
        super().__init__(name, connector, market_data, time_provider, config)
        self.symbol = config.get("symbol", "BTCUSDT")
        self.test_param = str(config.get("test_param", "Hello World"))
        self.dummy = str(config.get("dummy", "Option A"))
        self.emulator_enabled = self._parse_bool(config.get("emulator_enabled", True))
        self.timeframe = config.get("timeframe", "1H")
        self.position_size_usdt = float(config.get("position_size", 10.0))
        
        self.position: Optional[Dict] = None
        self.counter = 0
        self.last_price = 0.0
        self._subscription_task: Optional[asyncio.Task] = None
        self._keep_alive_task: Optional[asyncio.Task] = None

    async def start(self):
        try:
            if not self.validate_config():
                self._status = BotStatus.ERROR
                return
            self._status = BotStatus.RUNNING
            self._logger.info(f"[{self.name}] TestBot started. Param: {self.test_param}, Dummy: {self.dummy}")
            
            # Подписываемся на свечи в реальном режиме (если не эмуляция)
            if not self.emulator_enabled:
                interval = self._str_to_interval(self.timeframe)
                self._subscription_task = asyncio.create_task(
                    self.market_data.subscribe_candles(self.symbol, interval, self._on_candle)
                )
                self._logger.info(f"[{self.name}] Subscribed to candles, timeframe={self.timeframe}")
            else:
                # В эмуляции используем on_tick (приходит каждый тик)
                self._logger.info(f"[{self.name}] Running in emulation mode, using on_tick updates")
            
            self._keep_alive_task = asyncio.create_task(self._keep_alive())
        except Exception as e:
            self._status = BotStatus.ERROR
            self._error_message = str(e)
            self._logger.error(f"Error starting test bot: {e}", exc_info=True)

    async def _keep_alive(self):
        try:
            while self._status == BotStatus.RUNNING:
                await self.check_cancelled()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def stop(self):
        try:
            self._status = BotStatus.STOPPED
            if self._subscription_task:
                self._subscription_task.cancel()
            if self._keep_alive_task:
                self._keep_alive_task.cancel()
            if self.position:
                await self.close_position()
            self._logger.info(f"[{self.name}] TestBot stopped")
        except Exception as e:
            self._logger.error(f"Error stopping test bot: {e}", exc_info=True)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "symbol": self.symbol,
            "position_open": self.position is not None,
            "side": self.position['side'] if self.position else '',
            "entry_price": self.position['entry_price'] if self.position else 0.0,
            "last_price": self.last_price
        }

    def _open_position(self, side: str, price: float):
        self.position = {
            'side': side,
            'entry_price': price,
            'size': self.position_size_usdt
        }
        self._logger.info(f"[{self.name}] Opened {side} at {price}, size={self.position_size_usdt} USDT")
        self.on_order_filled({'type': 'open', 'side': side, 'price': price, 'size': self.position_size_usdt})

    def _close_position(self, price: float):
        if not self.position:
            return
        side = self.position['side']
        entry = self.position['entry_price']
        size = self.position['size']
        pnl = (price - entry) * size / entry if side == 'long' else (entry - price) * size / entry
        self._logger.info(f"[{self.name}] Closed {side} at {price}, PnL={pnl:.2f} USDT")
        self.on_order_filled({'type': 'close', 'side': side, 'price': price, 'pnl': pnl, 'size': size})
        self.position = None

    async def on_tick(self, symbol: str, price: float):
        """Обработчик тиков (используется в эмуляции)."""
        try:
            await self.check_cancelled()
            if not self.is_running or symbol != self.symbol:
                return
            self.last_price = price
            self.counter += 1
            if self.counter % 10 == 0:
                if self.position is None:
                    side = random.choice(['long', 'short'])
                    self._open_position(side, price)
                else:
                    self._close_position(price)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._logger.error(f"Error in on_tick: {e}", exc_info=True)

    async def on_candle(self, symbol: str, candle: Dict):
        """Обработчик свечей (используется в реальном режиме)."""
        try:
            await self.check_cancelled()
            if not self.is_running or symbol != self.symbol:
                return
            price = candle['close']
            self.last_price = price
            self.counter += 1
            if self.counter % 10 == 0:
                if self.position is None:
                    side = random.choice(['long', 'short'])
                    self._open_position(side, price)
                else:
                    self._close_position(price)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._logger.error(f"Error in on_candle: {e}", exc_info=True)

    async def _on_candle(self, candle):
        """Обёртка для вызова on_candle."""
        await self.on_candle(self.symbol, candle)

    def _str_to_interval(self, timeframe: str):
        from core.market_data_provider import Interval
        mapping = {'1m': Interval.M1, '5m': Interval.M5, '15m': Interval.M15,
                   '30m': Interval.M30, '1H': Interval.H1, '4H': Interval.H4,
                   '1D': Interval.D1, '1W': Interval.W1}
        return mapping.get(timeframe, Interval.H1)

    def validate_config(self) -> bool:
        if not self.symbol:
            self._logger.error("Symbol is required")
            return False
        if self.position_size_usdt <= 0:
            self._logger.error("Position size must be positive")
            return False
        return True