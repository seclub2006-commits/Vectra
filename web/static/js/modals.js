// web/static/js/modals.js

import { STRATEGIES, TIMEFRAMES } from './config.js';
import { escapeHtml, showError, showSuccess, showModal, hideModal, getElementSafe } from './utils.js';
import { getConnectorsList, setBotsList } from './state.js';
import { getConnectors, getSymbols, startBot, createConnector, getStrategyParamsSchema } from './api.js';
import { loadBotsTable } from './ui.js';

// ==================== КАСТОМНЫЙ СЕЛЕКТОР СИМВОЛОВ ====================
export function createSymbolSelector(symbols, selectedSymbol, onSelect) {
    const container = document.createElement('div');
    container.className = 'custom-symbol-select';

    const input = document.createElement('input');
    input.type = 'text';
    input.placeholder = 'Поиск пары или выберите из списка...';
    input.value = selectedSymbol || '';

    const listContainer = document.createElement('div');
    listContainer.className = 'symbol-list-container';

    container.appendChild(input);
    container.appendChild(listContainer);

    function renderList(filter = '') {
        listContainer.innerHTML = '';
        const filtered = symbols.filter(s => s.toLowerCase().includes(filter.toLowerCase()));
        if (filtered.length === 0) {
            const noData = document.createElement('div');
            noData.className = 'symbol-option';
            noData.textContent = 'Нет совпадений';
            listContainer.appendChild(noData);
        } else {
            filtered.forEach(sym => {
                const option = document.createElement('div');
                option.className = 'symbol-option';
                if (sym === selectedSymbol) option.classList.add('selected');
                option.textContent = sym;
                option.addEventListener('click', () => {
                    input.value = sym;
                    selectedSymbol = sym;
                    if (onSelect) onSelect(sym);
                    listContainer.classList.remove('show');
                    document.querySelectorAll('.symbol-option').forEach(opt => opt.classList.remove('selected'));
                    option.classList.add('selected');
                });
                listContainer.appendChild(option);
            });
        }
    }

    input.addEventListener('focus', () => {
        renderList(input.value);
        listContainer.classList.add('show');
    });
    input.addEventListener('input', () => {
        renderList(input.value);
        listContainer.classList.add('show');
    });
    document.addEventListener('click', (e) => {
        if (!container.contains(e.target)) {
            listContainer.classList.remove('show');
        }
    });

    if (symbols.length) renderList('');
    return container;
}

// ==================== ГЕНЕРАЦИЯ ИМЕНИ БОТА ====================
export function generateBotName(strategyDisplayName) {
    const baseName = strategyDisplayName.replace('Bot', '').trim();
    const prefix = baseName ? `Бот ${baseName}` : 'Бот';

    // Получаем список ботов из глобального состояния
    let maxId = 0;
    const botsList = window.botsList || [];
    if (botsList.length) {
        maxId = Math.max(...botsList.map(b => b.id));
    } else {
        const lastId = localStorage.getItem('lastBotId');
        if (lastId) maxId = parseInt(lastId);
    }
    const newId = maxId + 1;
    localStorage.setItem('lastBotId', newId);
    return `${prefix} ${newId}`;
}

// ==================== МОДАЛЬНОЕ ОКНО СОЗДАНИЯ БОТА ====================
export async function showCreateBotModal() {
    const connectors = await getConnectors();

    const html = `
        <div style="width: 90vw; max-width: 700px;">
            <h3>Создание нового бота</h3>
            <form id="create-bot-form">
                <fieldset style="border: 1px solid #4a4a5a; border-radius: 8px; padding: 12px; margin-bottom: 20px;">
                    <legend style="padding: 0 8px; font-weight: bold;">📦 Основные настройки</legend>
                    <div class="form-group">
                        <label>Имя бота</label>
                        <input type="text" id="new-name" placeholder="Оставьте пустым для автогенерации">
                        <small style="color: #aaa;">Пример: Бот EMA 1</small>
                    </div>
                    <div class="form-group">
                        <label>Коннектор</label>
                        <select id="new-connector" required>
                            ${connectors.map(c => `<option value="${escapeHtml(c.name)}">${escapeHtml(c.name)}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Тип продукта</label>
                        <select id="new-product-type">
                            <option value="USDT-FUTURES">USDT-фьючерсы</option>
                            <option value="SPOT">Спот</option>
                            <option value="COIN-FUTURES">Coin-фьючерсы</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Источник рыночных данных</label>
                        <select id="new-market-source">
                            <option value="websocket">WebSocket (реальное время)</option>
                            <option value="rest_polling">REST опрос</option>
                            <option value="database">База данных (кэш)</option>
                            <option value="csv">CSV файл</option>
                        </select>
                    </div>
                    <div class="form-group" id="new-csv-config-group" style="display: none;">
                        <label>Конфигурация CSV (JSON)</label>
                        <input type="text" id="new-csv-config" placeholder='{"csv_path": "data.csv", "replay_delay_seconds": 60}'>
                    </div>
                    <div class="form-group">
                        <label>Торговая пара</label>
                        <div id="new-symbol-container"></div>
                    </div>
                    <div class="form-group">
                        <label>Таймфрейм</label>
                        <select id="new-timeframe">
                            ${TIMEFRAMES.map(tf => `<option>${tf}</option>`).join('')}
                        </select>
                    </div>
                    <div class="form-group">
                        <label>Размер позиции (USDT)</label>
                        <input type="number" id="new-pos-size" value="10" step="1">
                    </div>
                    <div class="form-group" id="new-leverage-group">
                        <label>Плечо</label>
                        <input type="number" id="new-leverage" value="10" step="1">
                    </div>
                    <div class="form-group">
                        <label><input type="checkbox" id="new-emulator" checked> Режим эмуляции</label>
                    </div>
                </fieldset>

                <fieldset style="border: 1px solid #7c3aed; border-radius: 8px; padding: 12px;">
                    <legend style="padding: 0 8px; font-weight: bold; color: #7c3aed;">🧠 Параметры стратегии</legend>
                    <div id="dynamic-params-create" style="min-height: 80px;">
                        <p>Выберите стратегию, чтобы загрузить параметры.</p>
                    </div>
                </fieldset>

                <div style="margin-top: 20px; text-align: right;">
                    <button type="submit" class="primary">Создать и запустить</button>
                    <button type="button" id="cancel-create" class="secondary">Отмена</button>
                </div>
            </form>
        </div>
    `;

    showModal(html);

    // Инициализация динамических элементов формы
    await initCreateBotForm();
}

async function initCreateBotForm() {
    const connectorSelect = getElementSafe('new-connector');
    const productTypeSelect = getElementSafe('new-product-type');
    const marketSourceSelect = getElementSafe('new-market-source');
    const csvConfigGroup = getElementSafe('new-csv-config-group');
    const leverageGroup = getElementSafe('new-leverage-group');
    const symbolContainer = getElementSafe('new-symbol-container');

    // Создаём select стратегий
    const strategySelect = document.createElement('select');
    strategySelect.id = 'new-strategy-select';
    strategySelect.innerHTML = STRATEGIES.map(s => `<option value="${s.path}">${s.display}</option>`).join('');

    const dynamicParamsDiv = getElementSafe('dynamic-params-create');
    if (dynamicParamsDiv) {
        dynamicParamsDiv.innerHTML = '';
        dynamicParamsDiv.appendChild(document.createTextNode('Стратегия: '));
        dynamicParamsDiv.appendChild(strategySelect);
        dynamicParamsDiv.appendChild(document.createElement('br'));
        const paramsContainer = document.createElement('div');
        paramsContainer.id = 'strategy-params-container';
        dynamicParamsDiv.appendChild(paramsContainer);
    }

    let currentSymbols = [];
    let currentSymbolSelector = null;

    async function loadSymbols() {
        const connector = connectorSelect?.value;
        const productType = productTypeSelect?.value;
        if (!connector) return;
        try {
            const symbols = await getSymbols(connector, productType);
            currentSymbols = symbols;
            if (currentSymbolSelector) {
                if (symbolContainer) symbolContainer.innerHTML = '';
                currentSymbolSelector = createSymbolSelector(currentSymbols, '', () => { });
                if (symbolContainer) symbolContainer.appendChild(currentSymbolSelector);
            } else {
                currentSymbolSelector = createSymbolSelector(currentSymbols, '', () => { });
                if (symbolContainer) symbolContainer.appendChild(currentSymbolSelector);
            }
        } catch (e) {
            console.error(e);
            if (symbolContainer) symbolContainer.innerHTML = '<div style="color: red;">Ошибка загрузки символов</div>';
        }
    }

    function toggleLeverageVisibility() {
        const productType = productTypeSelect?.value;
        if (leverageGroup) {
            if (productType === 'SPOT') leverageGroup.style.display = 'none';
            else leverageGroup.style.display = 'block';
        }
    }

    function toggleCsvConfig() {
        if (csvConfigGroup) {
            csvConfigGroup.style.display = marketSourceSelect?.value === 'csv' ? 'block' : 'none';
        }
    }

    async function loadStrategySchema() {
        const strategyPath = strategySelect.value;
        const schema = await getStrategyParamsSchema(strategyPath);
        const paramsContainer = getElementSafe('strategy-params-container');
        if (!paramsContainer) return;
        paramsContainer.innerHTML = '';
        if (Object.keys(schema).length === 0) {
            paramsContainer.innerHTML = '<p>Нет дополнительных параметров</p>';
            return;
        }
        for (const [key, meta] of Object.entries(schema)) {
            const label = meta.label || key;
            const inputId = `param_${key}`;
            let inputHtml = '';
            if (meta.type === 'int' || meta.type === 'float') {
                inputHtml = `<input type="number" id="${inputId}" value="${meta.default || ''}" step="${meta.step || (meta.type === 'int' ? 1 : 0.1)}">`;
            } else if (meta.type === 'bool') {
                inputHtml = `<input type="checkbox" id="${inputId}" ${meta.default ? 'checked' : ''}>`;
            } else if (meta.type === 'choice') {
                inputHtml = `<select id="${inputId}">${meta.options.map(opt => `<option ${meta.default === opt ? 'selected' : ''}>${opt}</option>`).join('')}</select>`;
            } else {
                inputHtml = `<input type="text" id="${inputId}" value="${meta.default || ''}">`;
            }
            const div = document.createElement('div');
            div.className = 'form-group';
            div.innerHTML = `<label>${label}</label>${inputHtml}`;
            paramsContainer.appendChild(div);
        }
    }

    connectorSelect?.addEventListener('change', loadSymbols);
    productTypeSelect?.addEventListener('change', () => { toggleLeverageVisibility(); loadSymbols(); });
    marketSourceSelect?.addEventListener('change', toggleCsvConfig);
    strategySelect.addEventListener('change', loadStrategySchema);

    toggleLeverageVisibility();
    toggleCsvConfig();
    await loadSymbols();
    await loadStrategySchema();

    const cancelBtn = getElementSafe('cancel-create');
    if (cancelBtn) cancelBtn.addEventListener('click', () => hideModal());

    const form = getElementSafe('create-bot-form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            await handleCreateBotSubmit();
        });
    }
}

async function handleCreateBotSubmit() {
    let botName = getElementSafe('new-name')?.value.trim();
    const strategySelect = getElementSafe('new-strategy-select');
    const connector = getElementSafe('new-connector')?.value;
    const symbolContainer = getElementSafe('new-symbol-container');
    const symbolInput = symbolContainer?.querySelector('input');
    const symbol = symbolInput?.value;
    const timeframe = getElementSafe('new-timeframe')?.value;
    const positionSize = parseFloat(getElementSafe('new-pos-size')?.value || '10');
    const emulatorEnabled = getElementSafe('new-emulator')?.checked || false;
    const leverageGroup = getElementSafe('new-leverage-group');
    const leverage = (leverageGroup?.style.display !== 'none') ? parseInt(getElementSafe('new-leverage')?.value || '10') : 1;
    const productType = getElementSafe('new-product-type')?.value;
    const marketDataSource = getElementSafe('new-market-source')?.value;
    let marketDataSourceConfig = '';
    if (marketDataSource === 'csv') {
        marketDataSourceConfig = getElementSafe('new-csv-config')?.value || '';
    }

    if (!symbol) {
        showError('Выберите торговую пару');
        return;
    }

    if (!botName) {
        const strategyDisplay = strategySelect?.options[strategySelect.selectedIndex]?.text || 'Bot';
        botName = generateBotName(strategyDisplay);
    }

    const params = {
        leverage: leverage.toString(),
        emulator_enabled: emulatorEnabled ? 'true' : 'false',
        product_type: productType,
    };

    // Собираем параметры стратегии
    const paramsContainer = getElementSafe('strategy-params-container');
    if (paramsContainer) {
        const inputs = paramsContainer.querySelectorAll('input, select');
        inputs.forEach(input => {
            let key = input.id;
            if (key.startsWith('param_')) key = key.substring(6);
            let value;
            if (input.type === 'checkbox') value = input.checked;
            else if (input.type === 'number') value = parseFloat(input.value);
            else value = input.value;
            params[key] = value;
        });
    }

    try {
        await startBot({
            bot_id: 0,
            name: botName,
            strategy: strategySelect?.value,
            connector_name: connector,
            symbol: symbol,
            timeframe: timeframe,
            position_size: positionSize,
            params: params,
            market_data_source: marketDataSource,
            market_data_source_config: marketDataSourceConfig
        });
        hideModal();
        showSuccess(`Бот "${botName}" создан и запущен`);
        await loadBotsTable();
    } catch (err) {
        showError(err.message);
    }
}

// ==================== МОДАЛЬНОЕ ОКНО СОЗДАНИЯ КОННЕКТОРА ====================
export async function showCreateConnectorModal() {
    const html = `
        <h3>Новый коннектор</h3>
        <form id="connector-form">
            <div class="form-group"><label>Имя</label><input id="conn-name" required></div>
            <div class="form-group"><label>Биржа</label><select id="conn-exchange"><option>bitget</option></select></div>
            <div class="form-group"><label>Тип продукта</label><select id="conn-product"><option>USDT-FUTURES</option><option>SPOT</option></select></div>
            <div class="form-group"><label>API Key</label><input id="conn-api-key"></div>
            <div class="form-group"><label>API Secret</label><input type="password" id="conn-api-secret"></div>
            <div class="form-group"><label>Passphrase</label><input type="password" id="conn-passphrase"></div>
            <div class="form-group"><label><input type="checkbox" id="conn-testnet" checked> Тестовая сеть</label></div>
            <button type="submit" class="primary">Создать</button>
        </form>
    `;
    showModal(html);

    const form = getElementSafe('connector-form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const settings = {
                name: getElementSafe('conn-name')?.value,
                exchange_id: getElementSafe('conn-exchange')?.value,
                product_type: getElementSafe('conn-product')?.value,
                api_key: getElementSafe('conn-api-key')?.value,
                api_secret: getElementSafe('conn-api-secret')?.value,
                api_passphrase: getElementSafe('conn-passphrase')?.value,
                testnet: getElementSafe('conn-testnet')?.checked || false
            };
            try {
                await createConnector(settings);
                hideModal();
                showSuccess('Коннектор создан');
                // Обновляем список коннекторов в UI
                const { renderConnectors } = await import('./ui.js');
                await renderConnectors();
            } catch (err) {
                showError(err.message);
            }
        });
    }
}