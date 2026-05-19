# core/database.py
import json
import time
import os
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, delete, update, and_

from core.config_storage import ConfigStorage
from core.models import Base, Bot, Trade, Connector, LogEntry, CachedCandle
from utils.encryption import encrypt_data, decrypt_data

logger = logging.getLogger(__name__)


class Database(ConfigStorage):
    def __init__(self, db_url: str = "sqlite+aiosqlite:///vectra.db"):
        self.db_url = db_url
        self.engine = None
        self.session_maker = None

    async def init(self):
        self.engine = create_async_engine(self.db_url)
        self.session_maker = sessionmaker(self.engine, class_=AsyncSession, expire_on_commit=False)
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self):
        if self.engine:
            await self.engine.dispose()

    async def get_bot(self, bot_id: int) -> Optional[Bot]:
        async with self.session_maker() as session:
            result = await session.execute(select(Bot).where(Bot.id == bot_id))
            return result.scalar_one_or_none()

    async def get_bots(self) -> List[Bot]:
        async with self.session_maker() as session:
            result = await session.execute(select(Bot))
            return result.scalars().all()

    async def save_bot(self, bot: Bot) -> Bot:
        if isinstance(bot.emulator_enabled, str):
            bot.emulator_enabled = bot.emulator_enabled.lower() == 'true'
        logger.info(f"save_bot: bot.id={bot.id}, emulator_enabled={bot.emulator_enabled}")
        async with self.session_maker() as session:
            if bot.id is None:
                session.add(bot)
                logger.info("save_bot: adding new bot")
            else:
                bot = await session.merge(bot)
                logger.info(f"save_bot: merging existing bot id={bot.id}")
            await session.commit()
            if bot.id is None:
                await session.refresh(bot)
            check = await session.get(Bot, bot.id)
            logger.info(f"save_bot: after commit, DB has emulator_enabled={check.emulator_enabled if check else 'N/A'}")
            return bot

    async def update_bot_config(self, bot_id: int, new_config: Dict[str, Any]) -> None:
        logger.info(f"=== update_bot_config START: bot_id={bot_id}, new_config={new_config} ===")
        async with self.session_maker() as session:
            bot = await session.get(Bot, bot_id)
            if not bot:
                logger.warning(f"update_bot_config: bot {bot_id} not found")
                return

            if 'connector_name' in new_config:
                old = bot.connector
                bot.connector = new_config['connector_name']
                logger.info(f"  -> connector_name: '{old}' -> '{bot.connector}'")
            if 'symbol' in new_config:
                old = bot.symbol
                bot.symbol = new_config['symbol']
                logger.info(f"  -> symbol: '{old}' -> '{bot.symbol}'")
            if 'timeframe' in new_config:
                old = bot.timeframe
                bot.timeframe = new_config['timeframe']
                logger.info(f"  -> timeframe: '{old}' -> '{bot.timeframe}'")
            if 'position_size' in new_config:
                old = bot.position_size
                bot.position_size = new_config['position_size']
                logger.info(f"  -> position_size: {old} -> {bot.position_size}")
            if 'emulator_enabled' in new_config:
                old = bot.emulator_enabled
                emu_val = new_config['emulator_enabled']
                if isinstance(emu_val, str):
                    emu_val = emu_val.lower() == 'true'
                bot.emulator_enabled = emu_val
                logger.info(f"  -> emulator_enabled: {old} -> {bot.emulator_enabled}")
            
            if 'market_data_source' in new_config:
                old = bot.market_data_source
                bot.market_data_source = new_config['market_data_source']
                logger.info(f"  -> market_data_source: '{old}' -> '{bot.market_data_source}'")
            if 'market_data_source_config' in new_config:
                old = bot.market_data_source_config
                bot.market_data_source_config = new_config['market_data_source_config']
                logger.info(f"  -> market_data_source_config: '{old}' -> '{bot.market_data_source_config}'")

            if 'params' in new_config and isinstance(new_config['params'], dict):
                old_params = {}
                if bot.params:
                    try:
                        old_params = json.loads(bot.params)
                    except json.JSONDecodeError:
                        logger.error(f"Invalid JSON in bot.params: {bot.params}, resetting")
                old_params.update(new_config['params'])
                bot.params = json.dumps(old_params)
                logger.info(f"  -> params merged: {old_params}")

            try:
                await session.commit()
                await session.refresh(bot)
                logger.info(f"=== update_bot_config SUCCESS: bot_id={bot_id}, new timeframe={bot.timeframe}, params={bot.params} ===")
            except Exception as e:
                logger.error(f"Ошибка при коммите: {e}", exc_info=True)
                await session.rollback()
                raise

    async def delete_bot(self, bot_id: int) -> None:
        async with self.session_maker() as session:
            bot = await session.get(Bot, bot_id)
            if bot:
                await session.delete(bot)
                await session.commit()

    async def add_trade(self, trade: Trade) -> None:
        async with self.session_maker() as session:
            session.add(trade)
            await session.commit()

    async def get_trades(self, bot_id: Optional[int] = None, limit: int = 100) -> List[Trade]:
        async with self.session_maker() as session:
            query = select(Trade)
            if bot_id is not None:
                query = query.where(Trade.bot_id == bot_id)
            query = query.order_by(Trade.close_time.desc()).limit(limit)
            result = await session.execute(query)
            return result.scalars().all()

    # ==================== КОННЕКТОРЫ ====================
    async def get_connector(self, name: str) -> Optional[Connector]:
        async with self.session_maker() as session:
            result = await session.execute(select(Connector).where(Connector.name == name))
            conn = result.scalar_one_or_none()
            if conn:
                conn.api_key = decrypt_data(conn.api_key)
                conn.api_secret = decrypt_data(conn.api_secret)
                conn.api_passphrase = decrypt_data(conn.api_passphrase)
                if not conn.api_key:
                    logger.warning(f"Расшифровка ключа для коннектора {conn.name} вернула пустую строку.")
            return conn

    async def get_connectors_list(self) -> List[Connector]:
        async with self.session_maker() as session:
            result = await session.execute(select(Connector))
            connectors = result.scalars().all()
            for conn in connectors:
                try:
                    conn.api_key = decrypt_data(conn.api_key)
                    conn.api_secret = decrypt_data(conn.api_secret)
                    conn.api_passphrase = decrypt_data(conn.api_passphrase)
                    if not conn.api_key:
                        logger.warning(f"Расшифровка ключа для коннектора {conn.name} вернула пустую строку.")
                except Exception as e:
                    logger.error(f"Ошибка расшифровки коннектора {conn.name}: {e}")
                    conn.api_key = conn.api_secret = conn.api_passphrase = ''
            return connectors

    async def save_connector(self, connector: Connector) -> None:
        logger.info(f"save_connector: name={connector.name}")
        if connector.api_key and not connector.api_key.startswith('gAAAAA'):
            connector.api_key = encrypt_data(connector.api_key)
        if connector.api_secret and not connector.api_secret.startswith('gAAAAA'):
            connector.api_secret = encrypt_data(connector.api_secret)
        if connector.api_passphrase and not connector.api_passphrase.startswith('gAAAAA'):
            connector.api_passphrase = encrypt_data(connector.api_passphrase)

        async with self.session_maker() as session:
            await session.merge(connector)
            await session.commit()

    async def delete_connector(self, name: str) -> None:
        async with self.session_maker() as session:
            conn = await session.get(Connector, name)
            if conn:
                await session.delete(conn)
                await session.commit()

    # ==================== ЛОГИ ====================
    async def add_log(self, level: str, category: str, message_ru: str) -> None:
        log = LogEntry(
            timestamp=int(time.time() * 1000),
            level=level.upper(),
            category=category,
            message_ru=message_ru
        )
        async with self.session_maker() as session:
            session.add(log)
            await session.commit()

    async def get_logs_since(self, since_timestamp_ms: int, limit: int = 1000) -> List[Dict]:
        async with self.session_maker() as session:
            stmt = select(LogEntry).where(LogEntry.timestamp >= since_timestamp_ms).order_by(LogEntry.timestamp)
            result = await session.execute(stmt)
            logs = result.scalars().all()
            logs = logs[-limit:] if len(logs) > limit else logs
            return [
                {
                    'timestamp': log.timestamp,
                    'level': log.level,
                    'category': log.category,
                    'message_ru': log.message_ru
                }
                for log in logs
            ]

    async def delete_old_logs(self, days: int = None) -> int:
        if days is None:
            days = int(os.getenv('LOG_RETENTION_DAYS', '30'))
        threshold = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
        stmt = delete(LogEntry).where(LogEntry.timestamp < threshold)
        async with self.session_maker() as session:
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount

    # ==================== КЭШИРОВАННЫЕ СВЕЧИ ====================
    async def get_cached_candles(self, symbol: str, interval: str, limit: int = 100,
                                 start_time: Optional[int] = None,
                                 end_time: Optional[int] = None) -> List[CachedCandle]:
        async with self.session_maker() as session:
            query = select(CachedCandle).where(
                CachedCandle.symbol == symbol,
                CachedCandle.interval == interval
            )
            if start_time:
                query = query.where(CachedCandle.timestamp >= start_time)
            if end_time:
                query = query.where(CachedCandle.timestamp <= end_time)
            query = query.order_by(CachedCandle.timestamp.desc()).limit(limit)
            result = await session.execute(query)
            return result.scalars().all()

    async def save_cached_candles(self, candles: List[Dict], symbol: str, interval: str) -> None:
        async with self.session_maker() as session:
            for c in candles:
                existing = await session.execute(
                    select(CachedCandle).where(
                        CachedCandle.symbol == symbol,
                        CachedCandle.interval == interval,
                        CachedCandle.timestamp == c['timestamp']
                    )
                )
                if not existing.scalar_one_or_none():
                    cached = CachedCandle(
                        symbol=symbol,
                        interval=interval,
                        timestamp=c['timestamp'],
                        open=c['open'],
                        high=c['high'],
                        low=c['low'],
                        close=c['close'],
                        volume=c['volume']
                    )
                    session.add(cached)
            await session.commit()