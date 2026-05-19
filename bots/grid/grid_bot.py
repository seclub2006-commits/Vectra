# bots/grid/grid_bot.py
"""
Сеточный бот (Grid Trading Bot).
Размещает сетку лимитных ордеров на покупку и продажу вокруг текущей цены.
При срабатывании ордера автоматически выставляет противоположный ордер для фиксации прибыли.
"""

import asyncio
import math
from typing import Dict, Any, Optional, List

from bots.base_bot import BaseBot, BotTradeSide, BotOrderType, BotStatus


class GridBot(BaseBot):
    @classmethod
    def get_params_schema(cls) -> Dict[str, Any]:
        return {
            "grid_levels": {
                "type": "int",
                "default": 10,
                "min": 2,
                "max": 50,
                "label": "Количество уровней сетки"
            },
            "grid_range_percent": {
                "type": "float",
                "default": 5.0,
                "min": 0.5,
                "max": 20.0,
                "step": 0.5,
                "label": "Диапазон сетки (%)"
            },
            "leverage": {
                "type": "int",
                "default": 1,
                "min": 1,
                "max": 125,
                "label": "Плечо (для фьючерсов)"
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
        self.grid_levels = int(config.get("grid_levels", 10))
        self.grid_range_percent = float(config.get("grid_range_percent", 5.0))
        self.leverage = int(config.get("leverage", 1))
        self.emulator_enabled = self._parse_bool(config.get("emulator_enabled", True))
        self.position_size_usdt = float(config.get("position_size", 10.0))

        # Состояние сетки
        self.base_price: Optional[float] = None          # цена, вокруг которой построена сетка
        self.grid_buy_orders: List[Dict] = []            # активные ордера на покупку
        self.grid_sell_orders: List[Dict] = []           # активные ордера на продажу
        self.active_grid_orders: Dict[str, Dict] = {}    # order_id -> информация об ордере (тип, цена)
        self._keep_alive_task: Optional[asyncio.Task] = None
        self._price_update_task: Optional[asyncio.Task] = None
        self._is_initialized = False

    async def start(self):
        try:
            if not self.validate_config():
                self._status = BotStatus.ERROR
                return

            if not self.emulator_enabled and self.leverage > 1:
                await self.connector.set_leverage(self.symbol, self.leverage, margin_mode='crossed')

            # Получаем текущую цену для построения сетки
            ticker = await self.connector.get_ticker(self.symbol)
            self.base_price = ticker['last']

            # Инициализируем сетку
            await self._init_grid()

            self._status = BotStatus.RUNNING
            self._logger.info(f"GridBot started with {self.grid_levels} levels, range {self.grid_range_percent}%, base price={self.base_price}")

            # Фоновые задачи
            self._keep_alive_task = asyncio.create_task(self._keep_alive())
            if not self.emulator_enabled:
                # В реальном режиме периодически проверяем исполненные ордера
                self._price_update_task = asyncio.create_task(self._monitor_orders())

        except Exception as e:
            self._status = BotStatus.ERROR
            self._error_message = str(e)
            self._logger.error(f"Error starting GridBot: {e}", exc_info=True)

    async def _keep_alive(self):
        try:
            while self._status == BotStatus.RUNNING:
                await self.check_cancelled()
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass

    async def _monitor_orders(self):
        """Периодически проверяет состояние активных ордеров и восстанавливает сетку."""
        while self._status == BotStatus.RUNNING and not self.emulator_enabled:
            try:
                await self.check_cancelled()
                # Получаем список открытых ордеров с биржи
                open_orders = await self.connector.get_open_orders(self.symbol)
                open_ids = {o['orderId'] for o in open_orders if o.get('orderId')}

                # Находим ордера, которые были исполнены (есть в active_grid_orders, но нет в open_orders)
                filled = []
                for order_id, info in list(self.active_grid_orders.items()):
                    if order_id not in open_ids:
                        filled.append((order_id, info))

                for order_id, info in filled:
                    # Ордер исполнен – удаляем из активных и создаём противоположный
                    del self.active_grid_orders[order_id]
                    await self._on_grid_order_filled(info['type'], info['price'], info['quantity'])

                # Если количество активных ордеров меньше половины сетки – перестраиваем
                if len(self.active_grid_orders) < self.grid_levels:
                    await self._rebalance_grid()

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Order monitor error: {e}")
            await asyncio.sleep(2)

    async def _init_grid(self):
        """Строит начальную сетку лимитных ордеров вокруг текущей цены."""
        if self.base_price is None:
            ticker = await self.connector.get_ticker(self.symbol)
            self.base_price = ticker['last']

        half_range = self.grid_range_percent / 100.0
        min_price = self.base_price * (1 - half_range)
        max_price = self.base_price * (1 + half_range)
        step = (max_price - min_price) / self.grid_levels

        # Очищаем предыдущие ордера
        await self._cancel_all_grid_orders()

        # Создаём уровни сетки: buy ниже цены, sell выше
        for i in range(1, self.grid_levels + 1):
            buy_price = min_price + step * (i - 1)
            sell_price = min_price + step * i

            if buy_price >= self.base_price:
                continue
            if sell_price <= self.base_price:
                continue

            quantity = self.position_size_usdt / buy_price
            quantity = round(quantity, 6)

            # Ордер на покупку
            if not self._manual_override:
                order = await self._place_limit_order('buy', buy_price, quantity)
                if order:
                    self.grid_buy_orders.append(order)
                    self.active_grid_orders[order['orderId']] = {
                        'type': 'buy',
                        'price': buy_price,
                        'quantity': quantity,
                        'target_sell_price': sell_price
                    }

            # Ордер на продажу
            if not self._manual_override:
                order = await self._place_limit_order('sell', sell_price, quantity)
                if order:
                    self.grid_sell_orders.append(order)
                    self.active_grid_orders[order['orderId']] = {
                        'type': 'sell',
                        'price': sell_price,
                        'quantity': quantity,
                        'target_buy_price': buy_price
                    }

        self._logger.info(f"Grid initialized: {len(self.grid_buy_orders)} buy orders, {len(self.grid_sell_orders)} sell orders")

    async def _place_limit_order(self, side: str, price: float, quantity: float) -> Optional[Dict]:
        """Размещает лимитный ордер (в эмуляции или реально)."""
        if self.emulator_enabled:
            # В эмуляции просто запоминаем ордер как активный
            order_id = f"emu_{side}_{price}_{id(self)}"
            order = {'orderId': order_id, 'price': price, 'quantity': quantity, 'side': side}
            return order
        else:
            return await self.connector.create_order(
                symbol=self.symbol,
                side=side,
                order_type='limit',
                quantity=quantity,
                price=price
            )

    async def _cancel_all_grid_orders(self):
        """Отменяет все текущие ордера сетки."""
        for order in self.grid_buy_orders + self.grid_sell_orders:
            if not self.emulator_enabled and order.get('orderId'):
                try:
                    await self.connector.cancel_order(self.symbol, order_id=order['orderId'])
                except Exception as e:
                    self._logger.warning(f"Cancel order error: {e}")
        self.grid_buy_orders.clear()
        self.grid_sell_orders.clear()
        self.active_grid_orders.clear()

    async def _on_grid_order_filled(self, order_type: str, price: float, quantity: float):
        """Обработка исполнения ордера сетки – выставляем противоположный ордер."""
        if order_type == 'buy':
            # Купили – выставляем ордер на продажу по цене + шаг
            sell_price = price * (1 + self.grid_range_percent / 100 / self.grid_levels)
            sell_price = round(sell_price, 2)
            self._logger.info(f"Grid buy filled at {price}, placing sell at {sell_price}")
            if not self._manual_override:
                order = await self._place_limit_order('sell', sell_price, quantity)
                if order:
                    self.grid_sell_orders.append(order)
                    self.active_grid_orders[order['orderId']] = {
                        'type': 'sell',
                        'price': sell_price,
                        'quantity': quantity
                    }
        else:
            # Продали – выставляем ордер на покупку по цене - шаг
            buy_price = price * (1 - self.grid_range_percent / 100 / self.grid_levels)
            buy_price = round(buy_price, 2)
            self._logger.info(f"Grid sell filled at {price}, placing buy at {buy_price}")
            if not self._manual_override:
                order = await self._place_limit_order('buy', buy_price, quantity)
                if order:
                    self.grid_buy_orders.append(order)
                    self.active_grid_orders[order['orderId']] = {
                        'type': 'buy',
                        'price': buy_price,
                        'quantity': quantity
                    }

    async def _rebalance_grid(self):
        """Перестраивает сетку, если цена сильно ушла от base_price."""
        ticker = await self.connector.get_ticker(self.symbol)
        current_price = ticker['last']
        deviation = abs(current_price - self.base_price) / self.base_price * 100
        if deviation > self.grid_range_percent * 1.5:
            self._logger.info(f"Price moved {deviation:.2f}%, rebalancing grid")
            self.base_price = current_price
            await self._init_grid()

    async def stop(self):
        try:
            self._status = BotStatus.STOPPED
            if self._price_update_task:
                self._price_update_task.cancel()
            if self._keep_alive_task:
                self._keep_alive_task.cancel()
            await self._cancel_all_grid_orders()
            self._logger.info("GridBot stopped")
        except Exception as e:
            self._logger.error(f"Error stopping GridBot: {e}", exc_info=True)

    def get_status(self) -> Dict[str, Any]:
        return {
            "running": self.is_running,
            "symbol": self.symbol,
            "grid_levels": self.grid_levels,
            "active_orders": len(self.active_grid_orders),
            "base_price": self.base_price or 0.0,
            "buy_orders_count": len(self.grid_buy_orders),
            "sell_orders_count": len(self.grid_sell_orders)
        }

    # ==================== Ручное управление ====================
    async def manual_open_position(self, side: str, size_usdt: float, **kwargs) -> Dict:
        """Ручное открытие позиции (приостанавливает авто-сетку)."""
        if not self._manual_override:
            await self.set_manual_override(True)

        # Отменяем все сеточные ордера
        await self._cancel_all_grid_orders()

        # Открываем позицию вручную
        ticker = await self.connector.get_ticker(self.symbol)
        price = ticker['last']
        side_enum = BotTradeSide.LONG if side.lower() == 'long' else BotTradeSide.SHORT

        order = await self.open_position(
            side=side_enum,
            price=price,
            order_type=BotOrderType.MARKET,
            size_usdt=size_usdt,
            manual=True
        )
        if order:
            return {"success": True, "entry_price": price, "order_id": order.get('orderId')}
        return {"success": False, "error": "Failed to open position"}

    async def manual_close_position(self, price: float = None) -> Dict:
        """Ручное закрытие позиции."""
        if not self._manual_override:
            await self.set_manual_override(True)

        ticker = await self.connector.get_ticker(self.symbol)
        close_price = price or ticker['last']
        # Закрываем позицию (в эмуляции или реально)
        result = await self.close_position(price=close_price, manual=True)
        return {"success": True, "close_price": close_price, "result": result}

    # ==================== Описание стратегии ====================
    def get_strategy_description(self) -> Dict[str, Any]:
        return {
            "type": "grid",
            "indicators": [],
            "levels": [],
            "conditions": f"Grid trading with {self.grid_levels} levels, range {self.grid_range_percent}%",
            "can_visualize": False
        }

    def validate_config(self) -> bool:
        if not self.symbol:
            self._logger.error("Symbol is required")
            return False
        if self.position_size_usdt <= 0:
            self._logger.error("Position size must be positive")
            return False
        if self.grid_levels < 2:
            self._logger.error("Grid levels must be at least 2")
            return False
        if self.grid_range_percent <= 0:
            self._logger.error("Grid range must be positive")
            return False
        return True

    async def on_parameters_changed(self, changed_params: Dict[str, Any]):
        """Динамическое изменение параметров сетки."""
        need_reinit = False
        if 'grid_levels' in changed_params:
            self.grid_levels = int(changed_params['grid_levels'])
            need_reinit = True
        if 'grid_range_percent' in changed_params:
            self.grid_range_percent = float(changed_params['grid_range_percent'])
            need_reinit = True
        if 'leverage' in changed_params:
            self.leverage = int(changed_params['leverage'])
            if not self.emulator_enabled:
                await self.connector.set_leverage(self.symbol, self.leverage, margin_mode='crossed')
        if need_reinit and self.is_running and not self._manual_override:
            await self._init_grid()
        self._logger.info(f"Parameters updated: {changed_params}")