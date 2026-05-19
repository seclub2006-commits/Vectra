// web/static/js/timers.js

import { REFRESH_INTERVAL, STATUS_INTERVAL } from './config.js';
import { setRefreshInterval, clearRefreshInterval, getRefreshInterval } from './state.js';
import { loadBotsTable, loadTabContent, updateConnStatus } from './ui.js';

/**
 * Запускает все периодические обновления:
 * - Обновление таблицы ботов
 * - Обновление активной вкладки
 * - Проверка статуса соединения с ядром
 */
export function startRefreshTimers() {
    console.log('[Timers] Starting refresh timers');

    // Таймер обновления таблицы ботов
    const botsTimer = setInterval(() => {
        loadBotsTable().catch(err => console.error('[Timers] Error refreshing bots:', err));
    }, REFRESH_INTERVAL);
    setRefreshInterval('bots', botsTimer);

    // Таймер обновления активной вкладки
    const tabsTimer = setInterval(() => {
        const activeTabBtn = document.querySelector('.tab-btn.active');
        const tabId = activeTabBtn?.dataset.tab;
        if (tabId) {
            loadTabContent(tabId).catch(err => console.error('[Timers] Error refreshing tab:', err));
        }
    }, REFRESH_INTERVAL);
    setRefreshInterval('tabs', tabsTimer);

    // Таймер проверки статуса соединения
    const statusTimer = setInterval(() => {
        updateConnStatus().catch(err => console.error('[Timers] Error updating connection status:', err));
    }, STATUS_INTERVAL);
    setRefreshInterval('status', statusTimer);
}

/**
 * Останавливает все периодические обновления.
 * Используется при выходе из системы или перезагрузке приложения.
 */
export function stopRefreshTimers() {
    console.log('[Timers] Stopping all refresh timers');

    const timerNames = ['bots', 'tabs', 'status'];
    for (const name of timerNames) {
        const timerId = getRefreshInterval(name);
        if (timerId) {
            clearInterval(timerId);
            clearRefreshInterval(name);
        }
    }
}

/**
 * Перезапускает все таймеры (полезно после восстановления соединения).
 */
export function restartRefreshTimers() {
    stopRefreshTimers();
    startRefreshTimers();
}