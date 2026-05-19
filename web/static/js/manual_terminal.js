// web/static/js/manual_terminal.js – диагностическая версия
import { CHART_CANDLES_LIMIT } from './config.js';
import { showError, showSuccess } from './utils.js';
import {
    getConnectors,
    getSymbols,
    getCandles,
    subscribeCandles,
    getBalance,
    getPositions,
    getOpenOrders,
    createOrder,
    cancelOrder,
    closePosition,
    setLeverage,
    setTPSL,
    getOrderBook
} from './api.js';

let currentConnector = null;
let currentSymbol = null;
let currentTimeframe = '1H';
let currentMarketDataSource = 'websocket';
let currentMarketDataSourceConfig = '';
let currentPosition = null;
let refreshInterval = null;
let chart = null;
let candleSeries = null;
let wsCandles = null;

const dom = {};

function cacheDom() {
    dom.connectorSelect = document.getElementById('connector-select');
    dom.symbolSelect = document.getElementById('symbol-select');
    dom.timeframeSelect = document.getElementById('timeframe-select');
    dom.sourceSelect = document.getElementById('data-source-select');
    dom.balanceDiv = document.getElementById('balance-display');
    dom.positionInfoDiv = document.getElementById('position-info');
    dom.orderSide = document.getElementById('order-side');
    dom.orderType = document.getElementById('order-type');
    dom.orderPrice = document.getElementById('order-price');
    dom.orderAmount = document.getElementById('order-amount');
    dom.orderSubmit = document.getElementById('order-submit');
    dom.leverageSlider = document.getElementById('leverage-slider');
    dom.leverageValue = document.getElementById('leverage-value');
    dom.leverageApply = document.getElementById('leverage-apply');
    dom.tpPrice = document.getElementById('tp-price');
    dom.slPrice = document.getElementById('sl-price');
    dom.tpslApply = document.getElementById('tpsl-apply');
    dom.closePositionBtn = document.getElementById('close-position-btn');
    dom.openOrdersTable = document.getElementById('open-orders-table-body');
    const statusDiv = document.getElementById('conn-status');
    if (statusDiv) statusDiv.style.display = 'none';
}

function attachEvents() {
    dom.connectorSelect?.addEventListener('change', async (e) => {
        currentConnector = e.target.value;
        await loadSymbols();
        if (currentSymbol) {
            await initChart(true);
            await refreshAll();
        }
    });
    dom.symbolSelect?.addEventListener('change', async (e) => {
        currentSymbol = e.target.value;
        await initChart(true);
        await refreshAll();
    });
    dom.timeframeSelect?.addEventListener('change', async (e) => {
        currentTimeframe = e.target.value;
        await initChart(true);
    });
    dom.sourceSelect?.addEventListener('change', (e) => {
        currentMarketDataSource = e.target.value;
        if (currentMarketDataSource === 'csv') {
            currentMarketDataSourceConfig = prompt('CSV config JSON:') || '';
        } else {
            currentMarketDataSourceConfig = '';
        }
        if (currentSymbol) initChart(true);
    });
    dom.orderSubmit?.addEventListener('click', () => submitOrder());
    dom.leverageApply?.addEventListener('click', () => applyLeverage());
    dom.tpslApply?.addEventListener('click', () => applyTPSL());
    dom.closePositionBtn?.addEventListener('click', () => closeCurrentPosition());
    dom.leverageSlider?.addEventListener('input', () => {
        if (dom.leverageValue) dom.leverageValue.textContent = dom.leverageSlider.value + 'x';
    });
}

async function loadConnectors() {
    try {
        let response = await getConnectors();
        let connectors = [];
        if (Array.isArray(response)) connectors = response;
        else if (response && response.data) connectors = response.data;
        else if (response && response.connectors) connectors = response.connectors;
        if (!connectors.length) {
            dom.connectorSelect.innerHTML = '<option>-- Нет коннекторов --</option>';
            return;
        }
        dom.connectorSelect.innerHTML = '<option value="">-- Выберите коннектор --</option>';
        for (const c of connectors) {
            const opt = document.createElement('option');
            opt.value = c.name;
            opt.textContent = `${c.name} (${c.exchange} - ${c.product_type})`;
            dom.connectorSelect.appendChild(opt);
        }
        const urlParams = new URLSearchParams(window.location.search);
        const preferredConnector = urlParams.get('connector');
        if (preferredConnector && connectors.some(c => c.name === preferredConnector)) {
            dom.connectorSelect.value = preferredConnector;
            currentConnector = preferredConnector;
        } else if (connectors.length) {
            dom.connectorSelect.value = connectors[0].name;
            currentConnector = connectors[0].name;
        }
    } catch (err) {
        console.error(err);
        showError('Ошибка загрузки коннекторов');
    }
}

async function loadSymbols() {
    if (!currentConnector) return;
    try {
        let response = await getSymbols(currentConnector, 'USDT-FUTURES');
        console.log('Symbols response:', response); // для диагностики

        let symbols = [];
        if (Array.isArray(response)) {
            symbols = response;
        } else if (response && response.data) {
            symbols = response.data;
        } else if (response && response.symbols) {
            symbols = response.symbols;
        } else if (response && typeof response === 'object') {
            // Если пришёл объект, но мы не знаем ключ – показываем ошибку
            throw new Error('Неожиданный формат ответа: ' + JSON.stringify(response).substring(0, 200));
        }

        if (!symbols.length) {
            dom.symbolSelect.innerHTML = '<option style="color:orange;">-- Нет символов (пустой список) --</option>';
            return;
        }

        dom.symbolSelect.innerHTML = '<option value="">-- Выберите символ --</option>';
        for (const sym of symbols) {
            const opt = document.createElement('option');
            opt.value = sym;
            opt.textContent = sym;
            dom.symbolSelect.appendChild(opt);
        }

        const urlParams = new URLSearchParams(window.location.search);
        const preferredSymbol = urlParams.get('symbol');
        if (preferredSymbol && symbols.includes(preferredSymbol)) {
            dom.symbolSelect.value = preferredSymbol;
            currentSymbol = preferredSymbol;
        } else if (symbols.length) {
            dom.symbolSelect.value = symbols[0];
            currentSymbol = symbols[0];
        }
    } catch (err) {
        console.error('loadSymbols error:', err);
        // Показываем ошибку прямо в селекте
        dom.symbolSelect.innerHTML = `<option style="color:red;">❌ Ошибка: ${err.message}</option>`;
        showError('Ошибка загрузки символов: ' + err.message);
    }
}

async function initChart(force = false) {
    if (!currentSymbol || !currentConnector) return;
    const container = document.getElementById('chart');
    if (!container) return;
    if (force && chart) {
        if (wsCandles) wsCandles.close();
        chart.remove();
        chart = null;
    }
    if (!chart) {
        if (typeof LightweightCharts === 'undefined') {
            showError('LightweightCharts не загружен');
            return;
        }
        chart = LightweightCharts.createChart(container, {
            layout: { background: { color: '#0d1117' }, textColor: '#ddd' },
            grid: { vertLines: { color: '#2a2a3a' }, horzLines: { color: '#2a2a3a' } },
            width: container.clientWidth,
            height: 500,
            timeScale: { timeVisible: true }
        });
        candleSeries = chart.addCandlestickSeries({
            upColor: '#26a69a', downColor: '#ef5350'
        });
        window.addEventListener('resize', () => chart.applyOptions({ width: container.clientWidth }));
    }
    const candles = await getCandles({
        connector: currentConnector,
        symbol: currentSymbol,
        timeframe: currentTimeframe,
        limit: CHART_CANDLES_LIMIT,
        market_data_source: currentMarketDataSource,
        market_data_source_config: currentMarketDataSourceConfig
    });
    if (candles && candles.length) {
        const data = candles.map(c => ({ time: c[0] / 1000, open: c[1], high: c[2], low: c[3], close: c[4] }));
        candleSeries.setData(data);
        chart.timeScale().fitContent();
    }
    if (wsCandles) wsCandles.close();
    if (currentMarketDataSource === 'websocket' || currentMarketDataSource === 'csv') {
        wsCandles = subscribeCandles(
            currentConnector, currentSymbol, currentTimeframe,
            (candle) => candleSeries?.update({ time: candle.timestamp / 1000, open: candle.open, high: candle.high, low: candle.low, close: candle.close }),
            console.error,
            currentMarketDataSource,
            currentMarketDataSourceConfig
        );
    }
}

function startRefreshLoop() {
    if (refreshInterval) clearInterval(refreshInterval);
    refreshInterval = setInterval(async () => {
        if (currentConnector && currentSymbol) await refreshAll();
    }, 2000);
}

async function refreshAll() {
    await Promise.all([updateBalance(), updatePosition(), updateOpenOrders()]);
}

async function updateBalance() {
    if (!currentConnector) return;
    try {
        const balances = await getBalance(currentConnector);
        const usdt = balances.find(b => b.currency === 'USDT');
        dom.balanceDiv.innerHTML = `<strong>USDT:</strong> ${usdt ? usdt.available.toFixed(2) : '0'}<br>${balances.map(b => `${b.currency}: ${b.total.toFixed(2)}`).join(' | ')}`;
    } catch (err) { }
}

async function updatePosition() {
    if (!currentConnector || !currentSymbol) return;
    try {
        const positions = await getPositions(currentConnector, currentSymbol);
        currentPosition = positions[0] || null;
        if (dom.positionInfoDiv) {
            if (currentPosition) {
                dom.positionInfoDiv.innerHTML = `Позиция: ${currentPosition.side.toUpperCase()} ${currentPosition.size} @ ${currentPosition.entry_price}<br>PnL: ${currentPosition.pnl.toFixed(2)}`;
                dom.closePositionBtn.disabled = false;
            } else {
                dom.positionInfoDiv.innerHTML = 'Нет позиции';
                dom.closePositionBtn.disabled = true;
            }
        }
    } catch (err) { }
}

async function updateOpenOrders() {
    if (!currentConnector || !currentSymbol) return;
    try {
        const orders = await getOpenOrders(currentConnector, currentSymbol);
        if (!dom.openOrdersTable) return;
        dom.openOrdersTable.innerHTML = '';
        for (const o of orders) {
            const row = dom.openOrdersTable.insertRow();
            row.insertCell(0).textContent = o.order_id;
            row.insertCell(1).textContent = o.side;
            row.insertCell(2).textContent = o.order_type;
            row.insertCell(3).textContent = o.price;
            row.insertCell(4).textContent = o.quantity;
            row.insertCell(5).textContent = o.filled;
            const btn = document.createElement('button');
            btn.textContent = 'Отменить';
            btn.onclick = () => cancelOrderById(o.order_id);
            row.insertCell(6).appendChild(btn);
        }
    } catch (err) { }
}

async function submitOrder() {
    const side = dom.orderSide.value;
    const type = dom.orderType.value;
    let price = parseFloat(dom.orderPrice.value);
    const amount = parseFloat(dom.orderAmount.value);
    if (isNaN(amount) || amount <= 0) return showError('Введите количество');
    if (type !== 'market' && isNaN(price)) return showError('Укажите цену');
    try {
        const result = await createOrder({
            connector_name: currentConnector,
            symbol: currentSymbol,
            side, order_type: type,
            quantity: amount, price: price || 0,
            preset_tp: 0, preset_sl: 0
        });
        if (result.status === 'ok') {
            showSuccess('Ордер отправлен');
            await updateOpenOrders();
            await updateBalance();
        } else showError(result.error);
    } catch (err) { showError(err.message); }
}

async function applyLeverage() {
    const lev = parseInt(dom.leverageSlider.value);
    if (!currentConnector || !currentSymbol) return;
    try {
        await setLeverage(currentConnector, currentSymbol, lev, 'crossed');
        showSuccess(`Плечо ${lev}x`);
    } catch (err) { showError(err.message); }
}

async function applyTPSL() {
    let tp = parseFloat(dom.tpPrice.value) || 0;
    let sl = parseFloat(dom.slPrice.value) || 0;
    if (!tp && !sl) return showError('Укажите TP или SL');
    if (!currentPosition) return showError('Нет позиции');
    try {
        if (tp) await setTPSL({ connector_name: currentConnector, symbol: currentSymbol, hold_side: currentPosition.side, trigger_price: tp, execute_price: 0, tpsl_type: 'profit_plan', size: currentPosition.size });
        if (sl) await setTPSL({ connector_name: currentConnector, symbol: currentSymbol, hold_side: currentPosition.side, trigger_price: sl, execute_price: 0, tpsl_type: 'loss_plan', size: currentPosition.size });
        showSuccess('TP/SL установлены');
    } catch (err) { showError(err.message); }
}

async function closeCurrentPosition() {
    if (!currentPosition) return showError('Нет позиции');
    try {
        await closePosition(currentConnector, currentSymbol, currentPosition.side);
        showSuccess('Позиция закрыта');
        await updatePosition();
        await updateBalance();
    } catch (err) { showError(err.message); }
}

async function cancelOrderById(orderId) {
    try {
        await cancelOrder(currentConnector, currentSymbol, orderId);
        showSuccess('Ордер отменён');
        await updateOpenOrders();
    } catch (err) { showError(err.message); }
}

async function init() {
    cacheDom();
    attachEvents();
    await loadConnectors();
    if (currentConnector) {
        await loadSymbols();
        const urlParams = new URLSearchParams(window.location.search);
        if (urlParams.get('timeframe')) currentTimeframe = urlParams.get('timeframe');
        if (urlParams.get('market_data_source')) currentMarketDataSource = urlParams.get('market_data_source');
        if (urlParams.get('market_data_source_config')) currentMarketDataSourceConfig = urlParams.get('market_data_source_config');
        if (dom.timeframeSelect && currentTimeframe) dom.timeframeSelect.value = currentTimeframe;
        if (dom.sourceSelect && currentMarketDataSource) dom.sourceSelect.value = currentMarketDataSource;
        startRefreshLoop();
        await initChart();
        await refreshAll();
    } else {
        showError('Коннектор не выбран');
    }
}

document.addEventListener('DOMContentLoaded', init);