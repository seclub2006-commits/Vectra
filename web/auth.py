# web/auth.py
"""
Аутентификация: проверка пароля и создание JWT токенов.
"""

from datetime import datetime, timedelta
from typing import Optional

from jose import jwt

from web.config import CORE_PASSWORD, JWT_SECRET_KEY, JWT_ALGORITHM, JWT_ACCESS_TOKEN_EXPIRE_MINUTES


def verify_password(plain_password: str) -> bool:
    """Проверяет пароль (простое сравнение с паролем ядра)."""
    return plain_password == CORE_PASSWORD


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Создаёт JWT токен доступа."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)
    return encoded_jwt