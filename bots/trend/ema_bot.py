# bots/trend/ema_bot.py
"""
Бот на пересечении EMA (Exponential Moving Average).
Добавлена поддержка ручного управления (manual override) и описания стратегии.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from bots.base_bot import BaseBot, BotTradeSide, BotOrderType, BotStatus


class EmaBot(BaseBot):
    @classmethod
    def get_params_schema(cls) -> Dict[str, Any]:
        return {
            "fast_period": {"type": "int", "default": 9, "min": 1, "max": 200, "label": "Fast EMA период"},
            "slow_period": {"type": "int", "default": 21, "min": 1, "max": 500, "label": "Slow EMA период"},
            "leverage": {"type": "int", "default": 10, "min": 1, "max": 125, "label": "Плечо"},
            "emulator_enabled": {"type": "bool", "default": True, "label": "Режим эмуляции"},
            "stop_loss_percent": {"type": "float", "default": 2.0, "min": 0.1, "max": 50, "step": 0.5, "label": "Stop Loss (%)"},
            "take_profit_percent": {"type": "float", "default": 5.0, "min": 0.5, "max": 100, "step": 0.5, "label": "Take Profit (%)"}
        }

    def __init__(self, name: str, connector, market_data, time_provider, config: Dict[str, Any]):
        super().__init__(name, connector, market_data, time_provider, config)

        self.symbol = config.get("symbol", "BTCUSDT")
        self.fast_period = int(config.get("fast_period", 9))
        self.slow_period = int(config.get("slow_period", 21))
        self.leverage = int(config.get("leverage", 10))
        self.emulator_enabled = self._parse_bool(config.get("emulator_enabled", True))
        self.position_size_usdt = float(config.get("position_size", 10.0))
        self.stop_loss_percent = float(config.get("stop_loss_percent", 2.0))
        self.take_profit_percent = float(config.get("take_profit_percent", 5.0))

        self.position: Optional[Dict] = None
        self.last_price: Optional[float] = None
        self.ema_fast_history = []
        self.ema_slow_history = []
        self._subscription_task: Optional[asyncio.Task] = None
        self._keep_alive_task: Optional[asyncio.Task] = None

    async def start(self):
        try:
            if not self.validate_config():
                self._status = BotStatus.ERROR
                return
            if not self.emulator_enabled and self.leverage > 1:
                await self.connector.set_leverage(self.symbol, self.leverage, margin_mode='crossed')
            self._status = BotStatus.RUNNING
            self._logger.info(f"EmaBot started (mode: {'EMULATION' if self.emulator_enabled else 'LIVE'})")
            if not self.emulator_enabled:
                interval = self._str_to_interval(self.config.get("timeframe", "1H"))
                self._subscription_task = asyncio.create_task(
                    self.market_data.subscribe_candles(self.symbol, interval, self._on_candle)
                )
            self._keep_alive_task = asyncio.create_task(self._keep_alive())
        except Exception as e:
            self._status = BotStatus.ERROR
            self._error_message = str(e)
            self._logger.error(f"Error in start: {e}", exc_info=True)

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
            if self.position and not self._manual_override:
                await self.close_position()
            self._logger.info("EmaBot stopped")
        except Exception as e:
            self._logger.error(f"Error in stop: {e}", exc_info=True)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "symbol": self.symbol,
            "position_open": self.position is not None,
            "side": self.position['side'] if self.position else '',
            "entry_price": self.position['entry_price'] if self.position else 0.0
        }

    async def on_candle(self, symbol: str, candle: Dict):
        if self._manual_override:
            return
        try:
            await self.check_cancelled()
            if symbol != self.symbol or not self.is_running:
                return
            close_price = candle['close']
            await self._process_price(close_price)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._logger.error(f"Error in on_candle: {e}", exc_info=True)

    async def on_tick(self, symbol: str, price: float):
        if self._manual_override:
            return
        try:
            await self.check_cancelled()
            if not self.emulator_enabled:
                return
            if symbol != self.symbol or not self.is_running:
                return
            await self._process_price(price)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._logger.error(f"Error in on_tick: {e}", exc_info=True)

    async def _on_candle(self, candle):
        await self.on_candle(self.symbol, candle)

    async def _process_price(self, price: float):
        if self._manual_override:
            return
        self.last_price = price
        ema_fast, ema_slow = self._update_ema(price)
        if ema_fast is None or ema_slow is None:
            return

        if self.position is None:
            if ema_fast > ema_slow:
                await self._open_position(BotTradeSide.LONG, price)
            elif ema_fast < ema_slow:
                await self._open_position(BotTradeSide.SHORT, price)
        else:
            if self.position['side'] == 'long' and ema_fast < ema_slow:
                await self._close_position(price)
            elif self.position['side'] == 'short' and ema_fast > ema_slow:
                await self._close_position(price)

    def _update_ema(self, price: float):
        self.ema_fast_history.append(price)
        self.ema_slow_history.append(price)
        if len(self.ema_fast_history) > self.fast_period:
            self.ema_fast_history.pop(0)
        if len(self.ema_slow_history) > self.slow_period:
            self.ema_slow_history.pop(0)

        ema_fast = None
        ema_slow = None
        if len(self.ema_fast_history) >= self.fast_period:
            ema_fast = sum(self.ema_fast_history) / self.fast_period
        if len(self.ema_slow_history) >= self.slow_period:
            ema_slow = sum(self.ema_slow_history) / self.slow_period
        return ema_fast, ema_slow

    async def _open_position(self, side: BotTradeSide, price: float):
        if self.emulator_enabled:
            self._open_position_emu(side, price)
        else:
            await self._open_position_real(side, price)

    async def _close_position(self, price: float):
        if self.emulator_enabled:
            self._close_position_emu(price)
        else:
            await self._close_position_real(price)

    def _open_position_emu(self, side: BotTradeSide, price: float):
        size_usdt = self.position_size_usdt
        self.position = {'side': side.value, 'entry_price': price, 'size': size_usdt}
        self._logger.info(f"[EMU] Opened {side.value} at {price}, size={size_usdt} USDT")
        self.on_order_filled({'type': 'open', 'side': side.value, 'price': price, 'size': size_usdt})

    def _close_position_emu(self, price: float):
        if not self.position:
            return
        side = self.position['side']
        entry = self.position['entry_price']
        size = self.position['size']
        pnl = (price - entry) * size / entry if side == 'long' else (entry - price) * size / entry
        self._logger.info(f"[EMU] Closed {side} at {price}, PnL={pnl:.2f} USDT")
        self.on_order_filled({'type': 'close', 'side': side, 'price': price, 'pnl': pnl, 'size': size})
        self.position = None

    async def _open_position_real(self, side: BotTradeSide, price: float):
        size_contracts = self.position_size_usdt / price
        order = await self.connector.create_order(
            symbol=self.symbol,
            side='buy' if side == BotTradeSide.LONG else 'sell',
            order_type='market',
            quantity=round(size_contracts, 6)
        )
        if self.take_profit_percent > 0:
            tp_price = price * (1 + self.take_profit_percent / 100) if side == BotTradeSide.LONG else price * (1 - self.take_profit_percent / 100)
            await self.connector.set_tpsl(self.symbol, side.value, tp_price, 0, 'profit_plan')
        if self.stop_loss_percent > 0:
            sl_price = price * (1 - self.stop_loss_percent / 100) if side == BotTradeSide.LONG else price * (1 + self.stop_loss_percent / 100)
            await self.connector.set_tpsl(self.symbol, side.value, sl_price, 0, 'loss_plan')
        self.position = {'side': side.value, 'entry_price': price, 'order_id': order.get('orderId'), 'size': self.position_size_usdt}
        self._logger.info(f"[LIVE] Opened {side.value} at {price}, orderId={order.get('orderId')}")
        self.on_order_filled({'type': 'open', 'side': side.value, 'price': price, 'size': self.position_size_usdt})

    async def _close_position_real(self, price: float):
        if not self.position:
            return
        side = self.position['side']
        await self.connector.close_position(self.symbol, hold_side=side)
        entry = self.position['entry_price']
        size = self.position['size']
        pnl = (price - entry) * size / entry if side == 'long' else (entry - price) * size / entry
        self._logger.info(f"[LIVE] Closed {side} at {price}, PnL={pnl:.2f} USDT")
        self.on_order_filled({'type': 'close', 'side': side, 'price': price, 'pnl': pnl, 'size': size})
        self.position = None

    # ==================== Ручное управление (ИСПРАВЛЕНО) ====================
    async def manual_open_position(self, side: str, size_usdt: float, **kwargs) -> Dict:
        self._logger.info(f"Manual open position called: side={side}, size_usdt={size_usdt}")
        if not self._manual_override:
            await self.set_manual_override(True)

        if self.position:
            return {"success": False, "error": "Position already open"}

        ticker = await self.connector.get_ticker(self.symbol)
        current_price = float(ticker['last'])
        side_enum = BotTradeSide.LONG if side.lower() == 'long' else BotTradeSide.SHORT

        # Используем open_position с manual=True
        order = await self.open_position(
            side=side_enum,
            price=current_price,
            order_type=BotOrderType.MARKET,
            size_usdt=size_usdt,
            manual=True
        )
        if not order:
            return {"success": False, "error": "Failed to open position"}

        if self.emulator_enabled:
            self.position = {'side': side_enum.value, 'entry_price': current_price, 'size': size_usdt}
        else:
            self.position = {'side': side_enum.value, 'entry_price': current_price, 'order_id': order.get('orderId'), 'size': size_usdt}

        self.on_order_filled({'type': 'open', 'side': side_enum.value, 'price': current_price, 'size': size_usdt})
        return {"success": True, "entry_price": current_price, "side": side}

    async def manual_close_position(self, price: float = None) -> Dict:
        self._logger.info(f"Manual close position called, price={price}")
        if not self.position:
            return {"success": False, "error": "No open position"}

        if price is None:
            ticker = await self.connector.get_ticker(self.symbol)
            price = float(ticker['last'])

        side_enum = BotTradeSide.LONG if self.position['side'] == 'long' else BotTradeSide.SHORT
        result = await self.close_position(side=side_enum, price=price, manual=True)

        entry = self.position['entry_price']
        size = self.position['size']
        pnl = (price - entry) * size / entry if self.position['side'] == 'long' else (entry - price) * size / entry
        self._logger.info(f"[MANUAL] Closed {self.position['side']} at {price}, PnL={pnl:.2f} USDT")
        self.on_order_filled({'type': 'close', 'side': self.position['side'], 'price': price, 'pnl': pnl, 'size': size})
        self.position = None
        return {"success": True, "close_price": price}

    # ==================== Описание стратегии ====================
    def get_strategy_description(self) -> Dict[str, Any]:
        return {
            "type": "ema",
            "indicators": [
                {
                    "name": f"EMA {self.fast_period}",
                    "params": {"period": self.fast_period},
                    "color": "#FFAA00",
                    "separate_axis": False
                },
                {
                    "name": f"EMA {self.slow_period}",
                    "params": {"period": self.slow_period},
                    "color": "#00AAFF",
                    "separate_axis": False
                }
            ],
            "levels": [],
            "conditions": f"Buy when fast EMA crosses above slow EMA, sell when crosses below",
            "can_visualize": True
        }

    def _str_to_interval(self, timeframe: str):
        from core.market_data_provider import Interval
        mapping = {'1m': Interval.M1, '5m': Interval.M5, '15m': Interval.M15,
                   '30m': Interval.M30, '1H': Interval.H1, '4H': Interval.H4,
                   '1D': Interval.D1, '1W': Interval.W1}
        return mapping.get(timeframe, Interval.H1)

    def validate_config(self) -> bool:
        if not super().validate_config():
            return False
        if not self.symbol:
            self._logger.error("Symbol is required")
            return False
        if self.position_size_usdt <= 0:
            self._logger.error("Position size must be positive")
            return False
        if self.fast_period >= self.slow_period:
            self._logger.warning("Fast period should be less than slow period")
        return True

    async def on_parameters_changed(self, changed_params: Dict[str, Any]):
        if 'fast_period' in changed_params:
            self.fast_period = int(changed_params['fast_period'])
        if 'slow_period' in changed_params:
            self.slow_period = int(changed_params['slow_period'])
        if 'leverage' in changed_params:
            self.leverage = int(changed_params['leverage'])
            if not self.emulator_enabled:
                await self.connector.set_leverage(self.symbol, self.leverage, margin_mode='crossed')
        if 'stop_loss_percent' in changed_params:
            self.stop_loss_percent = float(changed_params['stop_loss_percent'])
        if 'take_profit_percent' in changed_params:
            self.take_profit_percent = float(changed_params['take_profit_percent'])
        self._logger.info(f"Parameters updated: {changed_params}")