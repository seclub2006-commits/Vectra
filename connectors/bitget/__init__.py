# connectors/bitget/__init__.py
from .spot import BitgetSpotConnector
from .futures import BitgetFuturesConnector

__all__ = ["BitgetSpotConnector", "BitgetFuturesConnector"]