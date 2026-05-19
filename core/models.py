# core/models.py
from sqlalchemy import Column, Integer, String, Float, BigInteger, Boolean, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class Bot(Base):
    __tablename__ = 'bots'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    strategy = Column(String)
    connector = Column(String)
    symbol = Column(String)
    timeframe = Column(String)
    margin_mode = Column(String)
    leverage = Column(Integer)
    position_size = Column(Float)
    params = Column(String)
    enabled = Column(Boolean, default=True)
    emulator_enabled = Column(Boolean, default=False)
    created_at = Column(BigInteger, default=0)
    product_type = Column(String, default='USDT-FUTURES')
    market_data_source = Column(String, default='websocket')
    market_data_source_config = Column(String, default='')

class Trade(Base):
    __tablename__ = 'trades'
    id = Column(Integer, primary_key=True)
    bot_id = Column(Integer)
    bot_name = Column(String)
    symbol = Column(String)
    side = Column(String)
    open_time = Column(BigInteger)
    open_price = Column(Float)
    close_time = Column(BigInteger)
    close_price = Column(Float)
    pnl = Column(Float)
    size = Column(Float)

class Connector(Base):
    __tablename__ = 'connectors'
    name = Column(String, primary_key=True)
    exchange_id = Column(String)
    testnet = Column(Boolean, default=True)
    api_key = Column(String)
    api_secret = Column(String)
    api_passphrase = Column(String)
    product_type = Column(String, default='USDT-FUTURES')
    status = Column(String, default='offline')
    max_retries = Column(Integer, default=3)
    retry_backoff = Column(Float, default=2.0)
    ws_ping_interval = Column(Integer, default=30)
    ws_reconnect_delay = Column(Integer, default=5)
    ip_whitelist = Column(String, default='')
    auto_reconnect = Column(Boolean, default=True)
    retry_on_limit = Column(Boolean, default=True)
    http_timeout_read = Column(Integer, default=10)
    http_timeout_connect = Column(Integer, default=5)
    order_type_default = Column(String, default='limit')

class LogEntry(Base):
    __tablename__ = 'logs'
    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(BigInteger, nullable=False)
    level = Column(String, nullable=False)
    category = Column(String, nullable=False)
    message_ru = Column(String, nullable=False)

class CachedCandle(Base):
    __tablename__ = 'cached_candles'
    id = Column(Integer, primary_key=True)
    symbol = Column(String, index=True)
    interval = Column(String)
    timestamp = Column(BigInteger, index=True)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float)
    volume = Column(Float)

    __table_args__ = (UniqueConstraint('symbol', 'interval', 'timestamp', name='_symbol_interval_ts_uc'),)