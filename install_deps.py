#!/usr/bin/env python3
"""
install_deps.py – универсальный менеджер зависимостей.
Определяет все используемые пакеты проекта, обновляет requirements.txt,
удаляет неиспользуемые пакеты (с подтверждением).
"""

import ast
import importlib.metadata
import itertools
import re
import subprocess
import sys
from pathlib import Path
from typing import Set, Dict, List, Optional

# ==================== КОНФИГУРАЦИЯ ====================
PROJECT_DIRS = ["bots", "connectors", "core", "utils", "web", "scripts", "gui", "tests"]
INTERNAL_MODULES = {
    "bots", "connectors", "core", "utils", "web", "scripts", "gui", "tests",
    "config", "models", "core_pb2", "core_pb2_grpc", "indicators"
}

MODULE_TO_PACKAGE = {
    "grpc": "grpcio",
    "grpc_tools": "grpcio-tools",
    "pandas": "pandas",
    "numpy": "numpy",
    "websockets": "websockets",
    "aiohttp": "aiohttp",
    "sqlalchemy": "sqlalchemy",
    "aiosqlite": "aiosqlite",
    "dotenv": "python-dotenv",
    "cryptography": "cryptography",
    "fastapi": "fastapi",
    "uvicorn": "uvicorn",
    "jose": "python-jose",
    "passlib": "passlib",
    "redis": "redis",
    "multipart": "python-multipart",
    "httpx": "httpx",
    "ccxt": "ccxt",
    "pydantic": "pydantic",
}

EXTRA_DEPENDENCIES = {
    "aiosqlite",
    "ccxt",
    "redis",
    "python-multipart",
}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================
def get_local_module_names(root: Path, dirs: List[str]) -> Set[str]:
    local_names = set()
    for d in dirs:
        dir_path = root / d
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            if py_file.name == "__init__.py":
                local_names.add(py_file.parent.name)
            else:
                local_names.add(py_file.stem)
        for subdir in dir_path.rglob("*/__init__.py"):
            local_names.add(subdir.parent.name)
    return local_names

def get_all_py_files(root: Path, dirs: List[str]) -> List[Path]:
    py_files = []
    for d in dirs:
        dir_path = root / d
        if not dir_path.exists():
            continue
        for py_file in dir_path.rglob("*.py"):
            py_files.append(py_file)
    return py_files

def extract_imports(file_path: Path) -> Set[str]:
    imports = set()
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (SyntaxError, UnicodeDecodeError):
        return imports
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mod = alias.name.split('.')[0]
                imports.add(mod)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mod = node.module.split('.')[0]
                imports.add(mod)
    return imports

def extract_dynamic_imports(file_path: Path) -> Set[str]:
    imports = set()
    pattern_importlib = re.compile(r'importlib\.import_module\([\'"]([a-zA-Z0-9_.-]+)[\'"]\)')
    pattern_builtin = re.compile(r'__import__\([\'"]([a-zA-Z0-9_.-]+)[\'"]\)')
    pattern_exec = re.compile(r'exec\([\'"](?:import|from)\s+([a-zA-Z0-9_.-]+)')
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            imports.update(pattern_importlib.findall(content))
            imports.update(pattern_builtin.findall(content))
            imports.update(pattern_exec.findall(content))
    except Exception:
        pass
    return imports

def scan_db_connection_strings(root: Path) -> Set[str]:
    found = set()
    patterns = {
        r'sqlite\+aiosqlite://': 'aiosqlite',
        r'postgresql\+asyncpg://': 'asyncpg',
        r'postgresql\+psycopg2://': 'psycopg2',
        r'mysql\+aiomysql://': 'aiomysql',
        r'mysql\+pymysql://': 'pymysql',
    }
    for py_file in get_all_py_files(root, PROJECT_DIRS):
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                content = f.read()
                for pattern, pkg in patterns.items():
                    if re.search(pattern, content):
                        found.add(pkg)
        except Exception:
            continue
    return found

def scan_config_files(root: Path) -> Set[str]:
    found = set()
    keywords = ['aiosqlite', 'ccxt', 'redis', 'multipart', 'fastapi', 'uvicorn', 'grpcio']
    for conf_file in root.glob(".env*"):
        try:
            data = conf_file.read_text(encoding='utf-8')
            for kw in keywords:
                if kw in data:
                    found.add(kw)
        except Exception:
            pass
    # Исправлено: используем itertools.chain или list() для объединения генераторов
    for yaml_file in itertools.chain(root.glob("*.yaml"), root.glob("*.yml"), root.glob("*.json")):
        try:
            data = yaml_file.read_text(encoding='utf-8')
            for kw in keywords:
                if kw in data:
                    found.add(kw)
        except Exception:
            pass
    return found

def scan_pyproject_toml(root: Path) -> Set[str]:
    pyproject = root / "pyproject.toml"
    if not pyproject.exists():
        return set()

    # Динамическая загрузка tomllib или tomli
    data = None
    if sys.version_info >= (3, 11):
        import tomllib
        with open(pyproject, "rb") as f:
            data = tomllib.load(f)
    else:
        import importlib.util
        if importlib.util.find_spec("tomli") is not None:
            import importlib
            tomli = importlib.import_module("tomli")
            with open(pyproject, "rb") as f:
                data = tomli.load(f)
        else:
            print("⚠️ tomli не установлен, пропускаем pyproject.toml")
            return set()

    deps = set()
    project_deps = data.get("project", {}).get("dependencies", [])
    for dep in project_deps:
        pkg_name = re.split(r'[=<>~!@]', dep)[0].strip().lower()
        if pkg_name:
            deps.add(pkg_name)
    opt_deps = data.get("project", {}).get("optional-dependencies", {})
    for group in opt_deps.values():
        for dep in group:
            pkg_name = re.split(r'[=<>~!@]', dep)[0].strip().lower()
            if pkg_name:
                deps.add(pkg_name)
    tool_sections = data.get("tool", {})
    for tool in tool_sections:
        if tool in ("pytest", "black", "mypy", "isort", "flake8", "coverage", "tox", "pre-commit"):
            deps.add(tool)
    return deps

def scan_setup(root: Path) -> Set[str]:
    deps = set()
    setup_py = root / "setup.py"
    if setup_py.exists():
        try:
            with open(setup_py, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r'install_requires\s*=\s*[\(\[]\s*([^)\]]+)', content, re.DOTALL)
                if match:
                    lines = match.group(1)
                    for pkg in re.findall(r'[\'"]([a-zA-Z0-9_.-]+)[\'"]', lines):
                        deps.add(pkg.lower())
        except Exception:
            pass
    setup_cfg = root / "setup.cfg"
    if setup_cfg.exists():
        try:
            with open(setup_cfg, "r", encoding="utf-8") as f:
                content = f.read()
                match = re.search(r'install_requires\s*=\s*(.+?)(?:\n\s*\n|\Z)', content, re.DOTALL)
                if match:
                    lines = match.group(1)
                    for pkg in re.findall(r'([a-zA-Z0-9_.-]+)', lines):
                        deps.add(pkg.lower())
        except Exception:
            pass
    return deps

def scan_requirement_files(root: Path) -> Set[str]:
    deps = set()
    for req_file in root.glob("requirements*.in"):
        try:
            with open(req_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        pkg = re.split(r'[=<>~!@]', line)[0].strip().lower()
                        if pkg:
                            deps.add(pkg)
        except Exception:
            pass
    pipfile = root / "Pipfile"
    if pipfile.exists():
        try:
            with open(pipfile, "r", encoding="utf-8") as f:
                content = f.read()
                for pkg in re.findall(r'^([a-zA-Z0-9_.-]+)\s*=', content, re.MULTILINE):
                    deps.add(pkg.lower())
        except Exception:
            pass
    return deps

def scan_dev_tools(root: Path) -> Set[str]:
    deps = set()
    precommit = root / ".pre-commit-config.yaml"
    if precommit.exists():
        try:
            with open(precommit, "r", encoding="utf-8") as f:
                content = f.read()
                repos = re.findall(r'repo:\s.*/([a-zA-Z0-9_.-]+)', content)
                for repo in repos:
                    deps.add(repo.lower())
        except Exception:
            pass
    tox = root / "tox.ini"
    if tox.exists():
        try:
            with open(tox, "r", encoding="utf-8") as f:
                content = f.read()
                for dep_line in re.findall(r'deps\s*=\s*(.+)', content):
                    for pkg in re.split(r'[,\s]+', dep_line):
                        pkg = pkg.strip().lower()
                        if pkg and not pkg.startswith('#'):
                            deps.add(pkg)
        except Exception:
            pass
    return deps

def resolve_package_name(module_name: str, local_modules: Set[str]) -> Optional[str]:
    module_name = module_name.lower()
    if module_name in local_modules or module_name in INTERNAL_MODULES:
        return None
    if module_name in MODULE_TO_PACKAGE:
        return MODULE_TO_PACKAGE[module_name]
    if hasattr(sys, 'stdlib_module_names') and module_name in sys.stdlib_module_names:
        return None
    if '.' in module_name or module_name.startswith('_'):
        return None
    return module_name

def read_requirements(req_path: Path) -> Dict[str, str]:
    if not req_path.exists():
        return {}
    packages = {}
    with open(req_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = re.match(r'^([a-zA-Z0-9_.-]+)([=<>~!@]+.+)?$', line)
            if match:
                name = match.group(1).lower()
                version = match.group(2) if match.group(2) else ''
                packages[name] = version
    return packages

def write_requirements(req_path: Path, packages: Dict[str, str]):
    with open(req_path, "w", encoding="utf-8") as f:
        for name, version in sorted(packages.items()):
            if version:
                f.write(f"{name}{version}\n")
            else:
                f.write(f"{name}\n")

def main():
    root = Path(__file__).parent.absolute()
    print(f"🔍 Сканируем проект в {root}")

    local_modules = get_local_module_names(root, PROJECT_DIRS)
    print(f"📁 Локальных модулей: {len(local_modules)}")
    local_modules.update(INTERNAL_MODULES)

    all_imports = set()
    dynamic_imports = set()
    py_files = get_all_py_files(root, PROJECT_DIRS)
    print(f"📄 Найдено {len(py_files)} Python-файлов")
    for py_file in py_files:
        all_imports.update(extract_imports(py_file))
        dynamic_imports.update(extract_dynamic_imports(py_file))
    all_imports.update(dynamic_imports)
    print(f"📦 Уникальных импортов: {len(all_imports)}")

    required_packages = set()
    for imp in all_imports:
        pkg = resolve_package_name(imp, local_modules)
        if pkg:
            required_packages.add(pkg)

    db_packages = scan_db_connection_strings(root)
    config_packages = scan_config_files(root)
    pyproject_packages = scan_pyproject_toml(root)
    setup_packages = scan_setup(root)
    req_in_packages = scan_requirement_files(root)
    dev_tools_packages = scan_dev_tools(root)

    required_packages.update(db_packages)
    required_packages.update(config_packages)
    required_packages.update(pyproject_packages)
    required_packages.update(setup_packages)
    required_packages.update(req_in_packages)
    required_packages.update(dev_tools_packages)
    required_packages.update(EXTRA_DEPENDENCIES)

    required_packages = {p for p in required_packages if p and isinstance(p, str)}

    print("\n📋 Требуемые пакеты:")
    for pkg in sorted(required_packages):
        print(f"   {pkg}")

    req_path = root / "requirements.txt"
    current_packages = read_requirements(req_path)
    print(f"\n📄 Текущий requirements.txt содержит {len(current_packages)} пакетов")

    to_add = required_packages - set(current_packages.keys())
    to_remove = set(current_packages.keys()) - required_packages

    if to_add:
        print("\n➕ Будет добавлено:")
        for pkg in sorted(to_add):
            print(f"   + {pkg}")
    if to_remove:
        print("\n➖ Будет удалено (не используются):")
        for pkg in sorted(to_remove):
            print(f"   - {pkg}")

    answer = input("\nПродолжить обновление requirements.txt и установку? (y/N): ").strip().lower()
    if answer != 'y':
        print("Отмена.")
        sys.exit(0)

    new_packages = {}
    for pkg, ver in current_packages.items():
        if pkg not in to_remove:
            new_packages[pkg] = ver
    for pkg in to_add:
        new_packages[pkg] = ''
    write_requirements(req_path, new_packages)
    print(f"✅ requirements.txt обновлён (теперь {len(new_packages)} пакетов)")

    print("\n📦 Устанавливаем зависимости...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(req_path)], check=True)
        print("✅ Установка завершена.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Ошибка при установке: {e}")
        sys.exit(1)

    if to_remove:
        ans = input("\n⚠️ Удалить неиспользуемые пакеты из системы? (y/N): ").strip().lower()
        if ans == 'y':
            for pkg in to_remove:
                print(f"Удаляем {pkg}...")
                subprocess.run([sys.executable, "-m", "pip", "uninstall", "-y", pkg], capture_output=True, check=False)
            print("✅ Удаление завершено.")
    print("\n🎉 Готово!")

if __name__ == "__main__":
    main()