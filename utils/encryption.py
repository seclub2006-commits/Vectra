# utils/encryption.py
import os
import base64
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken
from dotenv import load_dotenv, set_key

ENV_PATH = Path(__file__).parent.parent / '.env'

def _get_or_create_key() -> str:
    load_dotenv(ENV_PATH)
    key = os.getenv('ENCRYPTION_KEY')
    if key:
        try:
            base64.urlsafe_b64decode(key)
            Fernet(key.encode())
            return key
        except Exception:
            pass
    new_key = Fernet.generate_key().decode()
    set_key(str(ENV_PATH), 'ENCRYPTION_KEY', new_key)
    load_dotenv(ENV_PATH, override=True)
    return new_key

_KEY = _get_or_create_key()
_FERNET = Fernet(_KEY.encode())

def encrypt_data(data: str) -> str:
    if not data:
        return ''
    if data.startswith('gAAAAA'):
        return data
    return _FERNET.encrypt(data.encode()).decode()

def decrypt_data(encrypted: str) -> str:
    if not encrypted:
        return ''
    if not encrypted.startswith('gAAAAA'):
        return encrypted
    try:
        return _FERNET.decrypt(encrypted.encode()).decode()
    except InvalidToken:
        # Не выводим ошибку в консоль, чтобы не засорять логи
        return ''