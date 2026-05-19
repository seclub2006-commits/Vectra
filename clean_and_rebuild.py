#!/usr/bin/env python3
# clean_and_rebuild.py - очистка кеша и перегенерация protobuf файлов

import os
import sys
import shutil
import subprocess
from pathlib import Path

def clean_pycache(root_dir):
    """Удаляет все __pycache__ папки и .pyc файлы"""
    deleted = 0
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Удаляем __pycache__ папки
        if '__pycache__' in dirnames:
            pycache_path = os.path.join(dirpath, '__pycache__')
            try:
                shutil.rmtree(pycache_path)
                print(f"🗑️  Удалён: {pycache_path}")
                deleted += 1
            except Exception as e:
                print(f"❌ Ошибка удаления {pycache_path}: {e}")
        # Удаляем .pyc файлы
        for file in filenames:
            if file.endswith('.pyc'):
                file_path = os.path.join(dirpath, file)
                try:
                    os.remove(file_path)
                    print(f"🗑️  Удалён: {file_path}")
                    deleted += 1
                except Exception as e:
                    print(f"❌ Ошибка удаления {file_path}: {e}")
    print(f"✅ Очищено {deleted} кеш-файлов/папок")

def clean_protobuf_files(root_dir):
    """Удаляет сгенерированные protobuf файлы"""
    files_to_remove = ['core_pb2.py', 'core_pb2_grpc.py']
    removed = 0
    for filename in files_to_remove:
        filepath = root_dir / filename
        if filepath.exists():
            try:
                os.remove(filepath)
                print(f"🗑️  Удалён: {filepath}")
                removed += 1
            except Exception as e:
                print(f"❌ Ошибка удаления {filepath}: {e}")
    if removed == 0:
        print("ℹ️  Protobuf файлы не найдены или уже удалены")

def generate_protobuf(root_dir):
    """Генерирует protobuf файлы заново"""
    proto_file = root_dir / 'protos' / 'core.proto'
    if not proto_file.exists():
        print(f"❌ Файл {proto_file} не найден")
        return False
    print(f"🔨 Генерация protobuf из {proto_file}...")
    cmd = [
        sys.executable, '-m', 'grpc_tools.protoc',
        f'-I{root_dir / "protos"}',
        f'--python_out={root_dir}',
        f'--grpc_python_out={root_dir}',
        str(proto_file)
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Protobuf файлы успешно сгенерированы")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка генерации protobuf: {e}")
        print(f"stderr: {e.stderr}")
        return False

def clean_database(root_dir, ask=True):
    """Удаляет базу данных core.db"""
    db_path = root_dir / 'core.db'
    if not db_path.exists():
        print("ℹ️  База данных не найдена")
        return
    if ask:
        response = input(f"Удалить базу данных {db_path}? (y/N): ").strip().lower()
        if response != 'y':
            print("ℹ️  База данных не удалена")
            return
    try:
        os.remove(db_path)
        print(f"🗑️  База данных удалена: {db_path}")
    except Exception as e:
        print(f"❌ Ошибка удаления базы данных: {e}")

def main():
    root_dir = Path(__file__).parent.absolute()
    print("🧹 Начинаем очистку и пересборку проекта...")
    print(f"📁 Корень проекта: {root_dir}")

    # 1. Очистка кеша Python
    clean_pycache(root_dir)

    # 2. Удаление старых protobuf файлов
    clean_protobuf_files(root_dir)

    # 3. Перегенерация protobuf
    if not generate_protobuf(root_dir):
        sys.exit(1)

    # 4. Опционально: очистка базы данных (спрашиваем)
    clean_database(root_dir, ask=True)

    print("\n✅ Готово! Теперь можно запускать проект.")
    print("   Запуск: python run.py --mode both")

if __name__ == '__main__':
    main()