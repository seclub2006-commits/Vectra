# core/emulated_connector.py
import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime

from connectors.base.exchange_connector import ExchangeConnector
from connectors.base.exceptions import APIError

logger = logging.getLogger(__name__)


class EmulatedConnector(ExchangeConnector):
    """
    Эмулятор торгового коннектора.
    Рыночные данные (ticker, order book, свечи) берутся из реального коннектора.
    Торговые операции (create_order, close_position, set_tpsl) симулируются локально.
    """

    def __init__(self, real_connector: ExchangeConnector, initial_balance_usdt: float = 10000.0):
        super().__init__(real_connector.name, real_connector.config)
        self.real = real_connector
        self.initial_balance_usdt = initial_balance_usdt
        self.status = real_connector.status
        self._real_connector_name = real_connector.name  # для отслеживания в task_manager

        # Состояние эмуляции
        self._balances: Dict[str, Dict[str, float]] = {
            'USDT': {'free': initial_balance_usdt, 'locked': 0.0}
        }
        self._positions: Dict[str, Dict[str, Dict]] = {}  # symbol -> side -> {size, entry_price}
        self._orders: Dict[str, Dict] = {}
        self._tpsl_orders: Dict[str, Dict] = {}
        self._next_order_id = 1

    # ---------- Прокси для рыночных данных ----------
    async def connect(self) -> bool:
        return await self.real.connect()

    async def disconnect(self):
        # Не отключаем реальный коннектор, только свои ресурсы, если есть
        pass

    async def check_connection(self) -> bool:
        return await self.real.check_connection()

    async def get_server_time(self) -> int:
        return await self.real.get_server_time()

    async def get_ticker(self, symbol: str) -> Dict:
        return await self.real.get_ticker(symbol)

    async def get_tickers(self, product_type: str = None) -> List[Dict]:
        return await self.real.get_tickers(product_type)

    async def get_klines(self, symbol: str, interval: str, limit: int = 100,
                         start_time: Optional[int] = None,
                         end_time: Optional[int] = None) -> List[Dict]:
        return await self.real.get_klines(symbol, interval, limit, start_time, end_time)

    async def get_order_book(self, symbol: str, limit: int = 20, merge_scale: str = 'scale0') -> Dict:
        return await self.real.get_order_book(symbol, limit, merge_scale)

    async def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        return await self.real.get_trades(symbol, limit)

    async def get_contracts(self, product_type: str, symbol: str = None) -> List[Dict]:
        return await self.real.get_contracts(product_type, symbol)

    # ---------- Эмуляция торговых методов ----------
    async def create_order(self, symbol: str, side: str, order_type: str,
                           quantity: float, price: Optional[float] = None,
                           reduce_only: bool = False, client_oid: str = None,
                           preset_tp: float = None, preset_sl: float = None,
                           stp_mode: str = 'none') -> Dict:
        # Получаем текущую цену
        ticker = await self.get_ticker(symbol)
        if order_type == 'market':
            exec_price = ticker['last']
            if side == 'buy' and ticker.get('ask', 0) > 0:
                exec_price = ticker['ask']
            elif side == 'sell' and ticker.get('bid', 0) > 0:
                exec_price = ticker['bid']
        else:  # limit
            if price is None:
                raise APIError('400', 'Limit order requires price')
            exec_price = price

        cost = quantity * exec_price

        # Проверки
        if side == 'buy':
            usdt = self._balances.get('USDT', {})
            if usdt.get('free', 0) < cost:
                raise APIError('400', f'Insufficient USDT balance: {usdt["free"]:.2f} < {cost:.2f}')
        else:  # sell
            pos = self._get_position(symbol, 'long')
            if not pos or pos['size'] < quantity:
                raise APIError('400', f'Insufficient position size: {pos["size"] if pos else 0} < {quantity}')

        # Создаём ордер
        order_id = str(self._next_order_id)
        self._next_order_id += 1
        now_ms = int(datetime.now().timestamp() * 1000)
        order = {
            'orderId': order_id,
            'clientOid': client_oid,
            'symbol': symbol,
            'side': side,
            'order_type': order_type,
            'price': exec_price,
            'quantity': quantity,
            'filled': quantity,
            'status': 'filled',
            'timestamp': now_ms
        }
        self._orders[order_id] = order

        # Обновляем баланс и позиции
        if side == 'buy':
            pos = self._get_position(symbol, 'long')
            if pos:
                total_cost = pos['entry_price'] * pos['size'] + exec_price * quantity
                pos['size'] += quantity
                pos['entry_price'] = total_cost / pos['size']
            else:
                self._set_position(symbol, 'long', {'size': quantity, 'entry_price': exec_price})
            self._balances['USDT']['free'] -= cost
            self._balances['USDT']['locked'] += cost
        else:  # sell
            pos = self._get_position(symbol, 'long')
            if pos['size'] == quantity:
                self._delete_position(symbol, 'long')
            else:
                pos['size'] -= quantity
            self._balances['USDT']['free'] += cost
            self._balances['USDT']['locked'] -= cost

        # Сохраняем TP/SL для последующей эмуляции
        if preset_tp or preset_sl:
            self._tpsl_orders[f"tpsl_{order_id}"] = {
                'symbol': symbol,
                'side': side,
                'tp': preset_tp,
                'sl': preset_sl,
                'quantity': quantity
            }

        logger.info(f"[EMU] Order filled: {side} {quantity} {symbol} @ {exec_price}, cost={cost:.2f}")
        return {'orderId': order_id, 'clientOid': client_oid, 'symbol': symbol, 'status': 'filled'}

    async def cancel_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        # Ордера исполняются мгновенно, отмена не требуется
        return {'orderId': order_id, 'clientOid': client_oid, 'cancelled': True}

    async def cancel_all_orders(self, symbol: str = None, product_type: str = None) -> List[Dict]:
        return []

    async def get_open_orders(self, symbol: str = None, product_type: str = None) -> List[Dict]:
        return [o for o in self._orders.values() if o['status'] == 'new']

    async def get_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        return self._orders.get(order_id, {})

    async def get_order_history(self, symbol: str = None, product_type: str = None,
                                start_time: int = None, end_time: int = None,
                                limit: int = 100) -> List[Dict]:
        orders = list(self._orders.values())
        if start_time:
            orders = [o for o in orders if o['timestamp'] >= start_time]
        if end_time:
            orders = [o for o in orders if o['timestamp'] <= end_time]
        return orders[-limit:]

    async def get_fills(self, symbol: str = None, product_type: str = None,
                        start_time: int = None, end_time: int = None,
                        limit: int = 100) -> List[Dict]:
        fills = []
        for o in self._orders.values():
            if o['status'] == 'filled':
                fills.append({
                    'tradeId': o['orderId'],
                    'orderId': o['orderId'],
                    'symbol': o['symbol'],
                    'price': o['price'],
                    'size': o['quantity'],
                    'quote_volume': o['price'] * o['quantity'],
                    'side': o['side'],
                    'fee': 0,
                    'timestamp': o['timestamp']
                })
        if start_time:
            fills = [f for f in fills if f['timestamp'] >= start_time]
        if end_time:
            fills = [f for f in fills if f['timestamp'] <= end_time]
        return fills[-limit:]

    async def get_balance(self, currency: str = None) -> List[Dict]:
        if currency:
            b = self._balances.get(currency.upper(), {'free': 0, 'locked': 0})
            return [{'currency': currency.upper(), 'available': b['free'], 'frozen': b['locked'], 'total': b['free'] + b['locked']}]
        else:
            return [{'currency': cur, 'available': b['free'], 'frozen': b['locked'], 'total': b['free'] + b['locked']}
                    for cur, b in self._balances.items()]

    async def get_positions(self, symbol: str = None) -> List[Dict]:
        result = []
        for sym, sides in self._positions.items():
            if symbol and sym != symbol:
                continue
            for side, pos in sides.items():
                if pos['size'] > 0:
                    ticker = await self.get_ticker(sym)
                    mark_price = ticker.get('last', pos['entry_price'])
                    pnl = (mark_price - pos['entry_price']) * pos['size'] if side == 'long' else (pos['entry_price'] - mark_price) * pos['size']
                    result.append({
                        'symbol': sym,
                        'side': side,
                        'size': pos['size'],
                        'entry_price': pos['entry_price'],
                        'mark_price': mark_price,
                        'unrealized_pnl': pnl,
                        'leverage': 1,
                        'margin': pos['size'] * pos['entry_price'],
                        'liquidation_price': 0,
                        'margin_mode': 'crossed'
                    })
        return result

    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'crossed',
                           hold_side: str = None) -> Dict:
        return {'symbol': symbol, 'leverage': leverage, 'margin_mode': margin_mode}

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Dict:
        return {'symbol': symbol, 'margin_mode': margin_mode}

    async def add_margin(self, symbol: str, amount: float, hold_side: str) -> Dict:
        if self._balances.get('USDT', {}).get('free', 0) >= amount:
            self._balances['USDT']['free'] -= amount
            self._balances['USDT']['locked'] += amount
        return {'symbol': symbol, 'added': amount}

    async def set_tpsl(self, symbol: str, hold_side: str, trigger_price: float,
                       execute_price: float, tpsl_type: str, size: float = 0) -> Dict:
        order_id = f"tpsl_{self._next_order_id}"
        self._next_order_id += 1
        self._tpsl_orders[order_id] = {
            'symbol': symbol,
            'hold_side': hold_side,
            'trigger_price': trigger_price,
            'execute_price': execute_price,
            'type': tpsl_type,
            'size': size
        }
        logger.info(f"[EMU] Set {tpsl_type} for {symbol} {hold_side} at {trigger_price}")
        return {'orderId': order_id}

    async def cancel_tpsl(self, symbol: str, order_id: str) -> Dict:
        self._tpsl_orders.pop(order_id, None)
        return {'orderId': order_id, 'cancelled': True}

    async def close_position(self, symbol: str, hold_side: str = '') -> Dict:
        positions = await self.get_positions(symbol)
        for pos in positions:
            if hold_side and pos['side'] != hold_side:
                continue
            if pos['size'] > 0:
                side = 'sell' if pos['side'] == 'long' else 'buy'
                await self.create_order(symbol, side, 'market', pos['size'])
        return {'symbol': symbol, 'closed': True}

    async def get_funding_rate(self, symbol: str) -> Dict:
        return await self.real.get_funding_rate(symbol)

    async def get_funding_history(self, symbol: str, limit: int = 20) -> List[Dict]:
        return []

    async def get_interest_rate_history(self, coin: str) -> Dict:
        return {}

    async def subscribe(self, channel: str, symbol: str = None, callback: Callable = None, private: bool = False):
        await self.real.subscribe(channel, symbol, callback, private)

    async def unsubscribe_all(self, symbol: str = None):
        await self.real.unsubscribe_all(symbol)

    # ---------- Вспомогательные методы ----------
    def _get_position(self, symbol: str, side: str) -> Optional[Dict]:
        return self._positions.get(symbol, {}).get(side)

    def _set_position(self, symbol: str, side: str, pos: Dict):
        if symbol not in self._positions:
            self._positions[symbol] = {}
        self._positions[symbol][side] = pos

    def _delete_position(self, symbol: str, side: str):
        if symbol in self._positions and side in self._positions[symbol]:
            del self._positions[symbol][side]
            if not self._positions[symbol]:
                del self._positions[symbol]