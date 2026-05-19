# connectors/bitget/spot/orders.py
from typing import Dict, List, Optional

class OrderMixin:
    """Миксин для обычных ордеров (без триггеров)."""

    async def _get_symbol_precision(self, symbol: str) -> tuple:
        if not hasattr(self, '_symbols_cache'):
            self._symbols_cache = {}
        if symbol not in self._symbols_cache:
            symbols = await self.get_symbols(symbol)
            if symbols:
                self._symbols_cache[symbol] = symbols[0]
            else:
                self._symbols_cache[symbol] = {'pricePrecision': 2, 'quantityPrecision': 6}
        info = self._symbols_cache[symbol]
        return int(info.get('pricePrecision', 2)), int(info.get('quantityPrecision', 6))

    async def _normalize_spot_price(self, symbol: str, price: float) -> float:
        price_prec, _ = await self._get_symbol_precision(symbol)
        return round(price, price_prec)

    async def _normalize_spot_quantity(self, symbol: str, qty: float) -> float:
        _, qty_prec = await self._get_symbol_precision(symbol)
        return round(qty, qty_prec)

    async def create_order(self, symbol: str, side: str, order_type: str,
                           quantity: float, price: Optional[float] = None,
                           reduce_only: bool = False, client_oid: str = None,
                           preset_tp: float = None, preset_sl: float = None,
                           stp_mode: str = 'none') -> Dict:
        endpoint = '/api/v2/spot/trade/place-order'
        quantity = await self._normalize_spot_quantity(symbol, quantity)
        body = {
            'symbol': symbol.upper(),
            'side': side,
            'orderType': order_type,
            'size': str(quantity),
            'stpMode': stp_mode
        }
        if order_type == 'limit' and price:
            price = await self._normalize_spot_price(symbol, price)
            body['price'] = str(price)
            body['force'] = 'gtc'
        elif order_type == 'market':
            body['force'] = 'gtc'
        if client_oid:
            body['clientOid'] = client_oid
        if preset_tp is not None:
            tp = await self._normalize_spot_price(symbol, preset_tp)
            body['presetTakeProfitPrice'] = str(tp)
        if preset_sl is not None:
            sl = await self._normalize_spot_price(symbol, preset_sl)
            body['presetStopLossPrice'] = str(sl)
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {
            'orderId': data.get('orderId'),
            'clientOid': data.get('clientOid', client_oid),
            'symbol': symbol,
            'status': 'new'
        }

    async def cancel_replace_order(self, symbol: str, new_price: float, new_size: float,
                                   order_id: str = None, client_oid: str = None,
                                   new_client_oid: str = None) -> Dict:
        endpoint = '/api/v2/spot/trade/cancel-replace-order'
        new_price = await self._normalize_spot_price(symbol, new_price)
        new_size = await self._normalize_spot_quantity(symbol, new_size)
        body = {
            'symbol': symbol.upper(),
            'price': str(new_price),
            'size': str(new_size)
        }
        if order_id:
            body['orderId'] = order_id
        elif client_oid:
            body['clientOid'] = client_oid
        else:
            raise ValueError("order_id or client_oid required")
        if new_client_oid:
            body['newClientOid'] = new_client_oid
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {
            'orderId': data.get('orderId'),
            'clientOid': data.get('clientOid'),
            'success': data.get('success') == 'success',
            'message': data.get('msg')
        }

    async def batch_cancel_replace_orders(self, order_list: List[Dict]) -> List[Dict]:
        endpoint = '/api/v2/spot/trade/batch-cancel-replace-order'
        formatted = []
        for ord in order_list:
            symbol = ord['symbol']
            price = await self._normalize_spot_price(symbol, ord['price'])
            size = await self._normalize_spot_quantity(symbol, ord['size'])
            item = {
                'symbol': symbol.upper(),
                'price': str(price),
                'size': str(size)
            }
            if 'orderId' in ord:
                item['orderId'] = ord['orderId']
            elif 'clientOid' in ord:
                item['clientOid'] = ord['clientOid']
            if 'newClientOid' in ord:
                item['newClientOid'] = ord['newClientOid']
            formatted.append(item)
        body = {'orderList': formatted}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data

    async def cancel_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        endpoint = '/api/v2/spot/trade/cancel-order'
        body = {'symbol': symbol.upper()}
        if order_id:
            body['orderId'] = order_id
        elif client_oid:
            body['clientOid'] = client_oid
        else:
            raise ValueError("order_id or client_oid required")
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    async def batch_cancel_orders(self, symbol: str = None, batch_mode: str = 'single',
                                  order_list: List[Dict] = None) -> Dict:
        endpoint = '/api/v2/spot/trade/batch-cancel-order'
        body = {'batchMode': batch_mode}
        if symbol:
            body['symbol'] = symbol.upper()
        if order_list:
            body['orderList'] = []
            for ord in order_list:
                item = {}
                if 'orderId' in ord:
                    item['orderId'] = ord['orderId']
                if 'clientOid' in ord:
                    item['clientOid'] = ord['clientOid']
                if batch_mode == 'multiple' and 'symbol' in ord:
                    item['symbol'] = ord['symbol'].upper()
                body['orderList'].append(item)
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data

    async def cancel_order_by_symbol(self, symbol: str) -> Dict:
        endpoint = '/api/v2/spot/trade/cancel-symbol-order'
        body = {'symbol': symbol.upper()}
        await self._request('POST', endpoint, data=body, signed=True)
        return {'symbol': symbol, 'cancelled': True}

    async def batch_create_orders(self, order_list: List[Dict], symbol: str = None, batch_mode: str = 'single') -> Dict:
        endpoint = '/api/v2/spot/trade/batch-orders'
        body = {'batchMode': batch_mode}
        if symbol and batch_mode == 'single':
            body['symbol'] = symbol.upper()
        body['orderList'] = []
        for ord in order_list:
            item = {
                'side': ord['side'],
                'orderType': ord['orderType'],
                'force': ord.get('force', 'gtc')
            }
            sym = ord.get('symbol', symbol) if batch_mode == 'multiple' else symbol
            if not sym:
                raise ValueError("Symbol is required for order normalization")
            if 'price' in ord and ord['price']:
                norm_price = await self._normalize_spot_price(sym, ord['price'])
                item['price'] = str(norm_price)
            norm_size = await self._normalize_spot_quantity(sym, ord['size'])
            item['size'] = str(norm_size)
            if 'clientOid' in ord:
                item['clientOid'] = ord['clientOid']
            if 'stpMode' in ord:
                item['stpMode'] = ord['stpMode']
            if batch_mode == 'multiple' and 'symbol' in ord:
                item['symbol'] = ord['symbol'].upper()
            if 'preset_tp' in ord:
                tp = await self._normalize_spot_price(sym, ord['preset_tp'])
                item['presetTakeProfitPrice'] = str(tp)
            if 'preset_sl' in ord:
                sl = await self._normalize_spot_price(sym, ord['preset_sl'])
                item['presetStopLossPrice'] = str(sl)
            body['orderList'].append(item)
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data

    async def get_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        endpoint = '/api/v2/spot/trade/orderInfo'
        params = {'symbol': symbol.upper()}
        if order_id:
            params['orderId'] = order_id
        elif client_oid:
            params['clientOid'] = client_oid
        else:
            raise ValueError("order_id or client_oid required")
        data = await self._request('GET', endpoint, params=params, signed=True)
        if isinstance(data, list) and len(data) > 0:
            item = data[0]
        elif isinstance(data, dict) and 'data' in data:
            item = data['data'][0] if data['data'] else {}
        else:
            item = data
        return {
            'orderId': item.get('orderId'),
            'clientOid': item.get('clientOid'),
            'symbol': item.get('symbol'),
            'price': float(item.get('price', 0)),
            'quantity': float(item.get('size', 0)),
            'filled': float(item.get('baseVolume', 0)),
            'status': item.get('status'),
            'side': item.get('side'),
            'orderType': item.get('orderType'),
            'price_avg': float(item.get('priceAvg', 0)),
            'quote_volume': float(item.get('quoteVolume', 0)),
            'fee_detail': item.get('feeDetail'),
            'timestamp': int(item.get('cTime', 0))
        }

    async def get_open_orders(self, symbol: str = None, start_time: int = None,
                              end_time: int = None, limit: int = 100,
                              id_less_than: str = None, tpsl_type: str = 'normal') -> List[Dict]:
        endpoint = '/api/v2/spot/trade/unfilled-orders'
        params = {'limit': min(limit, 100), 'tpslType': tpsl_type}
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
        orders = []
        for item in data:
            orders.append({
                'orderId': item['orderId'],
                'clientOid': item.get('clientOid'),
                'symbol': item['symbol'],
                'price': float(item.get('priceAvg', 0)),
                'quantity': float(item.get('size', 0)),
                'filled': float(item.get('baseVolume', 0)),
                'status': item['status'],
                'side': item['side'],
                'orderType': item['orderType'],
                'preset_tp': float(item.get('presetTakeProfitPrice', 0)),
                'preset_sl': float(item.get('presetStopLossPrice', 0)),
                'timestamp': int(item.get('cTime', 0))
            })
        return orders

    async def get_order_history(self, symbol: str = None, start_time: int = None,
                                end_time: int = None, limit: int = 100,
                                id_less_than: str = None, tpsl_type: str = 'normal') -> List[Dict]:
        endpoint = '/api/v2/spot/trade/history-orders'
        params = {'limit': min(limit, 100), 'tpslType': tpsl_type}
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
        orders = []
        for item in data:
            orders.append({
                'orderId': item['orderId'],
                'clientOid': item.get('clientOid'),
                'symbol': item['symbol'],
                'price': float(item.get('price', 0)),
                'quantity': float(item.get('size', 0)),
                'filled': float(item.get('baseVolume', 0)),
                'status': item['status'],
                'side': item['side'],
                'orderType': item['orderType'],
                'price_avg': float(item.get('priceAvg', 0)),
                'quote_volume': float(item.get('quoteVolume', 0)),
                'fee_detail': item.get('feeDetail'),
                'timestamp': int(item.get('cTime', 0))
            })
        return orders

    async def get_fills(self, symbol: str = None, order_id: str = None,
                        start_time: int = None, end_time: int = None,
                        limit: int = 100, id_less_than: str = None) -> List[Dict]:
        endpoint = '/api/v2/spot/trade/fills'
        params = {'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        if order_id:
            params['orderId'] = order_id
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
        for item in data:
            fills.append({
                'tradeId': item.get('tradeId'),
                'orderId': item['orderId'],
                'symbol': item['symbol'],
                'price': float(item['priceAvg']),
                'size': float(item['size']),
                'quote_volume': float(item.get('amount', 0)),
                'side': item['side'],
                'fee': float(item.get('feeDetail', {}).get('totalFee', 0)),
                'fee_coin': item.get('feeDetail', {}).get('feeCoin', ''),
                'timestamp': int(item.get('cTime', 0))
            })
        return fills