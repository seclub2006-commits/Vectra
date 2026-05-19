// web/static/js/config.js

// Настройки обновления
export const REFRESH_INTERVAL = 5000;      // мс, интервал обновления таблиц
export const STATUS_INTERVAL = 3000;       // мс, проверка соединения
export const BROADCAST_INTERVAL = 2000;    // мс, WebSocket обновления статусов

// Настройки графиков
export const CHART_HEIGHT = 400;
export const CHART_DEFAULT_TIMEFRAME = '1H';
export const CHART_CANDLES_LIMIT = 500;

// Логи
export const LOGS_DAYS_BACK = 7;           // за сколько дней показывать логи
export const LOGS_PER_PAGE_DEFAULT = 100;

// API и WebSocket
export const API_BASE = '/api';
export const WS_CANDLES_URL = '/ws/candles';
export const WS_UPDATES_URL = '/ws/updates';

// Цвета и темы
export const THEME_DARK = 'dark';
export const THEME_LIGHT = 'light';
export const THEME_STORAGE_KEY = 'theme';

// Индикаторы по умолчанию
export const DEFAULT_EMA_PERIOD = 12;
export const DEFAULT_RSI_PERIOD = 14;

// Доступные таймфреймы
export const TIMEFRAMES = ['1m', '5m', '15m', '1H', '4H', '1D'];

// Стратегии для создания бота
export const STRATEGIES = [
    { display: 'EMA Bot', path: 'trend.ema_bot.EmaBot' },
    { display: 'RSI Bot', path: 'trend.rsi_bot.RSIBot' },
    { display: 'Grid Bot', path: 'grid.grid_bot.GridBot' },
    { display: 'Test Bot', path: 'test.test_bot.TestBot' },
    { display: 'Manual Bot', path: 'manual.manual_bot.ManualBot' }
];