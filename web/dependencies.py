# web/dependencies.py
"""
Зависимости FastAPI для внедрения в роутеры.
"""

from typing import Optional
from fastapi import HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt

from web.config import JWT_SECRET_KEY, JWT_ALGORITHM
from web.grpc_client import GrpcCoreClient

# Глобальный экземпляр gRPC клиента (будет установлен в main.py)
_grpc_client: Optional[GrpcCoreClient] = None

security = HTTPBearer(auto_error=False)


def set_grpc_client(client: GrpcCoreClient):
    """Устанавливает глобальный экземпляр gRPC клиента (вызывается при старте)."""
    global _grpc_client
    _grpc_client = client


async def get_grpc_client() -> GrpcCoreClient:
    """Depends: возвращает gRPC клиент."""
    if _grpc_client is None:
        raise HTTPException(status_code=503, detail="gRPC client not initialized")
    return _grpc_client


async def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)) -> str:
    """
    Depends: извлекает и валидирует JWT токен, возвращает имя пользователя.
    Используется для защиты API эндпоинтов.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return username
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")


async def verify_websocket_token(token: str) -> bool:
    """Проверяет JWT токен для WebSocket соединения (без raise)."""
    if not token:
        return False
    try:
        payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
        return payload.get("sub") is not None
    except JWTError:
        return False