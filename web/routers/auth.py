# web/routers/auth.py
"""
Эндпоинты для аутентификации (логин).
"""

from fastapi import APIRouter, HTTPException

from web.models import LoginRequest
from web.auth import verify_password, create_access_token

router = APIRouter(prefix="/api", tags=["auth"])


@router.post("/login")
async def login(request: LoginRequest):
    """Аутентификация пользователя и выдача JWT токена."""
    if not verify_password(request.password):
        raise HTTPException(status_code=401, detail="Invalid password")
    access_token = create_access_token(data={"sub": "trader"})
    return {"access_token": access_token, "token_type": "bearer"}