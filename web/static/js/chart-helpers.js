// web/static/js/chart-helpers.js

import { calculateEMA, calculateRSI } from './utils.js';

/**
 * Преобразует массив свечей из API-формата [[timestamp, open, high, low, close, volume], ...]
 * в формат для Lightweight Charts: { time: number, open: number, high: number, low: number, close: number }
 * @param {Array} candles - массив свечей из API
 * @returns {Array} массив объектов для графика
 */
export function convertCandlesToChartData(candles) {
    if (!candles || !candles.length) return [];
    return candles.map(c => ({
        time: c[0] / 1000,           // timestamp в секундах
        open: c[1],
        high: c[2],
        low: c[3],
        close: c[4],
        volume: c[5]                 // объём (опционально)
    }));
}

/**
 * Обновляет последнюю свечу в серии (для WebSocket обновлений)
 * @param {Object} series - серия свечей Lightweight Charts
 * @param {Object} candle - свеча из WebSocket { timestamp, open, high, low, close, volume }
 */
export function updateLastCandle(series, candle) {
    if (!series || !candle) return;
    series.update({
        time: candle.timestamp / 1000,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close
    });
}

/**
 * Добавляет новую серию с индикатором на график
 * @param {Object} chart - экземпляр Lightweight Charts
 * @param {string} type - 'ema' или 'rsi'
 * @param {number} period - период индикатора
 * @param {Array} candles - исторические свечи (в API-формате)
 * @param {string} color - цвет линии
 * @returns {Object} созданная серия (или null при ошибке)
 */
export function addIndicatorToChart(chart, type, period, candles, color = '#00ffaa') {
    if (!chart || !candles || !candles.length) return null;

    let values;
    if (type === 'ema') {
        values = calculateEMA(candles, period);
    } else if (type === 'rsi') {
        values = calculateRSI(candles, period);
    } else {
        console.warn(`Unknown indicator type: ${type}`);
        return null;
    }

    const series = chart.addLineSeries({
        color: color,
        lineWidth: 1,
        title: `${type.toUpperCase()}(${period})`
    });

    const chartData = convertCandlesToChartData(candles);
    const data = chartData.map((c, i) => ({
        time: c.time,
        value: values[i]
    })).filter(d => d.value !== null);

    series.setData(data);
    return series;
}

/**
 * Добавляет горизонтальную линию на график
 * @param {Object} chart - экземпляр Lightweight Charts
 * @param {number} price - цена (уровень)
 * @param {string} color - цвет линии
 * @param {number} lineWidth - толщина (по умолчанию 1)
 * @param {number} lineStyle - стиль (0=сплошная, 1=пунктирная, 2=точечная...)
 * @returns {Object} созданная серия линии
 */
export function addHorizontalLineToChart(chart, price, color = '#ffaa00', lineWidth = 1, lineStyle = 2) {
    if (!chart) return null;
    const series = chart.addLineSeries({
        color: color,
        lineWidth: lineWidth,
        lineStyle: lineStyle,
        priceLineVisible: false,
        lastValueVisible: false
    });
    const timeRange = chart.timeScale().getVisibleRange();
    if (timeRange) {
        series.setData([
            { time: timeRange.from, value: price },
            { time: timeRange.to, value: price }
        ]);
    }
    return series;
}

/**
 * Обновляет существующую горизонтальную линию при изменении видимой области
 * @param {Object} series - серия линии
 * @param {Object} chart - экземпляр Lightweight Charts
 * @param {number} price - цена
 */
export function updateHorizontalLineRange(series, chart, price) {
    if (!series || !chart) return;
    const timeRange = chart.timeScale().getVisibleRange();
    if (timeRange) {
        series.setData([
            { time: timeRange.from, value: price },
            { time: timeRange.to, value: price }
        ]);
    }
}

/**
 * Создаёт пустой график с настройками по умолчанию
 * @param {HTMLElement} container - DOM-элемент, в который будет помещён график
 * @param {number} height - высота в пикселях (по умолчанию 400)
 * @returns {Object} экземпляр Lightweight Charts
 */
export function createDefaultChart(container, height = 400) {
    if (!container) return null;
    return LightweightCharts.createChart(container, {
        layout: {
            background: { color: '#0d1117' },
            textColor: '#ddd'
        },
        grid: {
            vertLines: { color: '#2a2a3a' },
            horzLines: { color: '#2a2a3a' }
        },
        width: container.clientWidth,
        height: height,
        timeScale: {
            timeVisible: true,
            borderColor: '#2a2a3a',
            secondsVisible: false
        },
        crosshair: {
            mode: LightweightCharts.CrosshairMode.Normal
        },
        rightPriceScale: {
            borderColor: '#2a2a3a'
        }
    });
}

/**
 * Создаёт свечную серию для графика
 * @param {Object} chart - экземпляр Lightweight Charts
 * @returns {Object} серия свечей
 */
export function createCandlestickSeries(chart) {
    if (!chart) return null;
    return chart.addCandlestickSeries({
        upColor: '#26a69a',
        downColor: '#ef5350',
        borderVisible: false,
        wickUpColor: '#26a69a',
        wickDownColor: '#ef5350',
        priceLineVisible: false
    });
}

/**
 * Загружает исторические свечи через REST и отображает их на графике
 * @param {Object} series - серия свечей
 * @param {Function} getCandlesFn - асинхронная функция для получения свечей (должна возвращать массив в API-формате)
 * @param {Object} params - параметры для getCandlesFn (connector, symbol, timeframe, limit и т.д.)
 * @returns {Promise<boolean>} успех операции
 */
export async function loadCandlesToSeries(series, getCandlesFn, params) {
    if (!series) return false;
    try {
        const candles = await getCandlesFn(params);
        if (!candles || !candles.length) return false;
        const chartData = convertCandlesToChartData(candles);
        series.setData(chartData);
        return true;
    } catch (err) {
        console.error('Failed to load candles:', err);
        return false;
    }
}

/**
 * Очищает все серии (кроме свечной) с графика
 * @param {Object} chart - экземпляр Lightweight Charts
 * @param {Array} seriesToKeep - массив серий, которые нужно сохранить (например, свечная серия)
 */
export function clearNonEssentialSeries(chart, seriesToKeep = []) {
    if (!chart) return;
    // Получить все серии невозможно напрямую, поэтому этот метод требует отслеживания серий в вызывающем коде.
    // Обычно используется ручное удаление через вызов chart.removeSeries(series).
    console.warn('clearNonEssentialSeries must be implemented manually due to Lightweight Charts API limitations');
}