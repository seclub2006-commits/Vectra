// web/static/js/connectors.js

import { escapeHtml, showError, showSuccess, showModal, hideModal, getElementSafe } from './utils.js';
import { getConnectorsList, setConnectorsList, updateConnectorInList, removeConnectorFromList } from './state.js';
import { getConnectorSettings, updateConnectorSettings, deleteConnector, setConnectorStatus } from './api.js';
import { renderConnectors } from './ui.js';

// ==================== РЕДАКТИРОВАНИЕ КОННЕКТОРА ====================
export async function editConnector(name) {
    try {
        const settings = await getConnectorSettings(name);

        const html = `
            <h3>Редактирование коннектора ${escapeHtml(name)}</h3>
            <form id="edit-connector-form">
                <div class="form-group">
                    <label>API Key</label>
                    <input id="edit-api-key" value="${escapeHtml(settings.api_key || '')}" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>API Secret</label>
                    <input type="password" id="edit-api-secret" value="${escapeHtml(settings.api_secret || '')}" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>Passphrase</label>
                    <input type="password" id="edit-passphrase" value="${escapeHtml(settings.api_passphrase || '')}" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="edit-testnet" ${settings.testnet ? 'checked' : ''}> 
                        Тестовая сеть (демо-режим)
                    </label>
                </div>
                <div class="form-group">
                    <label>Тип продукта</label>
                    <select id="edit-product-type">
                        <option value="USDT-FUTURES" ${settings.product_type === 'USDT-FUTURES' ? 'selected' : ''}>USDT-фьючерсы</option>
                        <option value="SPOT" ${settings.product_type === 'SPOT' ? 'selected' : ''}>Спот</option>
                        <option value="COIN-FUTURES" ${settings.product_type === 'COIN-FUTURES' ? 'selected' : ''}>Coin-фьючерсы</option>
                        <option value="USDC-FUTURES" ${settings.product_type === 'USDC-FUTURES' ? 'selected' : ''}>USDC-фьючерсы</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Максимальное количество повторных попыток</label>
                    <input type="number" id="edit-max-retries" value="${settings.max_retries || 3}" step="1">
                </div>
                <div class="form-group">
                    <label>Задержка между повторами (сек)</label>
                    <input type="number" id="edit-retry-backoff" value="${settings.retry_backoff || 2.0}" step="0.5">
                </div>
                <div class="form-group">
                    <label>Интервал WebSocket ping (сек)</label>
                    <input type="number" id="edit-ws-ping" value="${settings.ws_ping_interval || 30}" step="5">
                </div>
                <div class="form-group">
                    <label>Задержка переподключения WebSocket (сек)</label>
                    <input type="number" id="edit-ws-reconnect" value="${settings.ws_reconnect_delay || 5}" step="1">
                </div>
                <div class="form-group">
                    <label>Таймаут HTTP запроса (чтение, сек)</label>
                    <input type="number" id="edit-http-timeout" value="${settings.http_timeout_read || 10}" step="1">
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="edit-auto-reconnect" ${settings.auto_reconnect !== false ? 'checked' : ''}>
                        Автоматически переподключать WebSocket при обрыве
                    </label>
                </div>
                <div class="form-group">
                    <label>
                        <input type="checkbox" id="edit-retry-on-limit" ${settings.retry_on_limit !== false ? 'checked' : ''}>
                        Повторять запрос при превышении лимита (429)
                    </label>
                </div>
                <div style="margin-top: 20px; text-align: right;">
                    <button type="submit" class="primary">Сохранить</button>
                    <button type="button" id="cancel-edit-connector" class="secondary">Отмена</button>
                </div>
            </form>
        `;

        showModal(html);

        const form = getElementSafe('edit-connector-form');
        const cancelBtn = getElementSafe('cancel-edit-connector');

        if (cancelBtn) {
            cancelBtn.addEventListener('click', () => hideModal());
        }

        if (form) {
            form.addEventListener('submit', async (e) => {
                e.preventDefault();

                const newSettings = {
                    api_key: getElementSafe('edit-api-key')?.value || '',
                    api_secret: getElementSafe('edit-api-secret')?.value || '',
                    api_passphrase: getElementSafe('edit-passphrase')?.value || '',
                    testnet: getElementSafe('edit-testnet')?.checked || false,
                    product_type: getElementSafe('edit-product-type')?.value || 'USDT-FUTURES',
                    max_retries: parseInt(getElementSafe('edit-max-retries')?.value || '3'),
                    retry_backoff: parseFloat(getElementSafe('edit-retry-backoff')?.value || '2.0'),
                    ws_ping_interval: parseInt(getElementSafe('edit-ws-ping')?.value || '30'),
                    ws_reconnect_delay: parseInt(getElementSafe('edit-ws-reconnect')?.value || '5'),
                    http_timeout_read: parseInt(getElementSafe('edit-http-timeout')?.value || '10'),
                    auto_reconnect: getElementSafe('edit-auto-reconnect')?.checked || false,
                    retry_on_limit: getElementSafe('edit-retry-on-limit')?.checked !== false
                };

                try {
                    const result = await updateConnectorSettings(name, newSettings);
                    if (result.status === 'ok' || result.success) {
                        hideModal();
                        showSuccess(`Коннектор "${name}" обновлён`);
                        await renderConnectors();
                    } else {
                        showError(result.message || 'Ошибка обновления');
                    }
                } catch (err) {
                    showError(err.message);
                }
            });
        }
    } catch (err) {
        showError(`Ошибка загрузки настроек коннектора: ${err.message}`);
    }
}

// ==================== УДАЛЕНИЕ КОННЕКТОРА ====================
export async function deleteConnectorAction(name) {
    if (!confirm(`Удалить коннектор "${name}"?\n\nВНИМАНИЕ: Коннектор можно удалить только если он не используется ни одним ботом.`)) {
        return;
    }

    try {
        const result = await deleteConnector(name);
        if (result.status === 'ok' || result.success) {
            removeConnectorFromList(name);
            showSuccess(`Коннектор "${name}" удалён`);
            await renderConnectors();
        } else {
            showError(result.message || 'Не удалось удалить коннектор (возможно, он используется ботами)');
        }
    } catch (err) {
        showError(err.message);
    }
}

// ==================== ИЗМЕНЕНИЕ СТАТУСА КОННЕКТОРА (ONLINE/OFFLINE) ====================
export async function setConnectorStatusAction(name, status) {
    const actionText = status === 'online' ? 'подключить' : 'отключить';
    if (!confirm(`${actionText === 'подключить' ? 'Подключить' : 'Отключить'} коннектор "${name}"?`)) {
        return;
    }

    try {
        const result = await setConnectorStatus(name, status);
        if (result.status === 'ok' || result.success) {
            showSuccess(`Коннектор "${name}" ${status === 'online' ? 'подключён' : 'отключён'}`);
            await renderConnectors();
        } else {
            showError(result.message || `Ошибка при ${actionText} коннектора`);
        }
    } catch (err) {
        showError(err.message);
    }
}

// ==================== ПРОВЕРКА СТАТУСА КОННЕКТОРА ====================
export async function checkConnectorStatus(name) {
    try {
        // Используем существующий API эндпоинт (если есть) или получаем через список
        const connectors = await getConnectorsList();
        const connector = connectors.find(c => c.name === name);
        return connector?.status === 'online';
    } catch (err) {
        console.error(`Error checking connector ${name} status:`, err);
        return false;
    }
}

// ==================== ОБНОВЛЕНИЕ ВСЕХ КОННЕКТОРОВ (ПОЛУЧЕНИЕ СВЕЖИХ ДАННЫХ) ====================
export async function refreshConnectorsList() {
    try {
        const { renderConnectors } = await import('./ui.js');
        await renderConnectors();
    } catch (err) {
        showError(`Ошибка обновления списка коннекторов: ${err.message}`);
    }
}