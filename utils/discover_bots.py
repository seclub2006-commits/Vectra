# utils/discover_bots.py
import os
import sys
import importlib
import inspect
import logging
from typing import Dict, Tuple

BOTS_DIR = "bots"
logger = logging.getLogger(__name__)


def discover_bots() -> Dict[str, Dict[str, Tuple[type, str]]]:
    """
    Обнаруживает все классы ботов в папке bots/ (рекурсивно).
    Возвращает словарь: {категория: {отображаемое_имя: (класс, полный_импортный_путь)}}
    где полный_импортный_путь например: 'trend.ema_bot.EmaBot'
    
    ВАЖНО: больше не создаёт файлы автоматически. Если папка bots пуста или отсутствует,
    возвращает пустой словарь.
    """
    bots_dict = {}

    # Проверяем существование папки bots
    if not os.path.exists(BOTS_DIR):
        logger.warning(f"Папка {BOTS_DIR} не найдена. Боты не будут загружены.")
        return bots_dict

    # Добавляем корневую папку bots в sys.path для импорта
    bots_root = os.path.abspath(BOTS_DIR)
    if bots_root not in sys.path:
        sys.path.insert(0, bots_root)

    for root, dirs, files in os.walk(BOTS_DIR):
        rel_path = os.path.relpath(root, BOTS_DIR)
        if rel_path == '.':
            category = 'general'
        else:
            category = rel_path

        for file in files:
            if file.endswith(".py") and file not in ["__init__.py", "base_bot.py"]:
                module_rel_path = os.path.join(rel_path, file[:-3]) if rel_path != '.' else file[:-3]
                module_name = f"bots.{module_rel_path.replace(os.sep, '.')}"
                try:
                    module = importlib.import_module(module_name)
                    from bots.base_bot import BaseBot
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if issubclass(obj, BaseBot) and obj != BaseBot:
                            full_import_path = module_rel_path.replace(os.sep, '.') + '.' + name
                            if category not in bots_dict:
                                bots_dict[category] = {}
                            bots_dict[category][name] = (obj, full_import_path)
                            logger.debug(f"Найден бот: {category}/{name} -> {full_import_path}")
                except Exception as e:
                    logger.error(f"Ошибка загрузки бота {module_name}: {e}")

    if not bots_dict:
        logger.warning("Не найдено ни одного бота в папке bots/. Создайте ботов вручную или скопируйте примеры.")
    
    return bots_dict