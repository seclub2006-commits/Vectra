// web/static/js/state.js

// ==================== БОТЫ ====================
let _botsList = [];
export function getBotsList() { return _botsList; }
export function setBotsList(list) { _botsList = list || []; }
export function updateBotInList(botId, updates) {
    const index = _botsList.findIndex(b => b.id === botId);
    if (index !== -1) {
        _botsList[index] = { ..._botsList[index], ...updates };
    }
}
export function removeBotFromList(botId) {
    _botsList = _botsList.filter(b => b.id !== botId);
}

// ==================== КОННЕКТОРЫ ====================
let _connectorsList = [];
export function getConnectorsList() { return _connectorsList; }
export function setConnectorsList(list) { _connectorsList = list || []; }
export function updateConnectorInList(name, updates) {
    const index = _connectorsList.findIndex(c => c.name === name);
    if (index !== -1) {
        _connectorsList[index] = { ..._connectorsList[index], ...updates };
    }
}
export function removeConnectorFromList(name) {
    _connectorsList = _connectorsList.filter(c => c.name !== name);
}

// ==================== РУЧНОЙ БОТ (текущий активный) ====================
let _currentManualBotId = null;
let _currentManualSymbol = '';
let _currentManualConnector = '';
let _currentManualTf = '1H';
let _chartActive = false;

export function getCurrentManualBotId() { return _currentManualBotId; }
export function setCurrentManualBotId(id) { _currentManualBotId = id; }

export function getCurrentManualSymbol() { return _currentManualSymbol; }
export function setCurrentManualSymbol(symbol) { _currentManualSymbol = symbol; }

export function getCurrentManualConnector() { return _currentManualConnector; }
export function setCurrentManualConnector(connector) { _currentManualConnector = connector; }

export function getCurrentManualTf() { return _currentManualTf; }
export function setCurrentManualTf(tf) { _currentManualTf = tf; }

export function isChartActive() { return _chartActive; }
export function setChartActive(active) { _chartActive = active; }

// ==================== ГРАФИКИ И ИНДИКАТОРЫ ====================
let _manualChart = null;
let _manualCandleSeries = null;
let _manualWs = null;
let _manualIndicators = [];      // массив { series, type, period }
let _manualDrawings = [];        // массив { type, price, color, series }
let _manualEntryLine = null;
let _manualTpLine = null;
let _manualSlLine = null;
let _manualStrategyLines = [];

export function getManualChart() { return _manualChart; }
export function setManualChart(chart) { _manualChart = chart; }

export function getManualCandleSeries() { return _manualCandleSeries; }
export function setManualCandleSeries(series) { _manualCandleSeries = series; }

export function getManualWs() { return _manualWs; }
export function setManualWs(ws) {
    if (_manualWs) _manualWs.close();
    _manualWs = ws;
}

export function getManualIndicators() { return _manualIndicators; }
export function setManualIndicators(indicators) { _manualIndicators = indicators; }
export function addManualIndicator(indicator) { _manualIndicators.push(indicator); }
export function clearManualIndicators() {
    _manualIndicators.forEach(ind => { if (ind.series && _manualChart) _manualChart.removeSeries(ind.series); });
    _manualIndicators = [];
}

export function getManualDrawings() { return _manualDrawings; }
export function setManualDrawings(drawings) { _manualDrawings = drawings; }
export function addManualDrawing(drawing) { _manualDrawings.push(drawing); }
export function clearManualDrawings() {
    _manualDrawings.forEach(d => { if (d.series && _manualChart) _manualChart.removeSeries(d.series); });
    _manualDrawings = [];
}

export function getManualEntryLine() { return _manualEntryLine; }
export function setManualEntryLine(line) { _manualEntryLine = line; }
export function getManualTpLine() { return _manualTpLine; }
export function setManualTpLine(line) { _manualTpLine = line; }
export function getManualSlLine() { return _manualSlLine; }
export function setManualSlLine(line) { _manualSlLine = line; }
export function getManualStrategyLines() { return _manualStrategyLines; }
export function setManualStrategyLines(lines) { _manualStrategyLines = lines; }

// ==================== ЛОГИ ====================
let _currentLogPage = 1;
let _logsPerPage = 100;
let _allLogsCache = [];

export function getCurrentLogPage() { return _currentLogPage; }
export function setCurrentLogPage(page) { _currentLogPage = page; }
export function incrementLogPage() { _currentLogPage++; }
export function decrementLogPage() { if (_currentLogPage > 1) _currentLogPage--; }

export function getLogsPerPage() { return _logsPerPage; }
export function setLogsPerPage(limit) { _logsPerPage = limit; }

export function getAllLogsCache() { return _allLogsCache; }
export function setAllLogsCache(logs) { _allLogsCache = logs; }
export function clearLogsCache() { _allLogsCache = []; }

// ==================== ИНТЕРВАЛЫ ОБНОВЛЕНИЯ ====================
let _refreshIntervals = {};
export function getRefreshInterval(name) { return _refreshIntervals[name]; }
export function setRefreshInterval(name, intervalId) {
    if (_refreshIntervals[name]) clearInterval(_refreshIntervals[name]);
    _refreshIntervals[name] = intervalId;
}
export function clearRefreshInterval(name) {
    if (_refreshIntervals[name]) {
        clearInterval(_refreshIntervals[name]);
        delete _refreshIntervals[name];
    }
}
export function clearAllRefreshIntervals() {
    Object.keys(_refreshIntervals).forEach(name => clearRefreshInterval(name));
}

// ==================== WEBSOCKET ОБНОВЛЕНИЙ ====================
let _wsUpdates = null;
let _updateCallbacks = {};

export function getWsUpdates() { return _wsUpdates; }
export function setWsUpdates(ws) { _wsUpdates = ws; }
export function closeWsUpdates() { if (_wsUpdates) _wsUpdates.close(); _wsUpdates = null; }

export function getUpdateCallbacks() { return _updateCallbacks; }
export function setUpdateCallback(type, callback) { _updateCallbacks[type] = callback; }
export function removeUpdateCallback(type) { delete _updateCallbacks[type]; }

// ==================== ВСПОМОГАТЕЛЬНЫЕ ====================
export function resetAllState() {
    _botsList = [];
    _connectorsList = [];
    _currentManualBotId = null;
    _currentManualSymbol = '';
    _currentManualConnector = '';
    _currentManualTf = '1H';
    _chartActive = false;
    _manualChart = null;
    _manualCandleSeries = null;
    if (_manualWs) _manualWs.close();
    _manualWs = null;
    _manualIndicators = [];
    _manualDrawings = [];
    _manualEntryLine = null;
    _manualTpLine = null;
    _manualSlLine = null;
    _manualStrategyLines = [];
    _currentLogPage = 1;
    _logsPerPage = 100;
    _allLogsCache = [];
    clearAllRefreshIntervals();
    closeWsUpdates();
    _updateCallbacks = {};
}