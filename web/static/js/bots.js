// web/static/js/bots.js

import { CHART_CANDLES_LIMIT, TIMEFRAMES } from './config.js';
import { escapeHtml, showError, showSuccess, showModal, hideModal, getElementSafe, calculateEMA, calculateRSI } from './utils.js';
import { getBotsList, setBotsList, updateBotInList, getConnectorsList } from './state.js';
import {
    getBots, startBot, stopBot, deleteBot, updateBotConfig,
    getBotParamsSchema, getBotStatus, getBotTrades, getStrategyParamsSchema,
    getConnectors, getSymbols, getCandles, subscribeCandles
} from './api.js';
import { loadBotsTable, renderConnectors } from './ui.js';
import { createSymbolSelector, generateBotName } from './modals.js';

// ==================== ЗАПУСК БОТА ====================
export async function startBotAction(botId) {
    const bot = getBotsList().find(b => b.id === botId);
    if (!bot) {
        showError('Бот не найден');
        return;
    }
    try {
        let params = {};
        try {
            params = JSON.parse(bot.params || '{}');
        } catch (e) { }

        if (!params.leverage) params.leverage = '10';
        if (!params.emulator_enabled) params.emulator_enabled = bot.emulator_enabled ? 'true' : 'false';
        if (!params.product_type) params.product_type = bot.product_type || 'USDT-FUTURES';

        await startBot({
            bot_id: botId,
            name: bot.name,
            strategy: bot.strategy,
            connector_name: bot.connector,
            symbol: bot.symbol,
            timeframe: bot.timeframe || '1H',
            position_size: bot.position_size || 10,
            params: params,
            market_data_source: bot.market_data_source || 'websocket',
            market_data_source_config: bot.market_data_source_config || ''
        });
        showSuccess(`Бот ${bot.name} запущен`);
        await loadBotsTable();
    } catch (e) {
        showError(e.message);
    }
}

// ==================== ОСТАНОВКА БОТА ====================
export async function stopBotAction(botId) {
    try {
        await stopBot(botId);
        showSuccess('Бот остановлен');
        await loadBotsTable();
    } catch (e) {
        showError(e.message);
    }
}

// ==================== УДАЛЕНИЕ БОТА ====================
export async function deleteBotAction(botId) {
    if (!confirm('Удалить бота? Все данные о сделках будут потеряны.')) return;
    try {
        await deleteBot(botId);
        showSuccess('Бот удалён');
        await loadBotsTable();
    } catch (e) {
        showError(e.message);
    }
}

// ==================== РЕДАКТИРОВАНИЕ БОТА ====================
export async function editBotAction(botId) {
    const bot = getBotsList().find(b => b.id === botId);
    if (!bot) {
        showError('Бот не найден');
        return;
    }

    let params = {};
    try {
        params = JSON.parse(bot.params || '{}');
    } catch (e) { }

    const connectors = await getConnectors();

    let schema = {};
    let schemaLoadError = false;
    try {
        if (bot.running) {
            schema = await getBotParamsSchema(botId);
        } else {
            schema = await getStrategyParamsSchema(bot.strategy);
        }
        if (!schema || Object.keys(schema).length === 0) {
            schemaLoadError = true;
        }
    } catch (e) {
        console.warn(e);
        schemaLoadError = true;
    }

    const productType = bot.product_type || 'USDT-FUTURES';
    const marketDataSource = bot.market_data_source || 'websocket';
    const marketDataSourceConfig = bot.market_data_source_config || '';

    const html = `
        <div style="width: 90vw; max-width: 900px;">
            <h3>Редактирование бота ${escapeHtml(bot.name)}</h3>
            ${schemaLoadError ? `
                <div class="card" style="background: #ffaa3311; border-left: 4px solid #ffaa33; margin-bottom: 16px;">
                    <i class="fas fa-exclamation-triangle"></i> Не удалось загрузить схему параметров стратегии.
                </div>
            ` : ''}
            <form id="edit-bot-form">
                <fieldset style="border:1px solid #4a4a5a; border-radius:8px; padding:12px; margin-bottom:20px;">
                    <legend style="padding:0 8px;">📦 Основные настройки</legend>
                    <div class="form-group"><label>Имя</label><input id="edit-name" value="${escapeHtml(bot.name)}" required></div>
                    <div class="form-group"><label>Коннектор</label><select id="edit-connector">${connectors.map(c => `<option ${c.name === bot.connector ? 'selected' : ''} value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`).join('')}</select></div>
                    <div class="form-group"><label>Тип продукта</label><select id="edit-product-type">
                        <option value="USDT-FUTURES" ${productType === 'USDT-FUTURES' ? 'selected' : ''}>USDT-фьючерсы</option>
                        <option value="SPOT" ${productType === 'SPOT' ? 'selected' : ''}>Спот</option>
                        <option value="COIN-FUTURES" ${productType === 'COIN-FUTURES' ? 'selected' : ''}>Coin-фьючерсы</option>
                    </select></div>
                    <div class="form-group"><label>Источник данных</label><select id="edit-market-source">
                        <option value="websocket" ${marketDataSource === 'websocket' ? 'selected' : ''}>WebSocket</option>
                        <option value="rest_polling" ${marketDataSource === 'rest_polling' ? 'selected' : ''}>REST опрос</option>
                        <option value="database" ${marketDataSource === 'database' ? 'selected' : ''}>База данных</option>
                        <option value="csv" ${marketDataSource === 'csv' ? 'selected' : ''}>CSV</option>
                    </select></div>
                    <div class="form-group" id="edit-csv-config-group" style="${marketDataSource === 'csv' ? 'block' : 'none'}">
                        <label>Конфигурация CSV</label>
                        <input id="edit-csv-config" value='${escapeHtml(marketDataSourceConfig)}'>
                    </div>
                    <div class="form-group"><label>Торговая пара</label><div id="edit-symbol-container"></div></div>
                    <div class="form-group"><label>Таймфрейм</label><select id="edit-timeframe">${TIMEFRAMES.map(tf => `<option ${tf === bot.timeframe ? 'selected' : ''}>${tf}</option>`).join('')}</select></div>
                    <div class="form-group"><label>Размер позиции (USDT)</label><input type="number" id="edit-pos-size" value="${bot.position_size || 10}"></div>
                    <div class="form-group" id="edit-leverage-group" style="${productType !== 'SPOT' ? 'block' : 'none'}">
                        <label>Плечо</label><input type="number" id="edit-leverage" value="${params.leverage || 10}">
                    </div>
                    <div class="form-group"><label><input type="checkbox" id="edit-emulator" ${bot.emulator_enabled ? 'checked' : ''}> Режим эмуляции</label></div>
                </fieldset>
                <fieldset style="border:1px solid #7c3aed; border-radius:8px; padding:12px;">
                    <legend style="color:#7c3aed; padding:0 8px;">🧠 Параметры стратегии</legend>
                    <div id="dynamic-params-edit">
                        ${schemaLoadError ?
            '<p style="color: #ffaa33;">Параметры стратегии недоступны.</p>' :
            (Object.keys(schema).length === 0 ? '<p>Нет настраиваемых параметров</p>' : '')}
                    </div>
                </fieldset>
                <div style="margin-top:20px; text-align:right;">
                    <button type="submit" class="primary">Сохранить</button>
                    <button type="button" id="cancel-edit" class="secondary">Отмена</button>
                </div>
            </form>
        </div>
    `;

    showModal(html);
    await initEditBotForm(bot, params, schema, schemaLoadError);
}

async function initEditBotForm(bot, currentParams, schema, schemaLoadError) {
    const connectorSelect = getElementSafe('edit-connector');
    const productTypeSelect = getElementSafe('edit-product-type');
    const marketSourceEdit = getElementSafe('edit-market-source');
    const csvGroupEdit = getElementSafe('edit-csv-config-group');
    const leverageGroupEdit = getElementSafe('edit-leverage-group');
    const symbolContainerEdit = getElementSafe('edit-symbol-container');
    let symbolSelectorEdit = null;
    let currentSymbolsEdit = [];

    async function loadSymbolsEdit() {
        const connector = connectorSelect?.value;
        const productType = productTypeSelect?.value;
        if (!connector) return;
        try {
            const symbols = await getSymbols(connector, productType);
            currentSymbolsEdit = symbols;
            if (symbolSelectorEdit) {
                if (symbolContainerEdit) symbolContainerEdit.innerHTML = '';
                symbolSelectorEdit = createSymbolSelector(currentSymbolsEdit, bot.symbol, () => { });
                if (symbolContainerEdit) symbolContainerEdit.appendChild(symbolSelectorEdit);
            } else {
                symbolSelectorEdit = createSymbolSelector(currentSymbolsEdit, bot.symbol, () => { });
                if (symbolContainerEdit) symbolContainerEdit.appendChild(symbolSelectorEdit);
            }
        } catch (e) {
            if (symbolContainerEdit) symbolContainerEdit.innerHTML = '<div style="color:red;">Ошибка загрузки символов</div>';
        }
    }

    function toggleLeverageEdit() {
        if (leverageGroupEdit) {
            leverageGroupEdit.style.display = productTypeSelect?.value === 'SPOT' ? 'none' : 'block';
        }
    }

    function toggleCsvEdit() {
        if (csvGroupEdit) {
            csvGroupEdit.style.display = marketSourceEdit?.value === 'csv' ? 'block' : 'none';
        }
    }

    connectorSelect?.addEventListener('change', loadSymbolsEdit);
    productTypeSelect?.addEventListener('change', () => { toggleLeverageEdit(); loadSymbolsEdit(); });
    marketSourceEdit?.addEventListener('change', toggleCsvEdit);
    toggleLeverageEdit();
    toggleCsvEdit();
    await loadSymbolsEdit();

    if (!schemaLoadError && Object.keys(schema).length > 0) {
        const dynamicDiv = getElementSafe('dynamic-params-edit');
        if (dynamicDiv) {
            dynamicDiv.innerHTML = '';
            for (const [key, meta] of Object.entries(schema)) {
                const label = meta.label || key;
                let inputHtml = '';
                const value = currentParams[key] !== undefined ? currentParams[key] : meta.default;
                if (meta.type === 'int') {
                    inputHtml = `<input type="number" id="param-${key}" value="${value}" step="1">`;
                } else if (meta.type === 'float') {
                    inputHtml = `<input type="number" id="param-${key}" value="${value}" step="${meta.step || 0.01}">`;
                } else if (meta.type === 'bool') {
                    const checked = value ? 'checked' : '';
                    inputHtml = `<input type="checkbox" id="param-${key}" ${checked}>`;
                } else if (meta.type === 'choice') {
                    inputHtml = `<select id="param-${key}">${meta.options.map(opt => `<option ${value === opt ? 'selected' : ''}>${opt}</option>`).join('')}</select>`;
                } else {
                    inputHtml = `<input type="text" id="param-${key}" value="${escapeHtml(String(value))}">`;
                }
                dynamicDiv.innerHTML += `<div class="form-group"><label>${label}</label>${inputHtml}</div>`;
            }
        }
    }

    const cancelBtn = getElementSafe('cancel-edit');
    if (cancelBtn) cancelBtn.addEventListener('click', () => hideModal());

    const form = getElementSafe('edit-bot-form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            await handleEditBotSubmit(bot, schema, schemaLoadError, symbolSelectorEdit);
        });
    }
}

async function handleEditBotSubmit(bot, schema, schemaLoadError, symbolSelectorEdit) {
    const newParams = {};

    if (!schemaLoadError && Object.keys(schema).length > 0) {
        for (const key of Object.keys(schema)) {
            const input = document.getElementById(`param-${key}`);
            if (input) {
                if (schema[key].type === 'bool') newParams[key] = input.checked;
                else if (schema[key].type === 'int') newParams[key] = parseInt(input.value);
                else if (schema[key].type === 'float') newParams[key] = parseFloat(input.value);
                else newParams[key] = input.value;
            }
        }
    } else {
        try {
            Object.assign(newParams, JSON.parse(bot.params || '{}'));
        } catch (e) { }
    }

    const productTypeSelect = getElementSafe('edit-product-type');
    const leverageInput = getElementSafe('edit-leverage');
    if (productTypeSelect?.value !== 'SPOT' && leverageInput) {
        newParams.leverage = parseInt(leverageInput.value);
    } else {
        newParams.leverage = 1;
    }

    const symbol = symbolSelectorEdit?.querySelector('input')?.value;
    if (!symbol) {
        showError('Выберите торговую пару');
        return;
    }

    const marketSourceEdit = getElementSafe('edit-market-source');
    let marketDataSourceConfig = '';
    if (marketSourceEdit?.value === 'csv') {
        marketDataSourceConfig = getElementSafe('edit-csv-config')?.value || '';
    }

    const data = {
        bot_id: bot.id,
        connector_name: getElementSafe('edit-connector')?.value,
        symbol: symbol,
        timeframe: getElementSafe('edit-timeframe')?.value,
        position_size: parseFloat(getElementSafe('edit-pos-size')?.value || '10'),
        params: newParams,
        emulator_enabled: getElementSafe('edit-emulator')?.checked || false,
        market_data_source: marketSourceEdit?.value || 'websocket',
        market_data_source_config: marketDataSourceConfig
    };

    try {
        await updateBotConfig(data);
        hideModal();
        showSuccess('Бот обновлён');
        await loadBotsTable();
    } catch (err) {
        showError(err.message);
    }
}

// ==================== ГРАФИК БОТА ====================
export async function showBotChart(botId) {
    const bot = getBotsList().find(b => b.id === botId);
    if (!bot) {
        showError('Бот не найден');
        return;
    }

    // Проверяем, является ли бот ручным (ManualBot)
    const isManualBot = bot.strategy && bot.strategy.includes('ManualBot');

    if (isManualBot) {
        // Открываем расширенный терминал в новом окне с параметрами бота
        // Формируем URL с query-параметрами
        const params = new URLSearchParams({
            connector: bot.connector,
            symbol: bot.symbol,
            timeframe: bot.timeframe || '1H',
            market_data_source: bot.market_data_source || 'websocket',
            market_data_source_config: bot.market_data_source_config || ''
        });
        const terminalUrl = `/manual-terminal?${params.toString()}`;
        window.open(terminalUrl, '_blank', 'width=1400,height=900,resizable=yes,scrollbars=yes');
        return;
    }

    // Старый график для других ботов (EMA, RSI, Grid, Test)
    const win = window.open('', '_blank');
    if (!win) {
        showError('Не удалось открыть окно. Разрешите всплывающие окна.');
        return;
    }

    win.document.write(`
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>График ${bot.symbol} - ${bot.name}</title>
            <link rel="stylesheet" href="/static/css/style.css">
            <style>
                body { background:#0d1117; margin:0; padding:16px; font-family: monospace; }
                .controls { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
                button, select { padding: 6px 12px; background: #2a2a3a; border: 1px solid #4a4a5a; border-radius: 6px; color: white; cursor: pointer; }
                button:hover { background: #3a3a5a; }
                #chart { width: 100%; height: 85vh; }
            </style>
        </head>
        <body>
            <div class="controls">
                <button id="add-indicator">📊 Добавить индикатор</button>
                <button id="add-hline">📏 Горизонтальная линия</button>
                <button id="clear-lines">🗑 Очистить линии</button>
                <select id="timeframe">
                    <option>1m</option><option>5m</option><option>15m</option>
                    <option>1H</option><option>4H</option><option>1D</option>
                </select>
                <button id="change-tf">Применить</button>
                <button id="close-window" style="background:#dc2626;">✖ Закрыть</button>
            </div>
            <div id="chart"></div>
        </body>
        </html>
    `);
    win.document.close();

    const script = win.document.createElement('script');
    script.src = 'https://unpkg.com/lightweight-charts@4.1.0/dist/lightweight-charts.standalone.js';
    script.async = true;
    script.defer = true;
    script.onload = () => {
        initChartInWindow(win, bot);
    };
    win.document.head.appendChild(script);
}

// Вспомогательная функция для инициализации графика в новом окне (для обычных ботов)
function initChartInWindow(win, bot) {
    const botConnector = bot.connector;
    const botSymbol = bot.symbol;
    const botId = bot.id;

    const scriptContent = `
        const botConnector = '${botConnector}';
        const botSymbol = '${botSymbol}';
        const botId = ${botId};
        const CHART_CANDLES_LIMIT = ${CHART_CANDLES_LIMIT};
        
        let chart, candleSeries;
        let currentTimeframe = '1H';
        let drawings = [];
        let wsInstance = null;
        let indicators = {};

        function getAuthToken() { return localStorage.getItem('access_token'); }
        
        async function apiRequest(endpoint, options = {}) {
            const url = '/api' + endpoint;
            const headers = { 'Content-Type': 'application/json' };
            const token = getAuthToken();
            if (token) headers['Authorization'] = 'Bearer ' + token;
            const resp = await fetch(url, { ...options, headers });
            const data = await resp.json();
            if (!resp.ok) throw new Error(data.detail || data.message);
            return data;
        }

        async function loadCandles(tf) {
            const resp = await apiRequest('/candles', {
                method: 'POST',
                body: JSON.stringify({
                    connector: botConnector,
                    symbol: botSymbol,
                    timeframe: tf,
                    limit: CHART_CANDLES_LIMIT,
                    market_data_source: 'websocket'
                })
            });
            return resp.data.map(c => ({ time: c[0]/1000, open: c[1], high: c[2], low: c[3], close: c[4] }));
        }

        function calculateEMA(closes, period) {
            const ema = [];
            const multiplier = 2 / (period + 1);
            for (let i = 0; i < closes.length; i++) {
                if (i === 0) ema.push(closes[i]);
                else if (i < period - 1) ema.push(null);
                else if (i === period - 1) {
                    let sum = 0;
                    for (let j = 0; j < period; j++) sum += closes[j];
                    ema.push(sum / period);
                } else {
                    ema.push((closes[i] - ema[i-1]) * multiplier + ema[i-1]);
                }
            }
            return ema;
        }

        function calculateRSI(closes, period) {
            const changes = [];
            for (let i = 1; i < closes.length; i++) changes.push(closes[i] - closes[i-1]);
            const gains = changes.map(c => c > 0 ? c : 0);
            const losses = changes.map(c => c < 0 ? -c : 0);
            const rsi = new Array(closes.length).fill(null);
            let avgGain = gains.slice(0, period).reduce((a,b)=>a+b,0)/period;
            let avgLoss = losses.slice(0, period).reduce((a,b)=>a+b,0)/period;
            for (let i = period; i < closes.length; i++) {
                if (avgLoss === 0) rsi[i] = 100;
                else rsi[i] = 100 - 100 / (1 + avgGain/avgLoss);
                if (i < closes.length - 1) {
                    avgGain = (avgGain*(period-1) + gains[i])/period;
                    avgLoss = (avgLoss*(period-1) + losses[i])/period;
                }
            }
            return rsi;
        }

        function saveDrawings() {
            localStorage.setItem('drawings_' + botId, JSON.stringify(drawings.map(d => ({ type: d.type, price: d.price, color: d.color }))));
        }

        function loadDrawings() {
            const saved = localStorage.getItem('drawings_' + botId);
            if (saved) {
                drawings = JSON.parse(saved);
                for (const d of drawings) {
                    if (d.type === 'hline') addHorizontalLine(d.price, d.color);
                }
            }
        }

        function addHorizontalLine(price, color = '#ffaa00') {
            const line = chart.addLineSeries({ color: color, lineWidth: 1, lineStyle: 2, priceLineVisible: false });
            const timeRange = chart.timeScale().getVisibleRange();
            if (timeRange) {
                line.setData([{ time: timeRange.from, value: price }, { time: timeRange.to, value: price }]);
            }
            drawings.push({ type: 'hline', price: price, color: color, lineRef: line });
            saveDrawings();
            return line;
        }

        async function addIndicator(type, period) {
            const candles = await loadCandles(currentTimeframe);
            const closes = candles.map(c => c.close);
            let values;
            if (type === 'ema') values = calculateEMA(closes, period);
            else if (type === 'rsi') values = calculateRSI(closes, period);
            else return;
            const series = chart.addLineSeries({ color: '#00ffaa', lineWidth: 1 });
            const data = candles.map((c, i) => ({ time: c.time, value: values[i] })).filter(d => d.value !== null);
            series.setData(data);
            indicators[type + period] = series;
        }

        async function initChart(tf) {
            if (wsInstance) wsInstance.close();
            if (chart) chart.remove();
            
            chart = LightweightCharts.createChart(document.getElementById('chart'), {
                layout: { background: { color: '#0d1117' }, textColor: '#ddd' },
                grid: { vertLines: { color: '#2a2a3a' }, horzLines: { color: '#2a2a3a' } },
                timeScale: { timeVisible: true }
            });
            candleSeries = chart.addCandlestickSeries();
            const candles = await loadCandles(tf);
            candleSeries.setData(candles);
            chart.timeScale().fitContent();
            
            drawings.forEach(d => { if (d.lineRef) chart.removeSeries(d.lineRef); });
            drawings = [];
            loadDrawings();
            
            const token = getAuthToken();
            if (token) {
                const wsUrl = 'ws://' + location.host + '/ws/candles?token=' + encodeURIComponent(token) +
                    '&connector=' + encodeURIComponent(botConnector) + '&symbol=' + encodeURIComponent(botSymbol) + '&timeframe=' + tf;
                wsInstance = new WebSocket(wsUrl);
                wsInstance.onmessage = (e) => {
                    const c = JSON.parse(e.data);
                    candleSeries.update({ time: c.timestamp/1000, open: c.open, high: c.high, low: c.low, close: c.close });
                };
                wsInstance.onerror = (err) => console.error('WS error:', err);
            }
        }

        window.addEventListener('DOMContentLoaded', () => {
            initChart('1H');
            document.getElementById('add-indicator').addEventListener('click', () => {
                const type = prompt('Тип (ema/rsi):', 'ema');
                const period = parseInt(prompt('Период:', type === 'ema' ? 12 : 14));
                if (type && period) addIndicator(type, period);
            });
            document.getElementById('add-hline').addEventListener('click', () => {
                const price = parseFloat(prompt('Цена линии:'));
                if (price) addHorizontalLine(price);
            });
            document.getElementById('clear-lines').addEventListener('click', () => {
                for (const d of drawings) {
                    if (d.lineRef) chart.removeSeries(d.lineRef);
                }
                drawings = [];
                saveDrawings();
            });
            document.getElementById('change-tf').addEventListener('click', async () => {
                currentTimeframe = document.getElementById('timeframe').value;
                await initChart(currentTimeframe);
            });
            document.getElementById('close-window').addEventListener('click', () => window.close());
        });
    `;

    const scriptBlock = win.document.createElement('script');
    scriptBlock.textContent = scriptContent;
    win.document.body.appendChild(scriptBlock);
}