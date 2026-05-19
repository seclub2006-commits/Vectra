# connectors/bitget/futures/__init__.py
import logging
import traceback
from typing import List

from connectors.bitget.common import BitgetBaseConnector
from .market import MarketMixin
from .account import AccountMixin
from .position import PositionMixin
from .orders import OrderMixin
from .trigger import TriggerMixin
from .websocket import WebSocketMixin

logger = logging.getLogger(__name__)


class BitgetFuturesConnector(
    MarketMixin,
    AccountMixin,
    PositionMixin,
    OrderMixin,
    TriggerMixin,
    WebSocketMixin,
    BitgetBaseConnector
):
    def __init__(self, name: str, config: dict):
        super().__init__(name, config)
        self.margin_coin = config.get('margin_coin', 'USDT')
        self.logger = logging.getLogger(f"connector.futures.{name}")

    async def connect(self) -> bool:
        try:
            self.logger.info("Connecting to Bitget Futures (demo mode) ...")
            
            # Проверка наличия ключей (без вывода в лог)
            if not self.api_key:
                self.logger.error("ERROR: api_key is empty! Check encryption/decryption.")
                self.status = 'offline'
                return False
            if not self.api_secret:
                self.logger.error("ERROR: api_secret is empty!")
                self.status = 'offline'
                return False
            if not self.api_passphrase:
                self.logger.error("ERROR: api_passphrase is empty!")
                self.status = 'offline'
                return False
            
            # Пытаемся получить баланс – лучший тест подключения
            try:
                balances = await self.get_balance()
                self.logger.info(f"Balance fetched: {len(balances)} coins")
                if balances:
                    usdt = next((b for b in balances if b['currency'] == 'USDT'), None)
                    if usdt:
                        self.logger.info(f"USDT balance: available={usdt['available']}, equity={usdt.get('equity', 0)}")
            except Exception as e:
                self.logger.error(f"Failed to get balance: {type(e).__name__} - {e}")
                self.status = 'offline'
                return False
            
            self.status = 'online'
            self.logger.info(f"Futures connector {self.name} connected (product={self.product_type})")
            return True
        except Exception as e:
            traceback.print_exc()
            self.logger.error(f"Futures connector {self.name} connection failed: {type(e).__name__} - {e}")
            self.status = 'offline'
            return False

    async def get_markets(self) -> List[str]:
        contracts = await self.get_contracts(self.product_type)
        return [c['symbol'] for c in contracts]

    async def cleanup_all(self):
        """Отменить все ордера, закрыть все позиции и удалить плановые ордера."""
        self.logger.info("Cleaning up all futures state...")
        try:
            await self.cancel_all_orders()
        except Exception as e:
            self.logger.debug(f"Cancel all orders error (ignored): {e}")
        positions = await self.get_positions()
        if positions and isinstance(positions, list):
            for pos in positions:
                if pos.get('size', 0) != 0:
                    try:
                        await self.close_position(pos['symbol'], pos['side'])
                    except Exception as e:
                        self.logger.debug(f"Close position error (ignored): {e}")
        triggers = await self.get_trigger_orders()
        if triggers and isinstance(triggers, list):
            for t in triggers:
                try:
                    await self.cancel_trigger_order(t['symbol'], t['orderId'])
                except Exception as e:
                    self.logger.debug(f"Cancel trigger order error (ignored): {e}")
        self.logger.info("Cleanup complete")

    async def disconnect(self):
        """
        Переопределяем disconnect, чтобы закрыть WebSocket-менеджер.
        """
        if hasattr(self, '_ws_manager') and self._ws_manager is not None:
            try:
                await self._ws_manager.stop()
                self.logger.info("WebSocket manager stopped")
            except Exception as e:
                self.logger.error(f"Error stopping WebSocket manager: {e}")
        await super().disconnect()