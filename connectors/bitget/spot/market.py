# connectors/bitget/spot/market.py
from typing import Dict, List, Optional

class MarketMixin:
    """Миксин рыночных данных для спота."""

    async def get_coins(self, coin: str = None) -> List[Dict]:
        endpoint = '/api/v2/spot/public/coins'
        params = {}
        if coin:
            params['coin'] = coin.upper()
        data = await self._request('GET', endpoint, params=params, signed=False)
        return data if isinstance(data, list) else []

    async def get_symbols(self, symbol: str = None) -> List[Dict]:
        endpoint = '/api/v2/spot/public/symbols'
        params = {}
        if symbol:
            params['symbol'] = symbol.upper()
        data = await self._request('GET', endpoint, params=params, signed=False)
        return data if isinstance(data, list) else []

    async def get_vip_fee_rate(self) -> List[Dict]:
        endpoint = '/api/v2/spot/market/vip-fee-rate'
        return await self._request('GET', endpoint, signed=False)

    async def get_ticker(self, symbol: str) -> Dict:
        endpoint = '/api/v2/spot/market/tickers'
        params = {'symbol': symbol.upper()}
        data = await self._request('GET', endpoint, params=params, signed=False)
        items = data if isinstance(data, list) else data.get('list', [])
        for item in items:
            if item.get('symbol') == symbol.upper():
                return {
                    'symbol': item['symbol'],
                    'last': float(item['lastPr']),
                    'bid': float(item['bidPr']),
                    'ask': float(item['askPr']),
                    'high': float(item['high24h']),
                    'low': float(item['low24h']),
                    'volume': float(item['baseVolume']),
                    'quote_volume': float(item['quoteVolume']),
                    'open_24h': float(item.get('open', 0)),
                    'change_24h': float(item.get('change24h', 0)),
                    'timestamp': int(item['ts'])
                }
        return {}

    async def get_tickers(self, product_type: str = None) -> List[Dict]:
        endpoint = '/api/v2/spot/market/tickers'
        data = await self._request('GET', endpoint, signed=False)
        if isinstance(data, list):
            return data
        return data.get('list', [])

    async def get_order_book(self, symbol: str, limit: int = 20, merge_scale: str = 'step0') -> Dict:
        """Стакан ордеров. Параметр merge_scale: step0, step1... (step0 - нет слияния)."""
        endpoint = '/api/v2/spot/market/orderbook'
        params = {'symbol': symbol.upper(), 'limit': limit, 'type': merge_scale}
        data = await self._request('GET', endpoint, params=params, signed=False)
        return {
            'bids': [[float(p), float(q)] for p, q in data.get('bids', [])],
            'asks': [[float(p), float(q)] for p, q in data.get('asks', [])],
            'timestamp': int(data.get('ts', 0))
        }

    async def get_merge_depth(self, symbol: str, precision: str = 'scale0', limit: int = 100) -> Dict:
        endpoint = '/api/v2/spot/market/merge-depth'
        params = {'symbol': symbol.upper(), 'precision': precision, 'limit': limit}
        data = await self._request('GET', endpoint, params=params, signed=False)
        return {
            'bids': [[float(p), float(q)] for p, q in data.get('bids', [])],
            'asks': [[float(p), float(q)] for p, q in data.get('asks', [])],
            'timestamp': int(data.get('ts', 0)),
            'scale': data.get('scale', ''),
            'precision': data.get('precision', ''),
            'is_max_precision': data.get('isMaxPrecision', 'NO')
        }

    def _convert_interval(self, interval: str) -> str:
        mapping = {
            '1m': '1min', '5m': '5min', '15m': '15min', '30m': '30min',
            '1H': '1h', '4H': '4h', '6H': '6h', '12H': '12h',
            '1D': '1day', '3D': '3day', '1W': '1week', '1M': '1M',
            '6Hutc': '6Hutc', '12Hutc': '12Hutc', '1Dutc': '1Dutc',
            '3Dutc': '3Dutc', '1Wutc': '1Wutc', '1Mutc': '1Mutc'
        }
        return mapping.get(interval, interval)

    async def get_klines(self, symbol: str, interval: str, limit: int = 100,
                         start_time: Optional[int] = None,
                         end_time: Optional[int] = None) -> List[Dict]:
        endpoint = '/api/v2/spot/market/candles'
        params = {
            'symbol': symbol.upper(),
            'granularity': self._convert_interval(interval),
            'limit': min(limit, 1000)
        }
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
                'quote_volume': float(arr[7]) if len(arr) > 7 else 0.0
            })
        return candles

    async def get_history_klines(self, symbol: str, interval: str, end_time: int,
                                 limit: int = 100) -> List[Dict]:
        endpoint = '/api/v2/spot/market/history-candles'
        params = {
            'symbol': symbol.upper(),
            'granularity': self._convert_interval(interval),
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
                'quote_volume': float(arr[7]) if len(arr) > 7 else 0.0
            })
        return candles

    async def get_auction(self, symbol: str) -> Dict:
        endpoint = '/api/v2/spot/market/auction'
        params = {'symbol': symbol.upper()}
        return await self._request('GET', endpoint, params=params, signed=False)

    async def get_recent_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        endpoint = '/api/v2/spot/market/fills'
        params = {'symbol': symbol.upper(), 'limit': min(limit, 500)}
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
        endpoint = '/api/v2/spot/market/fills-history'
        params = {'symbol': symbol.upper(), 'limit': min(limit, 1000)}
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