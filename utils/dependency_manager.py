# utils/dependency_manager.py
import sys
import site
import importlib
import os

REQUIRED_MODULES = [
    "grpcio", "protobuf", "dotenv",      # grpcio_tools не нужен для работы
    "PyQt5", "matplotlib", "pandas", "numpy",
    "sqlalchemy", "aiosqlite", "websockets", "aiohttp", "cryptography"
]

def ensure_all_site_packages_in_path():
    """Добавляет все возможные пути site-packages в sys.path."""
    # 1. Системные site-packages (например, C:\Python3\Lib\site-packages)
    for p in site.getsitepackages():
        if p not in sys.path:
            sys.path.insert(0, p)

    # 2. Пользовательские site-packages (--user)
    #    site.getusersitepackages() возвращает Roaming (AppData\Roaming)
    user_site = site.getusersitepackages()
    if user_site and user_site not in sys.path:
        sys.path.insert(0, user_site)

    # 3. На Windows пакеты из --user также могут попасть в Local (AppData\Local)
    if os.name == 'nt':
        local_appdata = os.environ.get('LOCALAPPDATA', '')
        if local_appdata:
            # Пример: C:\Users\Admin\AppData\Local\Python\pythoncore-3.14-64\Lib\site-packages
            local_sp = os.path.join(local_appdata, 'Python', f'pythoncore-{sys.version_info[0]}.{sys.version_info[1]}-64', 'Lib', 'site-packages')
            if os.path.isdir(local_sp) and local_sp not in sys.path:
                sys.path.insert(0, local_sp)

def check_module(module_name: str) -> bool:
    try:
        __import__(module_name)
        return True
    except ImportError as e:
        # Для отладки выводим, какой модуль и почему не импортируется
        print(f"   DEBUG: {module_name} -> {e}")
        return False

def get_missing_modules():
    ensure_all_site_packages_in_path()
    importlib.invalidate_caches()
    missing = []
    for m in REQUIRED_MODULES:
        if not check_module(m):
            missing.append(m)
    return missing

def check_dependencies_only():
    missing = get_missing_modules()
    if missing:
        print(f"⚠️ Отсутствуют модули: {', '.join(missing)}")
        print("   Запустите 'python install_deps.py' для установки.")
        return False
    return True

# Для обратной совместимости
ensure_dependencies = check_dependencies_only