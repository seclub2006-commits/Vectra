#!/usr/bin/env python3
# deploy_to_github.py – полностью автоматическая выгрузка проекта на GitHub
# с защитой от случайной публикации API-ключей и секретов.

import os
import subprocess
import sys
import re
from pathlib import Path
from dotenv import load_dotenv

# ========== ЗАГРУЖАЕМ НАСТРОЙКИ ИЗ .env ==========
load_dotenv()
TOKEN = os.getenv("GITHUB_TOKEN", "")
GIT_USER_NAME = os.getenv("GIT_USER_NAME", "Vectra Bot")
GIT_USER_EMAIL = os.getenv("GIT_USER_EMAIL", "bot@vectra.local")
REPO_NAME = os.getenv("GITHUB_REPO_NAME", "TradingBot")
REPO_DESC = os.getenv("GITHUB_REPO_DESC", "Vectra Trading Platform")
PRIVATE = os.getenv("GITHUB_PRIVATE", "false").lower() == "true"
BRANCH = "main"

# ========== СПИСОК ОПАСНЫХ ПАТТЕРНОВ ==========
DANGEROUS_PATTERNS = [
    r'api_key\s*=\s*["\']?[\w-]{10,}',
    r'api_secret\s*=\s*["\']?[\w-]{20,}',
    r'passphrase\s*=\s*["\']?[\w-]{8,}',
    r'password\s*=\s*["\']?\S+',
    r'token\s*=\s*["\']?gh[pru]_[A-Za-z0-9]{36,}',
    r'ENCRYPTION_KEY\s*=\s*["\']?[\w\-+=/]{20,}',
    r'BEGIN (RSA|DSA|EC|PGP) PRIVATE KEY',
    r'-----BEGIN.*PRIVATE KEY-----',
    r'GITHUB_TOKEN\s*=\s*["\']?gh[pru]_[A-Za-z0-9]{36,}',
    r'bg_[a-f0-9]{32}',                     # Bitget API Key
    r'[a-f0-9]{64}',                        # длинный hex (может быть секретом)
    r'kirizek\d*',                          # конкретный пример из quick_test.py
]
# Компилируем паттерны один раз
DANGEROUS_REGEX = [re.compile(p, re.IGNORECASE) for p in DANGEROUS_PATTERNS]

# ========== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==========
def run(cmd, check=True, capture=False):
    proc = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and proc.returncode != 0:
        print(f"❌ Ошибка: {proc.stderr.strip()}")
        sys.exit(1)
    return proc.stdout.strip() if capture else proc

def is_ignored_by_gitignore(file_path):
    """Проверяет, игнорируется ли файл текущим .gitignore."""
    try:
        # git check-ignore вернёт 0, если файл игнорируется
        result = subprocess.run(
            f"git check-ignore {file_path}",
            shell=True, capture_output=True, text=True
        )
        return result.returncode == 0
    except:
        return False

def file_contains_secrets(file_path):
    """Возвращает True, если в файле найден хотя бы один опасный паттерн."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            for regex in DANGEROUS_REGEX:
                if regex.search(content):
                    return True
    except Exception:
        pass
    return False

def scan_dangerous_files(root_dir):
    """Сканирует все файлы в проекте, возвращает список опасных файлов, не игнорируемых .gitignore."""
    dangerous = []
    for root, dirs, files in os.walk(root_dir):
        # Пропускаем скрытые папки и системные
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('__pycache__', 'venv', 'env')]
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, root_dir)
            # Пропускаем сам скрипт и .git
            if file == 'deploy_to_github.py' or '.git' in rel_path:
                continue
            # Если файл уже в .gitignore – не тревожим
            if is_ignored_by_gitignore(rel_path):
                continue
            if file_contains_secrets(file_path):
                dangerous.append(rel_path)
    return dangerous

def add_to_gitignore(paths):
    """Добавляет пути в файл .gitignore (создаёт, если нет)."""
    gitignore_path = Path(".gitignore")
    existing = set()
    if gitignore_path.exists():
        with open(gitignore_path, 'r', encoding='utf-8') as f:
            existing = set(line.strip() for line in f if line.strip())
    with open(gitignore_path, 'a', encoding='utf-8') as f:
        for p in paths:
            if p not in existing:
                f.write(f"\n# Автоматически добавлено deploy_to_github.py\n{p}\n")
                print(f"   ➕ Добавлен в .gitignore: {p}")

# ========== ОСНОВНАЯ ФУНКЦИЯ ==========
def main():
    root_dir = Path(__file__).parent.absolute()
    os.chdir(root_dir)
    print(f"📁 Рабочая папка: {os.getcwd()}")

    # 1. Проверка Git
    if not run("git --version", capture=True):
        print("❌ Git не установлен. Установите Git и перезапустите.")
        sys.exit(1)
    print("✅ Git найден")

    # 2. Проверка токена
    if not TOKEN:
        print("❌ Не задан GITHUB_TOKEN в файле .env. Добавьте строку GITHUB_TOKEN=ваш_токен")
        sys.exit(1)
    print("✅ Токен найден в .env")

    # 3. Настройка имени и email для Git
    run(f'git config --global user.name "{GIT_USER_NAME}"')
    run(f'git config --global user.email "{GIT_USER_EMAIL}"')
    print(f"✅ Git настроен: {GIT_USER_NAME} <{GIT_USER_EMAIL}>")

    # 4. Инициализация Git (если нужно)
    if not Path(".git").exists():
        run("git init")
        run(f"git checkout -b {BRANCH}")
        print("✅ Git инициализирован")
    else:
        print("✅ Git репозиторий уже существует")

    # 5. Сканирование опасных файлов
    print("\n🔍 Сканирование файлов на наличие секретов...")
    dangerous_files = scan_dangerous_files(root_dir)
    if dangerous_files:
        print("\n⚠️  ВНИМАНИЕ! Найдены файлы, которые могут содержать секреты:")
        for f in dangerous_files:
            print(f"   📄 {f}")
        print("\nЧто делаем?")
        print("  1. Пропустить эти файлы (не добавлять в Git) – рекомендовано")
        print("  2. Добавить их в .gitignore и пропустить")
        print("  3. Всё равно добавить (НЕ РЕКОМЕНДУЕТСЯ)")
        choice = input("Ваш выбор (1/2/3) [1]: ").strip() or "1"
        if choice == "1":
            for f in dangerous_files:
                run(f"git update-index --assume-unchanged {f}", check=False)
                print(f"   ⏭️  Файл {f} будет пропущен (не попадёт в коммит)")
        elif choice == "2":
            add_to_gitignore(dangerous_files)
            print("✅ Опасные файлы добавлены в .gitignore. Они не попадут в репозиторий.")
        else:
            print("⚠️  Вы решили добавить файлы, несмотря на риск. Убедитесь, что они не содержат реальных ключей!")
    else:
        print("✅ Опасных файлов не обнаружено.")

    # 6. Добавление файлов и коммит
    print("\n📦 Добавление файлов в Git...")
    run("git add .")
    status = run("git status --porcelain", capture=True)
    if not status:
        print("⚠️  Нет изменений для коммита.")
    else:
        run('git commit -m "Initial commit"')
        print("✅ Коммит создан")

    # 7. Создание репозитория на GitHub
    try:
        import requests
    except ImportError:
        print("⚠️  Устанавливаем requests...")
        run(f"{sys.executable} -m pip install requests")
        import requests

    headers = {"Authorization": f"token {TOKEN}", "Accept": "application/vnd.github.v3+json"}
    data = {"name": REPO_NAME, "description": REPO_DESC, "private": PRIVATE, "auto_init": False}
    resp = requests.post("https://api.github.com/user/repos", json=data, headers=headers)

    if resp.status_code == 201:
        repo_url = resp.json()["clone_url"]
        print(f"✅ Репозиторий создан: {repo_url}")
    elif resp.status_code == 422 and "already exists" in resp.text:
        print("⚠️  Репозиторий уже существует, подключаемся к нему.")
        user = requests.get("https://api.github.com/user", headers=headers).json()
        repo_url = f"https://github.com/{user['login']}/{REPO_NAME}.git"
    else:
        print(f"❌ Ошибка API: {resp.status_code} - {resp.text}")
        sys.exit(1)

    # 8. Установка remote и push
    current_remote = run("git remote get-url origin", check=False, capture=True)
    if current_remote:
        run(f"git remote set-url origin {repo_url}")
    else:
        run(f"git remote add origin {repo_url}")

    run(f"git push -u origin {BRANCH}")
    print(f"\n🎉 Готово! Проект на GitHub: {repo_url.replace('.git', '')}")

if __name__ == "__main__":
    main()