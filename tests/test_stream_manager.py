# tests/test_stream_manager.py
import pytest
from unittest.mock import Mock, AsyncMock, patch
from PyQt5.QtCore import QCoreApplication
from gui.chart_v2.stream_manager import StreamManager, StreamKey
from gui.async_client import AsyncClient
from gui.chart_v2.models import Candle


@pytest.fixture
def async_client_mock():
    client = Mock(AsyncClient)
    client._sync = Mock()
    client._sync.stub = Mock()
    client._sync.password = "test"
    return client


@pytest.fixture
def stream_manager(async_client_mock):
    return StreamManager(async_client_mock)


def test_subscribe_creates_stream(stream_manager, qtbot):
    """Проверяет, что при первой подписке создаётся новый стрим."""
    callback = Mock()
    unsubscribe = stream_manager.subscribe(
        connector="bitget",
        symbol="BTCUSDT",
        timeframe="1H",
        market_data_source="websocket",
        market_data_source_config="",
        callback=callback
    )
    
    # Проверяем, что в _streams появился ключ
    key = StreamKey("bitget", "BTCUSDT", "1H", "websocket", "")
    assert key in stream_manager._streams
    info = stream_manager._streams[key]
    assert info['refcount'] == 1
    assert callback in info['callbacks']
    assert info['worker'] is not None
    
    # Отписываемся
    unsubscribe()
    assert key not in stream_manager._streams


def test_subscribe_reuses_existing_stream(stream_manager, qtbot):
    """Проверяет, что повторная подписка с теми же параметрами не создаёт новый стрим."""
    callback1 = Mock()
    callback2 = Mock()
    
    unsub1 = stream_manager.subscribe("bitget", "BTCUSDT", "1H", "websocket", "", callback1)
    key = StreamKey("bitget", "BTCUSDT", "1H", "websocket", "")
    first_worker = stream_manager._streams[key]['worker']
    
    unsub2 = stream_manager.subscribe("bitget", "BTCUSDT", "1H", "websocket", "", callback2)
    
    # Должен быть тот же worker
    assert stream_manager._streams[key]['worker'] is first_worker
    assert stream_manager._streams[key]['refcount'] == 2
    assert callback2 in stream_manager._streams[key]['callbacks']
    
    unsub1()
    assert stream_manager._streams[key]['refcount'] == 1
    unsub2()
    assert key not in stream_manager._streams


def test_candle_received_calls_callbacks(stream_manager, qtbot):
    """Проверяет, что полученная свеча передаётся всем подписчикам."""
    callback1 = Mock()
    callback2 = Mock()
    
    stream_manager.subscribe("bitget", "BTCUSDT", "1H", "websocket", "", callback1)
    stream_manager.subscribe("bitget", "BTCUSDT", "1H", "websocket", "", callback2)
    
    key = StreamKey("bitget", "BTCUSDT", "1H", "websocket", "")
    worker = stream_manager._streams[key]['worker']
    
    # Эмулируем получение свечи от worker
    test_candle = Candle(timestamp=1000, open=50000, high=51000, low=49000, close=50500, volume=100)
    # Испускаем сигнал от worker (в реальности сигнал приходит из потока, но мы вызываем напрямую)
    worker.candle_received.emit(test_candle)
    
    # Даём время на обработку сигнала в главном цикле
    qtbot.wait(10)
    
    callback1.assert_called_once_with(test_candle)
    callback2.assert_called_once_with(test_candle)


def test_shutdown_stops_all_streams(stream_manager, qtbot):
    """Проверяет, что shutdown останавливает все стримы."""
    stream_manager.subscribe("bitget", "BTCUSDT", "1H", "websocket", "", Mock())
    stream_manager.subscribe("binance", "ETHUSDT", "5m", "websocket", "", Mock())
    
    assert len(stream_manager._streams) == 2
    workers = [info['worker'] for info in stream_manager._streams.values()]
    
    stream_manager.shutdown()
    
    assert len(stream_manager._streams) == 0
    # Проверяем, что у каждого worker был вызван stop
    for worker in workers:
        assert worker._running is False