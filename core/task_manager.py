# core/task_manager.py
import asyncio
import json
import logging
import os
import traceback
from typing import Dict, List, Optional, Any
from contextlib import suppress

from core.config_storage import ConfigStorage
from core.models import Bot, Connector
from core.bot_worker import run_bot_task
from core.emulated_connector import EmulatedConnector
from core.market_data_provider_factory import MarketDataProviderFactory
from connectors import get_connector_class

logger = logging.getLogger(__name__)


class TaskManager:
    def __init__(self, db: ConfigStorage):
        self.db = db
        self._tasks: Dict[int, asyncio.Task] = {}
        self._bot_cancel_events: Dict[int, asyncio.Event] = {}
        self._bot_instances: Dict[int, Any] = {}
        self._connector_pool: Dict[str, Any] = {}
        self._connector_refcnt: Dict[str, int] = {}
        self._connector_logged_online: Dict[str, bool] = {}
        self._shutdown_event = asyncio.Event()
        self._lock = asyncio.Lock()
        self._bot_statuses: Dict[int, Dict] = {}
        self._connector_create_locks: Dict[str, asyncio.Lock] = {}
        self._connector_created_by_admin: Dict[str, bool] = {}
        self._health_check_task: Optional[asyncio.Task] = None
        self._global_connector_lock = asyncio.Lock()
        
        # Лимит на количество одновременно работающих ботов
        self._max_concurrent_bots = int(os.getenv('MAX_CONCURRENT_BOTS', '50'))
        self._bot_semaphore = asyncio.Semaphore(self._max_concurrent_bots)

    async def init(self):
        connectors = await self.db.get_connectors_list()
        async with self._lock:
            for conn in connectors:
                self._connector_pool[conn.name] = None
                self._connector_refcnt[conn.name] = 0
                self._connector_logged_online[conn.name] = False
                self._connector_created_by_admin[conn.name] = False
                self._connector_create_locks[conn.name] = asyncio.Lock()
        logger.info("TaskManager initialized with %d connector stubs", len(self._connector_pool))
        self._health_check_task = asyncio.create_task(self._health_check_loop())

    async def shutdown(self):
        logger.info("Shutting down TaskManager...")
        self._shutdown_event.set()
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        for bot_id, task in list(self._tasks.items()):
            await self.stop_bot(bot_id)
        async with self._lock:
            for name, connector in list(self._connector_pool.items()):
                if connector is not None:
                    with suppress(Exception):
                        await connector.disconnect()
                    self._connector_pool[name] = None
                    self._connector_refcnt[name] = 0
        logger.info("TaskManager shutdown complete")

    async def log(self, level: str, category: str, message: str):
        try:
            await self.db.add_log(level, category, message)
        except Exception as e:
            logger.error(f"Failed to write log to DB: {e}")

    # ---------- Управление коннекторами ----------
    async def create_connector_instance(self, name: str, skip_refcnt: bool = False) -> Optional[Any]:
        async with self._global_connector_lock:
            if name in self._connector_pool and self._connector_pool[name] is not None:
                return self._connector_pool[name]
            
            conn_data = await self.db.get_connector(name)
            if not conn_data:
                logger.error(f"Connector {name} not found in DB")
                return None
            
            connector_class = get_connector_class(conn_data.exchange_id, conn_data.product_type)
            if not connector_class:
                logger.error(f"Connector class not found for {conn_data.exchange_id}/{conn_data.product_type}")
                return None
            
            config = {
                'exchange': conn_data.exchange_id,
                'demo': conn_data.testnet,
                'api_key': conn_data.api_key,
                'api_secret': conn_data.api_secret,
                'api_passphrase': conn_data.api_passphrase,
                'product_type': conn_data.product_type,
                'margin_coin': 'USDT',
                'max_retries': getattr(conn_data, 'max_retries', 3),
                'retry_backoff': getattr(conn_data, 'retry_backoff', 2.0),
                'ws_ping_interval': getattr(conn_data, 'ws_ping_interval', 30),
                'ws_reconnect_delay': getattr(conn_data, 'ws_reconnect_delay', 5),
                'ip_whitelist': getattr(conn_data, 'ip_whitelist', ''),
                'auto_reconnect': getattr(conn_data, 'auto_reconnect', True),
                'retry_on_limit': getattr(conn_data, 'retry_on_limit', True),
                'http_timeout_read': getattr(conn_data, 'http_timeout_read', 10),
                'http_timeout_connect': getattr(conn_data, 'http_timeout_connect', 5),
                'order_type_default': getattr(conn_data, 'order_type_default', 'limit')
            }
            connector = connector_class(name, config)
            try:
                connected = await connector.connect()
                if not connected:
                    await self.log("ERROR", "connector", f"Коннектор '{name}' не смог подключиться")
                    return None
            except Exception as e:
                await self.log("ERROR", "connector", f"Ошибка подключения коннектора '{name}': {e}")
                logger.error(f"Connector {name} connection error: {e}")
                return None
            
            async with self._lock:
                self._connector_pool[name] = connector
                if not skip_refcnt:
                    self._connector_refcnt[name] = 0
                if not self._connector_logged_online.get(name, False):
                    await self.log("INFO", "connector", f"Коннектор '{name}' успешно подключён")
                    self._connector_logged_online[name] = True
                logger.info(f"Connector {name} created and connected, refcnt={self._connector_refcnt.get(name, 0)}")
                return connector

    async def _get_or_create_connector(self, name: str, increase_refcnt: bool = True) -> Optional[Any]:
        connector = await self.create_connector_instance(name, skip_refcnt=not increase_refcnt)
        if connector and increase_refcnt:
            async with self._lock:
                self._connector_refcnt[name] = self._connector_refcnt.get(name, 0) + 1
        return connector

    async def release_connector(self, name: str):
        async with self._lock:
            if name not in self._connector_refcnt:
                return
            old_cnt = self._connector_refcnt[name]
            self._connector_refcnt[name] = max(0, old_cnt - 1)
            logger.debug(f"Released connector {name}, refcnt={self._connector_refcnt[name]}")
            if self._connector_refcnt[name] <= 0:
                connector = self._connector_pool.get(name)
                if connector:
                    with suppress(Exception):
                        await connector.disconnect()
                    self._connector_pool[name] = None
                    self._connector_logged_online[name] = False
                    self._connector_created_by_admin[name] = False
                    await self.log("INFO", "connector", f"Коннектор '{name}' отключён (не используется)")
                    logger.info(f"Connector {name} disconnected and removed from pool")

    async def reconnect_connector(self, name: str) -> bool:
        async with self._lock:
            old_conn = self._connector_pool.get(name)
            if old_conn:
                with suppress(Exception):
                    await old_conn.disconnect()
                self._connector_pool[name] = None
                self._connector_logged_online[name] = False
        new_conn = await self.create_connector_instance(name, skip_refcnt=False)
        if new_conn:
            async with self._lock:
                self._connector_pool[name] = new_conn
                self._connector_logged_online[name] = True
            await self.log("INFO", "connector", f"Коннектор '{name}' переподключён")
            return True
        else:
            await self.log("ERROR", "connector", f"Не удалось переподключить коннектор '{name}'")
            return False

    async def update_connector(self, name: str, new_config: Dict[str, Any]) -> bool:
        async with self._lock:
            refcnt = self._connector_refcnt.get(name, 0)
            if refcnt > 0:
                await self.log("WARNING", "connector", 
                               f"Коннектор '{name}' используется {refcnt} ботами. Обновление настроек временно недоступно.")
                return False
        
        conn = await self.db.get_connector(name)
        if not conn:
            return False
        for key, value in new_config.items():
            if hasattr(conn, key):
                setattr(conn, key, value)
        await self.db.save_connector(conn)
        return await self.reconnect_connector(name)

    async def get_connector_status(self, name: str) -> str:
        async with self._lock:
            if self._connector_pool.get(name) is not None:
                return 'online'
        return 'offline'

    async def remove_connector(self, name: str) -> bool:
        async with self._lock:
            refcnt = self._connector_refcnt.get(name, 0)
            if refcnt > 0:
                logger.warning(f"Connector {name} is in use (refcnt={refcnt}), cannot remove")
                return False
            connector = self._connector_pool.get(name)
            if connector:
                with suppress(Exception):
                    await connector.disconnect()
            self._connector_pool.pop(name, None)
            self._connector_refcnt.pop(name, None)
            self._connector_logged_online.pop(name, None)
            self._connector_created_by_admin.pop(name, None)
            self._connector_create_locks.pop(name, None)
            return True

    # ---------- Фоновый мониторинг ----------
    async def _health_check_loop(self):
        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(30)
                async with self._lock:
                    names = list(self._connector_pool.keys())
                for name in names:
                    connector = self._connector_pool.get(name)
                    if connector is None:
                        continue
                    try:
                        is_online = await connector.check_connection()
                        async with self._lock:
                            if is_online:
                                if not self._connector_logged_online.get(name, False):
                                    await self.log("INFO", "connector", f"Коннектор '{name}' восстановил соединение")
                                    self._connector_logged_online[name] = True
                            else:
                                if self._connector_logged_online.get(name, False):
                                    await self.log("WARNING", "connector", f"Коннектор '{name}' потерял соединение")
                                    self._connector_logged_online[name] = False
                    except Exception as e:
                        logger.warning(f"Health check failed for {name}: {e}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Health check loop error: {e}")

    # ---------- Боты ----------
    async def create_bot(
        self,
        bot_id: int,
        name: str,
        bot_full_path: str,
        connector_name: str,
        symbol: str,
        timeframe: str,
        position_size: float,
        params: dict,
        emulator_enabled: bool,
        market_data_source: str = "websocket",
        market_data_source_config: str = ""
    ) -> bool:
        async with self._lock:
            current_bots = len(self._tasks)
            if current_bots >= self._max_concurrent_bots:
                logger.error(f"Cannot start bot {name}: max concurrent bots limit {self._max_concurrent_bots} reached")
                await self.log("ERROR", "bot", f"Не удалось запустить бота {name}: превышен лимит одновременно работающих ботов ({self._max_concurrent_bots})")
                return False

        async with self._lock:
            if bot_id in self._tasks:
                logger.warning(f"Bot {bot_id} already running")
                return False
        
        await self._bot_semaphore.acquire()
        
        real_connector = None
        connector = None
        market_data = None
        try:
            real_connector = await self._get_or_create_connector(connector_name, increase_refcnt=True)
            if real_connector is None:
                logger.error(f"Cannot create/acquire real connector {connector_name}")
                return False
            
            if emulator_enabled:
                initial_balance = params.get('initial_balance', 10000.0)
                connector = EmulatedConnector(real_connector, initial_balance_usdt=initial_balance)
                logger.info(f"Bot {name} will use emulated connector (real: {connector_name})")
            else:
                connector = real_connector
                logger.info(f"Bot {name} will use real connector {connector_name}")
            
            try:
                market_data = MarketDataProviderFactory.create(
                    provider_type=market_data_source,
                    connector=connector,
                    symbol=symbol,
                    db=self.db if market_data_source == "database" else None,
                    config_json=market_data_source_config
                )
            except Exception as e:
                logger.error(f"Failed to create market data provider for bot {name}: {e}")
                await self.log("ERROR", "bot", f"Не удалось создать провайдер данных для бота {name}: {e}")
                raise
            
            bot_config = {
                'symbol': symbol,
                'timeframe': timeframe,
                'position_size': position_size,
                'emulator_enabled': emulator_enabled,
                'connector_name': connector_name,
                'market_data_source': market_data_source,
                'market_data_source_config': market_data_source_config,
                **params
            }
            cancel_event = asyncio.Event()
            bot_instance_holder = {"instance": None}

            def on_status(bot_id: int, status: Dict):
                asyncio.create_task(self._update_bot_status(bot_id, status))

            # ИСПРАВЛЕНИЕ: передаём task_manager=self в run_bot_task
            async def run_with_instance_capture():
                await run_bot_task(
                    bot_id, name, connector, bot_full_path, bot_config,
                    cancel_event, self.db, on_status, instance_holder=bot_instance_holder,
                    task_manager=self   # <--- добавлено
                )

            task = asyncio.create_task(run_with_instance_capture(), name=f"Bot-{bot_id}")
            def task_done_callback(t: asyncio.Task):
                self._bot_semaphore.release()
                if t.cancelled():
                    pass
                elif t.exception():
                    logger.error(f"Bot {bot_id} task failed: {t.exception()}")
            task.add_done_callback(task_done_callback)
            
            async with self._lock:
                self._tasks[bot_id] = task
                self._bot_cancel_events[bot_id] = cancel_event
                self._bot_statuses[bot_id] = {'running': True}
                self._bot_instances[bot_id] = {
                    'instance': None,
                    'emulator_enabled': emulator_enabled,
                    'real_connector_name': connector_name
                }

            async def wait_for_instance():
                while not self._shutdown_event.is_set():
                    if bot_instance_holder["instance"] is not None:
                        async with self._lock:
                            self._bot_instances[bot_id]['instance'] = bot_instance_holder["instance"]
                        break
                    await asyncio.sleep(0.1)
            asyncio.create_task(wait_for_instance())
            logger.info(f"Bot {name} (id={bot_id}) started as asyncio task")
            return True
        
        except Exception as e:
            logger.error(f"Failed to create bot {name}: {e}", exc_info=True)
            self._bot_semaphore.release()
            if real_connector is not None:
                await self.release_connector(connector_name)
            return False

    async def stop_bot(self, bot_id: int) -> bool:
        async with self._lock:
            cancel_event = self._bot_cancel_events.get(bot_id)
            task = self._tasks.get(bot_id)
            if not cancel_event or not task:
                return False
            bot_info = self._bot_instances.get(bot_id, {})
            emulator_enabled = bot_info.get('emulator_enabled', False)
            real_connector_name = bot_info.get('real_connector_name')
            cancel_event.set()
        
        try:
            await asyncio.wait_for(task, timeout=15.0)
        except asyncio.TimeoutError:
            logger.warning(f"Bot {bot_id} did not stop gracefully, cancelling task")
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        except Exception as e:
            logger.error(f"Error stopping bot {bot_id}: {e}")
        
        async with self._lock:
            self._tasks.pop(bot_id, None)
            self._bot_cancel_events.pop(bot_id, None)
            self._bot_statuses.pop(bot_id, None)
            self._bot_instances.pop(bot_id, None)
            
            if emulator_enabled and real_connector_name:
                await self.release_connector(real_connector_name)
            elif not emulator_enabled:
                bot = await self.db.get_bot(bot_id)
                if bot:
                    await self.release_connector(bot.connector)
            logger.info(f"Bot {bot_id} stopped")
            return True

    async def delete_bot(self, bot_id: int):
        await self.stop_bot(bot_id)
        await self.db.delete_bot(bot_id)

    async def get_bots_list(self) -> List[Dict]:
        bots = await self.db.get_bots()
        result = []
        async with self._lock:
            running_ids = set(self._tasks.keys())
            for bot in bots:
                result.append({
                    'id': bot.id, 'name': bot.name, 'strategy': bot.strategy,
                    'connector': bot.connector, 'symbol': bot.symbol,
                    'running': bot.id in running_ids, 'enabled': bot.enabled,
                    'emulator_enabled': bot.emulator_enabled,
                    'position_size': bot.position_size, 'timeframe': bot.timeframe,
                    'params': bot.params,
                })
        return result

    async def get_bot_status(self, bot_id: int) -> Dict:
        async with self._lock:
            return self._bot_statuses.get(bot_id, {'running': False, 'bot_id': bot_id}).copy()

    async def _update_bot_status(self, bot_id: int, status: Dict):
        async with self._lock:
            self._bot_statuses[bot_id] = status

    # ==================== МЕТОДЫ ДЛЯ ГРАФИКА ====================
    async def get_bot_market_data_source(self, bot_id: int) -> tuple[str, str]:
        bot = await self.db.get_bot(bot_id)
        if not bot:
            return 'websocket', ''
        return getattr(bot, 'market_data_source', 'websocket'), getattr(bot, 'market_data_source_config', '')

    async def get_candles_with_source(
        self,
        connector_name: str,
        symbol: str,
        timeframe: str,
        limit: int,
        start_time: int,
        end_time: int,
        market_data_source: str = 'websocket',
        market_data_source_config: str = ''
    ) -> List[Dict]:
        connector = await self._get_or_create_connector(connector_name, increase_refcnt=False)
        if not connector:
            return []
        
        from core.market_data_provider_factory import MarketDataProviderFactory
        from core.market_data_provider import Interval
        try:
            provider = MarketDataProviderFactory.create(
                provider_type=market_data_source,
                connector=connector,
                symbol=symbol,
                db=self.db if market_data_source == 'database' else None,
                config_json=market_data_source_config
            )
        except Exception as e:
            logger.error(f"Failed to create market data provider for source {market_data_source}: {e}")
            return []
        
        candles = await provider.get_candles(symbol, Interval(timeframe), limit, start_time, end_time)
        return [c.to_dict() for c in candles]

    async def get_candles(self, connector_name: str, symbol: str, timeframe: str,
                          limit: int, start_time: int, end_time: int) -> List[Dict]:
        return await self.get_candles_with_source(
            connector_name, symbol, timeframe, limit, start_time, end_time,
            market_data_source='websocket', market_data_source_config=''
        )

    # ---------- Прямые вызовы коннекторов ----------
    async def get_ticker(self, connector_name: str, symbol: str) -> Dict:
        connector = await self._get_or_create_connector(connector_name, increase_refcnt=False)
        return await connector.get_ticker(symbol) if connector else {}

    async def get_symbols(self, connector_name: str, product_type: str) -> List[str]:
        connector = await self._get_or_create_connector(connector_name, increase_refcnt=False)
        if not connector: return []
        markets = await connector.get_markets()
        if product_type == "USDT-FUTURES":
            return [s for s in markets if s.endswith('USDT')]
        return markets

    async def get_order_book(self, connector_name: str, symbol: str, depth: int) -> Dict:
        connector = await self._get_or_create_connector(connector_name, increase_refcnt=False)
        return await connector.get_order_book(symbol, depth) if connector else {}

    async def set_leverage(self, connector_name: str, symbol: str, leverage: int, margin_mode: str):
        connector = await self._get_or_create_connector(connector_name, increase_refcnt=False)
        if connector: await connector.set_leverage(symbol, leverage, margin_mode)

    async def set_tpsl(self, connector_name: str, symbol: str, hold_side: str,
                       trigger_price: float, execute_price: float, tpsl_type: str, size: float):
        connector = await self._get_or_create_connector(connector_name, increase_refcnt=False)
        if connector: await connector.set_tpsl(symbol, hold_side, trigger_price, execute_price, tpsl_type, size)

    async def close_position(self, connector_name: str, symbol: str, hold_side: str):
        connector = await self._get_or_create_connector(connector_name, increase_refcnt=False)
        if connector: await connector.close_position(symbol, hold_side)

    async def get_position(self, connector_name: str, symbol: str) -> List[Dict]:
        connector = await self._get_or_create_connector(connector_name, increase_refcnt=False)
        return await connector.get_positions(symbol) if connector else []

    # ==================== МЕТОДЫ ДЛЯ РУЧНОГО УПРАВЛЕНИЯ ====================
    async def call_bot_method(self, bot_id: int, method_name: str, params: Dict) -> Any:
        bot_info = self._bot_instances.get(bot_id)
        if not bot_info or not bot_info.get('instance'):
            raise Exception(f"Bot {bot_id} not running")
        bot = bot_info['instance']
        method = getattr(bot, method_name, None)
        if not method:
            raise Exception(f"Method {method_name} not found in bot {bot_id}")
        if asyncio.iscoroutinefunction(method):
            return await method(**params)
        else:
            return method(**params)

    async def get_bot_strategy_description(self, bot_id: int) -> Dict:
        bot_info = self._bot_instances.get(bot_id)
        if not bot_info or not bot_info.get('instance'):
            return {}
        bot = bot_info['instance']
        if hasattr(bot, 'get_strategy_description'):
            return bot.get_strategy_description()
        return {"type": "unknown", "can_visualize": False}