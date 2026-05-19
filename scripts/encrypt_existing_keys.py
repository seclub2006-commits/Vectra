#!/usr/bin/env python3
"""Шифрует уже существующие API ключи в базе данных."""
import asyncio
import sys
from pathlib import Path

# Добавляем корень проекта в путь
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select
from core.database import Database
from core.models import Connector
from utils.encryption import encrypt_data

async def main():
    db = Database()
    await db.init()
    async with db.session_maker() as session:
        # Используем select из sqlalchemy
        stmt = select(Connector)
        result = await session.execute(stmt)
        connectors = result.scalars().all()
        for conn in connectors:
            # Если поле api_key не пустое и не начинается с признака зашифрованных данных Fernet ('gAAAAA')
            if conn.api_key and not conn.api_key.startswith('gAAAAA'):
                conn.api_key = encrypt_data(conn.api_key)
                conn.api_secret = encrypt_data(conn.api_secret)
                conn.api_passphrase = encrypt_data(conn.api_passphrase)
                session.add(conn)
        await session.commit()
    print("Шифрование завершено.")

if __name__ == '__main__':
    asyncio.run(main())