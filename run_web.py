#!/usr/bin/env python3
# run_web.py – запуск ядра и веб-сервера вместе

import subprocess
import sys
import time
import socket
import signal
from pathlib import Path

root = Path(__file__).parent

def is_port_open(host, port, timeout=2):
    try:
        with socket.create_connection((host, port), timeout):
            return True
    except:
        return False

def wait_for_core(host='localhost', port=9876, timeout=10):
    start = time.time()
    while time.time() - start < timeout:
        if is_port_open(host, port):
            return True
        time.sleep(0.5)
    return False

def main():
    print("🚀 Запуск gRPC ядра...")
    core = subprocess.Popen([sys.executable, str(root / "core" / "server.py")])
    
    print("⏳ Ожидание готовности ядра...")
    if not wait_for_core(timeout=15):
        print("❌ Ядро не запустилось за 15 секунд")
        core.terminate()
        sys.exit(1)
    
    print("✅ Ядро готово, запуск веб-сервера...")
    web = subprocess.Popen([sys.executable, str(root / "web" / "main.py")])
    
    def shutdown(signum, frame):
        print("\n🛑 Останавливаем процессы...")
        web.terminate()
        time.sleep(1)
        core.terminate()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)
    
    print("\n🌐 Веб-интерфейс доступен по адресу: http://localhost:8080")
    print("   (пароль указан в файле .env, переменная CORE_PASSWORD)")
    print("   Для выхода нажмите Ctrl+C\n")
    
    web.wait()
    core.terminate()

if __name__ == '__main__':
    main()