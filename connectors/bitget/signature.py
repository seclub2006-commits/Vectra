# connectors/bitget/signature.py
import hmac
import base64
import hashlib
from urllib.parse import urlencode

def generate_sign(secret: str, timestamp: str, method: str, request_path: str,
                  query_string: str = '', body: str = '') -> str:
    """
    Генерирует подпись для REST-запроса Bitget.
    :param secret: секретный ключ API
    :param timestamp: временная метка в миллисекундах (строка)
    :param method: HTTP метод (GET, POST)
    :param request_path: путь эндпоинта (начинается с /)
    :param query_string: строка параметров (без '?'), должна быть отсортирована по ключам
    :param body: тело запроса для POST (JSON строка)
    :return: подпись Base64
    """
    # Собираем preHash строку согласно спецификации Bitget
    pre_hash = timestamp + method.upper() + request_path
    if query_string:
        pre_hash += '?' + query_string
    pre_hash += body

    signature = hmac.new(secret.encode('utf-8'),
                         pre_hash.encode('utf-8'),
                         hashlib.sha256).digest()
    return base64.b64encode(signature).decode()

def generate_ws_sign(secret: str, timestamp: str) -> str:
    """
    Генерирует подпись для WebSocket логина Bitget.
    """
    message = timestamp + 'GET' + '/user/verify'
    signature = hmac.new(secret.encode('utf-8'),
                         message.encode('utf-8'),
                         hashlib.sha256).digest()
    return base64.b64encode(signature).decode()

def sort_query_string(params: dict) -> str:
    """
    Сортирует параметры по ключам и возвращает строку query.
    """
    if not params:
        return ''
    return urlencode(sorted(params.items()))