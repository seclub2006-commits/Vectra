// web/static/js/main.js

import { TIMEFRAMES, REFRESH_INTERVAL, STATUS_INTERVAL } from './config.js';
import { showSuccess, showError, showInfo, toggleTheme, getCurrentTheme, setTheme, hideModal } from './utils.js';
import {
    getBotsList, setBotsList, getConnectorsList, setConnectorsList,
    setRefreshInterval, clearRefreshInterval,
    getWsUpdates, setWsUpdates, closeWsUpdates, setUpdateCallback,
    resetAllState
} from './state.js';
import {
    getBots, getConnectors, getBotTrades,
    logout as apiLogout, connectUpdatesWebSocket
} from './api.js';
import { loadBotsTable, loadTabContent, filterBotsTable, updateConnStatus } from './ui.js';
import { startRefreshTimers, stopRefreshTimers } from './timers.js';
// Импорт старых manual-функций удалён
import { showCreateBotModal, showCreateConnectorModal } from './modals.js';

// ==================== ГЛОБАЛЬНЫЕ ФУНКЦИИ (для обратной совместимости) ====================
window.showLogin = showLoginUI;
window.botsList = [];

// ==================== ИНИЦИАЛИЗАЦИЯ ====================
async function init() {
    console.log('[Main] Initializing application...');

    const savedTheme = getCurrentTheme();
    setTheme(savedTheme);

    bindGlobalEvents();

    const token = localStorage.getItem('access_token');
    if (token) {
        try {
            await getBots();
            showMainUI();
        } catch (error) {
            console.warn('[Main] Token invalid, showing login');
            showLoginUI();
        }
    } else {
        showLoginUI();
    }
}

// ==================== ПОКАЗ ИНТЕРФЕЙСА ВХОДА ====================
function showLoginUI() {
    console.log('[Main] Showing login UI');
    const loginContainer = document.getElementById('login-container');
    const mainContainer = document.getElementById('main-container');
    if (loginContainer) loginContainer.style.display = 'flex';
    if (mainContainer) mainContainer.style.display = 'none';

    resetAllState();
    if (window.wsUpdates) window.wsUpdates.close();

    const pwdInput = document.getElementById('password-input');
    if (pwdInput) pwdInput.value = '';
    const errorDiv = document.getElementById('login-error');
    if (errorDiv) errorDiv.textContent = '';
}

// ==================== ПОКАЗ ОСНОВНОГО ИНТЕРФЕЙСА ====================
async function showMainUI() {
    console.log('[Main] Showing main UI');
    const loginContainer = document.getElementById('login-container');
    const mainContainer = document.getElementById('main-container');
    if (loginContainer) loginContainer.style.display = 'none';
    if (mainContainer) mainContainer.style.display = 'block';

    startRefreshTimers();

    await loadBotsTable();
    await loadTabContent('positions');
    await updateConnStatus();

    const ws = connectUpdatesWebSocket({
        'bots_status': (data) => {
            updateBotsStatusFromWebsocket(data);
        }
    });
    setWsUpdates(ws);

    setUpdateCallback('bots_status', updateBotsStatusFromWebsocket);
}

// ==================== ОБРАБОТЧИКИ ГЛОБАЛЬНЫХ СОБЫТИЙ ====================
function bindGlobalEvents() {
    const loginBtn = document.getElementById('login-btn');
    if (loginBtn) {
        loginBtn.addEventListener('click', async () => {
            const password = document.getElementById('password-input').value;
            const errorDiv = document.getElementById('login-error');
            try {
                const { login } = await import('./api.js');
                await login(password);
                showMainUI();
            } catch (e) {
                if (errorDiv) errorDiv.textContent = e.message;
                showError(e.message);
            }
        });
    }

    const logoutBtn = document.getElementById('logout-btn');
    if (logoutBtn) {
        logoutBtn.addEventListener('click', () => {
            apiLogout();
            showLoginUI();
        });
    }

    const refreshBtn = document.getElementById('refresh-btn');
    if (refreshBtn) refreshBtn.addEventListener('click', () => {
        loadBotsTable();
        loadTabContent(document.querySelector('.tab-btn.active')?.dataset.tab);
    });

    const addBotBtn = document.getElementById('add-bot-btn');
    if (addBotBtn) addBotBtn.addEventListener('click', () => showCreateBotModal());

    const addConnectorBtn = document.getElementById('add-connector-btn');
    if (addConnectorBtn) addConnectorBtn.addEventListener('click', () => showCreateConnectorModal());

    // Кнопка "Ручная торговля" удалена
    // Кнопка "Advanced Terminal" удалена

    const themeToggle = document.getElementById('theme-toggle');
    if (themeToggle) themeToggle.addEventListener('click', () => toggleTheme());

    const searchInput = document.getElementById('search-input');
    if (searchInput) searchInput.addEventListener('input', () => filterBotsTable());

    const filterSelect = document.getElementById('filter-select');
    if (filterSelect) filterSelect.addEventListener('change', () => filterBotsTable());

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const tabId = btn.dataset.tab;
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
            const pane = document.getElementById(`tab-${tabId}`);
            if (pane) pane.classList.add('active');
            loadTabContent(tabId);
        });
    });

    const closeModal = document.querySelector('.close-modal');
    if (closeModal) closeModal.addEventListener('click', () => hideModal());
    window.onclick = (e) => {
        const modal = document.getElementById('modal');
        if (e.target === modal) hideModal();
    };
}

// ==================== ОБНОВЛЕНИЕ СТАТУСОВ ИЗ WEBSOCKET ====================
function updateBotsStatusFromWebsocket(botsStatus) {
    for (const status of botsStatus) {
        const row = document.querySelector(`#bots-table tbody tr[data-bot-id="${status.id}"]`);
        if (row) {
            const statusCell = row.cells[7];
            const running = status.running;
            statusCell.innerHTML = `<span class="status ${running ? 'online' : 'offline'}">${running ? 'Работает' : 'Остановлен'}</span>`;
            const actionsCell = row.cells[8];
            const startBtn = actionsCell.querySelector('.btn-start');
            const stopBtn = actionsCell.querySelector('.btn-stop');
            if (startBtn) startBtn.disabled = running;
            if (stopBtn) stopBtn.disabled = !running;
        }
    }
}

// ==================== ЗАПУСК ====================
document.addEventListener('DOMContentLoaded', init);