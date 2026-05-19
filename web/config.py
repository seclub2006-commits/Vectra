# web/config.py
"""
Конфигурация веб-сервера: переменные окружения, CORS, параметры подключения.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# Веб-сервер
WEB_HOST = os.getenv("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8080").split(",")

# Подключение к gRPC ядру
CORE_HOST = os.getenv("CORE_HOST", "localhost")
CORE_PORT = int(os.getenv("CORE_PORT", "9876"))
CORE_PASSWORD = os.getenv("CORE_PASSWORD", "")

# JWT для аутентификации веб-интерфейса
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "your-secret-key-change-me")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
JWT_ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "30"))