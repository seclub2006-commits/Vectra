# utils/time_provider.py
import asyncio
"""
Абстрактный провайдер времени для тестирования и симуляции.
Позволяет заменить реальное время на ускоренное или управляемое в бэктестах.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional
import time as real_time


class TimeProvider(ABC):
    """Интерфейс для получения времени и пауз."""

    @abstractmethod
    def now_timestamp(self) -> float:
        """Текущее время в секундах с эпохи Unix (float)."""
        pass

    @abstractmethod
    def now_timestamp_ms(self) -> int:
        """Текущее время в миллисекундах (int)."""
        pass

    @abstractmethod
    def now_datetime(self) -> datetime:
        """Текущее время как datetime."""
        pass

    @abstractmethod
    async def sleep(self, seconds: float):
        """Приостановить выполнение на указанное количество секунд (виртуальных или реальных)."""
        pass


class RealTimeProvider(TimeProvider):
    """Реальная реализация времени (использует стандартный модуль time)."""

    def now_timestamp(self) -> float:
        return real_time.time()

    def now_timestamp_ms(self) -> int:
        return int(real_time.time() * 1000)

    def now_datetime(self) -> datetime:
        return datetime.now()

    async def sleep(self, seconds: float):
        await asyncio.sleep(seconds)   # asyncio.sleep использует реальное время


# Для симуляции можно будет создать SimulatedTimeProvider,
# который ускоряет или замедляет время, но это уже не абстракция.