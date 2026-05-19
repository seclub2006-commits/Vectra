"""
Скрипт для экспорта структуры проекта и содержимого всех файлов.
При повторном запуске создает новый файл с именем дамп1.txt, дамп2.txt и т.д.
Самые старые файлы (кроме последних 5) удаляются автоматически.
"""

import os
import sys
import re
from pathlib import Path
from datetime import datetime

class ProjectExporter:
    """Экспортер структуры и содержимого проекта"""
    
    # Папки и файлы, которые нужно исключить
    IGNORE_DIRS = {
        '__pycache__', 
        'venv', 
        'env', 
        '.venv', 
        '.git',
        'data',           # База данных
        '.pytest_cache',
        '.mypy_cache'
    }
    
    IGNORE_FILES = {
        '.pyc', 
        '.db',           # База данных
        '.sqlite',
        '.sqlite3',
    }
    
    IGNORE_EXTENSIONS = {
        '.pyc', '.db', '.sqlite', '.sqlite3', '.log'
    }
    
    def __init__(self, root_dir: str = "."):
        self.root_dir = Path(root_dir).resolve()
        self.output_file = self.get_next_filename()
        self.lines = []
    
    def get_next_filename(self) -> Path:
        """
        Определяет следующий номер для файла дамп.
        Ищет существующие файлы дамп*.txt и создаёт новый с номером на 1 больше максимума.
        """
        pattern = re.compile(r'дамп(\d+)\.txt')
        max_num = 0
        
        for file in self.root_dir.glob("дамп*.txt"):
            match = pattern.match(file.name)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
        
        next_num = max_num + 1
        filename = f"дамп{next_num}.txt"
        return self.root_dir / filename
    
    def should_ignore_dir(self, dir_name: str) -> bool:
        """Проверка, нужно ли игнорировать папку"""
        return dir_name in self.IGNORE_DIRS
    
    def should_ignore_file(self, file_path: Path) -> bool:
        """Проверка, нужно ли игнорировать файл"""
        # Игнорируем файлы дамп (старые отчёты)
        if file_path.name.startswith('дамп'):
            return True
        
        # Игнорируем сам скрипт
        if file_path.name == 'export_project.py':
            return True
        
        # Игнорируем по расширению
        if file_path.suffix in self.IGNORE_EXTENSIONS:
            return True
        
        return False
    
    def get_tree_structure(self) -> str:
        """Получает древовидную структуру проекта"""
        result = []
        result.append("📁 СТРУКТУРА ПРОЕКТА")
        result.append("=" * 60)
        result.append(f"📂 {self.root_dir.name}/")
        
        def walk_dir(directory: Path, prefix: str = "", is_last: bool = True):
            """Рекурсивный обход папок"""
            items = []
            
            # Собираем папки и файлы
            for item in sorted(directory.iterdir()):
                if item.is_dir():
                    if not self.should_ignore_dir(item.name):
                        items.append(("dir", item))
                else:
                    if not self.should_ignore_file(item):
                        items.append(("file", item))
            
            for i, (item_type, item_path) in enumerate(items):
                is_last_item = (i == len(items) - 1)
                
                # Выбираем символы для отображения
                if is_last_item:
                    branch = "└── "
                    new_prefix = prefix + "    "
                else:
                    branch = "├── "
                    new_prefix = prefix + "│   "
                
                if item_type == "dir":
                    result.append(f"{prefix}{branch}📁 {item_path.name}/")
                    walk_dir(item_path, new_prefix, is_last_item)
                else:
                    size = item_path.stat().st_size
                    size_str = self.format_size(size)
                    result.append(f"{prefix}{branch}📄 {item_path.name} ({size_str})")
        
        walk_dir(self.root_dir)
        return "\n".join(result)
    
    def format_size(self, size: int) -> str:
        """Форматирует размер файла"""
        for unit in ['B', 'KB', 'MB']:
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} GB"
    
    def read_file_content(self, file_path: Path) -> str:
        """Безопасное чтение содержимого файла"""
        try:
            # Пробуем разные кодировки
            for encoding in ['utf-8', 'cp1251', 'latin-1']:
                try:
                    with open(file_path, 'r', encoding=encoding) as f:
                        content = f.read()
                        # Ограничиваем размер для очень больших файлов (максимум 500KB)
                        if len(content) > 500000:
                            content = content[:500000] + "\n... [ФАЙЛ ОБРЕЗАН, ТОЛЬКО ПЕРВЫЕ 500KB]"
                        return content
                except UnicodeDecodeError:
                    continue
            return "[НЕ УДАЛОСЬ ПРОЧИТАТЬ: не текстовая кодировка]"
        except Exception as e:
            return f"[ОШИБКА ЧТЕНИЯ: {e}]"
    
    def get_file_language(self, file_path: Path) -> str:
        """Определяет язык программирования по расширению"""
        ext = file_path.suffix.lower()
        languages = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.html': 'HTML',
            '.css': 'CSS',
            '.json': 'JSON',
            '.yaml': 'YAML',
            '.yml': 'YAML',
            '.md': 'Markdown',
            '.txt': 'Text',
            '.env': 'Environment',
            '.gitignore': 'Git Ignore',
            '.sql': 'SQL',
            '.sh': 'Bash',
            '.bat': 'Batch',
        }
        return languages.get(ext, 'Unknown')
    
    def get_all_files_content(self) -> str:
        """Получает содержимое всех файлов проекта"""
        result = []
        result.append("\n" + "=" * 80)
        result.append("📄 СОДЕРЖИМОЕ ФАЙЛОВ")
        result.append("=" * 80)
        
        def walk_files(directory: Path, depth: int = 0):
            """Рекурсивный обход и вывод содержимого файлов"""
            for item in sorted(directory.iterdir()):
                if item.is_dir():
                    if not self.should_ignore_dir(item.name):
                        walk_files(item, depth + 1)
                else:
                    if not self.should_ignore_file(item):
                        self.export_file_content(item, result)
        
        walk_files(self.root_dir)
        return "\n".join(result)
    
    def export_file_content(self, file_path: Path, result: list):
        """Экспортирует содержимое одного файла"""
        relative_path = file_path.relative_to(self.root_dir)
        language = self.get_file_language(file_path)
        
        result.append("\n" + "=" * 80)
        result.append(f"📁 ФАЙЛ: {relative_path}")
        result.append(f"📝 Язык: {language}")
        result.append(f"📏 Размер: {self.format_size(file_path.stat().st_size)}")
        result.append("=" * 80)
        
        content = self.read_file_content(file_path)
        result.append(content)
        result.append("")  # Пустая строка после содержимого
    
    def get_summary(self) -> str:
        """Получает сводку по проекту"""
        result = []
        result.append("\n" + "=" * 60)
        result.append("📊 СВОДКА ПО ПРОЕКТУ")
        result.append("=" * 60)
        
        py_files = 0
        total_size = 0
        total_files = 0
        
        for root, dirs, files in os.walk(self.root_dir):
            # Фильтруем игнорируемые папки
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            
            for file in files:
                file_path = Path(root) / file
                if not self.should_ignore_file(file_path):
                    total_files += 1
                    total_size += file_path.stat().st_size
                    if file.endswith('.py'):
                        py_files += 1
        
        result.append(f"📁 Всего файлов: {total_files}")
        result.append(f"🐍 Python файлов: {py_files}")
        result.append(f"💾 Общий размер: {self.format_size(total_size)}")
        result.append(f"🕐 Экспорт выполнен: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        return "\n".join(result)
    
    def cleanup_old_exports(self, keep_last: int = 5):
        """
        Удаляет старые файлы дамп, оставляя только последние keep_last штук.
        """
        export_files = list(self.root_dir.glob("дамп*.txt"))
        if len(export_files) > keep_last:
            # Сортируем по дате создания (старые первые)
            export_files.sort(key=lambda x: x.stat().st_mtime)
            for old_file in export_files[:-keep_last]:
                old_file.unlink()
                print(f"   🗑️ Удален старый отчёт: {old_file.name}")
    
    def export(self):
        """Главный метод экспорта"""
        print(f"🚀 Начинаю экспорт проекта...")
        print(f"📂 Корневая папка: {self.root_dir}")
        print(f"📄 Выходной файл: {self.output_file.name}")
        print()
        
        # Собираем всё вместе
        print("📁 Сканирую структуру проекта...")
        structure = self.get_tree_structure()
        
        print("📄 Собираю содержимое файлов...")
        content = self.get_all_files_content()
        
        print("📊 Формирую сводку...")
        summary = self.get_summary()
        
        # Записываем в файл
        full_report = "\n".join([structure, content, summary])
        
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(full_report)
        
        # Очищаем старые отчёты (оставляем 5 последних)
        print("🧹 Очищаю старые отчёты...")
        self.cleanup_old_exports(keep_last=5)
        
        print()
        print("=" * 60)
        print("✅ ЭКСПОРТ ЗАВЕРШЕН УСПЕШНО!")
        print("=" * 60)
        print(f"📄 Отчёт сохранен в: {self.output_file.name}")
        print(f"📊 Статистика:")
        print(f"   • Структура проекта включена")
        print(f"   • Содержимое всех файлов включено")
        print(f"   • Размер отчёта: {self.format_size(self.output_file.stat().st_size)}")
        print(f"🕐 Время завершения: {datetime.now().strftime('%H:%M:%S')}")
        
        return full_report

def main():
    """Запуск экспортёра"""
    print()
    print("=" * 60)
    print("🔍 ЭКСПОРТ ПРОЕКТА TRADING BOT")
    print("=" * 60)
    print()
    
    # Создаём экспортёр в текущей директории
    exporter = ProjectExporter(".")
    
    try:
        exporter.export()
    except Exception as e:
        print(f"❌ Ошибка при экспорте: {e}")
        import traceback
        traceback.print_exc()
    
    print()
    input("Нажмите Enter для выхода...")

if __name__ == "__main__":
    main()