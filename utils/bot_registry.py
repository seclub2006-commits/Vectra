# utils/bot_registry.py
"""
Реестр разрешённых классов ботов.
Предотвращает инъекцию произвольного кода через параметр strategy.
"""

from typing import Dict, Type, Any
from bots.base_bot import BaseBot


class BotRegistry:
    """Синглтон-реестр всех доступных ботов."""
    _instance = None
    _bots: Dict[str, Type[BaseBot]] = {}
    _display_names: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._init_registry()
        return cls._instance

    def _init_registry(self):
        from utils.discover_bots import discover_bots
        bots_by_category = discover_bots()
        for category, bots in bots_by_category.items():
            for display_name, (bot_class, full_path) in bots.items():
                self._bots[full_path] = bot_class
                self._display_names[display_name] = full_path
                self._bots[display_name] = bot_class

    def get_bot_class(self, identifier: str) -> Type[BaseBot]:
        if identifier in self._bots:
            return self._bots[identifier]
        if identifier in self._display_names:
            full_path = self._display_names[identifier]
            return self._bots[full_path]
        raise ValueError(f"Unknown bot strategy: {identifier}. Available: {list(self._bots.keys())}")

    def is_valid_strategy(self, identifier: str) -> bool:
        return identifier in self._bots or identifier in self._display_names

    def get_all_strategies(self) -> Dict[str, str]:
        return self._display_names.copy()


_registry = None

def get_bot_registry() -> BotRegistry:
    global _registry
    if _registry is None:
        _registry = BotRegistry()
    return _registry