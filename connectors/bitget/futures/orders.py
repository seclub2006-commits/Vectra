# connectors/bitget/futures/orders.py
from typing import Dict, List, Optional

class OrderMixin:
    """Миксин для обычных ордеров (лимит/рынок, отмена, получение)."""

    # ========== Создание ордеров ==========
    async def create_order(self, symbol: str, side: str, order_type: str,
                           quantity: float, price: Optional[float] = None,
                           reduce_only: bool = False, client_oid: str = None,
                           preset_tp: float = None, preset_sl: float = None,
                           stp_mode: str = 'none') -> Dict:
        """Создать фьючерсный ордер."""
        pos_mode = await self._get_position_mode()
        norm_qty = await self._normalize_size(symbol, quantity)

        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginMode': self.config.get('margin_mode', 'crossed'),
            'marginCoin': self.margin_coin,
            'size': str(norm_qty),
            'side': side,
            'orderType': order_type,
            'stpMode': stp_mode
        }
        if order_type == 'limit' and price:
            body['price'] = str(price)
            body['force'] = 'gtc'
        elif order_type == 'market':
            pass
        else:
            body['force'] = 'gtc'

        if reduce_only:
            body['reduceOnly'] = 'YES'
        if client_oid:
            body['clientOid'] = client_oid

        if pos_mode == 'hedge_mode':
            trade_side = 'close' if reduce_only else 'open'
            body['tradeSide'] = trade_side

        if preset_tp:
            body['presetStopSurplusPrice'] = str(preset_tp)
        if preset_sl:
            body['presetStopLossPrice'] = str(preset_sl)

        body = {k: v for k, v in body.items() if v is not None}
        data = await self._request('POST', '/api/v2/mix/order/place-order', data=body, signed=True)
        return {
            'orderId': data.get('orderId'),
            'clientOid': data.get('clientOid', client_oid),
            'symbol': symbol,
            'status': 'new'
        }

    async def batch_create_orders(self, symbol: str, order_list: List[Dict]) -> Dict:
        endpoint = '/api/v2/mix/order/batch-place-order'
        pos_mode = await self._get_position_mode()
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginMode': self.config.get('margin_mode', 'crossed'),
            'marginCoin': self.margin_coin,
            'orderList': []
        }
        for ord in order_list:
            norm_qty = await self._normalize_size(symbol, ord['quantity'])
            item = {
                'size': str(norm_qty),
                'side': ord['side'],
                'orderType': ord['orderType']
            }
            if 'price' in ord and ord['price']:
                item['price'] = str(ord['price'])
            if 'clientOid' in ord:
                item['clientOid'] = ord['clientOid']
            if 'reduceOnly' in ord:
                item['reduceOnly'] = 'YES' if ord['reduceOnly'] else 'NO'
            if pos_mode == 'hedge_mode':
                trade_side = 'close' if ord.get('reduceOnly', False) else 'open'
                item['tradeSide'] = trade_side
            body['orderList'].append(item)
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data

    async def reversal_order(self, symbol: str, margin_coin: str, side: str,
                             size: float = None, client_oid: str = None,
                             trade_side: str = None) -> Dict:
        endpoint = '/api/v2/mix/order/click-backhand'
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginCoin': margin_coin.upper(),
            'side': side
        }
        if size:
            body['size'] = str(size)
        if client_oid:
            body['clientOid'] = client_oid
        if trade_side:
            body['tradeSide'] = trade_side
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    # ========== Отмена ордеров ==========
    async def cancel_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        """
        Отменить обычный ордер (лимит/рынок). Для плановых ордеров используйте cancel_trigger_order.
        """
        endpoint = '/api/v2/mix/order/cancel-order'
        body = {'symbol': symbol.upper(), 'productType': self.product_type, 'marginCoin': self.margin_coin}
        if order_id:
            body['orderId'] = order_id
        elif client_oid:
            body['clientOid'] = client_oid
        else:
            raise ValueError("order_id or client_oid required")
        
        # ИСПРАВЛЕНИЕ: больше не пытаемся отменить плановый ордер при ошибке
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    async def batch_cancel_orders(self, symbol: str, order_ids: List[str]) -> Dict:
        endpoint = '/api/v2/mix/order/batch-cancel-orders'
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginCoin': self.margin_coin,
            'orderIdList': [{'orderId': oid} for oid in order_ids]
        }
        return await self._request('POST', endpoint, data=body, signed=True)

    async def cancel_all_orders(self, symbol: str = None, product_type: str = None) -> List[Dict]:
        endpoint = '/api/v2/mix/order/cancel-all-orders'
        body = {'productType': self.product_type, 'marginCoin': self.margin_coin}
        if symbol:
            body['symbol'] = symbol.upper()
        data = await self._request('POST', endpoint, data=body, signed=True)
        cancelled = []
        for item in data.get('successList', []):
            cancelled.append({'orderId': item.get('orderId'), 'clientOid': item.get('clientOid')})
        return cancelled

    # ========== Модификация ордеров ==========
    async def modify_order(self, symbol: str, order_id: str, new_size: float = None,
                           new_price: float = None, new_client_oid: str = None) -> Dict:
        endpoint = '/api/v2/mix/order/modify-order'
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginCoin': self.margin_coin,
            'orderId': order_id,
            'newClientOid': new_client_oid or ''
        }
        if new_size is not None:
            body['newSize'] = str(new_size)
        if new_price is not None:
            body['newPrice'] = str(new_price)
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    # ========== Получение информации об ордерах ==========
    async def get_open_orders(self, symbol: str = None, product_type: str = None) -> List[Dict]:
        endpoint = '/api/v2/mix/order/orders-pending'
        params = {'productType': self.product_type}
        if symbol:
            params['symbol'] = symbol.upper()
        data = await self._request('GET', endpoint, params=params, signed=True)
        if data is None:
            return []
        orders = []
        for item in data.get('entrustedList', []):
            orders.append({
                'orderId': item['orderId'],
                'clientOid': item.get('clientOid'),
                'symbol': item['symbol'],
                'price': float(item['price']),
                'quantity': float(item['size']),
                'filled': float(item.get('baseVolume', 0)),
                'status': item['status'],
                'side': item['side'],
                'order_type': item['orderType'],
                'timestamp': int(item['cTime'])
            })
        return orders

    async def get_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        endpoint = '/api/v2/mix/order/detail'
        params = {'symbol': symbol.upper(), 'productType': self.product_type}
        if order_id:
            params['orderId'] = order_id
        elif client_oid:
            params['clientOid'] = client_oid
        else:
            raise ValueError("order_id or client_oid required")
        data = await self._request('GET', endpoint, params=params, signed=True)
        return {
            'orderId': data['orderId'],
            'clientOid': data.get('clientOid'),
            'symbol': data['symbol'],
            'price': float(data['price']),
            'quantity': float(data['size']),
            'filled': float(data.get('baseVolume', 0)),
            'status': data['state'],
            'side': data['side'],
            'order_type': data['orderType'],
            'timestamp': int(data['cTime'])
        }

    async def get_order_history(self, symbol: str = None, product_type: str = None,
                                start_time: int = None, end_time: int = None,
                                limit: int = 100) -> List[Dict]:
        endpoint = '/api/v2/mix/order/orders-history'
        params = {'productType': self.product_type, 'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        data = await self._request('GET', endpoint, params=params, signed=True)
        if data is None:
            return []
        orders = []
        for item in data.get('entrustedList', []):
            try:
                price = float(item.get('price', 0)) if item.get('price') else 0.0
            except (ValueError, TypeError):
                price = 0.0
            try:
                quantity = float(item.get('size', 0)) if item.get('size') else 0.0
            except (ValueError, TypeError):
                quantity = 0.0
            try:
                filled = float(item.get('baseVolume', 0)) if item.get('baseVolume') else 0.0
            except (ValueError, TypeError):
                filled = 0.0
            orders.append({
                'orderId': item['orderId'],
                'clientOid': item.get('clientOid'),
                'symbol': item['symbol'],
                'price': price,
                'quantity': quantity,
                'filled': filled,
                'status': item['status'],
                'side': item['side'],
                'order_type': item['orderType'],
                'timestamp': int(item['cTime'])
            })
        return orders

    async def get_fills(self, symbol: str = None, product_type: str = None,
                        start_time: int = None, end_time: int = None,
                        limit: int = 100, id_less_than: str = None) -> List[Dict]:
        endpoint = '/api/v2/mix/order/fills'
        params = {'productType': self.product_type, 'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        if data is None:
            return []
        fills = []
        for item in data.get('fillList', []):
            fills.append({
                'tradeId': item.get('tradeId'),
                'orderId': item['orderId'],
                'symbol': item['symbol'],
                'price': float(item['price']),
                'size': float(item['baseVolume']),
                'quote_volume': float(item.get('quoteVolume', 0)),
                'side': item['side'],
                'fee': float(item.get('feeDetail', [{}])[0].get('totalFee', 0)) if item.get('feeDetail') else 0,
                'timestamp': int(item['cTime'])
            })
        return fills

    # ========== Вспомогательные методы ==========
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