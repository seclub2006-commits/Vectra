# core/bot_worker.py
import asyncio
import logging
import time
import importlib
import traceback
from typing import Dict, Any, Optional, Callable

from connectors.base.exchange_connector import ExchangeConnector
from core.config_storage import ConfigStorage
from core.real_market_data_provider import RealMarketDataProvider
from utils.time_provider import RealTimeProvider

logger = logging.getLogger(__name__)


async def run_bot_task(
    bot_id: int,
    name: str,
    connector: ExchangeConnector,
    bot_full_path: str,
    config: Dict[str, Any],
    cancel_event: asyncio.Event,
    db: ConfigStorage,
    status_callback: Optional[Callable[[int, Dict], None]] = None,
    instance_holder: Optional[Dict] = None,
    task_manager: Optional[Any] = None,  # добавлен параметр
) -> None:
    """
    Асинхронная задача для запуска одного бота.
    При получении сигнала cancel_event останавливает бота.
    Периодически отправляет статус через status_callback.
    Если передан instance_holder, в него будет сохранён экземпляр бота.
    task_manager - ссылка на TaskManager для ручных ботов.
    """
    logger.info(f"Starting bot task {name} (id={bot_id})")

    async def safe_await(coro, default=None):
        try:
            return await coro
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"Bot {name}: error in {coro.__name__ if hasattr(coro, '__name__') else 'coroutine'}: {e}\n{traceback.format_exc()}")
            return default

    # --- Загрузка класса бота ---
    try:
        # bot_full_path должен быть вида "trend.ema_bot.EmaBot"
        parts = bot_full_path.split('.')
        if len(parts) < 2:
            raise ValueError(f"Invalid bot_full_path: {bot_full_path}")
        module_path = "bots." + ".".join(parts[:-1])
        class_name = parts[-1]
        module = importlib.import_module(module_path)
        bot_class = getattr(module, class_name)
        logger.info(f"Bot {name}: imported class {class_name} from {module_path}")
    except Exception as e:
        logger.error(f"Bot {name}: failed to import class {bot_full_path}: {e}\n{traceback.format_exc()}")
        if status_callback:
            status_callback(bot_id, {'running': False, 'error': 'import_failed'})
        return

    # --- Создание провайдера рыночных данных ---
    market_data = RealMarketDataProvider(connector)
    try:
        await safe_await(market_data.connect())
    except Exception as e:
        logger.error(f"Bot {name}: market_data connect failed: {e}")
        if status_callback:
            status_callback(bot_id, {'running': False, 'error': 'market_data_failed'})
        return

    time_provider = RealTimeProvider()

    # --- Создание экземпляра бота ---
    bot_instance = None
    try:
        bot_instance = bot_class(name, connector, market_data, time_provider, config)
        if hasattr(bot_instance, 'set_cancel_event'):
            bot_instance.set_cancel_event(cancel_event)
        
        # Передаём task_manager, если он нужен боту (например, ManualBot)
        if task_manager is not None and hasattr(bot_instance, 'set_task_manager'):
            bot_instance.set_task_manager(task_manager)
        
        # Сохраняем экземпляр, если передан holder
        if instance_holder is not None:
            instance_holder["instance"] = bot_instance
            
    except Exception as e:
        logger.error(f"Bot {name}: instantiation failed: {e}\n{traceback.format_exc()}")
        await safe_await(market_data.disconnect())
        if status_callback:
            status_callback(bot_id, {'running': False, 'error': 'instantiation_failed'})
        return

    # --- Обёртка on_order_filled для сохранения сделок в БД ---
    original_on_order_filled = getattr(bot_instance, 'on_order_filled', None)

    async def on_order_filled_wrapper(order_data):
        if order_data and order_data.get('type') in ('open', 'close'):
            trade_info = {
                'bot_id': bot_id,
                'bot_name': name,
                'symbol': config.get('symbol', ''),
                'side': order_data.get('side', ''),
                'open_time': int(time.time() * 1000) if order_data.get('type') == 'open' else 0,
                'open_price': order_data.get('price', 0.0) if order_data.get('type') == 'open' else 0.0,
                'close_time': int(time.time() * 1000) if order_data.get('type') == 'close' else 0,
                'close_price': order_data.get('price', 0.0) if order_data.get('type') == 'close' else 0.0,
                'pnl': order_data.get('pnl', 0.0),
                'size': order_data.get('size', 0.0)
            }
            try:
                from core.models import Trade
                trade_obj = Trade(**trade_info)
                await db.add_trade(trade_obj)
                logger.info(f"Bot {name} trade saved: {trade_info}")
            except Exception as e:
                logger.error(f"Bot {name}: failed to save trade: {e}")
        # Вызов оригинального обработчика (если есть) с учётом синхронности/асинхронности
        if original_on_order_filled:
            if asyncio.iscoroutinefunction(original_on_order_filled):
                await original_on_order_filled(order_data)
            else:
                original_on_order_filled(order_data)

    # Присваиваем обёртку (заменяем метод)
    bot_instance.on_order_filled = on_order_filled_wrapper

    # --- Запуск бота ---
    try:
        await safe_await(bot_instance.start())
        logger.info(f"Bot {name} started successfully")
    except Exception as e:
        logger.error(f"Bot {name}: start failed: {e}\n{traceback.format_exc()}")
        await safe_await(market_data.disconnect())
        if status_callback:
            status_callback(bot_id, {'running': False, 'error': 'start_failed'})
        return

    # --- Основной цикл: отправка статусов и ожидание отмены ---
    last_status_send = 0

    try:
        while not cancel_event.is_set():
            now = time.time()
            if now - last_status_send > 2:  # каждые 2 секунды
                try:
                    status = bot_instance.get_status()
                    status['running'] = True
                    status['bot_id'] = bot_id
                    status['timestamp'] = int(now * 1000)
                    status.setdefault('position_open', False)
                    status.setdefault('side', '')
                    status.setdefault('entry_price', 0.0)
                    status.setdefault('symbol', config.get('symbol', ''))
                    status.setdefault('open_positions', 0)
                    status.setdefault('closed_positions', 0)
                    if status_callback:
                        status_callback(bot_id, status)
                except Exception as e:
                    logger.error(f"Bot {name}: error getting status: {e}")
                last_status_send = now

            await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        logger.info(f"Bot {name} task cancelled")
    except Exception as e:
        logger.error(f"Bot {name} unexpected error in main loop: {e}\n{traceback.format_exc()}")
    finally:
        # --- Остановка бота ---
        try:
            await safe_await(bot_instance.stop())
            logger.info(f"Bot {name} stopped gracefully")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Bot {name}: stop error: {e}")
        await safe_await(market_data.disconnect())
        if status_callback:
            status_callback(bot_id, {'running': False, 'bot_id': bot_id})
        logger.info(f"Bot {name} task finished")