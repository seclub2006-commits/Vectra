# connectors/bitget/spot/trigger.py
from typing import Dict, List, Optional

class TriggerMixin:
    """Миксин для плановых ордеров (trigger orders) на споте."""

    async def place_plan_order(self, symbol: str, side: str, order_type: str,
                               size: float, trigger_price: float, trigger_type: str = 'fill_price',
                               execute_price: float = None, plan_type: str = 'amount',
                               client_oid: str = None, stp_mode: str = 'none') -> Dict:
        """
        Разместить плановый ордер (триггер).
        plan_type: 'amount' – size в базовой монете, 'total' – размер в котируемой монете.
        trigger_type: 'fill_price' (последняя цена), 'mark_price' (марк-цена) – обычно для фьючерсов, но на споте только fill_price.
        """
        endpoint = '/api/v2/spot/trade/place-plan-order'
        body = {
            'symbol': symbol.upper(),
            'side': side,
            'triggerPrice': str(trigger_price),
            'orderType': order_type,
            'size': str(size),
            'triggerType': trigger_type,
            'planType': plan_type,
            'stpMode': stp_mode
        }
        if execute_price is not None and order_type == 'limit':
            body['executePrice'] = str(execute_price)
        if client_oid:
            body['clientOid'] = client_oid
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    async def modify_plan_order(self, order_id: str = None, client_oid: str = None,
                                trigger_price: str = None, execute_price: str = None,
                                size: str = None, order_type: str = None) -> Dict:
        """Изменить существующий плановый ордер."""
        endpoint = '/api/v2/spot/trade/modify-plan-order'
        body = {}
        if order_id:
            body['orderId'] = order_id
        elif client_oid:
            body['clientOid'] = client_oid
        else:
            raise ValueError("order_id or client_oid required")
        if trigger_price is not None:
            body['triggerPrice'] = str(trigger_price)
        if execute_price is not None:
            body['executePrice'] = str(execute_price)
        if size is not None:
            body['size'] = str(size)
        if order_type is not None:
            body['orderType'] = order_type
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    async def cancel_plan_order(self, order_id: str = None, client_oid: str = None) -> bool:
        endpoint = '/api/v2/spot/trade/cancel-plan-order'
        body = {}
        if order_id:
            body['orderId'] = order_id
        elif client_oid:
            body['clientOid'] = client_oid
        else:
            raise ValueError("order_id or client_oid required")
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data.get('result') == 'success'

    async def batch_cancel_plan_orders(self, symbol_list: List[str] = None) -> Dict:
        """
        Отменить плановые ордера для списка символов.
        Если symbol_list не передан, отменяются все плановые ордера.
        """
        endpoint = '/api/v2/spot/trade/batch-cancel-plan-order'
        body = {}
        if symbol_list:
            body['symbolList'] = [s.upper() for s in symbol_list]
        else:
            body['symbolList'] = []
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data

    async def get_current_plan_orders(self, symbol: str = None, limit: int = 20,
                                      id_less_than: str = None,
                                      start_time: int = None, end_time: int = None) -> List[Dict]:
        """Текущие плановые ордера (ожидающие триггера)."""
        endpoint = '/api/v2/spot/trade/current-plan-order'
        params = {'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        if id_less_than:
            params['idLessThan'] = id_less_than
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        data = await self._request('GET', endpoint, params=params, signed=True)
        orders = []
        for item in data.get('orderList', []):
            orders.append({
                'orderId': item['orderId'],
                'clientOid': item.get('clientOid'),
                'symbol': item['symbol'],
                'side': item['side'],
                'size': float(item['size']),
                'trigger_price': float(item['triggerPrice']),
                'trigger_type': item.get('triggerType'),
                'order_type': item.get('orderType'),
                'execute_price': float(item.get('executePrice', 0)),
                'plan_type': item.get('planType', 'amount'),
                'status': item['status'],  # 'not_trigger', 'executing'
                'timestamp': int(item.get('cTime', 0))
            })
        return orders

    async def get_plan_sub_order(self, plan_order_id: str) -> List[Dict]:
        """Получить под-ордера, созданные после срабатывания планового ордера."""
        endpoint = '/api/v2/spot/trade/plan-sub-order'
        params = {'planOrderId': plan_order_id}
        data = await self._request('GET', endpoint, params=params, signed=True)
        sub_orders = []
        for item in data:
            sub_orders.append({
                'orderId': item.get('orderId'),
                'price': float(item.get('price', 0)),
                'type': item.get('type'),
                'status': item.get('status')
            })
        return sub_orders

    async def get_history_plan_orders(self, symbol: str = None, start_time: int = None,
                                      end_time: int = None, limit: int = 100,
                                      id_less_than: str = None) -> List[Dict]:
        """История плановых ордеров (исполненные, отменённые, с ошибкой)."""
        endpoint = '/api/v2/spot/trade/history-plan-order'
        params = {'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        orders = []
        for item in data.get('orderList', []):
            orders.append({
                'orderId': item['orderId'],
                'clientOid': item.get('clientOid'),
                'symbol': item['symbol'],
                'side': item['side'],
                'size': float(item['size']),
                'trigger_price': float(item['triggerPrice']),
                'trigger_type': item.get('triggerType'),
                'order_type': item.get('orderType'),
                'execute_price': float(item.get('executePrice', 0)),
                'plan_type': item.get('planType', 'amount'),
                'status': item['status'],
                'timestamp': int(item.get('cTime', 0))
            })
        return orders

    async def set_tpsl(self, symbol: str, hold_side: str, trigger_price: float,
                       execute_price: float, tpsl_type: str, size: float = 0) -> Dict:
        """
        Установить тейк-профит или стоп-лосс на споте.
        tpsl_type: 'profit_plan' (TP), 'loss_plan' (SL)
        hold_side: 'long' (длинная позиция) или 'short' (короткая позиция)
        Для длинной позиции TP/SL – это ордер на продажу (sell).
        Для короткой позиции TP/SL – это ордер на покупку (buy).
        """
        # Для длинной позиции закрываем продажей, для короткой – покупкой
        if hold_side == 'long':
            side = 'sell'
        else:  # short
            side = 'buy'
        
        # Если size == 0, значит TP/SL на всю позицию (в API Bitget для спота size обязателен, но 0 – особое значение)
        # В документации Bitget для спотовых TP/SL используется тот же эндпоинт place-plan-order
        # с plan_type='amount' и size = количество базовой монеты для закрытия.
        # Если size == 0, то попробуем отправить 0, но API может не принять. Лучше запросить размер позиции.
        # Для упрощения будем требовать size > 0.
        if size <= 0:
            raise ValueError("size must be > 0 for spot TP/SL")
        
        endpoint = '/api/v2/spot/trade/place-plan-order'
        body = {
            'symbol': symbol.upper(),
            'side': side,
            'orderType': 'limit' if execute_price > 0 else 'market',
            'size': str(size),
            'triggerPrice': str(trigger_price),
            'triggerType': 'fill_price',  # Для спота только fill_price
            'planType': 'amount'
        }
        if execute_price > 0:
            body['executePrice'] = str(execute_price)
        
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data['orderId'], 'type': tpsl_type}

    async def cancel_tpsl(self, symbol: str, order_id: str) -> Dict:
        """Отменить TP/SL (плановый ордер)."""
        return await self.cancel_plan_order(order_id=order_id)