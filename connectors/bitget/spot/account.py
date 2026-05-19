# connectors/bitget/spot/account.py
from typing import Dict, List, Optional

class AccountMixin:
    """Миксин для работы с аккаунтом, балансами, переводами, выводами."""

    # ========== Балансы ==========
    async def get_balance(self, currency: str = None, asset_type: str = 'hold_only') -> List[Dict]:
        """Баланс спотового счёта."""
        endpoint = '/api/v2/spot/account/assets'
        params = {'assetType': asset_type}
        if currency:
            params['coin'] = currency.upper()
        data = await self._request('GET', endpoint, params=params, signed=True)
        balances = []
        for item in data:
            balances.append({
                'currency': item['coin'],
                'available': float(item['available']),
                'frozen': float(item.get('frozen', 0)),
                'locked': float(item.get('locked', 0)),
                'limit_available': float(item.get('limitAvailable', 0)),
                'total': float(item['available']) + float(item.get('frozen', 0)),
                'update_time': int(item.get('uTime', 0))
            })
        return balances

    async def get_account_info(self) -> Dict:
        """Информация об аккаунте (права, рефералы, тип трейдера)."""
        endpoint = '/api/v2/spot/account/info'
        return await self._request('GET', endpoint, signed=True)

    async def get_subaccount_assets(self, id_less_than: str = None, limit: int = 10) -> List[Dict]:
        """Активы субаккаунтов (только с ненулевым балансом)."""
        endpoint = '/api/v2/spot/account/subaccount-assets'
        params = {'limit': min(limit, 50)}
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    async def get_account_bills(self, coin: str = None, group_type: str = None,
                                business_type: str = None, start_time: int = None,
                                end_time: int = None, limit: int = 100,
                                id_less_than: str = None) -> List[Dict]:
        """История счетов (балансовые изменения)."""
        endpoint = '/api/v2/spot/account/bills'
        params = {'limit': min(limit, 500)}
        if coin:
            params['coin'] = coin.upper()
        if group_type:
            params['groupType'] = group_type
        if business_type:
            params['businessType'] = business_type
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    # ========== Переводы ==========
    async def transfer(self, from_type: str, to_type: str, amount: str, coin: str,
                       symbol: str = None, client_oid: str = None) -> Dict:
        """Перевод между счетами (спот, фьючерсы, маржа, P2P)."""
        endpoint = '/api/v2/spot/wallet/transfer'
        body = {
            'fromType': from_type,
            'toType': to_type,
            'amount': str(amount),
            'coin': coin.upper()
        }
        if symbol:
            body['symbol'] = symbol.upper()
        if client_oid:
            body['clientOid'] = client_oid
        return await self._request('POST', endpoint, data=body, signed=True)

    async def get_transferable_coins(self, from_type: str, to_type: str) -> List[str]:
        """Список монет, доступных для перевода между указанными счетами."""
        endpoint = '/api/v2/spot/wallet/transfer-coin-info'
        params = {'fromType': from_type, 'toType': to_type}
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    async def subaccount_transfer(self, from_user_id: str, to_user_id: str,
                                  from_type: str, to_type: str, amount: str, coin: str,
                                  symbol: str = None, client_oid: str = None) -> Dict:
        """Перевод между субаккаунтами или между счетами внутри субаккаунта."""
        endpoint = '/api/v2/spot/wallet/subaccount-transfer'
        body = {
            'fromUserId': from_user_id,
            'toUserId': to_user_id,
            'fromType': from_type,
            'toType': to_type,
            'amount': str(amount),
            'coin': coin.upper()
        }
        if symbol:
            body['symbol'] = symbol.upper()
        if client_oid:
            body['clientOid'] = client_oid
        return await self._request('POST', endpoint, data=body, signed=True)

    async def get_main_sub_transfer_records(self, coin: str = None, role: str = 'initiator',
                                            sub_uid: str = None, start_time: int = None,
                                            end_time: int = None, limit: int = 100,
                                            id_less_than: str = None) -> List[Dict]:
        """История переводов между основным и субаккаунтами."""
        endpoint = '/api/v2/spot/account/sub-main-trans-record'
        params = {'limit': min(limit, 100)}
        if coin:
            params['coin'] = coin.upper()
        if role:
            params['role'] = role
        if sub_uid:
            params['subUid'] = sub_uid
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    async def get_transfer_records(self, coin: str, from_type: str = None,
                                   start_time: int = None, end_time: int = None,
                                   client_oid: str = None, limit: int = 100,
                                   id_less_than: str = None) -> List[Dict]:
        """История переводов между разными типами счетов (спот, фьючерсы, маржа)."""
        endpoint = '/api/v2/spot/account/transferRecords'
        params = {'coin': coin.upper(), 'limit': min(limit, 500)}
        if from_type:
            params['fromType'] = from_type
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if client_oid:
            params['clientOid'] = client_oid
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    # ========== Вывод и депозит ==========
    async def withdraw(self, coin: str, transfer_type: str, address: str, size: str,
                       chain: str = None, inner_to_type: str = 'uid', area_code: str = None,
                       tag: str = None, remark: str = None, client_oid: str = None) -> Dict:
        """Вывод средств (on-chain или внутренний)."""
        endpoint = '/api/v2/spot/wallet/withdrawal'
        body = {
            'coin': coin.upper(),
            'transferType': transfer_type,
            'address': address,
            'size': str(size)
        }
        if chain:
            body['chain'] = chain
        if transfer_type == 'internal_transfer':
            body['innerToType'] = inner_to_type
        if area_code:
            body['areaCode'] = area_code
        if tag:
            body['tag'] = tag
        if remark:
            body['remark'] = remark
        if client_oid:
            body['clientOid'] = client_oid
        data = await self._request('POST', endpoint, data=body, signed=True)
        return {'orderId': data.get('orderId'), 'clientOid': data.get('clientOid')}

    async def cancel_withdrawal(self, order_id: str) -> bool:
        """Отмена вывода (только в статусе pending)."""
        endpoint = '/api/v2/spot/wallet/cancel-withdrawal'
        body = {'orderId': order_id}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data == 'success'

    async def get_deposit_address(self, coin: str, chain: str = None) -> Dict:
        """Адрес для депозита."""
        endpoint = '/api/v2/spot/wallet/deposit-address'
        params = {'coin': coin.upper()}
        if chain:
            params['chain'] = chain
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    async def get_subaccount_deposit_address(self, sub_uid: str, coin: str, chain: str = None) -> Dict:
        """Адрес депозита для субаккаунта."""
        endpoint = '/api/v2/spot/wallet/subaccount-deposit-address'
        params = {'subUid': sub_uid, 'coin': coin.upper()}
        if chain:
            params['chain'] = chain
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    async def get_deposit_records(self, coin: str = None, start_time: int = None,
                                  end_time: int = None, limit: int = 20,
                                  id_less_than: str = None) -> List[Dict]:
        """История депозитов."""
        endpoint = '/api/v2/spot/wallet/deposit-records'
        params = {'limit': min(limit, 100)}
        if coin:
            params['coin'] = coin.upper()
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    async def get_withdrawal_records(self, coin: str = None, start_time: int = None,
                                     end_time: int = None, limit: int = 20,
                                     id_less_than: str = None, client_oid: str = None) -> List[Dict]:
        """История выводов."""
        endpoint = '/api/v2/spot/wallet/withdrawal-records'
        params = {'limit': min(limit, 100)}
        if coin:
            params['coin'] = coin.upper()
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        if client_oid:
            params['clientOid'] = client_oid
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    async def get_subaccount_deposit_records(self, sub_uid: str, coin: str = None,
                                             start_time: int = None, end_time: int = None,
                                             limit: int = 20, id_less_than: str = None) -> List[Dict]:
        """История депозитов субаккаунта."""
        endpoint = '/api/v2/spot/wallet/subaccount-deposit-records'
        params = {'subUid': sub_uid, 'limit': min(limit, 100)}
        if coin:
            params['coin'] = coin.upper()
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
        if id_less_than:
            params['idLessThan'] = id_less_than
        data = await self._request('GET', endpoint, params=params, signed=True)
        return data

    # ========== BGB Deduction ==========
    async def switch_bgb_deduct(self, deduct: bool) -> bool:
        """Включить/отключить оплату комиссий в BGB."""
        endpoint = '/api/v2/spot/account/switch-deduct'
        body = {'deduct': 'on' if deduct else 'off'}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data == True

    async def get_bgb_deduct_info(self) -> str:
        """Текущий статус оплаты комиссий в BGB."""
        endpoint = '/api/v2/spot/account/deduct-info'
        data = await self._request('GET', endpoint, signed=True)
        return data.get('deduct', 'off')

    # ========== Upgrade Account ==========
    async def upgrade_account(self, sub_uid: str = None) -> None:
        """Обновить аккаунт до унифицированного режима."""
        endpoint = '/api/v2/spot/account/upgrade'
        body = {}
        if sub_uid:
            body['subUid'] = sub_uid
        await self._request('POST', endpoint, data=body, signed=True)

    async def get_upgrade_status(self, sub_uid: str = None) -> Dict:
        """Статус обновления аккаунта."""
        endpoint = '/api/v2/spot/account/upgrade-status'
        params = {}
        if sub_uid:
            params['subUid'] = sub_uid
        return await self._request('GET', endpoint, params=params, signed=True)

    # ========== Modify Deposit Account ==========
    async def modify_deposit_account(self, coin: str, account_type: str) -> bool:
        """Изменить тип счёта для автоматического зачисления депозитов."""
        endpoint = '/api/v2/spot/wallet/modify-deposit-account'
        body = {'coin': coin.upper(), 'accountType': account_type}
        data = await self._request('POST', endpoint, data=body, signed=True)
        return data == 'success'