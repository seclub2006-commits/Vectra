#!/usr/bin/env python3
# scripts/generate_proto.py – генерирует *_pb2.py и *_pb2_grpc.py из core.proto

import os
import sys
from pathlib import Path

def main():
    # Корень проекта (два уровня вверх от scripts)
    root = Path(__file__).parent.parent.absolute()
    proto_file = root / 'protos' / 'core.proto'
    if not proto_file.exists():
        print(f"❌ Файл {proto_file} не найден")
        sys.exit(1)

    # Выходная директория – корень проекта
    out_dir = root
    print(f"🔨 Генерация из {proto_file} -> {out_dir}")
    # Команда: python -m grpc_tools.protoc -Iprotos --python_out=. --grpc_python_out=. protos/core.proto
    cmd = [
        sys.executable, '-m', 'grpc_tools.protoc',
        f'-I{root / "protos"}',
        f'--python_out={out_dir}',
        f'--grpc_python_out={out_dir}',
        str(proto_file)
    ]
    os.system(' '.join(cmd))
    print("✅ Генерация завершена. Созданы файлы core_pb2.py и core_pb2_grpc.py")
    # Переименовывать не нужно, они уже в корне

if __name__ == '__main__':
    main()