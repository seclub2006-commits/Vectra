import pytest
from unittest.mock import Mock, AsyncMock
from gui.chart_v2.controller import ChartController
from gui.async_client import AsyncClient

@pytest.mark.asyncio
async def test_controller_load_history():
    client = Mock(AsyncClient)
    client.get_candles_async = Mock()
    controller = ChartController(client)
    controller.connector = "bitget"
    controller.symbol = "BTCUSDT"
    controller.timeframe = "1H"
    controller._load_history_impl()
    # Проверяем, что вызван get_candles_async
    client.get_candles_async.assert_called_once()