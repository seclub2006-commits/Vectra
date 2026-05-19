# core/server.py
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
import json
import logging
import logging.handlers
import argparse
import grpc
import importlib
import inspect
from pathlib import Path
from dotenv import load_dotenv
import core_pb2
import core_pb2_grpc
from core.database import Database
from core.task_manager import TaskManager
from utils.time_provider import RealTimeProvider
from core.models import Connector, Bot
from core.market_data_provider import Interval, Candle
from core.market_data_provider_factory import MarketDataProviderFactory

# ==================== КОНФИГУРАЦИЯ ЛОГГИРОВАНИЯ ====================
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "vectra_core.log"
file_handler = logging.handlers.RotatingFileHandler(
    LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
file_handler.setLevel(logging.INFO)
logging.getLogger().addHandler(file_handler)
load_dotenv()
logger = logging.getLogger(__name__)
CORE_PASSWORD = os.getenv('CORE_PASSWORD', '')
if not CORE_PASSWORD:
    logger.warning("CORE_PASSWORD not set in .env! Authentication will be disabled (INSECURE).")

def check_auth(context):
    """Проверяет аутентификацию по метаданным. Выбрасывает RpcError при ошибке."""
    if not CORE_PASSWORD:
        return
    metadata = dict(context.invocation_metadata() or ())
    auth_header = metadata.get('authorization')
    if not auth_header:
        context.abort(grpc.StatusCode.UNAUTHENTICATED, "Missing authorization header")
    parts = auth_header.split()
    if len(parts) != 2 or parts[0].lower() != 'bearer':
        context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid authorization format, expected 'Bearer <password>'")
    token = parts[1]
    if token != CORE_PASSWORD:
        context.abort(grpc.StatusCode.PERMISSION_DENIED, "Invalid password")

class CoreServicer(core_pb2_grpc.CoreServiceServicer):
    def __init__(self):
        self.db = None
        self.task_manager = None
        self.time_provider = None
        self._init_lock = asyncio.Lock()
        self._initialized = False
        self._cleanup_task = None
        self._log_retention_days = int(os.getenv('LOG_RETENTION_DAYS', '30'))

    async def _ensure_init(self):
        if self._initialized:
            return
        async with self._init_lock:
            if self._initialized:
                return
            self.db = Database()
            await self.db.init()
            self.time_provider = RealTimeProvider()
            self.task_manager = TaskManager(self.db)
            await self.task_manager.init()
            self._initialized = True
            await self._log_message("INFO", "system", "Ядро Vectra успешно инициализировано")
            logger.info("CoreServicer initialized with TaskManager")
            if not self._cleanup_task:
                self._cleanup_task = asyncio.create_task(self._periodic_log_cleanup())
                await self._delete_old_logs()

    async def _delete_old_logs(self):
        try:
            deleted = await self.db.delete_old_logs(days=self._log_retention_days)
            if deleted:
                await self._log_message("INFO", "system", f"Удалено {deleted} старых записей логов")
        except Exception as e:
            logger.error(f"Ошибка при очистке логов: {e}")

    async def _periodic_log_cleanup(self):
        while True:
            await asyncio.sleep(24 * 3600)
            await self._delete_old_logs()

    async def _log_message(self, level: str, category: str, message_ru: str, also_print: bool = True):
        if self.db:
            try:
                await self.db.add_log(level, category, message_ru)
            except Exception as e:
                logger.error(f"Failed to write log to DB: {e}")
        if also_print:
            color = "\033[91m" if level == "ERROR" else ("\033[93m" if level == "WARNING" else "\033[92m")
            print(f"{color}[{level}] [{category}] {message_ru}\033[0m")

    # ==================== КОННЕКТОРЫ ====================
    async def CreateConnector(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            settings = {
                'name': request.name,
                'exchange_id': request.exchange_id,
                'testnet': request.testnet,
                'api_key': request.api_key,
                'api_secret': request.api_secret,
                'api_passphrase': request.api_passphrase,
                'product_type': request.product_type,
                'status': 'offline',
                'max_retries': getattr(request, 'max_retries', 3),
                'retry_backoff': getattr(request, 'retry_backoff', 2.0),
                'ws_ping_interval': getattr(request, 'ws_ping_interval', 30),
                'ws_reconnect_delay': getattr(request, 'ws_reconnect_delay', 5),
                'ip_whitelist': getattr(request, 'ip_whitelist', ''),
                'auto_reconnect': getattr(request, 'auto_reconnect', True),
                'retry_on_limit': getattr(request, 'retry_on_limit', True),
                'http_timeout_read': getattr(request, 'http_timeout_read', 10),
                'http_timeout_connect': getattr(request, 'http_timeout_connect', 5),
                'order_type_default': getattr(request, 'order_type_default', 'limit')
            }
            new_conn = Connector(**settings)
            await self.db.save_connector(new_conn)
            conn_instance = await self.task_manager.create_connector_instance(request.name, skip_refcnt=True)
            success = conn_instance is not None
            if success:
                c = await self.db.get_connector(request.name)
                if c:
                    c.status = 'online'
                    await self.db.save_connector(c)
            msg = "Connector created and connected"
            await self._log_message("INFO", "connector", f"Коннектор '{request.name}' создан ({'online' if success else 'offline'})")
            return core_pb2.StatusResponse(success=True, message=msg)
        except Exception as e:
            logger.error(f"CreateConnector failed: {e}", exc_info=True)
            await self._log_message("ERROR", "connector", f"Ошибка создания коннектора: {e}")
            return core_pb2.StatusResponse(success=False, message=str(e))

    async def GetConnectorsList(self, request, context):
        check_auth(context)
        await self._ensure_init()
        connectors_db = await self.db.get_connectors_list()
        response = core_pb2.ConnectorsListResponse()
        for c in connectors_db:
            item = response.connectors.add()
            item.name = c.name
            status = await self.task_manager.get_connector_status(c.name)
            item.status = status
            item.exchange = c.exchange_id
            item.testnet = c.testnet
            item.product_type = c.product_type
        return response

    async def GetConnectorSettings(self, request, context):
        check_auth(context)
        await self._ensure_init()
        conn = await self.db.get_connector(request.name)
        if not conn:
            return core_pb2.ConnectorSettingsResponse()
        resp = core_pb2.ConnectorSettingsResponse()
        resp.name = conn.name
        resp.exchange = conn.exchange_id
        resp.testnet = conn.testnet
        resp.api_key = conn.api_key
        resp.api_secret = conn.api_secret
        resp.api_passphrase = conn.api_passphrase
        resp.product_type = conn.product_type
        resp.max_retries = getattr(conn, 'max_retries', 3)
        resp.retry_backoff = getattr(conn, 'retry_backoff', 2.0)
        resp.ws_ping_interval = getattr(conn, 'ws_ping_interval', 30)
        resp.ws_reconnect_delay = getattr(conn, 'ws_reconnect_delay', 5)
        resp.ip_whitelist = getattr(conn, 'ip_whitelist', '')
        resp.auto_reconnect = getattr(conn, 'auto_reconnect', True)
        resp.retry_on_limit = getattr(conn, 'retry_on_limit', True)
        resp.http_timeout_read = getattr(conn, 'http_timeout_read', 10)
        resp.http_timeout_connect = getattr(conn, 'http_timeout_connect', 5)
        resp.order_type_default = getattr(conn, 'order_type_default', 'limit')
        return resp

    async def UpdateConnectorSettings(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            new_settings = json.loads(request.settings_json)
            success = await self.task_manager.update_connector(request.name, new_settings)
            if success:
                await self._log_message("INFO", "connector", f"Настройки коннектора '{request.name}' обновлены")
                return core_pb2.StatusResponse(success=True, message="updated")
            else:
                return core_pb2.StatusResponse(success=False, message="Connector is in use, cannot update")
        except Exception as e:
            return core_pb2.StatusResponse(success=False, message=str(e))

    async def DeleteConnector(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            status = await self.task_manager.get_connector_status(request.name)
            if status == 'online':
                removed = await self.task_manager.remove_connector(request.name)
                if not removed:
                    await self._log_message("WARNING", "connector", 
                        f"Коннектор '{request.name}' используется ботами, не может быть удалён")
                    return core_pb2.StatusResponse(success=False, 
                        message="Connector is in use by bots. Stop all bots using this connector first.")
            await self.db.delete_connector(request.name)
            await self._log_message("INFO", "connector", f"Коннектор '{request.name}' удалён из базы данных")
            return core_pb2.StatusResponse(success=True, message="deleted")
        except Exception as e:
            return core_pb2.StatusResponse(success=False, message=str(e))

    async def CheckConnector(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            connector = await self.task_manager._get_or_create_connector(request.name, increase_refcnt=False)
            if connector is None:
                return core_pb2.CheckConnectorResponse(status='offline')
            is_online = await connector.check_connection()
            status = 'online' if is_online else 'offline'
            conn = await self.db.get_connector(request.name)
            if conn and conn.status != status:
                conn.status = status
                await self.db.save_connector(conn)
            return core_pb2.CheckConnectorResponse(status=status)
        except Exception as e:
            logger.error(f"CheckConnector error: {e}")
            return core_pb2.CheckConnectorResponse(status='error')

    async def SetConnectorStatus(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            if request.status == 'online':
                success = await self.task_manager.reconnect_connector(request.name)
                if success:
                    conn = await self.db.get_connector(request.name)
                    if conn:
                        conn.status = 'online'
                        await self.db.save_connector(conn)
                    return core_pb2.StatusResponse(success=True, message="Connector connected")
                else:
                    return core_pb2.StatusResponse(success=False, message="Failed to connect")
            elif request.status == 'offline':
                removed = await self.task_manager.remove_connector(request.name)
                if removed:
                    conn = await self.db.get_connector(request.name)
                    if conn:
                        conn.status = 'offline'
                        await self.db.save_connector(conn)
                    return core_pb2.StatusResponse(success=True, message="Connector disconnected")
                else:
                    return core_pb2.StatusResponse(success=False, message="Connector is in use by bots")
            else:
                return core_pb2.StatusResponse(success=False, message="Invalid status")
        except Exception as e:
            return core_pb2.StatusResponse(success=False, message=str(e))

    # ==================== БОТЫ ====================
    async def StartBot(self, request, context):
        check_auth(context)
        print(f"[DEBUG StartBot] received: bot_id={request.bot_id}, name={request.name}, strategy={request.strategy}")
        await self._ensure_init()
        
        from utils.bot_registry import get_bot_registry
        registry = get_bot_registry()
        if not registry.is_valid_strategy(request.strategy):
            error_msg = f"Invalid strategy: {request.strategy}. Available: {list(registry.get_all_strategies().keys())}"
            self._logger.error(error_msg)
            return core_pb2.BotResponse(success=False, message=error_msg, bot_id=0)
        
        params = dict(request.params)
        emulator_enabled_str = params.pop('emulator_enabled', None)
        emulator_enabled = emulator_enabled_str.lower() == 'true' if isinstance(emulator_enabled_str, str) else bool(emulator_enabled_str) if emulator_enabled_str is not None else False
        
        market_data_source = getattr(request, 'market_data_source', 'websocket')
        market_data_source_config = getattr(request, 'market_data_source_config', '')
        
        bot_id = request.bot_id
        if bot_id == 0:
            product_type = params.get('product_type', None)
            if not product_type:
                conn = await self.db.get_connector(request.connector)
                product_type = conn.product_type if conn else 'USDT-FUTURES'
            bot = Bot(
                name=request.name, strategy=request.strategy, connector=request.connector,
                symbol=request.symbol, timeframe=request.timeframe, margin_mode=request.margin_mode,
                leverage=request.leverage, position_size=request.position_size,
                params=json.dumps(params), enabled=True, emulator_enabled=emulator_enabled,
                product_type=product_type,
                market_data_source=market_data_source,
                market_data_source_config=market_data_source_config
            )
            bot = await self.db.save_bot(bot)
            bot_id = bot.id
            print(f"[DEBUG StartBot] created new bot in DB, id={bot_id}")
        
        bot_class = registry.get_bot_class(request.strategy)
        full_module_path = f"{bot_class.__module__}.{bot_class.__name__}"
        if full_module_path.startswith('bots.'):
            full_module_path = full_module_path[5:]
        
        success = await self.task_manager.create_bot(
            bot_id, request.name, full_module_path, request.connector,
            request.symbol, request.timeframe, request.position_size, params, emulator_enabled,
            market_data_source=market_data_source,
            market_data_source_config=market_data_source_config
        )
        print(f"[DEBUG StartBot] create_bot returned success={success}")
        return core_pb2.BotResponse(success=success, message="ok" if success else "failed", bot_id=bot_id)

    async def StopBot(self, request, context):
        check_auth(context)
        await self._ensure_init()
        ok = await self.task_manager.stop_bot(request.bot_id)
        return core_pb2.BotResponse(success=ok, message="stopped" if ok else "not found", bot_id=request.bot_id)

    async def DeleteBot(self, request, context):
        check_auth(context)
        await self._ensure_init()
        await self.task_manager.delete_bot(request.bot_id)
        return core_pb2.BotResponse(success=True, message="deleted", bot_id=request.bot_id)

    async def GetBotsList(self, request, context):
        check_auth(context)
        await self._ensure_init()
        bots = await self.task_manager.get_bots_list()
        response = core_pb2.BotsListResponse()
        for b in bots:
            info = response.bots.add()
            info.id = b['id']; info.name = b['name']; info.strategy = b.get('strategy', '')
            info.connector = b.get('connector', ''); info.symbol = b.get('symbol', '')
            info.running = b.get('running', False)
        return response

    async def GetBotStatus(self, request, context):
        check_auth(context)
        await self._ensure_init()
        status = await self.task_manager.get_bot_status(request.bot_id)
        return core_pb2.BotStatusResponse(
            running=status.get('running', False), position_open=status.get('position_open', False),
            side=status.get('side', ''), entry_price=status.get('entry_price', 0.0),
            symbol=status.get('symbol', ''), open_positions=status.get('open_positions', 0),
            closed_positions=status.get('closed_positions', 0)
        )

    async def GetBotTrades(self, request, context):
        check_auth(context)
        await self._ensure_init()
        trades = await self.db.get_trades(request.bot_id)
        response = core_pb2.TradesResponse()
        for t in trades:
            tr = response.trades.add()
            tr.bot_id = t.bot_id; tr.bot_name = t.bot_name; tr.symbol = t.symbol; tr.side = t.side
            tr.open_time = t.open_time; tr.open_price = t.open_price
            tr.close_time = t.close_time; tr.close_price = t.close_price
            tr.pnl = t.pnl; tr.size = t.size
        return response

    async def GetFullState(self, request, context):
        check_auth(context)
        await self._ensure_init()
        bots = await self.task_manager.get_bots_list()
        connectors_db = await self.db.get_connectors_list()
        connectors = []
        for c in connectors_db:
            status = await self.task_manager.get_connector_status(c.name)
            connectors.append({'name': c.name, 'status': status, 'exchange': c.exchange_id,
                               'testnet': c.testnet, 'product_type': c.product_type})
        trades = await self.db.get_trades(limit=500)
        trades_list = [{'bot_id': t.bot_id, 'bot_name': t.bot_name, 'symbol': t.symbol,
                        'side': t.side, 'open_time': t.open_time, 'open_price': t.open_price,
                        'close_time': t.close_time, 'close_price': t.close_price, 'pnl': t.pnl, 'size': t.size} for t in trades]
        state = {"bots": bots, "connectors": connectors, "trades": trades_list}
        return core_pb2.FullStateResponse(state=json.dumps(state))

    async def CreateBot(self, request, context):
        check_auth(context)
        await self._ensure_init()
        
        from utils.bot_registry import get_bot_registry
        registry = get_bot_registry()
        if not registry.is_valid_strategy(request.strategy):
            error_msg = f"Invalid strategy: {request.strategy}"
            return core_pb2.BotResponse(success=False, message=error_msg, bot_id=0)
        
        params = dict(request.params)
        emulator_enabled_str = params.pop('emulator_enabled', 'false')
        emulator_enabled = emulator_enabled_str.lower() == 'true' if isinstance(emulator_enabled_str, str) else False
        product_type = params.get('product_type', 'USDT-FUTURES')
        market_data_source = getattr(request, 'market_data_source', 'websocket')
        market_data_source_config = getattr(request, 'market_data_source_config', '')
        bot = Bot(
            name=request.name, strategy=request.strategy, connector=request.connector,
            symbol=request.symbol, timeframe=request.timeframe, margin_mode=request.margin_mode,
            leverage=request.leverage, position_size=request.position_size,
            params=json.dumps(params), enabled=True, emulator_enabled=emulator_enabled,
            product_type=product_type,
            market_data_source=market_data_source,
            market_data_source_config=market_data_source_config
        )
        saved_bot = await self.db.save_bot(bot)
        return core_pb2.BotResponse(success=True, message="created", bot_id=saved_bot.id)

    async def UpdateBotConfig(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            params = json.loads(request.params_json) if request.params_json else {}
            new_config = {
                'connector_name': request.connector_name,
                'symbol': request.symbol,
                'timeframe': request.timeframe,
                'position_size': request.position_size,
                'params': params,
                'emulator_enabled': request.emulator_enabled,
                'market_data_source': getattr(request, 'market_data_source', 'websocket'),
                'market_data_source_config': getattr(request, 'market_data_source_config', '')
            }
            await self.db.update_bot_config(request.bot_id, new_config)
            return core_pb2.StatusResponse(success=True, message="updated")
        except Exception as e:
            return core_pb2.StatusResponse(success=False, message=str(e))

    # ==================== РЫНОЧНЫЕ ДАННЫЕ ====================
    async def GetCandles(self, request, context):
        check_auth(context)
        await self._ensure_init()
        candles = await self.task_manager.get_candles_with_source(
            connector_name=request.connector,
            symbol=request.symbol,
            timeframe=request.timeframe,
            limit=request.limit,
            start_time=request.start_time,
            end_time=request.end_time,
            market_data_source=getattr(request, 'market_data_source', 'websocket'),
            market_data_source_config=getattr(request, 'market_data_source_config', '')
        )
        response = core_pb2.CandlesResponse()
        for c in candles:
            candle = response.candles.add()
            candle.timestamp = c['timestamp']
            candle.open = c['open']
            candle.high = c['high']
            candle.low = c['low']
            candle.close = c['close']
            candle.volume = c['volume']
        return response

    async def GetTicker(self, request, context):
        check_auth(context)
        await self._ensure_init()
        ticker = await self.task_manager.get_ticker(request.connector, request.symbol)
        return core_pb2.TickerResponse(last=ticker.get('last',0), bid=ticker.get('bid',0), ask=ticker.get('ask',0), volume=ticker.get('volume',0))

    async def GetSymbols(self, request, context):
        check_auth(context)
        await self._ensure_init()
        symbols = await self.task_manager.get_symbols(request.connector, request.product_type)
        response = core_pb2.SymbolsResponse()
        response.symbols.extend(symbols)
        return response

    async def GetOrderBook(self, request, context):
        check_auth(context)
        await self._ensure_init()
        ob = await self.task_manager.get_order_book(request.connector, request.symbol, request.depth)
        response = core_pb2.OrderBookResponse()
        for p, a in ob.get('bids', []): response.bids.add(price=p, amount=a)
        for p, a in ob.get('asks', []): response.asks.add(price=p, amount=a)
        return response

    # ==================== ТОРГОВЛЯ И ПОЗИЦИИ ====================
    async def SetLeverage(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            await self.task_manager.set_leverage(request.connector_name, request.symbol, request.leverage, request.margin_mode)
            return core_pb2.StatusResponse(success=True, message="leverage set")
        except Exception as e: return core_pb2.StatusResponse(success=False, message=str(e))

    async def SetTPSL(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            await self.task_manager.set_tpsl(request.connector_name, request.symbol, request.hold_side,
                                             request.trigger_price, request.execute_price, request.tpsl_type, request.size)
            return core_pb2.StatusResponse(success=True, message="tpsl set")
        except Exception as e: return core_pb2.StatusResponse(success=False, message=str(e))

    async def GetPosition(self, request, context):
        check_auth(context)
        await self._ensure_init()
        positions = await self.task_manager.get_position(request.connector_name, request.symbol)
        response = core_pb2.GetPositionResponse(success=True)
        for p in positions:
            pos = response.positions.add()
            pos.symbol = p['symbol']; pos.side = p['side']; pos.size = p['size']
            pos.entry_price = p['entry_price']; pos.mark_price = p.get('mark_price', 0); pos.pnl = p.get('pnl', 0)
            pos.leverage = p.get('leverage', 1); pos.margin = p.get('margin', 0)
            pos.liquidation_price = p.get('liquidation_price', 0); pos.margin_mode = p.get('margin_mode', 'crossed')
        return response

    async def ClosePosition(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            await self.task_manager.close_position(request.connector_name, request.symbol, request.hold_side)
            return core_pb2.StatusResponse(success=True, message="position closed")
        except Exception as e: return core_pb2.StatusResponse(success=False, message=str(e))

    async def CreateOrder(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            connector = await self.task_manager._get_or_create_connector(request.connector_name, increase_refcnt=False)
            order = await connector.create_order(
                symbol=request.symbol, side=request.side, order_type=request.order_type,
                quantity=request.quantity, price=request.price if request.price > 0 else None,
                preset_tp=request.preset_tp if request.preset_tp > 0 else None,
                preset_sl=request.preset_sl if request.preset_sl > 0 else None
            )
            return core_pb2.CreateOrderResponse(success=True, order_id=order.get('orderId',''))
        except Exception as e: return core_pb2.CreateOrderResponse(success=False, error=str(e))

    async def CancelOrder(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            connector = await self.task_manager._get_or_create_connector(request.connector_name, increase_refcnt=False)
            await connector.cancel_order(symbol=request.symbol, order_id=request.order_id)
            return core_pb2.StatusResponse(success=True, message="order cancelled")
        except Exception as e: return core_pb2.StatusResponse(success=False, message=str(e))

    async def GetOpenOrders(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            connector = await self.task_manager._get_or_create_connector(request.connector_name, increase_refcnt=False)
            orders = await connector.get_open_orders(symbol=request.symbol)
            response = core_pb2.GetOpenOrdersResponse(success=True)
            for o in orders:
                ord_info = response.orders.add()
                ord_info.order_id = o.get('orderId',''); ord_info.client_oid = o.get('clientOid','')
                ord_info.symbol = o['symbol']; ord_info.price = o.get('price',0); ord_info.quantity = o.get('quantity',0)
                ord_info.filled = o.get('filled',0); ord_info.status = o.get('status','')
                ord_info.side = o.get('side',''); ord_info.order_type = o.get('order_type','')
                ord_info.timestamp = o.get('timestamp',0)
            return response
        except Exception as e: return core_pb2.GetOpenOrdersResponse(success=False, error=str(e))

    async def GetBalance(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            connector = await self.task_manager._get_or_create_connector(request.connector_name, increase_refcnt=False)
            balances = await connector.get_balance(currency=request.currency if request.currency else None)
            response = core_pb2.GetBalanceResponse(success=True)
            for b in balances:
                item = response.balances.add()
                item.currency = b['currency']; item.available = b['available']
                item.frozen = b.get('frozen',0); item.total = b['total']
            return response
        except Exception as e: return core_pb2.GetBalanceResponse(success=False, error=str(e))

    # ==================== РУЧНОЙ БОТ И ЛОГИ ====================
    async def CallManualBot(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            bot_info = self.task_manager._bot_instances.get(request.bot_id)
            if not bot_info or not bot_info.get('instance'):
                return core_pb2.CallManualBotResponse(
                    success=False,
                    error="Bot instance not found or not running"
                )
            bot = bot_info['instance']
            
            if hasattr(bot, 'mode') and bot.mode == 'attached' and bot.attached_bot_id > 0:
                target_bot_id = bot.attached_bot_id
                method_name = request.method
                params = json.loads(request.params_json) if request.params_json else {}
                self._log_message("INFO", "manual", 
                                 f"Перенаправление вызова {method_name} от бота {request.bot_id} к боту {target_bot_id}")
                result = await self.task_manager.call_bot_method(target_bot_id, method_name, params)
                return core_pb2.CallManualBotResponse(
                    success=True,
                    result_json=json.dumps(result, default=str)
                )
            else:
                method = getattr(bot, request.method, None)
                if not method:
                    return core_pb2.CallManualBotResponse(
                        success=False,
                        error=f"Method {request.method} not found"
                    )
                params = json.loads(request.params_json) if request.params_json else {}
                result = await method(**params)
                return core_pb2.CallManualBotResponse(
                    success=True,
                    result_json=json.dumps(result, default=str)
                )
        except Exception as e:
            self._log_message("ERROR", "manual", f"Ошибка в CallManualBot: {e}")
            return core_pb2.CallManualBotResponse(success=False, error=str(e))

    async def GetLogsSince(self, request, context):
        check_auth(context)
        await self._ensure_init()
        logs = await self.db.get_logs_since(request.since_timestamp, request.limit)
        response = core_pb2.GetLogsSinceResponse()
        for l in logs:
            entry = response.logs.add()
            entry.timestamp = l['timestamp']; entry.level = l['level']
            entry.category = l['category']; entry.message_ru = l['message_ru']
        return response

    async def GetBotMarketDataSource(self, request, context):
        check_auth(context)
        await self._ensure_init()
        source, config = await self.task_manager.get_bot_market_data_source(request.bot_id)
        return core_pb2.GetBotMarketDataSourceResponse(source=source, config=config)

    # ==================== СТРИМИНГ СВЕЧЕЙ ====================
    async def SubscribeCandles(self, request: core_pb2.SubscribeCandlesRequest, context):
        check_auth(context)
        await self._ensure_init()
        connector = await self.task_manager._get_or_create_connector(request.connector, increase_refcnt=False)
        if connector is None:
            await context.abort(grpc.StatusCode.NOT_FOUND, f"Connector {request.connector} not found")
            return

        try:
            provider = MarketDataProviderFactory.create(
                provider_type=request.market_data_source,
                connector=connector,
                symbol=request.symbol,
                db=self.db if request.market_data_source == 'database' else None,
                config_json=request.market_data_source_config
            )
        except Exception as e:
            logger.error(f"Failed to create market data provider for streaming: {e}")
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, str(e))
            return

        await provider.connect()
        queue = asyncio.Queue()

        async def on_candle(candle: Candle):
            await queue.put(candle)

        try:
            interval = Interval(request.timeframe)
            await provider.subscribe_candles(request.symbol, interval, on_candle)
        except Exception as e:
            logger.error(f"Failed to subscribe to candles: {e}")
            await provider.disconnect()
            await context.abort(grpc.StatusCode.INTERNAL, str(e))
            return

        try:
            while True:
                candle = await queue.get()
                pb_candle = core_pb2.Candle(
                    timestamp=candle.timestamp,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume
                )
                yield pb_candle
                if context.cancelled():
                    break
        except asyncio.CancelledError:
            pass
        finally:
            await provider.unsubscribe_all(request.symbol)
            await provider.disconnect()

    # ==================== НОВЫЕ RPC ====================
    async def CallBotMethod(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            params = json.loads(request.params_json) if request.params_json else {}
            result = await self.task_manager.call_bot_method(
                request.bot_id, request.method_name, params
            )
            return core_pb2.CallBotMethodResponse(
                success=True,
                result_json=json.dumps(result, default=str)
            )
        except Exception as e:
            return core_pb2.CallBotMethodResponse(success=False, error=str(e))

    async def GetBotStrategyDescription(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            desc = await self.task_manager.get_bot_strategy_description(request.bot_id)
            return core_pb2.GetBotStrategyDescriptionResponse(
                description_json=json.dumps(desc)
            )
        except Exception as e:
            return core_pb2.GetBotStrategyDescriptionResponse(description_json="{}")

    # ==================== НОВЫЙ RPC ДЛЯ СХЕМЫ ПАРАМЕТРОВ СТРАТЕГИИ ====================
    async def GetStrategyParamsSchema(self, request, context):
        check_auth(context)
        await self._ensure_init()
        try:
            strategy_name = request.strategy_name
            # Импортируем класс бота динамически
            # Формат: "trend.ema_bot.EmaBot" или "grid.grid_bot.GridBot"
            parts = strategy_name.split('.')
            if len(parts) < 2:
                raise ValueError(f"Invalid strategy name format: {strategy_name}")
            module_path = "bots." + ".".join(parts[:-1])
            class_name = parts[-1]
            module = importlib.import_module(module_path)
            bot_class = getattr(module, class_name)
            # Вызываем classmethod get_params_schema
            schema = bot_class.get_params_schema()
            schema_json = json.dumps(schema, default=str)
            return core_pb2.GetStrategyParamsSchemaResponse(schema_json=schema_json)
        except Exception as e:
            logger.error(f"GetStrategyParamsSchema failed: {e}", exc_info=True)
            # Возвращаем пустую схему при ошибке
            return core_pb2.GetStrategyParamsSchemaResponse(schema_json="{}")

    async def Shutdown(self, request, context):
        logger.info("Received Shutdown request")
        await self._log_message("INFO", "system", "Ядро Vectra завершает работу по команде")
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try: await self._cleanup_task
            except asyncio.CancelledError: pass
        if self.task_manager: await self.task_manager.shutdown()
        if self.db: await self.db.close()
        return core_pb2.StatusResponse(success=True, message="shutting down")


async def serve(host='0.0.0.0', port=9876):
    server = grpc.aio.server()
    servicer = CoreServicer()
    await servicer._ensure_init()
    core_pb2_grpc.add_CoreServiceServicer_to_server(servicer, server)
    server.add_insecure_port(f'{host}:{port}')
    await server.start()
    logger.info(f"gRPC server started on {host}:{port}")
    if CORE_PASSWORD:
        logger.info("Authentication is ENABLED (password required)")
    else:
        logger.warning("Authentication is DISABLED (no CORE_PASSWORD set)")
    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt, shutting down...")
    finally:
        await servicer.Shutdown(core_pb2.Empty(), None)
        await server.stop(grace=5)
        logger.info("gRPC server stopped")


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=9876)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    try:
        asyncio.run(serve(host=args.host, port=args.port))
    except KeyboardInterrupt:
        pass