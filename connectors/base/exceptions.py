# connectors/base/exceptions.py
class ConnectorError(Exception):
    """Базовое исключение для всех ошибок коннекторов."""
    pass

class ConfigError(ConnectorError):
    """Ошибка конфигурации."""
    pass

class APIError(ConnectorError):
    """Ошибка, возвращённая биржей (код не 00000)."""
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"API error {code}: {message}")

class NetworkError(ConnectorError):
    """Ошибка сети, таймаут."""
    pass

class RateLimitError(ConnectorError):
    """Превышен лимит запросов (429)."""
    pass

class AuthError(ConnectorError):
    """Ошибка авторизации (неверные ключи, подпись)."""
    pass