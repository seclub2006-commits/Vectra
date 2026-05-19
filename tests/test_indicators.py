import pytest
from gui.chart_v2.models import Candle
from gui.chart_v2.indicator_manager import EMAIndicator, RSIIndicator, VolumeIndicator

def test_ema_calculation():
    candles = [Candle(i, 100+i, 105+i, 95+i, 102+i, 1000) for i in range(20)]
    ema = EMAIndicator(period=5)
    result = ema.init(candles)
    assert len(result) == len(candles)
    assert result[0] is None  # первые period-1 свечей None
    assert result[-1] is not None
    # Проверяем инкрементальное обновление
    new_candle = Candle(21, 130, 135, 125, 128, 1100)
    new_val = ema.update(new_candle, candles)
    assert new_val is not None

def test_rsi_calculation():
    candles = [Candle(i, 100+i, 105+i, 95+i, 102+i, 1000) for i in range(30)]
    rsi = RSIIndicator(period=14)
    result = rsi.init(candles)
    assert len(result) == len(candles)
    assert result[14] is not None  # после period свечей