// web/static/js/ui.js

import { LOGS_DAYS_BACK, LOGS_PER_PAGE_DEFAULT } from './config.js';
import { escapeHtml, showError, showSuccess, formatDate, getElementSafe } from './utils.js';
import {
    getBotsList, setBotsList, getConnectorsList, setConnectorsList,
    getCurrentLogPage, setCurrentLogPage, getLogsPerPage, setLogsPerPage,
    getAllLogsCache, setAllLogsCache
} from './state.js';
import {
    getBots, getBotTrades, getPositions, getOpenOrders, getBalance,
    getConnectors, getLogs, closePosition, cancelOrder
} from './api.js';

// ==================== ТАБЛИЦА БОТОВ ====================
export async function loadBotsTable() {
    const tbody = document.querySelector('#bots-table tbody');
    if (!tbody) return;

    try {
        const bots = await getBots();
        setBotsList(bots);

        tbody.innerHTML = '';
        for (let idx = 0; idx < bots.length; idx++) {
            const bot = bots[idx];
            const row = tbody.insertRow();
            row.setAttribute('data-bot-id', bot.id);
            row.insertCell(0).innerText = idx + 1;
            row.insertCell(1).innerHTML = `<strong>${escapeHtml(bot.name)}</strong>`;
            const strategyShort = bot.strategy.split('.').pop() || bot.strategy;
            row.insertCell(2).innerText = strategyShort;
            row.insertCell(3).innerText = bot.symbol;
            row.insertCell(4).innerText = '0'; // будет обновлено после загрузки сделок
            row.insertCell(5).innerHTML = `<span class="pnl">0.00</span>`;
            row.insertCell(6).innerText = bot.connector;
            const running = bot.running || false;
            row.insertCell(7).innerHTML = `<span class="status ${running ? 'online' : 'offline'}">${running ? 'Работает' : 'Остановлен'}</span>`;
            const actions = row.insertCell(8);
            actions.innerHTML = `
                <button class="btn-start" data-id="${bot.id}" ${running ? 'disabled' : ''}><i class="fas fa-play"></i></button>
                <button class="btn-stop" data-id="${bot.id}" ${!running ? 'disabled' : ''}><i class="fas fa-stop"></i></button>
                <button class="btn-edit" data-id="${bot.id}"><i class="fas fa-edit"></i></button>
                <button class="btn-chart" data-id="${bot.id}"><i class="fas fa-chart-line"></i></button>
                <button class="btn-delete" data-id="${bot.id}"><i class="fas fa-trash"></i></button>
            `;
        }

        // Привязываем обработчики кнопок (импортируем динамически, чтобы избежать цикличности)
        const { startBotAction, stopBotAction, editBotAction, showBotChart, deleteBotAction } = await import('./bots.js');
        document.querySelectorAll('.btn-start').forEach(btn => btn.addEventListener('click', () => startBotAction(parseInt(btn.dataset.id))));
        document.querySelectorAll('.btn-stop').forEach(btn => btn.addEventListener('click', () => stopBotAction(parseInt(btn.dataset.id))));
        document.querySelectorAll('.btn-edit').forEach(btn => btn.addEventListener('click', () => editBotAction(parseInt(btn.dataset.id))));
        document.querySelectorAll('.btn-chart').forEach(btn => btn.addEventListener('click', () => showBotChart(parseInt(btn.dataset.id))));
        document.querySelectorAll('.btn-delete').forEach(btn => btn.addEventListener('click', () => deleteBotAction(parseInt(btn.dataset.id))));

        // Загружаем PnL для каждого бота
        for (const bot of bots) {
            loadBotPnL(bot.id);
        }
    } catch (e) {
        console.error(e);
        showError('Ошибка загрузки ботов');
    }
}

async function loadBotPnL(botId) {
    try {
        const trades = await getBotTrades(botId, 100);
        let totalPnl = 0;
        let closedCount = 0;
        for (const t of trades) {
            totalPnl += t.pnl || 0;
            if (t.close_time > 0) closedCount++;
        }
        const row = document.querySelector(`#bots-table tbody tr[data-bot-id="${botId}"]`);
        if (row) {
            row.cells[4].innerText = closedCount;
            const pnlSpan = row.cells[5].querySelector('.pnl');
            if (pnlSpan) {
                pnlSpan.innerText = totalPnl.toFixed(2);
                pnlSpan.className = `pnl ${totalPnl >= 0 ? 'positive-pnl' : 'negative-pnl'}`;
            }
        }
    } catch (e) { console.error(e); }
}

// ==================== ФИЛЬТРАЦИЯ ТАБЛИЦЫ ====================
export function filterBotsTable() {
    const search = getElementSafe('search-input')?.value.toLowerCase() || '';
    const filter = getElementSafe('filter-select')?.value || 'all';
    const rows = document.querySelectorAll('#bots-table tbody tr');
    rows.forEach(row => {
        const name = row.cells[1]?.innerText.toLowerCase() || '';
        const symbol = row.cells[3]?.innerText.toLowerCase() || '';
        const type = row.cells[2]?.innerText.toLowerCase() || '';
        const running = row.cells[7]?.innerText.includes('Работает');
        let visible = true;
        if (search && !name.includes(search) && !symbol.includes(search)) visible = false;
        if (filter === 'running' && !running) visible = false;
        if (filter === 'stopped' && running) visible = false;
        if (filter === 'trend' && !['ema', 'rsi'].some(t => type.includes(t))) visible = false;
        if (filter === 'grid' && !type.includes('grid')) visible = false;
        if (filter === 'manual' && !type.includes('manual')) visible = false;
        row.style.display = visible ? '' : 'none';
    });
}

// ==================== ВКЛАДКИ ====================
export async function loadTabContent(tabId) {
    if (tabId === 'positions') await renderPositions();
    else if (tabId === 'orders') await renderOrders();
    else if (tabId === 'portfolio') await renderPortfolio();
    else if (tabId === 'connectors') await renderConnectors();
    else if (tabId === 'logs') await renderLogs();
}

// ==================== ПОЗИЦИИ ====================
async function renderPositions() {
    const container = getElementSafe('tab-positions');
    if (!container) return;
    container.innerHTML = '<div class="card"><i class="fas fa-spinner fa-spin"></i> Загрузка позиций...</div>';
    try {
        const connectors = await getConnectors();
        let html = '';
        for (const conn of connectors) {
            try {
                const positions = await getPositions(conn.name);
                if (positions.length === 0) continue;
                html += `<h3><i class="fas fa-plug"></i> ${escapeHtml(conn.name)}</h3>
                        <table class="sub-table"><thead><tr><th>Символ</th><th>Сторона</th><th>Размер</th><th>Цена входа</th><th>Текущая цена</th><th>PnL</th><th>Действие</th></tr></thead><tbody>`;
                for (const p of positions) {
                    html += `<tr>
                        <td>${escapeHtml(p.symbol)}</td>
                        <td>${escapeHtml(p.side)}</td>
                        <td>${p.size}</td>
                        <td>${p.entry_price}</td>
                        <td>${p.mark_price}</td>
                        <td class="${p.pnl >= 0 ? 'positive-pnl' : 'negative-pnl'}">${p.pnl.toFixed(2)}</td>
                        <td><button class="close-pos" data-conn="${escapeHtml(conn.name)}" data-symbol="${escapeHtml(p.symbol)}" data-side="${escapeHtml(p.side)}"><i class="fas fa-times-circle"></i> Закрыть</button></td>
                    </tr>`;
                }
                html += '</tbody></table>';
            } catch (e) {
                console.warn(`Ошибка загрузки позиций для ${conn.name}:`, e);
                html += `<div class="card">Ошибка при загрузке позиций для ${conn.name}: ${e.message}</div>`;
            }
        }
        if (!html) html = '<div class="card">Нет открытых позиций.</div>';
        container.innerHTML = html;

        // Обработчики кнопок закрытия
        document.querySelectorAll('.close-pos').forEach(btn => {
            btn.addEventListener('click', async () => {
                const conn = btn.dataset.conn, symbol = btn.dataset.symbol, side = btn.dataset.side;
                if (confirm(`Закрыть позицию ${symbol} ${side}?`)) {
                    try {
                        await closePosition(conn, symbol, side);
                        await renderPositions();
                        showSuccess('Позиция закрыта');
                    } catch (e) { showError(e.message); }
                }
            });
        });
    } catch (e) {
        container.innerHTML = `<div class="card">Ошибка: ${e.message}</div>`;
    }
}

// ==================== ОРДЕРА ====================
async function renderOrders() {
    const container = getElementSafe('tab-orders');
    if (!container) return;
    container.innerHTML = '<div class="card"><i class="fas fa-spinner fa-spin"></i> Загрузка ордеров...</div>';
    try {
        const connectors = await getConnectors();
        let html = '';
        for (const conn of connectors) {
            try {
                const orders = await getOpenOrders(conn.name);
                if (orders.length === 0) continue;
                html += `<h3><i class="fas fa-plug"></i> ${escapeHtml(conn.name)}</h3>
                        <table class="sub-table"><thead><tr><th>ID</th><th>Символ</th><th>Сторона</th><th>Тип</th><th>Цена</th><th>Кол-во</th><th>Заполнено</th><th>Действие</th></tr></thead><tbody>`;
                for (const o of orders) {
                    html += `<tr>
                        <td>${escapeHtml(o.order_id)}</td>
                        <td>${escapeHtml(o.symbol)}</td>
                        <td>${escapeHtml(o.side)}</td>
                        <td>${escapeHtml(o.order_type)}</td>
                        <td>${o.price}</td>
                        <td>${o.quantity}</td>
                        <td>${o.filled}</td>
                        <td><button class="cancel-order" data-conn="${escapeHtml(conn.name)}" data-symbol="${escapeHtml(o.symbol)}" data-id="${escapeHtml(o.order_id)}"><i class="fas fa-ban"></i> Отменить</button></td>
                    </tr>`;
                }
                html += '</tbody></table>';
            } catch (e) {
                console.warn(`Ошибка загрузки ордеров для ${conn.name}:`, e);
                html += `<div class="card">Ошибка при загрузке ордеров для ${conn.name}: ${e.message}</div>`;
            }
        }
        if (!html) html = '<div class="card">Нет открытых ордеров.</div>';
        container.innerHTML = html;

        document.querySelectorAll('.cancel-order').forEach(btn => {
            btn.addEventListener('click', async () => {
                const conn = btn.dataset.conn, symbol = btn.dataset.symbol, id = btn.dataset.id;
                try {
                    await cancelOrder(conn, symbol, id);
                    await renderOrders();
                    showSuccess('Ордер отменён');
                } catch (e) { showError(e.message); }
            });
        });
    } catch (e) {
        container.innerHTML = `<div class="card">Ошибка: ${e.message}</div>`;
    }
}

// ==================== ПОРТФЕЛЬ (БАЛАНСЫ) ====================
async function renderPortfolio() {
    const container = getElementSafe('tab-portfolio');
    if (!container) return;
    container.innerHTML = '<div class="card"><i class="fas fa-spinner fa-spin"></i> Загрузка балансов...</div>';
    try {
        const connectors = await getConnectors();
        let html = '';
        for (const conn of connectors) {
            try {
                const balances = await getBalance(conn.name);
                if (balances.length === 0) continue;
                html += `<h3><i class="fas fa-plug"></i> ${escapeHtml(conn.name)}</h3>
                        <table class="sub-table"><thead><tr><th>Валюта</th><th>Доступно</th><th>Заморожено</th><th>Итого</th></tr></thead><tbody>`;
                for (const b of balances) {
                    html += `<tr>
                        <td>${escapeHtml(b.currency)}</td>
                        <td>${b.available}</td>
                        <td>${b.frozen}</td>
                        <td>${b.total}</td>
                    </tr>`;
                }
                html += '</tbody></table>';
            } catch (e) {
                console.warn(`Ошибка загрузки баланса для ${conn.name}:`, e);
                html += `<div class="card">Ошибка при загрузке баланса для ${conn.name}: ${e.message}</div>`;
            }
        }
        if (!html) html = '<div class="card">Нет данных о балансах.</div>';
        container.innerHTML = html;
    } catch (e) {
        container.innerHTML = `<div class="card">Ошибка: ${e.message}</div>`;
    }
}

// ==================== КОННЕКТОРЫ ====================
export async function renderConnectors() {
    const container = getElementSafe('tab-connectors');
    if (!container) return;
    container.innerHTML = '<div class="card"><i class="fas fa-spinner fa-spin"></i> Загрузка коннекторов...</div>';
    try {
        const connectors = await getConnectors();
        setConnectorsList(connectors);
        let html = `<table class="sub-table"><thead><tr><th>Имя</th><th>Биржа</th><th>Тип</th><th>Тестнет</th><th>Статус</th><th>Действия</th></tr></thead><tbody>`;
        for (const c of connectors) {
            html += `<tr>
                <td>${escapeHtml(c.name)}</td>
                <td>${escapeHtml(c.exchange)}</td>
                <td>${escapeHtml(c.product_type)}</td>
                <td>${c.testnet ? 'Да' : 'Нет'}</td>
                <td><span class="status ${c.status === 'online' ? 'online' : 'offline'}">${c.status === 'online' ? 'Онлайн' : 'Офлайн'}</span></td>
                <td>
                    <button class="connector-edit" data-name="${escapeHtml(c.name)}"><i class="fas fa-edit"></i></button>
                    <button class="connector-delete" data-name="${escapeHtml(c.name)}"><i class="fas fa-trash"></i></button>
                    ${c.status === 'online' ?
                    `<button class="connector-offline" data-name="${escapeHtml(c.name)}"><i class="fas fa-plug"></i> Откл</button>` :
                    `<button class="connector-online" data-name="${escapeHtml(c.name)}"><i class="fas fa-plug"></i> Подкл</button>`
                }
                </td>
            </tr>`;
        }
        html += '</tbody></table>';
        container.innerHTML = html;

        // Импортируем функции для работы с коннекторами
        const { editConnector, deleteConnectorAction, setConnectorStatusAction } = await import('./connectors.js');
        document.querySelectorAll('.connector-edit').forEach(btn => btn.addEventListener('click', () => editConnector(btn.dataset.name)));
        document.querySelectorAll('.connector-delete').forEach(btn => btn.addEventListener('click', () => deleteConnectorAction(btn.dataset.name)));
        document.querySelectorAll('.connector-online').forEach(btn => btn.addEventListener('click', () => setConnectorStatusAction(btn.dataset.name, 'online')));
        document.querySelectorAll('.connector-offline').forEach(btn => btn.addEventListener('click', () => setConnectorStatusAction(btn.dataset.name, 'offline')));
    } catch (e) {
        container.innerHTML = `<div class="card">Ошибка: ${e.message}</div>`;
    }
}

// ==================== ЛОГИ ====================
async function renderLogs() {
    const container = getElementSafe('tab-logs');
    if (!container) return;

    const since = Date.now() - LOGS_DAYS_BACK * 86400000;
    try {
        let logs = getAllLogsCache();
        if (!logs.length) {
            logs = await getLogs(since, 10000);
            setAllLogsCache(logs);
        }
        const totalPages = Math.ceil(logs.length / getLogsPerPage());
        const start = (getCurrentLogPage() - 1) * getLogsPerPage();
        const pageLogs = logs.slice(start, start + getLogsPerPage());

        let html = `<table class="sub-table"><thead><tr><th>Время</th><th>Уровень</th><th>Категория</th><th>Сообщение</th></tr></thead><tbody>`;
        for (const log of pageLogs) {
            const levelClass = `log-level-${log.level.toLowerCase()}`;
            html += `<tr>
                <td>${formatDate(log.timestamp)}</td>
                <td class="${levelClass}">${escapeHtml(log.level)}</td>
                <td>${escapeHtml(log.category)}</td>
                <td>${escapeHtml(log.message_ru)}</td>
            </tr>`;
        }
        html += `</tbody></table>
            <div class="pagination" style="margin-top:12px; display:flex; gap:8px; align-items:center;">
                <button id="log-prev" ${getCurrentLogPage() === 1 ? 'disabled' : ''}>Предыдущая</button>
                <span>Страница ${getCurrentLogPage()} из ${totalPages}</span>
                <button id="log-next" ${getCurrentLogPage() === totalPages ? 'disabled' : ''}>Следующая</button>
                <select id="log-limit">
                    <option value="50" ${getLogsPerPage() === 50 ? 'selected' : ''}>50</option>
                    <option value="100" ${getLogsPerPage() === 100 ? 'selected' : ''}>100</option>
                    <option value="200" ${getLogsPerPage() === 200 ? 'selected' : ''}>200</option>
                </select>
            </div>`;
        container.innerHTML = html;

        document.getElementById('log-prev')?.addEventListener('click', () => {
            if (getCurrentLogPage() > 1) {
                setCurrentLogPage(getCurrentLogPage() - 1);
                renderLogs();
            }
        });
        document.getElementById('log-next')?.addEventListener('click', () => {
            if (getCurrentLogPage() < totalPages) {
                setCurrentLogPage(getCurrentLogPage() + 1);
                renderLogs();
            }
        });
        document.getElementById('log-limit')?.addEventListener('change', (e) => {
            setLogsPerPage(parseInt(e.target.value));
            setCurrentLogPage(1);
            renderLogs();
        });
    } catch (e) {
        container.innerHTML = `<div class="card">Ошибка: ${e.message}</div>`;
    }
}

// ==================== СТАТУС СОЕДИНЕНИЯ ====================
export async function updateConnStatus() {
    const statusDiv = getElementSafe('conn-status');
    if (!statusDiv) return;
    try {
        const health = await fetch('/api/health');
        if (health.ok) statusDiv.innerHTML = '<i class="fas fa-circle" style="color:#10b981"></i> ОНЛАЙН';
        else statusDiv.innerHTML = '<i class="fas fa-circle" style="color:#ef4444"></i> ОФЛАЙН';
    } catch (e) {
        statusDiv.innerHTML = '<i class="fas fa-circle" style="color:#ef4444"></i> ОФЛАЙН';
    }
}