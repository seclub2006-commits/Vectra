# bots/trend/rsi_bot.py
"""
Бот на основе RSI (Relative Strength Index).
Открывает long при RSI < oversold_threshold, short при RSI > overbought_threshold.
Закрывает при обратном условии.
Добавлена поддержка ручного управления (manual override) и описания стратегии.
"""

import asyncio
from typing import Dict, Any, Optional

from bots.base_bot import BaseBot, BotTradeSide, BotStatus, BotOrderType


class RSIBot(BaseBot):
    @classmethod
    def get_params_schema(cls) -> Dict[str, Any]:
        return {
            "rsi_period": {
                "type": "int",
                "default": 14,
                "min": 2,
                "max": 50,
                "label": "Период RSI"
            },
            "oversold": {
                "type": "int",
                "default": 30,
                "min": 10,
                "max": 45,
                "label": "Уровень перепроданности"
            },
            "overbought": {
                "type": "int",
                "default": 70,
                "min": 55,
                "max": 90,
                "label": "Уровень перекупленности"
            },
            "emulator_enabled": {
                "type": "bool",
                "default": True,
                "label": "Режим эмуляции"
            }
        }

    def __init__(self, name: str, connector, market_data, time_provider, config: Dict[str, Any]):
        super().__init__(name, connector, market_data, time_provider, config)
        self.symbol = config.get("symbol", "BTCUSDT")
        self.rsi_period = int(config.get("rsi_period", 14))
        self.oversold = int(config.get("oversold", 30))
        self.overbought = int(config.get("overbought", 70))
        self.emulator_enabled = self._parse_bool(config.get("emulator_enabled", True))
        self.position_size_usdt = float(config.get("position_size", 10.0))

        self.position: Optional[Dict] = None
        self.prices: list = []
        self.current_rsi: float = 50.0
        self._keep_alive_task: Optional[asyncio.Task] = None

    async def start(self):
        try:
            if not self.validate_config():
                self._status = BotStatus.ERROR
                return
            self._status = BotStatus.RUNNING
            self._logger.info(f"RSIBot started (mode: {'EMULATION' if self.emulator_enabled else 'LIVE'})")
            self._keep_alive_task = asyncio.create_task(self._keep_alive())
        except Exception as e:
            self._status = BotStatus.ERROR
            self._error_message = str(e)
            self._logger.error(f"Start error: {e}", exc_info=True)

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
            if self._keep_alive_task:
                self._keep_alive_task.cancel()
                await asyncio.sleep(0)
            if self.position and not self._manual_override:
                await self.close_rsi_position()
            self._logger.info("RSIBot stopped")
        except Exception as e:
            self._logger.error(f"Stop error: {e}")

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "symbol": self.symbol,
            "position_open": self.position is not None,
            "side": self.position['side'] if self.position else '',
            "entry_price": self.position['entry_price'] if self.position else 0.0
        }

    async def on_tick(self, symbol: str, price: float):
        if self._manual_override:
            return
        try:
            await self.check_cancelled()
            if symbol != self.symbol or not self.is_running:
                return
            self.prices.append(price)
            if len(self.prices) > self.rsi_period:
                self.prices.pop(0)
            if len(self.prices) >= self.rsi_period:
                self.current_rsi = self._calculate_rsi(self.prices)
                await self._decide(price)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            self._logger.error(f"on_tick error: {e}", exc_info=True)

    def _calculate_rsi(self, prices: list) -> float:
        n = self.rsi_period
        deltas = [prices[i] - prices[i-1] for i in range(1, n)]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains) / n
        avg_loss = sum(losses) / n
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    async def _decide(self, price: float):
        if self._manual_override:
            return
        if self.position is None:
            if self.current_rsi < self.oversold:
                await self._open_position(BotTradeSide.LONG, price)
            elif self.current_rsi > self.overbought:
                await self._open_position(BotTradeSide.SHORT, price)
        else:
            if self.position['side'] == 'long' and self.current_rsi > self.overbought:
                await self._close_position(price)
            elif self.position['side'] == 'short' and self.current_rsi < self.oversold:
                await self._close_position(price)

    async def _open_position(self, side: BotTradeSide, price: float):
        if self.emulator_enabled:
            self._open_emu(side, price)
        else:
            await self._open_live(side, price)

    async def _close_position(self, price: float):
        if self.emulator_enabled:
            self._close_emu(price)
        else:
            await self._close_live(price)

    def _open_emu(self, side: BotTradeSide, price: float):
        self.position = {
            'side': side.value,
            'entry_price': price,
            'size': self.position_size_usdt
        }
        self._logger.info(f"[EMU] Open {side.value} at {price}")
        self.on_order_filled({'type': 'open', 'side': side.value, 'price': price, 'size': self.position_size_usdt})

    def _close_emu(self, price: float):
        if not self.position:
            return
        side = self.position['side']
        entry = self.position['entry_price']
        size = self.position['size']
        pnl = (price - entry) * size / entry if side == 'long' else (entry - price) * size / entry
        self._logger.info(f"[EMU] Close {side} at {price}, PnL={pnl:.2f}")
        self.on_order_filled({'type': 'close', 'side': side, 'price': price, 'pnl': pnl, 'size': size})
        self.position = None

    async def _open_live(self, side: BotTradeSide, price: float):
        size = self.position_size_usdt / price
        order = await self.connector.create_order(
            symbol=self.symbol,
            side='buy' if side == BotTradeSide.LONG else 'sell',
            order_type='market',
            quantity=round(size, 6)
        )
        self.position = {'side': side.value, 'entry_price': price, 'order_id': order.get('orderId'), 'size': self.position_size_usdt}
        self._logger.info(f"[LIVE] Opened {side.value} at {price}")
        self.on_order_filled({'type': 'open', 'side': side.value, 'price': price, 'size': self.position_size_usdt})

    async def _close_live(self, price: float):
        if not self.position:
            return
        await self.connector.close_position(self.symbol, hold_side=self.position['side'])
        self._logger.info(f"[LIVE] Closed {self.position['side']} at {price}")
        self.on_order_filled({'type': 'close', 'side': self.position['side'], 'price': price, 'size': self.position['size']})
        self.position = None

    async def close_rsi_position(self):
        if self.position:
            ticker = await self.connector.get_ticker(self.symbol)
            price = ticker.get('last', 0)
            if price > 0:
                await self._close_position(price)

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
        self._logger.info(f"[MANUAL] Closed {self.position['side']} at {price}, PnL={pnl:.2f}")
        self.on_order_filled({'type': 'close', 'side': self.position['side'], 'price': price, 'pnl': pnl, 'size': size})
        self.position = None
        return {"success": True, "close_price": price}

    # ==================== Описание стратегии ====================
    def get_strategy_description(self) -> Dict[str, Any]:
        return {
            "type": "rsi",
            "indicators": [
                {
                    "name": "RSI",
                    "params": {"period": self.rsi_period},
                    "levels": [self.oversold, self.overbought],
                    "separate_axis": True
                }
            ],
            "levels": [],
            "conditions": f"Buy when RSI < {self.oversold}, sell when RSI > {self.overbought}",
            "can_visualize": True
        }

    def validate_config(self) -> bool:
        if not self.symbol:
            self._logger.error("Symbol required")
            return False
        if self.position_size_usdt <= 0:
            self._logger.error("Position size must be positive")
            return False
        if self.rsi_period < 2:
            self._logger.error("RSI period must be at least 2")
            return False
        return True