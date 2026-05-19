# connectors/bitget/__init__.py
# connectors/__init__.py
from .base.exchange_connector import ExchangeConnector
from .base.exceptions import ConnectorError, ConfigError, APIError, NetworkError, RateLimitError, AuthError

__all__ = [
    "ExchangeConnector",
    "ConnectorError", "ConfigError", "APIError", "NetworkError", "RateLimitError", "AuthError",
    "get_connector_class"
]

def get_connector_class(exchange_id: str, product_type: str = None):
    """
    Возвращает класс коннектора по имени биржи и типу продукта.
    :param exchange_id: идентификатор биржи (например, 'bitget')
    :param product_type: тип продукта ('SPOT', 'USDT-FUTURES', 'COIN-FUTURES', 'USDC-FUTURES')
    :return: класс коннектора или None
    """
    if exchange_id.lower() != 'bitget':
        return None
    
    if product_type and product_type.upper() == 'SPOT':
        from .bitget.spot import BitgetSpotConnector
        return BitgetSpotConnector
    else:
        from .bitget.futures import BitgetFuturesConnector
        return BitgetFuturesConnector