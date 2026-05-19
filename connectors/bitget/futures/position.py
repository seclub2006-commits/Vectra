# connectors/bitget/futures/position.py
from typing import Dict, List, Optional

class PositionMixin:
    """Миксин для работы с позициями."""

    async def get_positions(self, symbol: str = None) -> List[Dict]:
        endpoint = '/api/v2/mix/position/all-position'
        params = {'productType': self.product_type}
        if symbol:
            params['symbol'] = symbol.upper()
        if self.margin_coin:
            params['marginCoin'] = self.margin_coin
        data = await self._request('GET', endpoint, params=params, signed=True)
        positions = []
        for pos in data:
            if float(pos.get('total', 0)) == 0:
                continue
            positions.append({
                'symbol': pos['symbol'],
                'side': 'long' if pos['holdSide'] == 'long' else 'short',
                'size': float(pos['total']),
                'entry_price': float(pos['openPriceAvg']),
                'mark_price': float(pos.get('markPrice', 0)),
                'unrealized_pnl': float(pos.get('unrealizedPL', 0)),
                'realized_pnl': float(pos.get('achievedProfits', 0)),
                'leverage': int(pos.get('leverage', 10)),
                'margin': float(pos.get('marginSize', 0)),
                'liquidation_price': float(pos.get('liquidationPrice', 0)),
                'margin_mode': pos.get('marginMode', 'crossed'),
                'pos_mode': pos.get('posMode', 'one_way_mode'),
                'maintenance_margin_rate': float(pos.get('keepMarginRate', 0)),
                'break_even_price': float(pos.get('breakEvenPrice', 0))
            })
        return positions

    async def get_single_position(self, symbol: str) -> Dict:
        endpoint = '/api/v2/mix/position/single-position'
        params = {'productType': self.product_type, 'symbol': symbol.upper(), 'marginCoin': self.margin_coin}
        data = await self._request('GET', endpoint, params=params, signed=True)
        if data and len(data) > 0:
            pos = data[0]
            return {
                'symbol': pos['symbol'],
                'side': 'long' if pos['holdSide'] == 'long' else 'short',
                'size': float(pos['total']),
                'entry_price': float(pos['openPriceAvg']),
                'mark_price': float(pos.get('markPrice', 0)),
                'unrealized_pnl': float(pos.get('unrealizedPL', 0)),
                'leverage': int(pos.get('leverage', 10)),
                'margin': float(pos.get('marginSize', 0)),
                'liquidation_price': float(pos.get('liquidationPrice', 0))
            }
        return {}

    async def get_position_adl_rank(self) -> List[Dict]:
        endpoint = '/api/v2/mix/position/adlRank'
        params = {'productType': self.product_type}
        return await self._request('GET', endpoint, params=params, signed=True)

    async def get_historical_positions(self, symbol: str = None, start_time: int = None,
                                       end_time: int = None, limit: int = 20,
                                       id_less_than: str = None) -> List[Dict]:
        endpoint = '/api/v2/mix/position/history-position'
        params = {'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        else:
            params['productType'] = self.product_type
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data.get('list', [])

    async def close_position(self, symbol: str, hold_side: str = '') -> Dict:
        return await self.flash_close_position(symbol, hold_side)

    async def flash_close_position(self, symbol: str, hold_side: str = None) -> Dict:
        endpoint = '/api/v2/mix/order/close-positions'
        body = {'productType': self.product_type, 'symbol': symbol.upper()}
        if hold_side:
            body['holdSide'] = hold_side
        await self._request('POST', endpoint, data=body, signed=True)
        return {'symbol': symbol, 'hold_side': hold_side, 'closed': True}