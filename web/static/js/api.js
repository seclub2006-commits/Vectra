// web/static/js/api.js

import { API_BASE } from './config.js';
import { getCurrentTheme } from './utils.js'; // для возможного использования в будущем

// ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
function getAuthToken() {
    return localStorage.getItem('access_token');
}

function setAuthToken(token) {
    if (token) localStorage.setItem('access_token', token);
    else localStorage.removeItem('access_token');
}

function getHeaders() {
    const headers = { 'Content-Type': 'application/json' };
    const token = getAuthToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;
    return headers;
}

async function apiRequest(endpoint, options = {}, retries = 2) {
    const url = `${API_BASE}${endpoint}`;
    let lastError = null;

    for (let attempt = 0; attempt <= retries; attempt++) {
        try {
            const response = await fetch(url, {
                ...options,
                headers: { ...getHeaders(), ...options.headers }
            });

            if (response.status === 401) {
                setAuthToken(null);
                if (typeof window.showLogin === 'function') {
                    window.showLogin();
                } else {
                    window.location.reload();
                }
                throw new Error('Unauthorized');
            }

            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || data.message || 'Request failed');
            return data;
        } catch (error) {
            lastError = error;
            if (attempt === retries) break;
            if (error.message === 'Failed to fetch' || error.message.includes('Network')) {
                await new Promise(resolve => setTimeout(resolve, 1000 * (attempt + 1)));
                continue;
            }
            break;
        }
    }
    throw lastError;
}

// ==================== АВТОРИЗАЦИЯ ====================
export async function login(password) {
    const data = await apiRequest('/login', {
        method: 'POST',
        body: JSON.stringify({ password })
    });
    setAuthToken(data.access_token);
    return true;
}

export function logout() {
    setAuthToken(null);
    if (typeof window.showLogin === 'function') window.showLogin();
    else window.location.reload();
}

// ==================== БОТЫ ====================
export async function getBots() {
    const res = await apiRequest('/bots');
    return res.data;
}

export async function startBot(botData) {
    const res = await apiRequest('/bots/start', { method: 'POST', body: JSON.stringify(botData) });
    return res;
}

export async function stopBot(botId) {
    const res = await apiRequest('/bots/stop', { method: 'POST', body: JSON.stringify({ bot_id: botId }) });
    return res;
}

export async function deleteBot(botId) {
    const res = await apiRequest('/bots/delete', { method: 'DELETE', body: JSON.stringify({ bot_id: botId }) });
    return res;
}

export async function updateBotConfig(data) {
    const res = await apiRequest('/bots/update_config', { method: 'POST', body: JSON.stringify(data) });
    return res;
}

export async function getBotStatus(botId) {
    const res = await apiRequest(`/bots/${botId}/status`);
    return res.data;
}

export async function getBotTrades(botId, limit = 100) {
    const res = await apiRequest(`/bots/${botId}/trades?limit=${limit}`);
    return res.data;
}

export async function getBotParamsSchema(botId) {
    const res = await apiRequest(`/bots/${botId}/params_schema`);
    return res.data;
}

export async function setBotParameter(botId, paramName, paramValue) {
    const res = await apiRequest(`/bots/${botId}/set_parameter`, {
        method: 'POST',
        body: JSON.stringify({ bot_id: botId, param_name: paramName, param_value: paramValue })
    });
    return res;
}

export async function getBotMarketDataSource(botId) {
    const res = await apiRequest(`/bots/${botId}/market_data_source`);
    return res.data;
}

export async function callBotMethod(botId, methodName, params) {
    const res = await apiRequest('/bot/method', {
        method: 'POST',
        body: JSON.stringify({ bot_id: botId, method_name: methodName, params })
    });
    return res;
}

export async function getBotStrategyDescription(botId) {
    const res = await apiRequest(`/bot/strategy?bot_id=${botId}`);
    return res.data;
}

export async function getStrategyParamsSchema(strategyPath) {
    const res = await apiRequest(`/strategy/params_schema?strategy_name=${encodeURIComponent(strategyPath)}`);
    return res.data;
}

// ==================== КОННЕКТОРЫ ====================
export async function getConnectors() {
    const res = await apiRequest('/connectors');
    return res.data;
}

export async function createConnector(settings) {
    const res = await apiRequest('/connectors/create', { method: 'POST', body: JSON.stringify(settings) });
    return res;
}

export async function getConnectorSettings(name) {
    const res = await apiRequest(`/connectors/${name}/settings`);
    return res.data;
}

export async function updateConnectorSettings(name, settings) {
    const res = await apiRequest(`/connectors/${name}/settings`, {
        method: 'PUT',
        body: JSON.stringify({ name, settings })
    });
    return res;
}

export async function deleteConnector(name) {
    const res = await apiRequest(`/connectors/${name}/delete`, { method: 'DELETE' });
    return res;
}

export async function setConnectorStatus(name, status) {
    const res = await apiRequest(`/connectors/${name}/status`, {
        method: 'POST',
        body: JSON.stringify({ name, status })
    });
    return res;
}

// ==================== РЫНОЧНЫЕ ДАННЫЕ ====================
export async function getCandles(params) {
    const res = await apiRequest('/candles', { method: 'POST', body: JSON.stringify(params) });
    return res.data;
}

export async function getTicker(connector, symbol) {
    const res = await apiRequest(`/ticker?connector=${encodeURIComponent(connector)}&symbol=${encodeURIComponent(symbol)}`);
    return res.data;
}

export async function getSymbols(connector, productType = '') {
    const res = await apiRequest(`/symbols?connector=${encodeURIComponent(connector)}&product_type=${encodeURIComponent(productType)}`);
    return res.data;
}

export async function getOrderBook(connector, symbol, depth = 20) {
    const res = await apiRequest(`/orderbook?connector=${encodeURIComponent(connector)}&symbol=${encodeURIComponent(symbol)}&depth=${depth}`);
    return res.data;
}

// ==================== БАЛАНС, ПОЗИЦИИ, ОРДЕРА ====================
export async function getBalance(connectorName, currency = '') {
    const res = await apiRequest(`/balance?connector_name=${encodeURIComponent(connectorName)}&currency=${encodeURIComponent(currency)}`);
    return res.data;
}

export async function getOpenOrders(connectorName, symbol = '') {
    const res = await apiRequest(`/orders?connector_name=${encodeURIComponent(connectorName)}&symbol=${encodeURIComponent(symbol)}`);
    return res.data;
}

export async function createOrder(orderData) {
    const res = await apiRequest('/order/create', { method: 'POST', body: JSON.stringify(orderData) });
    return res;
}

export async function cancelOrder(connectorName, symbol, orderId) {
    const res = await apiRequest('/order/cancel', {
        method: 'POST',
        body: JSON.stringify({ connector_name: connectorName, symbol, order_id: orderId })
    });
    return res;
}

export async function getPositions(connectorName, symbol = '') {
    const res = await apiRequest(`/positions?connector_name=${encodeURIComponent(connectorName)}&symbol=${encodeURIComponent(symbol)}`);
    return res.data;
}

export async function closePosition(connectorName, symbol, holdSide = '') {
    const res = await apiRequest('/position/close', {
        method: 'POST',
        body: JSON.stringify({ connector_name: connectorName, symbol, hold_side: holdSide })
    });
    return res;
}

export async function setLeverage(connectorName, symbol, leverage, marginMode = 'crossed') {
    const res = await apiRequest('/leverage', {
        method: 'POST',
        body: JSON.stringify({ connector_name: connectorName, symbol, leverage, margin_mode: marginMode })
    });
    return res;
}

export async function setTPSL(data) {
    const res = await apiRequest('/tpsl', { method: 'POST', body: JSON.stringify(data) });
    return res;
}

// ==================== ЛОГИ ====================
export async function getLogs(sinceTimestamp, limit = 1000) {
    const res = await apiRequest(`/logs?since_timestamp=${sinceTimestamp}&limit=${limit}`);
    return res.data;
}

// ==================== РУЧНЫЕ ВЫЗОВЫ ====================
export async function callManualBot(botId, method, params) {
    const res = await apiRequest('/manual/call', {
        method: 'POST',
        body: JSON.stringify({ bot_id: botId, method, params })
    });
    return res;
}

// ==================== WEBSOCKET СВЕЧЕЙ ====================
export function subscribeCandles(connector, symbol, timeframe, onCandle, onError, marketDataSource = 'websocket', config = '') {
    const token = getAuthToken();
    if (!token) {
        if (onError) onError(new Error('No auth token for WebSocket candles'));
        return null;
    }
    const wsUrl = `ws://${location.host}/ws/candles?token=${encodeURIComponent(token)}&connector=${encodeURIComponent(connector)}&symbol=${encodeURIComponent(symbol)}&timeframe=${encodeURIComponent(timeframe)}&market_data_source=${encodeURIComponent(marketDataSource)}&market_data_source_config=${encodeURIComponent(config)}`;
    const ws = new WebSocket(wsUrl);
    ws.onmessage = (event) => {
        try {
            const candle = JSON.parse(event.data);
            onCandle(candle);
        } catch (e) { console.error(e); }
    };
    ws.onerror = (err) => { if (onError) onError(err); };
    ws.onclose = (event) => {
        console.log(`Candles WebSocket closed, code=${event.code}`);
        if (event.code === 4001) {
            setAuthToken(null);
            if (typeof window.showLogin === 'function') window.showLogin();
        }
    };
    return ws;
}

// ==================== ОБНОВЛЕНИЯ ЧЕРЕЗ WEBSOCKET ====================
export function connectUpdatesWebSocket(callbacks) {
    const token = getAuthToken();
    if (!token) {
        console.error('No auth token for WebSocket updates');
        return null;
    }
    const wsUrl = `ws://${location.host}/ws/updates?token=${encodeURIComponent(token)}`;
    const ws = new WebSocket(wsUrl);
    ws.onopen = () => console.log('Updates WebSocket connected');
    ws.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (callbacks[data.type]) callbacks[data.type](data.data);
        } catch (e) { console.error(e); }
    };
    ws.onclose = (event) => {
        console.log(`Updates WebSocket closed, code=${event.code}`);
        if (event.code === 4001) {
            setAuthToken(null);
            if (typeof window.showLogin === 'function') window.showLogin();
            return;
        }
        setTimeout(() => connectUpdatesWebSocket(callbacks), 3000);
    };
    ws.onerror = (err) => console.error('WebSocket error:', err);
    return ws;
}