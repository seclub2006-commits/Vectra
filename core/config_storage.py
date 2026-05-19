# core/config_storage.py
"""
Абстрактное хранилище конфигураций (ботов, коннекторов, пользовательских настроек).
Позволяет легко переключаться между SQLite, файлами JSON, Redis и т.д.
"""

from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any
from core.models import Bot, Connector, Trade


class ConfigStorage(ABC):
    """
    Интерфейс для хранения и загрузки конфигураций ботов, коннекторов, сделок.
    """

    # ==================== Боты ====================

    @abstractmethod
    async def get_bot(self, bot_id: int) -> Optional[Bot]:
        """Загрузить бота по ID."""
        pass

    @abstractmethod
    async def get_bots(self) -> List[Bot]:
        """Загрузить всех ботов."""
        pass

    @abstractmethod
    async def save_bot(self, bot: Bot) -> None:
        """Сохранить или обновить бота."""
        pass

    @abstractmethod
    async def update_bot_config(self, bot_id: int, new_config: Dict[str, Any]) -> None:
        """Частично обновить конфигурацию бота (без замены всего объекта)."""
        pass

    @abstractmethod
    async def delete_bot(self, bot_id: int) -> None:
        """Удалить бота."""
        pass

    # ==================== Сделки ====================

    @abstractmethod
    async def add_trade(self, trade: Trade) -> None:
        """Добавить новую сделку в историю."""
        pass

    @abstractmethod
    async def get_trades(self, bot_id: Optional[int] = None, limit: int = 100) -> List[Trade]:
        """Получить список сделок (опционально для конкретного бота)."""
        pass

    # ==================== Коннекторы ====================

    @abstractmethod
    async def get_connector(self, name: str) -> Optional[Connector]:
        """Загрузить коннектор по имени."""
        pass

    @abstractmethod
    async def get_connectors_list(self) -> List[Connector]:
        """Загрузить все коннекторы."""
        pass

    @abstractmethod
    async def save_connector(self, connector: Connector) -> None:
        """Сохранить или обновить коннектор."""
        pass

    @abstractmethod
    async def delete_connector(self, name: str) -> None:
        """Удалить коннектор."""
        pass

    # ==================== Логи ====================

    @abstractmethod
    async def add_log(self, level: str, category: str, message_ru: str) -> None:
        """Добавить запись лога."""
        pass

    @abstractmethod
    async def get_logs_since(self, since_timestamp_ms: int, limit: int = 1000) -> List[Dict]:
        """Получить логи с указанной временной метки (включительно), отсортированные по времени."""
        pass

    # ==================== Общие методы ====================

    @abstractmethod
    async def init(self) -> None:
        """Инициализировать хранилище (создать таблицы, файлы, подключиться к БД)."""
        pass

    @abstractmethod
    async def close(self) -> None:
        """Закрыть соединения с хранилищем (если требуется)."""
        pass

    # ==================== Вспомогательные методы (опциональные) ====================

    async def clear_all(self) -> None:
        """Очистить все данные (опасно! – по умолчанию не реализовано)."""
        raise NotImplementedError("Clear all not implemented for this storage")

    async def export_to_file(self, path: str) -> None:
        """Экспортировать все данные в файл (например, JSON или CSV)."""
        raise NotImplementedError("Export not implemented")

    async def import_from_file(self, path: str) -> None:
        """Импортировать данные из файла."""
        raise NotImplementedError("Import not implemented")