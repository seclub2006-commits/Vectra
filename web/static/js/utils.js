// web/static/js/utils.js

import { THEME_DARK, THEME_LIGHT, THEME_STORAGE_KEY } from './config.js';

// ==================== NOTYF (глобальный объект) ====================
// Предполагается, что Notyf загружен из CDN в HTML
let notyfInstance = null;

export function getNotyf() {
    if (!notyfInstance && typeof Notyf !== 'undefined') {
        notyfInstance = new Notyf({
            duration: 3000,
            position: { x: 'right', y: 'top' },
            dismissible: true,
            ripple: true,
        });
    }
    return notyfInstance;
}

export function showSuccess(message) {
    const notyf = getNotyf();
    if (notyf) notyf.success(message);
    else console.log('[SUCCESS]', message);
}

export function showError(message) {
    const notyf = getNotyf();
    if (notyf) notyf.error(message);
    else console.error('[ERROR]', message);
}

export function showInfo(message) {
    const notyf = getNotyf();
    if (notyf) notyf.info(message);
    else console.log('[INFO]', message);
}

// ==================== ESCAPE HTML ====================
export function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/[&<>]/g, function (m) {
        if (m === '&') return '&amp;';
        if (m === '<') return '&lt;';
        if (m === '>') return '&gt;';
        return m;
    });
}

// ==================== ФОРМАТИРОВАНИЕ ДАТЫ ====================
export function formatDate(timestampMs) {
    if (!timestampMs) return '';
    const date = new Date(timestampMs);
    return date.toLocaleString();
}

export function formatTimeAgo(timestampMs) {
    const seconds = Math.floor((Date.now() - timestampMs) / 1000);
    if (seconds < 60) return `${seconds} сек назад`;
    const minutes = Math.floor(seconds / 60);
    if (minutes < 60) return `${minutes} мин назад`;
    const hours = Math.floor(minutes / 60);
    if (hours < 24) return `${hours} ч назад`;
    const days = Math.floor(hours / 24);
    return `${days} дн назад`;
}

// ==================== РАБОТА С ТЕМОЙ ====================
export function getCurrentTheme() {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved === THEME_LIGHT) return THEME_LIGHT;
    return THEME_DARK;
}

export function setTheme(theme) {
    const isDark = theme === THEME_DARK;
    const body = document.body;
    if (isDark) {
        body.classList.remove(THEME_LIGHT);
        body.classList.add(THEME_DARK);
    } else {
        body.classList.remove(THEME_DARK);
        body.classList.add(THEME_LIGHT);
    }
    localStorage.setItem(THEME_STORAGE_KEY, theme);

    // Управление CSS файлом светлой темы
    let link = document.getElementById('theme-css');
    if (!isDark && !link) {
        link = document.createElement('link');
        link.id = 'theme-css';
        link.rel = 'stylesheet';
        document.head.appendChild(link);
    }
    if (link) {
        link.href = isDark ? '' : '/static/css/light.css';
    }
}

export function toggleTheme() {
    const current = getCurrentTheme();
    setTheme(current === THEME_DARK ? THEME_LIGHT : THEME_DARK);
}

// ==================== ОБЩИЕ DOM-УТИЛИТЫ ====================
export function getElementSafe(id) {
    const el = document.getElementById(id);
    if (!el) console.warn(`Element with id "${id}" not found`);
    return el;
}

export function showModal(contentHtml) {
    const modal = getElementSafe('modal');
    const modalBody = getElementSafe('modal-body');
    if (!modal || !modalBody) return;
    modalBody.innerHTML = contentHtml;
    modal.style.display = 'flex';
}

export function hideModal() {
    const modal = getElementSafe('modal');
    if (modal) modal.style.display = 'none';
}

// ==================== РАСЧЁТ ИНДИКАТОРОВ (общие) ====================
export function calculateEMA(candles, period) {
    // candles: массив объектов { time, open, high, low, close, volume } или массив массивов [timestamp, open, high, low, close, volume]
    let closes;
    if (Array.isArray(candles[0])) {
        closes = candles.map(c => c[4]); // close индекс 4
    } else {
        closes = candles.map(c => c.close);
    }
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
            ema.push((closes[i] - ema[i - 1]) * multiplier + ema[i - 1]);
        }
    }
    return ema;
}

export function calculateRSI(candles, period) {
    let closes;
    if (Array.isArray(candles[0])) {
        closes = candles.map(c => c[4]);
    } else {
        closes = candles.map(c => c.close);
    }
    const changes = [];
    for (let i = 1; i < closes.length; i++) changes.push(closes[i] - closes[i - 1]);
    const gains = changes.map(c => c > 0 ? c : 0);
    const losses = changes.map(c => c < 0 ? -c : 0);
    const rsi = new Array(closes.length).fill(null);
    let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
    let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
    for (let i = period; i < closes.length; i++) {
        if (avgLoss === 0) rsi[i] = 100;
        else rsi[i] = 100 - 100 / (1 + avgGain / avgLoss);
        if (i < closes.length - 1) {
            avgGain = (avgGain * (period - 1) + gains[i]) / period;
            avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
        }
    }
    return rsi;
}

// ==================== ДЕБАГ ====================
export function logDebug(module, message, data = null) {
    if (localStorage.getItem('debug') === 'true') {
        if (data) console.log(`[${module}] ${message}`, data);
        else console.log(`[${module}] ${message}`);
    }
}