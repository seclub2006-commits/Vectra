# core/market_data_provider_factory.py
import json
from typing import Optional
from core.market_data_provider import MarketDataProvider
from core.real_market_data_provider import RealMarketDataProvider
from core.historical_market_data_provider import HistoricalMarketDataProvider
from core.csv_market_data_provider import CSVMarketDataProvider
from connectors.base.exchange_connector import ExchangeConnector
from core.database import Database

class MarketDataProviderFactory:
    @staticmethod
    def create(provider_type: str,
               connector: ExchangeConnector,
               symbol: str,
               db: Optional[Database] = None,
               config_json: str = '') -> MarketDataProvider:
        config = json.loads(config_json) if config_json else {}
        if provider_type == 'websocket':
            return RealMarketDataProvider(connector, mode='websocket')
        elif provider_type == 'rest_polling':
            interval = config.get('polling_interval', 5)
            return RealMarketDataProvider(connector, mode='rest_polling', polling_interval=interval)
        elif provider_type == 'database':
            if not db:
                raise ValueError("Database instance required for 'database' provider")
            return HistoricalMarketDataProvider(connector, db)
        elif provider_type == 'csv':
            csv_path = config.get('csv_path')
            if not csv_path:
                raise ValueError("CSV path missing in config")
            replay_delay = config.get('replay_delay_seconds', 60.0)
            return CSVMarketDataProvider(csv_path, symbol, replay_delay)
        else:
            raise ValueError(f"Unknown market data provider type: {provider_type}")