# bots/manual/manual_bot.py
"""
Ручной бот – универсальный терминал.
Режимы:
- standalone: самостоятельная торговля (выбор коннектора, символа, таймфрейма, индикаторов для визуализации)
- attached: привязка к другому боту, перехват управления его позициями
Поддерживает эмуляцию и реальную торговлю.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, List

from bots.base_bot import BaseBot, BotStatus, BotTradeSide, BotOrderType


class ManualBot(BaseBot):
    @classmethod
    def get_params_schema(cls) -> Dict[str, Any]:
        return {
            "mode": {
                "type": "choice",
                "default": "standalone",
                "options": ["standalone", "attached"],
                "label": "Режим работы"
            },
            "attached_bot_id": {
                "type": "int",
                "default": 0,
                "label": "ID привязанного бота (только для attached)"
            },
            "emulator_enabled": {
                "type": "bool",
                "default": True,
                "label": "Режим эмуляции"
            },
            "connector_name": {
                "type": "str",
                "default": "",
                "label": "Коннектор (для standalone)"
            },
            "symbol": {
                "type": "str",
                "default": "BTCUSDT",
                "label": "Торговая пара (для standalone)"
            },
            "timeframe": {
                "type": "str",
                "default": "1H",
                "label": "Таймфрейм (для standalone)"
            },
            "indicators": {
                "type": "str",
                "default": "[]",
                "label": "Список индикаторов для отображения (JSON)"
            },
            "default_leverage": {
                "type": "int",
                "default": 10,
                "min": 1,
                "max": 125,
                "label": "Плечо по умолчанию"
            }
        }

    def __init__(self, name: str, connector, market_data, time_provider, config: Dict[str, Any]):
        super().__init__(name, connector, market_data, time_provider, config)
        self.mode = config.get("mode", "standalone")
        self.attached_bot_id = int(config.get("attached_bot_id", 0))
        self.emulator_enabled = self._parse_bool(config.get("emulator_enabled", True))
        self.connector_name = config.get("connector_name", "")
        self.symbol = config.get("symbol", "BTCUSDT")
        self.timeframe = config.get("timeframe", "1H")
        self.default_leverage = int(config.get("default_leverage", 10))
        # Индикаторы для визуализации (список словарей)
        try:
            self.indicators_config = json.loads(config.get("indicators", "[]"))
        except json.JSONDecodeError:
            self.indicators_config = []

        # Состояние позиции (собственное, если standalone)
        self._current_position: Optional[Dict] = None
        self._leverage_set = self.default_leverage
        self._keep_alive_task: Optional[asyncio.Task] = None
        self._sync_task: Optional[asyncio.Task] = None   # для синхронизации позиции (в attached)

        # Для attached режима – кэш описания стратегии привязанного бота
        self._attached_strategy_desc: Optional[Dict] = None

        # Ссылка на TaskManager (устанавливается извне после создания бота)
        self._task_manager = None

    def set_task_manager(self, task_manager):
        """Устанавливает ссылку на TaskManager для вызовов методов других ботов."""
        self._task_manager = task_manager

    async def start(self):
        try:
            if not self.validate_config():
                self._status = BotStatus.ERROR
                return

            if self.mode == "standalone":
                if not self.emulator_enabled:
                    product_type = self.config.get('product_type', 'USDT-FUTURES')
                    if product_type != 'SPOT':
                        await self.connector.set_leverage(self.symbol, self.default_leverage, margin_mode='crossed')
                self._logger.info(f"ManualBot '{self.name}' запущен в режиме STANDALONE. Символ={self.symbol}, таймфрейм={self.timeframe}")
            else:
                if self.attached_bot_id <= 0:
                    self._logger.error("Attached mode requires attached_bot_id > 0")
                    self._status = BotStatus.ERROR
                    return
                self._logger.info(f"ManualBot '{self.name}' запущен в режиме ATTACHED к боту ID={self.attached_bot_id}")
                asyncio.create_task(self._fetch_attached_strategy())

            self._status = BotStatus.RUNNING
            self._keep_alive_task = asyncio.create_task(self._keep_alive())

            if self.mode == "attached" and not self.emulator_enabled:
                self._sync_task = asyncio.create_task(self._sync_position_loop())

        except Exception as e:
            self._status = BotStatus.ERROR
            self._error_message = str(e)
            self._logger.error(f"Ошибка запуска ManualBot: {e}", exc_info=True)

    async def _keep_alive(self):
        try:
            while self._status == BotStatus.RUNNING:
                await self.check_cancelled()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def _sync_position_loop(self):
        try:
            while self._status == BotStatus.RUNNING and self.mode == "attached":
                await self.check_cancelled()
                # Синхронизация будет выполняться при вызовах методов
                await asyncio.sleep(3)
        except asyncio.CancelledError:
            pass

    async def _fetch_attached_strategy(self):
        # Заглушка – описание будет установлено извне
        pass

    async def stop(self):
        try:
            self._status = BotStatus.STOPPED
            if self._sync_task:
                self._sync_task.cancel()
            if self._keep_alive_task:
                self._keep_alive_task.cancel()
            if self.mode == "standalone" and self._current_position:
                await self.manual_close_position()
            self._logger.info(f"ManualBot '{self.name}' остановлен")
        except Exception as e:
            self._logger.error(f"Ошибка остановки ManualBot: {e}")

    def get_status(self) -> Dict[str, Any]:
        if self.mode == "attached" and self.attached_bot_id > 0:
            return {
                "running": self.is_running,
                "symbol": self.symbol,
                "position_open": self._current_position is not None,
                "side": self._current_position['side'] if self._current_position else '',
                "entry_price": self._current_position['entry_price'] if self._current_position else 0.0,
                "mode": "attached",
                "attached_bot_id": self.attached_bot_id
            }
        else:
            return {
                "running": self.is_running,
                "symbol": self.symbol,
                "position_open": self._current_position is not None,
                "side": self._current_position['side'] if self._current_position else '',
                "entry_price": self._current_position['entry_price'] if self._current_position else 0.0,
                "leverage": self._leverage_set,
                "mode": "standalone"
            }

    # ==================== Ручные методы (с перенаправлением для attached) ====================
    async def _call_attached_bot_method(self, method_name: str, params: Dict) -> Dict:
        """
        Перенаправляет вызов метода к привязанному боту через TaskManager.
        """
        if not self._task_manager:
            self._logger.error("TaskManager not set, cannot call attached bot method")
            return {"success": False, "error": "TaskManager not configured"}

        if self.attached_bot_id <= 0:
            return {"success": False, "error": "No attached bot ID set"}

        try:
            result = await self._task_manager.call_bot_method(
                self.attached_bot_id,
                method_name,
                params
            )
            # result может быть любым типом, но для совместимости с интерфейсом ManualBot
            # оборачиваем в словарь, если это не словарь
            if isinstance(result, dict):
                return result
            else:
                return {"success": True, "result": result}
        except Exception as e:
            self._logger.error(f"Error calling attached bot method {method_name}: {e}")
            return {"success": False, "error": str(e)}

    async def manual_open_position(self, side: str, size_usdt: float, leverage: int = None,
                                   order_type: str = "market", price: float = None) -> Dict:
        self._logger.info(f"manual_open_position: side={side}, size_usdt={size_usdt}, mode={self.mode}")
        if self.mode == "attached" and self.attached_bot_id > 0:
            # Перенаправляем вызов к привязанному боту
            return await self._call_attached_bot_method("manual_open_position", {
                "side": side,
                "size_usdt": size_usdt,
                "leverage": leverage,
                "order_type": order_type,
                "price": price
            })
        else:
            if self._current_position:
                return {"success": False, "error": "Позиция уже открыта"}

            # Включаем ручной режим
            if not self._manual_override:
                await self.set_manual_override(True)

            lev = leverage or self.default_leverage
            if lev != self._leverage_set and not self.emulator_enabled:
                product_type = self.config.get('product_type', 'USDT-FUTURES')
                if product_type != 'SPOT':
                    await self.connector.set_leverage(self.symbol, lev, margin_mode='crossed')
                    self._leverage_set = lev

            ticker = await self.connector.get_ticker(self.symbol)
            current_price = float(ticker['last'])
            if price is None and order_type == "limit":
                price = current_price

            if order_type == "market":
                size_contracts = size_usdt / current_price
            else:
                size_contracts = size_usdt / price

            bot_side = BotTradeSide.LONG if side == "long" else BotTradeSide.SHORT
            order = await self.open_position(
                side=bot_side,
                price=price if order_type == "limit" else None,
                order_type=BotOrderType(order_type),
                size_usdt=size_usdt,
                manual=True   # игнорируем _manual_override
            )
            if not order:
                return {"success": False, "error": "Не удалось открыть позицию"}

            entry_price = price if order_type == "limit" else current_price
            self._current_position = {
                "side": side,
                "entry_price": entry_price,
                "size_usdt": size_usdt,
                "size_contracts": size_contracts,
                "leverage": lev,
                "open_time": self.time_provider.now_timestamp_ms(),
                "order_id": order.get('orderId')
            }
            await self._on_trade_open(entry_price, size_usdt, side)
            return {"success": True, "entry_price": entry_price, "order_id": order.get('orderId')}

    async def manual_close_position(self, price: float = None) -> Dict:
        self._logger.info(f"manual_close_position, price={price}, mode={self.mode}")
        if self.mode == "attached" and self.attached_bot_id > 0:
            return await self._call_attached_bot_method("manual_close_position", {"price": price})
        else:
            if not self._current_position:
                return {"success": False, "error": "Нет открытой позиции"}
            if price is None:
                ticker = await self.connector.get_ticker(self.symbol)
                price = float(ticker['last'])
            side = BotTradeSide.LONG if self._current_position['side'] == "long" else BotTradeSide.SHORT
            result = await self.close_position(side=side, price=price, manual=True)
            entry = self._current_position['entry_price']
            size_usdt = self._current_position['size_usdt']
            if self._current_position['side'] == "long":
                pnl = (price - entry) * (size_usdt / entry)
            else:
                pnl = (entry - price) * (size_usdt / entry)
            await self._on_trade_close(price, pnl, size_usdt)
            self._current_position = None
            return {"success": True, "pnl": pnl, "close_price": price}

    async def manual_set_tpsl(self, tp_price: float = None, sl_price: float = None) -> Dict:
        if self.mode == "attached" and self.attached_bot_id > 0:
            return await self._call_attached_bot_method("manual_set_tpsl", {"tp_price": tp_price, "sl_price": sl_price})
        else:
            if not self._current_position:
                return {"success": False, "error": "Нет открытой позиции"}
            if self.emulator_enabled:
                return {"success": False, "error": "TP/SL недоступны в режиме эмуляции"}
            side = self._current_position['side']
            size = self._current_position.get('size_contracts', 0)
            results = []
            if tp_price and tp_price > 0:
                tp_res = await self.connector.set_tpsl(
                    self.symbol, side, tp_price, 0, 'profit_plan', size
                )
                results.append({"type": "TP", "order_id": tp_res.get('orderId')})
            if sl_price and sl_price > 0:
                sl_res = await self.connector.set_tpsl(
                    self.symbol, side, sl_price, 0, 'loss_plan', size
                )
                results.append({"type": "SL", "order_id": sl_res.get('orderId')})
            return {"success": True, "results": results}

    async def manual_set_leverage(self, leverage: int) -> Dict:
        if self.mode == "attached" and self.attached_bot_id > 0:
            return await self._call_attached_bot_method("manual_set_leverage", {"leverage": leverage})
        else:
            if self.emulator_enabled:
                self._leverage_set = leverage
                return {"success": True, "message": f"Плечо изменено на {leverage} (эмуляция)"}
            product_type = self.config.get('product_type', 'USDT-FUTURES')
            if product_type == 'SPOT':
                return {"success": False, "error": "Спот не поддерживает плечо"}
            await self.connector.set_leverage(self.symbol, leverage, margin_mode='crossed')
            self._leverage_set = leverage
            return {"success": True, "leverage": leverage}

    async def manual_get_balance(self, currency: str = None) -> Dict:
        if self.mode == "attached" and self.attached_bot_id > 0:
            return await self._call_attached_bot_method("manual_get_balance", {"currency": currency})
        else:
            if self.emulator_enabled:
                return {"success": True, "balances": [], "message": "Эмуляция: баланс недоступен"}
            balances = await self.connector.get_balance(currency)
            return {"success": True, "balances": balances}

    async def manual_get_ticker(self) -> Dict:
        if self.mode == "attached" and self.attached_bot_id > 0:
            return await self._call_attached_bot_method("manual_get_ticker", {})
        else:
            ticker = await self.connector.get_ticker(self.symbol)
            return {"success": True, "ticker": ticker}

    # ==================== Вспомогательные методы ====================
    async def _on_trade_open(self, price: float, size_usdt: float, side: str):
        if hasattr(self, 'on_order_filled') and self.on_order_filled:
            order_data = {
                'type': 'open',
                'side': side,
                'price': price,
                'size': size_usdt
            }
            if asyncio.iscoroutinefunction(self.on_order_filled):
                await self.on_order_filled(order_data)
            else:
                self.on_order_filled(order_data)

    async def _on_trade_close(self, price: float, pnl: float, size_usdt: float):
        if hasattr(self, 'on_order_filled') and self.on_order_filled:
            side = self._current_position['side'] if self._current_position else 'unknown'
            order_data = {
                'type': 'close',
                'side': side,
                'price': price,
                'pnl': pnl,
                'size': size_usdt
            }
            if asyncio.iscoroutinefunction(self.on_order_filled):
                await self.on_order_filled(order_data)
            else:
                self.on_order_filled(order_data)

    # ==================== Описание стратегии ====================
    def get_strategy_description(self) -> Dict[str, Any]:
        if self.mode == "attached" and self.attached_bot_id > 0:
            if self._attached_strategy_desc:
                return self._attached_strategy_desc
            else:
                return {"type": "unknown", "can_visualize": False, "message": "Загрузка описания..."}
        else:
            indicators = []
            for ind_conf in self.indicators_config:
                ind_type = ind_conf.get("type")
                if ind_type == "EMA":
                    indicators.append({
                        "name": f"EMA {ind_conf.get('period', 12)}",
                        "params": {"period": ind_conf.get('period', 12)},
                        "color": ind_conf.get("color", "#FFAA00"),
                        "separate_axis": False
                    })
                elif ind_type == "RSI":
                    indicators.append({
                        "name": "RSI",
                        "params": {"period": ind_conf.get('period', 14)},
                        "levels": [ind_conf.get('oversold', 30), ind_conf.get('overbought', 70)],
                        "separate_axis": True
                    })
                elif ind_type == "Volume":
                    indicators.append({
                        "name": "Объёмы",
                        "params": {},
                        "separate_axis": True
                    })
            return {
                "type": "manual",
                "indicators": indicators,
                "levels": [],
                "conditions": "Ручное управление",
                "can_visualize": True
            }

    def set_attached_strategy_description(self, desc: Dict):
        self._attached_strategy_desc = desc

    def validate_config(self) -> bool:
        if self.mode == "standalone":
            if not self.symbol:
                self._logger.error("Symbol is required in standalone mode")
                return False
        else:
            if self.attached_bot_id <= 0:
                self._logger.error("Attached bot ID must be positive in attached mode")
                return False
        return True

    async def on_parameters_changed(self, changed_params: Dict[str, Any]):
        if 'mode' in changed_params:
            self.mode = changed_params['mode']
        if 'attached_bot_id' in changed_params:
            self.attached_bot_id = int(changed_params['attached_bot_id'])
            if self.mode == "attached":
                asyncio.create_task(self._fetch_attached_strategy())
        if 'symbol' in changed_params:
            self.symbol = changed_params['symbol']
        if 'timeframe' in changed_params:
            self.timeframe = changed_params['timeframe']
        if 'indicators' in changed_params:
            try:
                self.indicators_config = json.loads(changed_params['indicators'])
            except:
                pass
        self._logger.info(f"Parameters updated: {changed_params}")