# connectors/bitget/futures/account.py
import logging
from typing import Dict, List, Optional

from connectors.base.exceptions import APIError

logger = logging.getLogger(__name__)


class AccountMixin:
    """Миксин для управления аккаунтом, балансами, плечом, режимами."""

    # ========== Балансы и информация об аккаунте ==========
    async def get_balance(self, currency: str = None) -> List[Dict]:
        endpoint = '/api/v2/mix/account/accounts'
        params = {'productType': self.product_type}
        data = await self._request('GET', endpoint, params=params, signed=True)
        balances = []
        for account in data:
            if currency and account['marginCoin'] != currency.upper():
                continue
            balances.append({
                'currency': account['marginCoin'],
                'available': float(account['available']),
                'frozen': float(account.get('locked', 0)),
                'total': float(account.get('accountEquity', 0)),
                'equity': float(account.get('accountEquity', 0)),
                'unrealized_pnl': float(account.get('unrealizedPL', 0)),
                'crossed_risk_rate': float(account.get('crossedRiskRate', 0)),
                'margin_mode': account.get('marginMode', 'crossed')
            })
        return balances

    async def get_account(self, symbol: str) -> Dict:
        """Информация об аккаунте для конкретного символа."""
        endpoint = '/api/v2/mix/account/account'
        params = {'productType': self.product_type, 'symbol': symbol.upper(), 'marginCoin': self.margin_coin}
        data = await self._request('GET', endpoint, params=params, signed=True)
        return {
            'margin_coin': data.get('marginCoin'),
            'available': float(data.get('available', 0)),
            'locked': float(data.get('locked', 0)),
            'equity': float(data.get('accountEquity', 0)),
            'unrealized_pnl': float(data.get('unrealizedPL', 0)),
            'crossed_risk_rate': float(data.get('crossedRiskRate', 0)),
            'margin_mode': data.get('marginMode', 'crossed'),
            'pos_mode': data.get('posMode', 'one_way_mode'),
            'leverage': int(data.get('crossedMarginLeverage', 10))
        }

    async def get_subaccount_assets(self, product_type: str = None) -> List[Dict]:
        """Активы всех субаккаунтов (фьючерсы)."""
        endpoint = '/api/v2/mix/account/sub-account-assets'
        params = {'productType': product_type or self.product_type}
        return await self._request('GET', endpoint, params=params, signed=True)

    async def get_max_openable(self, symbol: str, pos_side: str, order_type: str,
                               open_price: float = None) -> Dict:
        endpoint = '/api/v2/mix/account/max-open'
        params = {
            'productType': self.product_type,
            'symbol': symbol.upper(),
            'marginCoin': self.margin_coin,
            'posSide': pos_side,
            'orderType': order_type
        }
        if open_price and order_type == 'limit':
            params['openPrice'] = str(open_price)
        data = await self._request('GET', endpoint, params=params, signed=True)
        return {'max_open': float(data.get('maxOpen', 0))}

    async def get_liquidation_price(self, symbol: str, pos_side: str, order_type: str,
                                    open_amount: float, open_price: float = None) -> Dict:
        endpoint = '/api/v2/mix/account/liq-price'
        params = {
            'productType': self.product_type,
            'symbol': symbol.upper(),
            'marginCoin': self.margin_coin,
            'posSide': pos_side,
            'orderType': order_type,
            'openAmount': str(open_amount)
        }
        if open_price and order_type == 'limit':
            params['openPrice'] = str(open_price)
        data = await self._request('GET', endpoint, params=params, signed=True)
        return {'liquidation_price': float(data.get('liqPrice', 0))}

    async def get_estimated_open_count(self, symbol: str, open_amount: float,
                                       open_price: float, leverage: int = 20) -> Dict:
        endpoint = '/api/v2/mix/account/open-count'
        params = {
            'productType': self.product_type,
            'symbol': symbol.upper(),
            'marginCoin': self.margin_coin,
            'openAmount': str(open_amount),
            'openPrice': str(open_price),
            'leverage': str(leverage)
        }
        data = await self._request('GET', endpoint, params=params, signed=True)
        return {'size': float(data.get('size', 0))}

    # ========== Управление плечом и режимом маржи ==========
    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'crossed',
                           hold_side: str = None) -> Dict:
        endpoint = '/api/v2/mix/account/set-leverage'
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginCoin': self.margin_coin,
            'marginMode': margin_mode
        }
        if margin_mode == 'isolated' and hold_side:
            body['holdSide'] = hold_side
            body['leverage'] = str(leverage)
        else:
            body['leverage'] = str(leverage)
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {
            'symbol': data.get('symbol'),
            'margin_coin': data.get('marginCoin'),
            'long_leverage': int(data.get('longLeverage', leverage)),
            'short_leverage': int(data.get('shortLeverage', leverage)),
            'cross_leverage': int(data.get('crossMarginLeverage', leverage)),
            'margin_mode': data.get('marginMode')
        }

    async def set_all_leverage(self, leverage: int) -> bool:
        endpoint = '/api/v2/mix/account/set-all-leverage'
        body = {'productType': self.product_type, 'leverage': str(leverage)}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data == 'success'

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Dict:
        endpoint = '/api/v2/mix/account/set-margin-mode'
        body = {'symbol': symbol.upper(), 'productType': self.product_type, 'marginCoin': self.margin_coin, 'marginMode': margin_mode}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {
            'symbol': data.get('symbol'),
            'margin_coin': data.get('marginCoin'),
            'margin_mode': data.get('marginMode')
        }

    async def set_position_mode(self, pos_mode: str) -> Dict:
        endpoint = '/api/v2/mix/account/set-position-mode'
        body = {'productType': self.product_type, 'posMode': pos_mode}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'pos_mode': data.get('posMode')}

    async def set_asset_mode(self, asset_mode: str) -> bool:
        """Установить режим активов: 'single' или 'union' (только для USDT-FUTURES)."""
        endpoint = '/api/v2/mix/account/set-asset-mode'
        body = {'productType': self.product_type, 'assetMode': asset_mode}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data == 'success'

    # ========== Маржинальные операции ==========
    async def add_margin(self, symbol: str, amount: float, hold_side: str) -> Dict:
        endpoint = '/api/v2/mix/account/set-margin'
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginCoin': self.margin_coin,
            'holdSide': hold_side,
            'amount': str(amount)
        }
        await self._request('POST', endpoint, data=body, signed=True)
        return {'symbol': symbol, 'increase': amount, 'hold_side': hold_side}

    async def reduce_margin(self, symbol: str, amount: float, hold_side: str) -> Dict:
        endpoint = '/api/v2/mix/account/set-margin'
        body = {
            'symbol': symbol.upper(),
            'productType': self.product_type,
            'marginCoin': self.margin_coin,
            'holdSide': hold_side,
            'amount': f"-{amount}"
        }
        await self._request('POST', endpoint, data=body, signed=True)
        return {'symbol': symbol, 'decrease': amount, 'hold_side': hold_side}

    async def set_auto_margin(self, symbol: str, hold_side: str, auto_margin: bool) -> Dict:
        endpoint = '/api/v2/mix/account/set-auto-margin'
        body = {
            'symbol': symbol.upper(),
            'marginCoin': self.margin_coin,
            'holdSide': hold_side,
            'autoMargin': 'on' if auto_margin else 'off'
        }
        await self._request('POST', endpoint, data=body, signed=True)
        return {'symbol': symbol, 'auto_margin': auto_margin, 'hold_side': hold_side}

    async def get_isolated_symbols(self) -> List[str]:
        endpoint = '/api/v2/mix/account/isolated-symbols'
        params = {'productType': self.product_type}
        data = await self._request('GET', endpoint, params=params, signed=True)
        return [item['symbol'] for item in data]

    # ========== История счетов и переводы ==========
    async def get_account_bills(self, symbol: str = None, start_time: int = None,
                                end_time: int = None, limit: int = 20) -> List[Dict]:
        endpoint = '/api/v2/mix/account/bill'
        params = {'productType': self.product_type, 'limit': min(limit, 100)}
        if symbol:
            params['symbol'] = symbol.upper()
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data.get('bills', [])

    async def get_interest_history(self, coin: str = None, product_type: str = None,
                                   start_time: int = None, end_time: int = None,
                                   limit: int = 20, id_less_than: str = None) -> Dict:
        endpoint = '/api/v2/mix/account/interest-history'
        params = {'productType': product_type or self.product_type, 'limit': min(limit, 100)}
        if coin:
            params['coin'] = coin.upper()
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        try:
            return await self._request('GET', endpoint, params=params, signed=True)
        except APIError as e:
            # Для демо-режима или если данные недоступны, возвращаем пустой словарь
            if e.code in ('400172', '40847', '40404', '400'):
                logger.warning(f"get_interest_history not available: {e}")
                return {'interestList': [], 'nextSettleTime': '', 'borrowAmount': '', 'borrowLimit': '', 'endId': ''}
            raise

    async def union_convert(self, coin: str, amount: str) -> Dict:
        """Конвертация монеты в USDT в режиме union margin."""
        endpoint = '/api/v2/mix/account/union-convert'
        body = {'coin': coin.upper(), 'amount': str(amount)}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'usdt_amount': float(data.get('usdtAmount', 0))}

    async def get_union_transfer_limits(self, coin: str) -> Dict:
        endpoint = '/api/v2/mix/account/transfer-limits'
        params = {'coin': coin.upper()}
        return await self._request('GET', endpoint, params=params, signed=True)

    async def get_union_config(self) -> Dict:
        endpoint = '/api/v2/mix/account/union-config'
        return await self._request('GET', endpoint, signed=True)

    async def get_switch_union_usdt(self) -> Dict:
        endpoint = '/api/v2/mix/account/switch-union-usdt'
        try:
            return await self._request('GET', endpoint, signed=True)
        except APIError as e:
            # Если режим не union, возвращаем 0
            if e.code in ('40847', '40404', '400'):
                logger.warning(f"get_switch_union_usdt not available: {e}")
                return {'usdtAmount': '0'}
            raise