# connectors/bitget/futures/trigger.py
from typing import Dict, List, Optional

class TriggerMixin:
    """Миксин для плановых ордеров, TP/SL, трейлинг-стопов."""

    async def _get_position_mode(self) -> str:
        try:
            endpoint = '/api/v2/mix/account/accounts'
            params = {'productType': self.product_type}
            data = await self._request('GET', endpoint, params=params, signed=True)
            if data and len(data) > 0:
                return data[0].get('posMode', 'one_way_mode')
        except Exception:
            pass
        return 'one_way_mode'

    async def set_tpsl(self, symbol: str, hold_side: str, trigger_price: float,
                       execute_price: float, tpsl_type: str, size: float = 0,
                       trigger_type: str = 'mark_price') -> Dict:
        """
        Установить TP/SL.
        :param hold_side: 'long' или 'short'
        :param trigger_price: цена срабатывания
        :param execute_price: цена исполнения (0 для рыночного)
        :param tpsl_type: 'profit_plan', 'loss_plan', 'moving_plan', 'pos_profit', 'pos_loss'
        :param size: количество контрактов (0 – вся позиция)
        :param trigger_type: 'mark_price' или 'fill_price'
        """
        trigger_price = await self._normalize_price(symbol, trigger_price)
        execute_price = await self._normalize_price(symbol, execute_price) if execute_price != 0 else 0
        size_str = str(size) if size > 0 else ''
        endpoint = '/api/v2/mix/order/place-tpsl-order'
        
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginCoin': self.margin_coin,
            'holdSide': hold_side.lower(),   # 'long' или 'short'
            'planType': tpsl_type,
            'triggerPrice': str(trigger_price),
            'triggerType': trigger_type,
            'executePrice': str(execute_price) if execute_price != 0 else '0',
            'size': size_str
        }
        
        if tpsl_type == 'moving_plan':
            body['rangeRate'] = str(trigger_price)
        
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data['orderId'], 'type': tpsl_type}

    async def modify_tpsl(self, symbol: str, order_id: str = None, client_oid: str = None,
                          trigger_price: str = None, execute_price: str = None,
                          size: str = None) -> Dict:
        endpoint = '/api/v2/mix/order/modify-tpsl-order'
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginCoin': self.margin_coin
        }
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
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    async def cancel_tpsl(self, symbol: str, order_id: str) -> Dict:
        return await self.cancel_trigger_order(symbol, order_id)

    async def place_position_tpsl(self, symbol: str, hold_side: str,
                                  stop_surplus_trigger_price: float = None,
                                  stop_surplus_execute_price: float = None,
                                  stop_surplus_size: float = 0,
                                  stop_loss_trigger_price: float = None,
                                  stop_loss_execute_price: float = None,
                                  stop_loss_size: float = 0,
                                  stp_mode: str = 'none') -> List[Dict]:
        endpoint = '/api/v2/mix/order/place-pos-tpsl'
        body = {
            'marginCoin': self.margin_coin,
            'productType': self.product_type,
            'symbol': symbol.upper(),
            'holdSide': hold_side.lower(),
            'stpMode': stp_mode
        }
        if stop_surplus_trigger_price is not None:
            body['stopSurplusTriggerPrice'] = str(stop_surplus_trigger_price)
            body['stopSurplusExecutePrice'] = str(stop_surplus_execute_price) if stop_surplus_execute_price is not None else '0'
            body['stopSurplusTriggerType'] = 'mark_price'
            if stop_surplus_size > 0:
                body['stopSurplusSize'] = str(stop_surplus_size)
        if stop_loss_trigger_price is not None:
            body['stopLossTriggerPrice'] = str(stop_loss_trigger_price)
            body['stopLossExecutePrice'] = str(stop_loss_execute_price) if stop_loss_execute_price is not None else '0'
            body['stopLossTriggerType'] = 'mark_price'
            if stop_loss_size > 0:
                body['stopLossSize'] = str(stop_loss_size)
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data

    async def place_trigger_order(self, symbol: str, side: str, trade_side: str,
                                  order_type: str, size: float, trigger_price: float,
                                  trigger_type: str = 'mark_price', price: float = None,
                                  reduce_only: bool = False, client_oid: str = None,
                                  preset_tp: float = None, preset_sl: float = None) -> Dict:
        norm_qty = await self._normalize_size(symbol, size)
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginMode': self.config.get('margin_mode', 'crossed'),
            'marginCoin': self.margin_coin,
            'planType': 'normal_plan',
            'side': side,
            'orderType': order_type,
            'size': str(norm_qty),
            'triggerPrice': str(trigger_price),
            'triggerType': trigger_type,
        }
        if order_type == 'limit' and price:
            body['price'] = str(price)
        if reduce_only:
            body['reduceOnly'] = 'YES'
        if client_oid:
            body['clientOid'] = client_oid
        if preset_tp:
            body['stopSurplusTriggerPrice'] = str(preset_tp)
            body['stopSurplusTriggerType'] = 'mark_price'
        if preset_sl:
            body['stopLossTriggerPrice'] = str(preset_sl)
            body['stopLossTriggerType'] = 'mark_price'
        pos_mode = await self._get_position_mode()
        if pos_mode == 'hedge_mode':
            body['tradeSide'] = trade_side
        data = await self._request('POST', '/api/v2/mix/order/place-plan-order', data=body, signed=True)
        return {'orderId': data['orderId'], 'clientOid': data.get('clientOid')}

    async def place_trailing_stop(self, symbol: str, side: str, trade_side: str,
                                  callback_rate: float, trigger_price: float,
                                  size: float, reduce_only: bool = False) -> Dict:
        norm_qty = await self._normalize_size(symbol, size)
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginMode': self.config.get('margin_mode', 'crossed'),
            'marginCoin': self.margin_coin,
            'planType': 'track_plan',
            'side': side,
            'orderType': 'market',
            'size': str(norm_qty),
            'triggerPrice': str(trigger_price),
            'triggerType': 'fill_price',
            'callbackRatio': str(callback_rate)
        }
        if reduce_only:
            body['reduceOnly'] = 'YES'
        pos_mode = await self._get_position_mode()
        if pos_mode == 'hedge_mode':
            body['tradeSide'] = trade_side
        data = await self._request('POST', '/api/v2/mix/order/place-plan-order', data=body, signed=True)
        return {'orderId': data['orderId'], 'clientOid': data.get('clientOid')}

    async def modify_trigger_order(self, symbol: str, order_id: str = None, client_oid: str = None,
                                   product_type: str = None, new_size: str = None,
                                   new_price: str = None, new_trigger_price: str = None,
                                   new_trigger_type: str = None, new_callback_ratio: str = None,
                                   new_stop_surplus_trigger_price: str = None,
                                   new_stop_surplus_execute_price: str = None,
                                   new_stop_surplus_trigger_type: str = None,
                                   new_stop_loss_trigger_price: str = None,
                                   new_stop_loss_execute_price: str = None,
                                   new_stop_loss_trigger_type: str = None) -> Dict:
        endpoint = '/api/v2/mix/order/modify-plan-order'
        body = {
            'symbol': symbol.upper(),
            'productType': product_type or self.product_type,
            'planType': 'normal_plan'
        }
        if order_id:
            body['orderId'] = order_id
        elif client_oid:
            body['clientOid'] = client_oid
        else:
            raise ValueError("order_id or client_oid required")
        if new_size:
            body['newSize'] = new_size
        if new_price is not None:
            body['newPrice'] = new_price
        if new_trigger_price:
            body['newTriggerPrice'] = new_trigger_price
        if new_trigger_type:
            body['newTriggerType'] = new_trigger_type
        if new_callback_ratio:
            body['newCallbackRatio'] = new_callback_ratio
        if new_stop_surplus_trigger_price is not None:
            body['newStopSurplusTriggerPrice'] = new_stop_surplus_trigger_price
        if new_stop_surplus_execute_price is not None:
            body['newStopSurplusExecutePrice'] = new_stop_surplus_execute_price
        if new_stop_surplus_trigger_type:
            body['newStopSurplusTriggerType'] = new_stop_surplus_trigger_type
        if new_stop_loss_trigger_price is not None:
            body['newStopLossTriggerPrice'] = new_stop_loss_trigger_price
        if new_stop_loss_execute_price is not None:
            body['newStopLossExecutePrice'] = new_stop_loss_execute_price
        if new_stop_loss_trigger_type:
            body['newStopLossTriggerType'] = new_stop_loss_trigger_type
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    async def get_trigger_orders(self, symbol: str = None, plan_type: str = 'normal_plan',
                                 limit: int = 100, id_less_than: str = None,
                                 start_time: int = None, end_time: int = None) -> List[Dict]:
        endpoint = '/api/v2/mix/order/orders-plan-pending'
        params = {'productType': self.product_type, 'planType': plan_type, 'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        if id_less_than:
            params['idLessThan'] = id_less_than
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        data = await self._request('GET', endpoint, params=params, signed=True)
        if data is None or not isinstance(data, dict):
            return []
        entrusted = data.get('entrustedList')
        if not isinstance(entrusted, list):
            entrusted = []
        orders = []
        for item in entrusted:
            orders.append({
                'orderId': item['orderId'],
                'clientOid': item.get('clientOid'),
                'symbol': item['symbol'],
                'plan_type': item['planType'],
                'side': item['side'],
                'size': float(item['size']),
                'trigger_price': float(item['triggerPrice']),
                'trigger_type': item.get('triggerType', ''),
                'status': item['planStatus'],
                'timestamp': int(item['cTime'])
            })
        return orders

    async def cancel_trigger_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        endpoint = '/api/v2/mix/order/cancel-plan-order'
        body = {
            'productType': self.product_type,
            'marginCoin': self.margin_coin,
            'symbol': symbol.upper(),
            'orderIdList': []
        }
        if order_id:
            body['orderIdList'].append({'orderId': order_id})
        elif client_oid:
            body['orderIdList'].append({'clientOid': client_oid})
        else:
            raise ValueError("order_id or client_oid required")
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': order_id, 'cancelled': len(data.get('successList', [])) > 0}

    async def cancel_all_trigger_orders(self, symbol: str = None, plan_type: str = None) -> Dict:
        endpoint = '/api/v2/mix/order/cancel-plan-order'
        body = {
            'productType': self.product_type,
            'marginCoin': self.margin_coin,
            'orderIdList': []
        }
        if symbol:
            body['symbol'] = symbol.upper()
        if plan_type:
            body['planType'] = plan_type
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data

    async def get_trigger_sub_order(self, plan_order_id: str) -> List[Dict]:
        endpoint = '/api/v2/mix/order/plan-sub-order'
        params = {'planOrderId': plan_order_id, 'productType': self.product_type}
        data = await self._request('GET', endpoint, params=params, signed=True)
        if not isinstance(data, list):
            return []
        sub_orders = []
        for item in data:
            sub_orders.append({
                'orderId': item.get('orderId'),
                'price': float(item.get('price', 0)),
                'type': item.get('type'),
                'status': item.get('status')
            })
        return sub_orders

    async def get_history_trigger_orders(self, symbol: str = None, plan_type: str = 'normal_plan',
                                         plan_status: str = None, limit: int = 100,
                                         id_less_than: str = None,
                                         start_time: int = None, end_time: int = None) -> List[Dict]:
        endpoint = '/api/v2/mix/order/orders-plan-history'
        params = {'productType': self.product_type, 'planType': plan_type, 'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        if plan_status:
            params['planStatus'] = plan_status
        if id_less_than:
            params['idLessThan'] = id_less_than
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        data = await self._request('GET', endpoint, params=params, signed=True)
        if data is None or not isinstance(data, dict):
            return []
        entrusted = data.get('entrustedList')
        if not isinstance(entrusted, list):
            entrusted = []
        orders = []
        for item in entrusted:
            orders.append({
                'orderId': item['orderId'],
                'clientOid': item.get('clientOid'),
                'symbol': item['symbol'],
                'plan_type': item['planType'],
                'side': item['side'],
                'size': float(item['size']),
                'trigger_price': float(item['triggerPrice']),
                'trigger_type': item.get('triggerType', ''),
                'status': item['planStatus'],
                'timestamp': int(item['cTime'])
            })
        return orders

    async def _load_contracts_cache(self):
        if not hasattr(self, '_contracts_cache'):
            self._contracts_cache = {}
            try:
                contracts = await self.get_contracts(self.product_type)
                for c in contracts:
                    self._contracts_cache[c['symbol']] = c
            except Exception:
                pass

    async def _normalize_size(self, symbol: str, size: float) -> float:
        await self._load_contracts_cache()
        contract = self._contracts_cache.get(symbol.upper())
        if contract:
            vol_place = int(contract.get('volumePlace', 4))
            return round(size, vol_place)
        return round(size, 4)

    async def _normalize_price(self, symbol: str, price: float) -> float:
        await self._load_contracts_cache()
        contract = self._contracts_cache.get(symbol.upper())
        if contract:
            price_place = int(contract.get('pricePlace', 2))
            return round(price, price_place)
        return round(price, 2)