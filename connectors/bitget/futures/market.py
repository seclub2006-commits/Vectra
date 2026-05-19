# connectors/bitget/futures/market.py
from typing import Dict, List, Optional

class MarketMixin:
    """Миксин для рыночных данных (фьючерсы)."""

    async def get_vip_fee_rate(self) -> List[Dict]:
        endpoint = '/api/v2/mix/market/vip-fee-rate'
        return await self._request('GET', endpoint, signed=False)

    async def get_interest_rate_history(self, coin: str) -> Dict:
        endpoint = '/api/v2/mix/market/union-interest-rate-history'
        params = {'coin': coin.upper()}
        return await self._request('GET', endpoint, params=params, signed=False)

    async def get_exchange_rate(self) -> List[Dict]:
        endpoint = '/api/v2/mix/market/exchange-rate'
        return await self._request('GET', endpoint, signed=False)

    async def get_discount_rate(self) -> List[Dict]:
        endpoint = '/api/v2/mix/market/discount-rate'
        return await self._request('GET', endpoint, signed=False)

    async def get_ticker(self, symbol: str) -> Dict:
        endpoint = '/api/v2/mix/market/tickers'
        params = {'productType': self.product_type}
        data = await self._request('GET', endpoint, params=params, signed=False)
        if isinstance(data, list):
            for item in data:
                if item.get('symbol') == symbol.upper():
                    return self._parse_ticker(item)
        return {}

    async def get_tickers(self, product_type: str = None) -> List[Dict]:
        pt = product_type or self.product_type
        endpoint = '/api/v2/mix/market/tickers'
        params = {'productType': pt}
        data = await self._request('GET', endpoint, params=params, signed=False)
        if isinstance(data, list):
            tickers = []
            for item in data:
                try:
                    tickers.append(self._parse_ticker(item))
                except Exception:
                    continue
            return tickers
        return []

    def _parse_ticker(self, item: dict) -> dict:
        def safe_float(val, default=0.0):
            if val is None or val == '':
                return default
            try:
                return float(val)
            except (ValueError, TypeError):
                return default

        return {
            'symbol': item.get('symbol', ''),
            'last': safe_float(item.get('lastPr')),
            'bid': safe_float(item.get('bidPr')),
            'ask': safe_float(item.get('askPr')),
            'high': safe_float(item.get('high24h')),
            'low': safe_float(item.get('low24h')),
            'volume': safe_float(item.get('baseVolume')),
            'quote_volume': safe_float(item.get('quoteVolume')),
            'open_interest': safe_float(item.get('holdingAmount')),
            'funding_rate': safe_float(item.get('fundingRate')),
            'next_funding_time': int(item.get('nextFundingTime', 0)),
            'mark_price': safe_float(item.get('markPrice')),
            'index_price': safe_float(item.get('indexPrice')),
            'timestamp': int(item.get('ts', 0))
        }

    async def get_merge_depth(self, symbol: str, precision: str = 'scale0', limit: int = 100) -> Dict:
        endpoint = '/api/v2/mix/market/merge-depth'
        params = {'productType': self.product_type, 'symbol': symbol.upper(), 'precision': precision, 'limit': limit}
        data = await self._request('GET', endpoint, params=params, signed=False)
        return {
            'bids': [[float(p), float(q)] for p, q in data.get('bids', [])],
            'asks': [[float(p), float(q)] for p, q in data.get('asks', [])],
            'timestamp': int(data.get('ts', 0)),
            'scale': data.get('scale', ''),
            'precision': data.get('precision', ''),
            'is_max_precision': data.get('isMaxPrecision', 'NO')
        }

    async def get_order_book(self, symbol: str, limit: int = 20, merge_scale: str = 'scale0') -> Dict:
        """Реализация get_order_book через get_merge_depth."""
        return await self.get_merge_depth(symbol, precision=merge_scale, limit=limit)

    async def get_klines(self, symbol: str, interval: str, limit: int = 100,
                         start_time: Optional[int] = None,
                         end_time: Optional[int] = None) -> List[Dict]:
        endpoint = '/api/v2/mix/market/candles'
        params = {'productType': self.product_type, 'symbol': symbol.upper(), 'granularity': interval, 'limit': min(limit, 1000)}
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        data = await self._request('GET', endpoint, params=params, signed=False)
        candles = []
        for arr in data:
            candles.append({
                'timestamp': int(arr[0]),
                'open': float(arr[1]),
                'high': float(arr[2]),
                'low': float(arr[3]),
                'close': float(arr[4]),
                'volume': float(arr[5]),
                'quote_volume': float(arr[6]) if len(arr) > 6 else 0
            })
        return candles

    async def get_historical_klines(self, symbol: str, interval: str,
                                    start_time: int, end_time: int,
                                    limit: int = 200) -> List[Dict]:
        endpoint = '/api/v2/mix/market/history-candles'
        params = {
            'productType': self.product_type,
            'symbol': symbol.upper(),
            'granularity': interval,
            'startTime': start_time,
            'endTime': end_time,
            'limit': min(limit, 200)
        }
        data = await self._request('GET', endpoint, params=params, signed=False)
        candles = []
        for arr in data:
            candles.append({
                'timestamp': int(arr[0]),
                'open': float(arr[1]),
                'high': float(arr[2]),
                'low': float(arr[3]),
                'close': float(arr[4]),
                'volume': float(arr[5]),
                'quote_volume': float(arr[6]) if len(arr) > 6 else 0
            })
        return candles

    async def get_historical_index_klines(self, symbol: str, interval: str,
                                          start_time: int, end_time: int,
                                          limit: int = 200) -> List[Dict]:
        endpoint = '/api/v2/mix/market/history-index-candles'
        params = {
            'productType': self.product_type,
            'symbol': symbol.upper(),
            'granularity': interval,
            'startTime': start_time,
            'endTime': end_time,
            'limit': min(limit, 200)
        }
        data = await self._request('GET', endpoint, params=params, signed=False)
        candles = []
        for arr in data:
            candles.append({
                'timestamp': int(arr[0]),
                'open': float(arr[1]),
                'high': float(arr[2]),
                'low': float(arr[3]),
                'close': float(arr[4]),
                'volume': float(arr[5]),
                'quote_volume': float(arr[6]) if len(arr) > 6 else 0
            })
        return candles

    async def get_historical_mark_klines(self, symbol: str, interval: str,
                                         start_time: int, end_time: int,
                                         limit: int = 200) -> List[Dict]:
        endpoint = '/api/v2/mix/market/history-mark-candles'
        params = {
            'productType': self.product_type,
            'symbol': symbol.upper(),
            'granularity': interval,
            'startTime': start_time,
            'endTime': end_time,
            'limit': min(limit, 200)
        }
        data = await self._request('GET', endpoint, params=params, signed=False)
        candles = []
        for arr in data:
            candles.append({
                'timestamp': int(arr[0]),
                'open': float(arr[1]),
                'high': float(arr[2]),
                'low': float(arr[3]),
                'close': float(arr[4]),
                'volume': float(arr[5]),
                'quote_volume': float(arr[6]) if len(arr) > 6 else 0
            })
        return candles

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        endpoint = '/api/v2/mix/market/fills'
        params = {'productType': self.product_type, 'symbol': symbol.upper(), 'limit': min(limit, 100)}
        data = await self._request('GET', endpoint, params=params, signed=False)
        trades = []
        for item in data:
            trades.append({
                'trade_id': item['tradeId'],
                'price': float(item['price']),
                'size': float(item['size']),
                'side': item['side'],
                'timestamp': int(item['ts'])
            })
        return trades

    async def get_history_trades(self, symbol: str, limit: int = 500,
                                 id_less_than: str = None,
                                 start_time: int = None, end_time: int = None) -> List[Dict]:
        endpoint = '/api/v2/mix/market/fills-history'
        params = {
            'productType': self.product_type,
            'symbol': symbol.upper(),
            'limit': min(limit, 1000)
        }
        if id_less_than:
            params['idLessThan'] = id_less_than
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        data = await self._request('GET', endpoint, params=params, signed=False)
        trades = []
        for item in data:
            trades.append({
                'trade_id': item['tradeId'],
                'price': float(item['price']),
                'size': float(item['size']),
                'side': item['side'],
                'timestamp': int(item['ts'])
            })
        return trades

    async def get_open_interest(self, symbol: str) -> Dict:
        endpoint = '/api/v2/mix/market/open-interest'
        params = {'productType': self.product_type, 'symbol': symbol.upper()}
        data = await self._request('GET', endpoint, params=params, signed=False)
        return {
            'symbol': data.get('openInterestList', [{}])[0].get('symbol', symbol),
            'size': float(data.get('openInterestList', [{}])[0].get('size', 0)),
            'timestamp': int(data.get('ts', 0))
        }

    async def get_funding_time(self, symbol: str) -> Dict:
        endpoint = '/api/v2/mix/market/funding-time'
        params = {'productType': self.product_type, 'symbol': symbol.upper()}
        data = await self._request('GET', endpoint, params=params, signed=False)
        if data and isinstance(data, list) and len(data) > 0:
            return {
                'symbol': data[0]['symbol'],
                'next_funding_time': int(data[0]['nextFundingTime']),
                'rate_period': int(data[0]['ratePeriod'])
            }
        return {}

    async def get_mark_index_prices(self, symbol: str) -> Dict:
        endpoint = '/api/v2/mix/market/symbol-price'
        params = {'productType': self.product_type, 'symbol': symbol.upper()}
        data = await self._request('GET', endpoint, params=params, signed=False)
        if data and isinstance(data, list) and len(data) > 0:
            return {
                'symbol': data[0]['symbol'],
                'mark_price': float(data[0]['markPrice']),
                'index_price': float(data[0]['indexPrice']),
                'last_price': float(data[0]['price']),
                'timestamp': int(data[0]['ts'])
            }
        return {}

    async def get_funding_rate(self, symbol: str) -> Dict:
        endpoint = '/api/v2/mix/market/current-fund-rate'
        params = {'productType': self.product_type, 'symbol': symbol.upper()}
        data = await self._request('GET', endpoint, params=params, signed=False)
        if data and isinstance(data, list) and len(data) > 0:
            item = data[0]
            return {
                'symbol': item['symbol'],
                'funding_rate': float(item['fundingRate']),
                'next_update': int(item.get('nextUpdate', 0)),
                'funding_interval': int(item.get('fundingRateInterval', 8)),
                'min_rate': float(item.get('minFundingRate', -0.003)),
                'max_rate': float(item.get('maxFundingRate', 0.003))
            }
        return {}

    async def get_funding_history(self, symbol: str, limit: int = 20, page_no: int = 1) -> List[Dict]:
        endpoint = '/api/v2/mix/market/history-fund-rate'
        params = {'productType': self.product_type, 'symbol': symbol.upper(), 'pageSize': min(limit, 100), 'pageNo': page_no}
        data = await self._request('GET', endpoint, params=params, signed=False)
        history = []
        for item in data:
            history.append({
                'symbol': item['symbol'],
                'funding_rate': float(item['fundingRate']),
                'funding_time': int(item['fundingTime'])
            })
        return history

    async def get_oi_limit(self, symbol: str = None) -> List[Dict]:
        endpoint = '/api/v2/mix/market/oi-limit'
        params = {'productType': self.product_type}
        if symbol:
            params['symbol'] = symbol.upper()
        return await self._request('GET', endpoint, params=params, signed=False)

    async def get_contracts(self, product_type: str = None, symbol: str = None) -> List[Dict]:
        pt = product_type or self.product_type
        endpoint = '/api/v2/mix/market/contracts'
        params = {'productType': pt}
        if symbol:
            params['symbol'] = symbol.upper()
        return await self._request('GET', endpoint, params=params, signed=False)

    async def get_position_tier(self, symbol: str) -> List[Dict]:
        endpoint = '/api/v2/mix/market/query-position-lever'
        params = {'productType': self.product_type, 'symbol': symbol.upper()}
        return await self._request('GET', endpoint, params=params, signed=False)