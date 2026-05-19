# utils/discover_connectors.py
import os
import sys
import importlib
import inspect
import logging
from typing import List, Tuple
from connectors.base import ExchangeConnector

CONNECTORS_DIR = "connectors"
logger = logging.getLogger(__name__)


def discover_connectors() -> List[Tuple[str, ExchangeConnector, type]]:
    """
    Обнаруживает все коннекторы в подпапках connectors/ (рекурсивно, исключая base).
    Возвращает список кортежей (exchange_name, instance, class).
    """
    connectors = []
    if not os.path.exists(CONNECTORS_DIR):
        os.makedirs(CONNECTORS_DIR)

    for root, dirs, files in os.walk(CONNECTORS_DIR):
        if "base" in root or "__pycache__" in root:
            continue

        for file in files:
            if file.endswith("_connector.py"):
                rel_path = os.path.relpath(root, CONNECTORS_DIR)
                module_parts = ["connectors"] + rel_path.split(os.sep) + [file[:-3]]
                module_name = ".".join(module_parts)

                try:
                    module = importlib.import_module(module_name)
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, ExchangeConnector) and obj != ExchangeConnector:
                            exchange_name = rel_path.split(os.sep)[-1] if rel_path != '.' else "unknown"
                            # Создаём экземпляр без конфига (только для метаданных)
                            instance = obj({})
                            connectors.append((exchange_name, instance, obj))
                            logger.debug(f"🔌 Найден коннектор: {exchange_name} -> {name}")
                except Exception as e:
                    logger.error(f"Ошибка загрузки {module_name}: {e}")

    return connectors


def get_available_exchanges() -> List[str]:
    """
    Возвращает список имён бирж, для которых есть реализованный коннектор
    в папке connectors/ (т.е. подпапка с *_connector.py).
    """
    exchanges = set()
    if not os.path.exists(CONNECTORS_DIR):
        return []
    for root, dirs, files in os.walk(CONNECTORS_DIR):
        if "base" in root or "__pycache__" in root:
            continue
        for file in files:
            if file.endswith("_connector.py"):
                rel_path = os.path.relpath(root, CONNECTORS_DIR)
                if rel_path != '.':
                    exchange_name = rel_path.split(os.sep)[-1]
                    exchanges.add(exchange_name)
    return sorted(exchanges)