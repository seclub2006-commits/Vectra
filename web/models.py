# web/models.py (полный файл)
from pydantic import BaseModel
from typing import Dict, List, Optional, Any


class LoginRequest(BaseModel):
    password: str


class StartBotRequest(BaseModel):
    bot_id: int = 0
    name: str
    strategy: str
    connector_name: str
    symbol: str
    timeframe: str
    position_size: float
    params: Dict[str, str]
    market_data_source: str = "websocket"
    market_data_source_config: str = ""


class StopBotRequest(BaseModel):
    bot_id: int


class DeleteBotRequest(BaseModel):
    bot_id: int


class UpdateBotConfigRequest(BaseModel):
    bot_id: int
    connector_name: str
    symbol: str
    timeframe: str
    position_size: float
    params: Dict[str, Any]
    emulator_enabled: bool
    market_data_source: str = "websocket"
    market_data_source_config: str = ""


class CreateConnectorRequest(BaseModel):
    name: str
    exchange_id: str
    testnet: bool = True
    api_key: str
    api_secret: str
    api_passphrase: str = ""
    product_type: str = "USDT-FUTURES"
    max_retries: int = 3
    retry_backoff: float = 2.0
    ws_ping_interval: int = 30
    ws_reconnect_delay: int = 5
    ip_whitelist: str = ""
    auto_reconnect: bool = True
    retry_on_limit: bool = True
    http_timeout_read: int = 10
    http_timeout_connect: int = 5
    order_type_default: str = "limit"


class UpdateConnectorRequest(BaseModel):
    name: str
    settings: Dict[str, Any]


class SetConnectorStatusRequest(BaseModel):
    name: str
    status: str  # online / offline


class GetCandlesRequest(BaseModel):
    connector: str
    symbol: str
    timeframe: str
    limit: int = 100
    start_time: int = 0
    end_time: int = 0
    market_data_source: str = "websocket"
    market_data_source_config: str = ""


class CreateOrderRequest(BaseModel):
    connector_name: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: float = 0
    preset_tp: float = 0
    preset_sl: float = 0


class CancelOrderRequest(BaseModel):
    connector_name: str
    symbol: str
    order_id: str


class SetLeverageRequest(BaseModel):
    connector_name: str
    symbol: str
    leverage: int
    margin_mode: str = "crossed"


class SetTPSLRequest(BaseModel):
    connector_name: str
    symbol: str
    hold_side: str
    trigger_price: float
    execute_price: float = 0
    tpsl_type: str
    size: float = 0


class ClosePositionRequest(BaseModel):
    connector_name: str
    symbol: str
    hold_side: str = ""


class CallManualBotRequest(BaseModel):
    bot_id: int
    method: str
    params: Dict[str, Any] = {}


class CallBotMethodRequest(BaseModel):
    bot_id: int
    method_name: str
    params: Dict[str, Any] = {}


class GetBotStrategyDescriptionRequest(BaseModel):
    bot_id: int


class GetLogsSinceRequest(BaseModel):
    since_timestamp: int
    limit: int = 1000


# ---- Новые модели ----
class GetBotParamsSchemaRequest(BaseModel):
    bot_id: int


class SetBotParameterRequest(BaseModel):
    bot_id: int
    param_name: str
    param_value: Any


class GetBotTradesRequest(BaseModel):
    bot_id: int
    limit: int = 100