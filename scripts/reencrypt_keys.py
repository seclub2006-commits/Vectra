# scripts/reencrypt_keys.py
import asyncio
import sys
from pathlib import Path
from sqlalchemy import select   # <-- добавлен импорт

sys.path.insert(0, str(Path(__file__).parent.parent))
from core.database import Database
from core.models import Connector
from utils.encryption import encrypt_data, decrypt_data

async def reencrypt():
    db = Database()
    await db.init()
    async with db.session_maker() as session:
        result = await session.execute(select(Connector))
        conns = result.scalars().all()
        for c in conns:
            plain_key = decrypt_data(c.api_key) if c.api_key else ''
            plain_secret = decrypt_data(c.api_secret) if c.api_secret else ''
            plain_pass = decrypt_data(c.api_passphrase) if c.api_passphrase else ''
            if plain_key:  # только если удалось расшифровать
                c.api_key = encrypt_data(plain_key)
                c.api_secret = encrypt_data(plain_secret)
                c.api_passphrase = encrypt_data(plain_pass)
                session.add(c)
        await session.commit()
        print("Перешифровка завершена")

if __name__ == '__main__':
    asyncio.run(reencrypt())