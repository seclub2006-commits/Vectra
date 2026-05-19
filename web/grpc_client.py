# web/grpc_client.py
import asyncio
import logging
import grpc
import json
from typing import Dict, Any, List, Optional

import core_pb2
import core_pb2_grpc

logger = logging.getLogger(__name__)


class GrpcCoreClient:
    """Клиент к gRPC серверу ядра с автоматическим восстановлением соединения."""

    def __init__(self, host: str = "localhost", port: int = 9876, password: str = ""):
        self.host = host
        self.port = port
        self.password = password

        self._connected = False
        self._shutdown = False
        self._reconnect_task: Optional[asyncio.Task] = None
        self._reconnect_lock = asyncio.Lock()

        self.channel: Optional[grpc.aio.Channel] = None
        self.stub: Optional[core_pb2_grpc.CoreServiceStub] = None

    # ---------- Управление соединением ----------
    async def connect(self) -> bool:
        try:
            if self.channel:
                await self.channel.close()
            self.channel = grpc.aio.insecure_channel(f"{self.host}:{self.port}")
            self.stub = core_pb2_grpc.CoreServiceStub(self.channel)

            metadata = [('authorization', f'Bearer {self.password}')]
            await self.stub.GetBotsList(core_pb2.Empty(), metadata=metadata, timeout=5)

            self._connected = True
            logger.info(f"gRPC client connected to {self.host}:{self.port}")
            return True

        except grpc.RpcError as e:
            logger.error(f"gRPC connection failed: {e.code()} - {e.details()}")
        except Exception as e:
            logger.error(f"Unexpected error during connection: {e}")

        self._connected = False
        self.stub = None
        if self.channel:
            await self.channel.close()
            self.channel = None
        return False

    async def disconnect(self):
        self._shutdown = True
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        if self.channel:
            await self.channel.close()
            self.channel = None
        self.stub = None
        self._connected = False
        logger.info("gRPC client disconnected")

    async def ensure_connection(self) -> bool:
        if self._connected and self.stub is not None:
            return True

        async with self._reconnect_lock:
            if self._connected and self.stub is not None:
                return True

            if self._reconnect_task and not self._reconnect_task.done():
                logger.debug("Waiting for ongoing reconnect task...")
                await self._reconnect_task
                return self._connected

            self._reconnect_task = asyncio.create_task(self._reconnect_loop())
            await self._reconnect_task
            return self._connected

    async def _reconnect_loop(self):
        delay = 1.0
        max_delay = 60.0
        while not self._shutdown and not self._connected:
            logger.info(f"Attempting to reconnect to gRPC core in {delay:.1f}s...")
            await asyncio.sleep(delay)
            if await self.connect():
                logger.info("gRPC core reconnected successfully")
                return
            delay = min(delay * 2, max_delay)

    async def _call(self, method, request, timeout: int = 60):
        if not await self.ensure_connection():
            raise Exception("gRPC client is not connected and reconnection failed")

        metadata = [('authorization', f'Bearer {self.password}')]
        try:
            return await method(request, metadata=metadata, timeout=timeout)
        except grpc.RpcError as e:
            if e.code() in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
                logger.warning(f"gRPC call failed with {e.code()}, marking disconnected and retrying once")
                self._connected = False
                if await self.ensure_connection():
                    logger.info("Retrying gRPC call after reconnection")
                    return await method(request, metadata=metadata, timeout=timeout)
            raise

    # ---------- Методы API (все через _call) ----------
    async def get_bots_list(self) -> List[Dict]:
        response = await self._call(self.stub.GetBotsList, core_pb2.Empty())
        bots = []
        for b in response.bots:
            bots.append({
                'id': b.id,
                'name': b.name,
                'strategy': b.strategy,
                'connector': b.connector,
                'symbol': b.symbol,
                'running': b.running,
            })
        return bots

    async def start_bot(self, bot_id: int, name: str, strategy: str,
                        connector_name: str, symbol: str, timeframe: str,
                        position_size: float, params: Dict[str, str],
                        market_data_source: str = 'websocket',
                        market_data_source_config: str = '') -> Dict:
        req = core_pb2.StartBotRequest(
            bot_id=bot_id,
            name=name,
            strategy=strategy,
            connector=connector_name,
            symbol=symbol,
            timeframe=timeframe,
            margin_mode="isolated",
            leverage=int(params.get('leverage', 10)),
            position_size=position_size,
            params=params,
            market_data_source=market_data_source,
            market_data_source_config=market_data_source_config
        )
        resp = await self._call(self.stub.StartBot, req)
        return {
            'success': resp.success,
            'message': resp.message,
            'bot_id': resp.bot_id
        }

    async def stop_bot(self, bot_id: int) -> Dict:
        req = core_pb2.StopBotRequest(bot_id=bot_id)
        resp = await self._call(self.stub.StopBot, req)
        return {'success': resp.success, 'message': resp.message}

    async def delete_bot(self, bot_id: int) -> Dict:
        req = core_pb2.DeleteBotRequest(bot_id=bot_id)
        resp = await self._call(self.stub.DeleteBot, req)
        return {'success': resp.success, 'message': resp.message}

    async def get_bot_status(self, bot_id: int) -> Dict:
        req = core_pb2.GetBotStatusRequest(bot_id=bot_id)
        resp = await self._call(self.stub.GetBotStatus, req)
        return {
            'running': resp.running,
            'position_open': resp.position_open,
            'side': resp.side,
            'entry_price': resp.entry_price,
            'symbol': resp.symbol,
            'open_positions': resp.open_positions,
            'closed_positions': resp.closed_positions
        }

    async def get_bot_trades(self, bot_id: int, limit: int = 100) -> List[Dict]:
        req = core_pb2.GetBotTradesRequest(bot_id=bot_id)
        resp = await self._call(self.stub.GetBotTrades, req)
        trades = []
        for t in resp.trades:
            trades.append({
                'bot_id': t.bot_id,
                'bot_name': t.bot_name,
                'symbol': t.symbol,
                'side': t.side,
                'open_time': t.open_time,
                'open_price': t.open_price,
                'close_time': t.close_time,
                'close_price': t.close_price,
                'pnl': t.pnl,
                'size': t.size
            })
        return trades

    async def update_bot_config(self, bot_id: int, connector_name: str,
                                symbol: str, timeframe: str, position_size: float,
                                params: Dict, emulator_enabled: bool,
                                market_data_source: str = 'websocket',
                                market_data_source_config: str = '') -> Dict:
        req = core_pb2.UpdateBotConfigRequest(
            bot_id=bot_id,
            connector_name=connector_name,
            symbol=symbol,
            timeframe=timeframe,
            position_size=position_size,
            params_json=json.dumps(params),
            emulator_enabled=emulator_enabled,
            market_data_source=market_data_source,
            market_data_source_config=market_data_source_config
        )
        resp = await self._call(self.stub.UpdateBotConfig, req)
        return {'success': resp.success, 'message': resp.message}

    # ---------- Коннекторы ----------
    async def get_connectors_list(self) -> List[Dict]:
        resp = await self._call(self.stub.GetConnectorsList, core_pb2.Empty())
        connectors = []
        for c in resp.connectors:
            connectors.append({
                'name': c.name,
                'status': c.status,
                'exchange': c.exchange,
                'testnet': c.testnet,
                'product_type': c.product_type
            })
        return connectors

    async def create_connector(self, settings: Dict) -> Dict:
        req = core_pb2.CreateConnectorRequest(
            name=settings.get('name', ''),
            exchange_id=settings.get('exchange_id', settings.get('exchange', 'bitget')),
            testnet=settings.get('testnet', True),
            api_key=settings.get('api_key', ''),
            api_secret=settings.get('api_secret', ''),
            api_passphrase=settings.get('api_passphrase', ''),
            product_type=settings.get('product_type', 'USDT-FUTURES'),
            max_retries=settings.get('max_retries', 3),
            retry_backoff=float(settings.get('retry_backoff', 2.0)),
            ws_ping_interval=int(settings.get('ws_ping_interval', 30)),
            ws_reconnect_delay=int(settings.get('ws_reconnect_delay', 5)),
            ip_whitelist=settings.get('ip_whitelist', ''),
            auto_reconnect=settings.get('auto_reconnect', True),
            retry_on_limit=settings.get('retry_on_limit', True),
            http_timeout_read=int(settings.get('http_timeout_read', 10)),
            http_timeout_connect=int(settings.get('http_timeout_connect', 5)),
            order_type_default=settings.get('order_type_default', 'limit')
        )
        resp = await self._call(self.stub.CreateConnector, req)
        return {'success': resp.success, 'message': resp.message}

    async def get_connector_settings(self, name: str) -> Dict:
        req = core_pb2.GetConnectorSettingsRequest(name=name)
        resp = await self._call(self.stub.GetConnectorSettings, req)
        return {
            'name': resp.name,
            'exchange': resp.exchange,
            'testnet': resp.testnet,
            'api_key': resp.api_key,
            'api_secret': resp.api_secret,
            'api_passphrase': resp.api_passphrase,
            'product_type': resp.product_type,
            'max_retries': resp.max_retries,
            'retry_backoff': resp.retry_backoff,
            'ws_ping_interval': resp.ws_ping_interval,
            'ws_reconnect_delay': resp.ws_reconnect_delay,
            'ip_whitelist': resp.ip_whitelist,
            'auto_reconnect': resp.auto_reconnect,
            'retry_on_limit': resp.retry_on_limit,
            'http_timeout_read': resp.http_timeout_read,
            'http_timeout_connect': resp.http_timeout_connect,
            'order_type_default': resp.order_type_default
        }

    async def update_connector_settings(self, name: str, settings: Dict) -> Dict:
        req = core_pb2.UpdateConnectorRequest(
            name=name,
            settings_json=json.dumps(settings)
        )
        resp = await self._call(self.stub.UpdateConnectorSettings, req)
        return {'success': resp.success, 'message': resp.message}

    async def delete_connector(self, name: str) -> Dict:
        req = core_pb2.DeleteConnectorRequest(name=name)
        resp = await self._call(self.stub.DeleteConnector, req)
        return {'success': resp.success, 'message': resp.message}

    async def set_connector_status(self, name: str, status: str) -> Dict:
        req = core_pb2.SetConnectorStatusRequest(name=name, status=status)
        resp = await self._call(self.stub.SetConnectorStatus, req)
        return {'success': resp.success, 'message': resp.message}

    # ---------- Рыночные данные ----------
    async def get_candles(self, connector: str, symbol: str, timeframe: str,
                          limit: int, start_time: int = 0, end_time: int = 0,
                          market_data_source: str = 'websocket',
                          market_data_source_config: str = '') -> List[List[float]]:
        req = core_pb2.CandlesRequest(
            connector=connector,
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
            start_time=start_time,
            end_time=end_time,
            market_data_source=market_data_source,
            market_data_source_config=market_data_source_config
        )
        resp = await self._call(self.stub.GetCandles, req)
        candles = []
        for c in resp.candles:
            candles.append([c.timestamp, c.open, c.high, c.low, c.close, c.volume])
        return candles

    async def get_ticker(self, connector: str, symbol: str) -> Dict:
        req = core_pb2.TickerRequest(connector=connector, symbol=symbol)
        resp = await self._call(self.stub.GetTicker, req)
        return {
            'last': resp.last,
            'bid': resp.bid,
            'ask': resp.ask,
            'volume': resp.volume
        }

    async def get_symbols(self, connector: str, product_type: str = '') -> List[str]:
        req = core_pb2.SymbolsRequest(connector=connector, product_type=product_type)
        resp = await self._call(self.stub.GetSymbols, req)
        return list(resp.symbols)

    async def get_order_book(self, connector: str, symbol: str, depth: int = 20) -> Dict:
        req = core_pb2.OrderBookRequest(connector=connector, symbol=symbol, depth=depth)
        resp = await self._call(self.stub.GetOrderBook, req)
        return {
            'bids': [[l.price, l.amount] for l in resp.bids],
            'asks': [[l.price, l.amount] for l in resp.asks]
        }

    # ---------- Торговля ----------
    async def create_order(self, connector_name: str, symbol: str, side: str,
                           order_type: str, quantity: float, price: float = 0,
                           preset_tp: float = 0, preset_sl: float = 0) -> Dict:
        req = core_pb2.CreateOrderRequest(
            connector_name=connector_name,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            preset_tp=preset_tp,
            preset_sl=preset_sl
        )
        resp = await self._call(self.stub.CreateOrder, req)
        if resp.success:
            return {'success': True, 'order_id': resp.order_id, 'client_oid': resp.client_oid}
        else:
            return {'success': False, 'error': resp.error}

    async def cancel_order(self, connector_name: str, symbol: str, order_id: str) -> Dict:
        req = core_pb2.CancelOrderRequest(
            connector_name=connector_name,
            symbol=symbol,
            order_id=order_id
        )
        resp = await self._call(self.stub.CancelOrder, req)
        return {'success': resp.success, 'message': resp.message}

    async def get_open_orders(self, connector_name: str, symbol: str = '') -> List[Dict]:
        req = core_pb2.GetOpenOrdersRequest(connector_name=connector_name, symbol=symbol)
        try:
            resp = await self._call(self.stub.GetOpenOrders, req)
            if not resp.success:
                logger.warning(f"get_open_orders failed for {connector_name}: {resp.error}")
                return []
            orders = []
            for o in resp.orders:
                orders.append({
                    'order_id': o.order_id,
                    'client_oid': o.client_oid,
                    'symbol': o.symbol,
                    'price': o.price,
                    'quantity': o.quantity,
                    'filled': o.filled,
                    'status': o.status,
                    'side': o.side,
                    'order_type': o.order_type,
                    'timestamp': o.timestamp
                })
            return orders
        except Exception as e:
            logger.error(f"get_open_orders exception for {connector_name}: {e}")
            return []

    async def get_balance(self, connector_name: str, currency: str = '') -> List[Dict]:
        req = core_pb2.GetBalanceRequest(connector_name=connector_name, currency=currency)
        try:
            resp = await self._call(self.stub.GetBalance, req)
            if not resp.success:
                logger.warning(f"get_balance failed for {connector_name}: {resp.error}")
                return []
            balances = []
            for b in resp.balances:
                balances.append({
                    'currency': b.currency,
                    'available': b.available,
                    'frozen': b.frozen,
                    'total': b.total
                })
            return balances
        except Exception as e:
            logger.error(f"get_balance exception for {connector_name}: {e}")
            return []

    async def get_position(self, connector_name: str, symbol: str = '') -> List[Dict]:
        req = core_pb2.GetPositionRequest(connector_name=connector_name, symbol=symbol)
        resp = await self._call(self.stub.GetPosition, req)
        if not resp.success:
            logger.warning(f"get_position failed for {connector_name}: {resp.error}")
            return []
        positions = []
        for p in resp.positions:
            positions.append({
                'symbol': p.symbol,
                'side': p.side,
                'size': p.size,
                'entry_price': p.entry_price,
                'mark_price': p.mark_price,
                'pnl': p.pnl,
                'leverage': p.leverage,
                'margin': p.margin,
                'liquidation_price': p.liquidation_price,
                'margin_mode': p.margin_mode
            })
        return positions

    async def close_position(self, connector_name: str, symbol: str, hold_side: str = '') -> Dict:
        req = core_pb2.ClosePositionRequest(
            connector_name=connector_name,
            symbol=symbol,
            hold_side=hold_side
        )
        resp = await self._call(self.stub.ClosePosition, req)
        return {'success': resp.success, 'message': resp.message}

    async def set_leverage(self, connector_name: str, symbol: str, leverage: int,
                           margin_mode: str = 'crossed') -> Dict:
        req = core_pb2.SetLeverageRequest(
            connector_name=connector_name,
            symbol=symbol,
            leverage=leverage,
            margin_mode=margin_mode
        )
        resp = await self._call(self.stub.SetLeverage, req)
        return {'success': resp.success, 'message': resp.message}

    async def set_tpsl(self, connector_name: str, symbol: str, hold_side: str,
                       trigger_price: float, execute_price: float,
                       tpsl_type: str, size: float = 0) -> Dict:
        req = core_pb2.SetTPSLRequest(
            connector_name=connector_name,
            symbol=symbol,
            hold_side=hold_side,
            trigger_price=trigger_price,
            execute_price=execute_price,
            tpsl_type=tpsl_type,
            size=size
        )
        resp = await self._call(self.stub.SetTPSL, req)
        return {'success': resp.success, 'message': resp.message}

    # ---------- Логи и ручные вызовы ----------
    async def get_logs_since(self, since_timestamp: int, limit: int = 1000) -> List[Dict]:
        req = core_pb2.GetLogsSinceRequest(since_timestamp=since_timestamp, limit=limit)
        resp = await self._call(self.stub.GetLogsSince, req)
        logs = []
        for l in resp.logs:
            logs.append({
                'timestamp': l.timestamp,
                'level': l.level,
                'category': l.category,
                'message_ru': l.message_ru
            })
        return logs

    async def call_manual_bot(self, bot_id: int, method: str, params: Dict) -> Dict:
        req = core_pb2.CallManualBotRequest(
            bot_id=bot_id,
            method=method,
            params_json=json.dumps(params)
        )
        resp = await self._call(self.stub.CallManualBot, req)
        if resp.success:
            result = json.loads(resp.result_json) if resp.result_json else {}
            return {'success': True, 'result': result}
        else:
            return {'success': False, 'error': resp.error}

    async def call_bot_method(self, bot_id: int, method_name: str, params: Dict) -> Dict:
        req = core_pb2.CallBotMethodRequest(
            bot_id=bot_id,
            method_name=method_name,
            params_json=json.dumps(params)
        )
        resp = await self._call(self.stub.CallBotMethod, req)
        if resp.success:
            result = json.loads(resp.result_json) if resp.result_json else {}
            return {'success': True, 'result': result}
        else:
            return {'success': False, 'error': resp.error}

    async def get_bot_strategy_description(self, bot_id: int) -> Dict:
        req = core_pb2.GetBotStrategyDescriptionRequest(bot_id=bot_id)
        resp = await self._call(self.stub.GetBotStrategyDescription, req)
        return json.loads(resp.description_json) if resp.description_json else {}

    async def get_bot_params_schema(self, bot_id: int) -> Dict:
        result = await self.call_bot_method(bot_id, "get_params_schema", {})
        if result.get("success"):
            return result.get("result", {})
        return {}

    async def set_bot_parameter(self, bot_id: int, param_name: str, param_value: Any) -> Dict:
        return await self.call_bot_method(bot_id, "set_parameter", {"name": param_name, "value": param_value})

    async def get_bot_market_data_source(self, bot_id: int) -> Dict:
        req = core_pb2.GetBotMarketDataSourceRequest(bot_id=bot_id)
        resp = await self._call(self.stub.GetBotMarketDataSource, req)
        return {"source": resp.source, "config": resp.config}

    async def get_all_bots_status(self) -> List[Dict]:
        bots = await self.get_bots_list()
        result = []
        for bot in bots:
            status = await self.get_bot_status(bot["id"])
            trades = await self.get_bot_trades(bot["id"], limit=1000)
            closed_count = len([t for t in trades if t.get("close_time", 0) > 0])
            total_pnl = sum(t.get("pnl", 0) for t in trades)
            result.append({
                "id": bot["id"],
                "name": bot["name"],
                "running": status["running"],
                "position_open": status["position_open"],
                "side": status["side"],
                "entry_price": status["entry_price"],
                "symbol": status["symbol"],
                "closed_trades": closed_count,
                "pnl": total_pnl
            })
        return result

    # ---------- Streaming свечей ----------
    def subscribe_candles_stream(self, request: core_pb2.SubscribeCandlesRequest):
        metadata = [('authorization', f'Bearer {self.password}')]
        return self.stub.SubscribeCandles(request, metadata=metadata)

    # ---------- НОВЫЙ МЕТОД для получения схемы параметров стратегии ----------
    async def get_strategy_params_schema(self, strategy_name: str) -> Dict:
        """Получить схему параметров стратегии по её имени (без запуска бота)."""
        req = core_pb2.GetStrategyParamsSchemaRequest(strategy_name=strategy_name)
        resp = await self._call(self.stub.GetStrategyParamsSchema, req)
        return json.loads(resp.schema_json) if resp.schema_json else {}