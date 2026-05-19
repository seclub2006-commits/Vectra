# connectors/bitget/common.py
import asyncio
import time
import json
import socket
import logging
from typing import Dict, List, Optional, Any, Callable
from collections import deque

import aiohttp
from aiohttp.resolver import ThreadedResolver

from connectors.base.exchange_connector import ExchangeConnector
from connectors.bitget.signature import generate_sign, sort_query_string
from connectors.base.exceptions import APIError, NetworkError

logger = logging.getLogger(__name__)


class BitgetBaseConnector(ExchangeConnector):
    """
    Базовый класс для коннекторов Bitget.
    Автоматически синхронизирует время с сервером.
    """

    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.api_key = config.get('api_key', '')
        self.api_secret = config.get('api_secret', '')
        self.api_passphrase = config.get('api_passphrase', '')
        self.demo = config.get('demo', False)
        self.product_type = config.get('product_type', 'USDT-FUTURES')
        self.ip_whitelist = config.get('ip_whitelist', '')
        self.max_retries = config.get('max_retries', 2)
        self.retry_backoff = config.get('retry_backoff', 1.0)
        self.ws_ping_interval = config.get('ws_ping_interval', 30)
        self.ws_reconnect_delay = config.get('ws_reconnect_delay', 5)

        self._session: Optional[aiohttp.ClientSession] = None
        self._request_semaphore = asyncio.Semaphore(20)
        self._last_request_time = 0
        self._min_request_interval = 0.05

        self.rest_url = 'https://api.bitget.com'

        # Синхронизация времени
        self._time_offset = 0.0
        self._server_time_fetched = False
        self._sync_lock = asyncio.Lock()

        # Улучшенное логирование состояния
        self._last_data_time = 0.0
        self._health_check_failures = 0
        self._health_check_successes = 0
        self._health_history = deque(maxlen=5)

    # ==================== СИНХРОНИЗАЦИЯ ВРЕМЕНИ ====================

    async def _get_server_time_offset(self) -> float:
        async with self._sync_lock:
            if self._server_time_fetched:
                return self._time_offset
            endpoint = '/api/v2/public/time'
            connector = aiohttp.TCPConnector(
                family=socket.AF_INET,
                resolver=ThreadedResolver(),
                force_close=True,
                enable_cleanup_closed=True,
                ttl_dns_cache=300,
            )
            timeout = aiohttp.ClientTimeout(total=5)
            try:
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.get(f"{self.rest_url}{endpoint}") as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            server_ms = int(data['data']['serverTime'])
                            local_ms = int(time.time() * 1000)
                            self._time_offset = (server_ms - local_ms) / 1000.0
                            self._server_time_fetched = True
                            logger.info(f"Time synchronized: offset = {self._time_offset:.3f} sec")
                            return self._time_offset
            except Exception as e:
                logger.warning(f"Failed to fetch server time: {e}")
            return 0.0

    def _get_timestamp_ms(self) -> str:
        local_ms = int(time.time() * 1000)
        if self._server_time_fetched:
            adjusted_ms = int(local_ms + self._time_offset * 1000)
            return str(adjusted_ms)
        return str(local_ms)

    # ==================== УПРАВЛЕНИЕ HTTP-СЕССИЕЙ ====================

    async def _ensure_session(self):
        if self._session is None or self._session.closed:
            connector = aiohttp.TCPConnector(
                family=socket.AF_INET,
                resolver=ThreadedResolver(),
                force_close=True,
                enable_cleanup_closed=True,
                ttl_dns_cache=300,
            )
            timeout = aiohttp.ClientTimeout(total=30, connect=15, sock_read=15)
            self._session = aiohttp.ClientSession(
                connector=connector,
                timeout=timeout,
                trust_env=True
            )
            logger.debug("HTTP session created with ThreadedResolver (synchronous DNS)")

    async def disconnect(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
        self.status = 'offline'

    # ==================== УЛУЧШЕННАЯ ПРОВЕРКА СОЕДИНЕНИЯ ====================
    async def check_connection(self) -> bool:
        try:
            await asyncio.wait_for(self.get_server_time(), timeout=5.0)
            self._health_check_failures = 0
            self._health_history.append(True)
            self.update_last_data_time()
            if sum(self._health_history) >= 3:
                return True
            return sum(self._health_history) > len(self._health_history) / 2
        except Exception as e:
            self._health_history.append(False)
            self._health_check_failures += 1
            logger.debug(f"Health check failed for {self.name}: {e}")
            if len(self._health_history) >= 5:
                return sum(self._health_history) >= 2
            return self._health_check_failures < 3

    def update_last_data_time(self):
        self._last_data_time = time.time()

    # ==================== БАЗОВЫЙ МЕТОД ЗАПРОСА (ИСПРАВЛЕН) ====================

    async def _request(self, method: str, endpoint: str, params: dict = None,
                       data: dict = None, signed: bool = True, retries: int = None) -> dict:
        now = time.time()
        elapsed = now - self._last_request_time
        if elapsed < self._min_request_interval:
            await asyncio.sleep(self._min_request_interval - elapsed)
        self._last_request_time = time.time()

        async with self._request_semaphore:
            await self._ensure_session()

            url = f"{self.rest_url}{endpoint}"
            headers = {
                'Content-Type': 'application/json',
                'locale': 'en-US'
            }

            # Для GET формируем query_string
            query_string = ''
            if params and method == 'GET':
                query_string = sort_query_string(params)
                full_url = f"{url}?{query_string}" if query_string else url
            else:
                full_url = url

            body_str = ''
            if data and method in ('POST', 'PUT'):
                body_str = json.dumps(data)

            max_attempts = retries if retries is not None else self.max_retries
            last_exception = None

            # Исправление: цикл повторных попыток, внутри которого получаем timestamp и генерируем подпись
            for attempt in range(max_attempts):
                # Получаем актуальный timestamp перед каждой попыткой
                timestamp = self._get_timestamp_ms()
                if signed:
                    sign = generate_sign(
                        self.api_secret, timestamp, method, endpoint,
                        query_string, body_str
                    )
                    headers.update({
                        'ACCESS-KEY': self.api_key,
                        'ACCESS-SIGN': sign,
                        'ACCESS-PASSPHRASE': self.api_passphrase,
                        'ACCESS-TIMESTAMP': timestamp,
                    })

                if self.demo:
                    headers['paptrading'] = '1'

                try:
                    async with self._session.request(
                        method, full_url, headers=headers,
                        params=None,
                        json=data if method in ('POST', 'PUT') else None
                    ) as resp:
                        if resp.status == 429:
                            delay = self.retry_backoff ** attempt
                            logger.warning(f"Rate limit 429, retrying in {delay}s")
                            await asyncio.sleep(delay)
                            continue
                        if resp.status != 200:
                            text = await resp.text()
                            raise APIError(str(resp.status), f"HTTP {resp.status}: {text}")

                        result = await resp.json()
                        code = result.get('code')
                        if code == '00000':
                            self.update_last_data_time()
                            return result.get('data', {}) if result.get('data') is not None else {}
                        
                        # Обработка ошибки истечения времени запроса
                        if code == '40008':
                            logger.warning("Request timestamp expired, resynchronizing time...")
                            await self._get_server_time_offset()
                            # Небольшая задержка перед повторной попыткой
                            await asyncio.sleep(0.1)
                            continue  # <-- ИСПРАВЛЕНИЕ: продолжаем цикл с новым timestamp
                        
                        if code == '429':
                            delay = self.retry_backoff ** attempt
                            logger.warning(f"API rate limit {code}, retrying in {delay}s")
                            await asyncio.sleep(delay)
                            continue
                        
                        # Любая другая ошибка API – не повторяем, выбрасываем сразу
                        raise APIError(code, result.get('msg', 'Unknown error'))

                except APIError as e:
                    # Ошибки API, кроме 40008 и 429, не повторяем
                    if e.code in ('40008', '429'):
                        last_exception = e
                        if attempt == max_attempts - 1:
                            raise
                        delay = self.retry_backoff ** attempt
                        logger.warning(f"API error {e.code}, retrying in {delay}s")
                        await asyncio.sleep(delay)
                        continue
                    else:
                        # Не повторяем ошибки авторизации, неверных параметров и т.д.
                        raise
                except Exception as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        raise NetworkError(f"Request failed: {e}")
                    logger.warning(f"Request error: {e}, retrying...")
                    await asyncio.sleep(self.retry_backoff ** attempt)

            if last_exception:
                raise last_exception
            return {}

    # ==================== ОБЩИЕ ПУБЛИЧНЫЕ МЕТОДЫ ====================

    async def get_server_time(self) -> int:
        endpoint = '/api/v2/public/time'
        data = await self._request('GET', endpoint, signed=False)
        return int(data.get('serverTime', 0))

    async def get_interest_rate_history(self, coin: str) -> Dict:
        endpoint = '/api/v2/mix/market/union-interest-rate-history'
        params = {'coin': coin.upper()}
        return await self._request('GET', endpoint, params=params, signed=False)

    # Абстрактные методы – будут реализованы в наследниках
    async def connect(self) -> bool:
        raise NotImplementedError

    async def get_ticker(self, symbol: str) -> Dict:
        raise NotImplementedError

    async def get_tickers(self, product_type: str = None) -> List[Dict]:
        raise NotImplementedError

    async def get_klines(self, symbol: str, interval: str, limit: int = 100,
                         start_time: Optional[int] = None,
                         end_time: Optional[int] = None) -> List[Dict]:
        raise NotImplementedError

    async def get_order_book(self, symbol: str, limit: int = 20, merge_scale: str = 'scale0') -> Dict:
        raise NotImplementedError

    async def get_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        raise NotImplementedError

    async def get_contracts(self, product_type: str, symbol: str = None) -> List[Dict]:
        raise NotImplementedError

    async def create_order(self, symbol: str, side: str, order_type: str,
                           quantity: float, price: Optional[float] = None,
                           reduce_only: bool = False, client_oid: str = None,
                           preset_tp: float = None, preset_sl: float = None,
                           stp_mode: str = 'none') -> Dict:
        raise NotImplementedError

    async def cancel_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        raise NotImplementedError

    async def cancel_all_orders(self, symbol: str = None, product_type: str = None) -> List[Dict]:
        raise NotImplementedError

    async def get_open_orders(self, symbol: str = None, product_type: str = None) -> List[Dict]:
        raise NotImplementedError

    async def get_order(self, symbol: str, order_id: str = None, client_oid: str = None) -> Dict:
        raise NotImplementedError

    async def get_order_history(self, symbol: str = None, product_type: str = None,
                                start_time: int = None, end_time: int = None,
                                limit: int = 100) -> List[Dict]:
        raise NotImplementedError

    async def get_fills(self, symbol: str = None, product_type: str = None,
                        start_time: int = None, end_time: int = None,
                        limit: int = 100) -> List[Dict]:
        raise NotImplementedError

    async def get_balance(self, currency: str = None) -> List[Dict]:
        raise NotImplementedError

    async def get_positions(self, symbol: str = None) -> List[Dict]:
        raise NotImplementedError

    async def set_leverage(self, symbol: str, leverage: int, margin_mode: str = 'crossed',
                           hold_side: str = None) -> Dict:
        raise NotImplementedError

    async def set_margin_mode(self, symbol: str, margin_mode: str) -> Dict:
        raise NotImplementedError

    async def add_margin(self, symbol: str, amount: float, hold_side: str) -> Dict:
        raise NotImplementedError

    async def set_tpsl(self, symbol: str, hold_side: str, trigger_price: float,
                       execute_price: float, tpsl_type: str, size: float = 0) -> Dict:
        raise NotImplementedError

    async def cancel_tpsl(self, symbol: str, order_id: str) -> Dict:
        raise NotImplementedError

    async def close_position(self, symbol: str, hold_side: str = '') -> Dict:
        raise NotImplementedError

    async def get_funding_rate(self, symbol: str) -> Dict:
        raise NotImplementedError

    async def get_funding_history(self, symbol: str, limit: int = 20) -> List[Dict]:
        raise NotImplementedError

    async def subscribe(self, channel: str, symbol: str = None, callback: Callable = None, private: bool = False):
        raise NotImplementedError

    async def unsubscribe_all(self, symbol: str = None):
        raise NotImplementedError