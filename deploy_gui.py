#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
GITHUB DEPLOY MANAGER – полная версия с запоминанием последнего пуша
и автоматическим созданием репозитория при ошибке 404.
"""

import os
import sys
import shutil
import subprocess
import threading
import json
import hashlib
from pathlib import Path
from datetime import datetime
from functools import lru_cache
from typing import Dict, List, Set, Optional, Tuple

from dotenv import load_dotenv
from pathspec import PathSpec
from pathspec.patterns.gitwildmatch import GitWildMatchPattern

from PyQt5.QtCore import (
    Qt,
    QThread,
    pyqtSignal,
    QSize,
    QFileInfo,
    QTimer
)
from PyQt5.QtGui import (
    QColor,
    QFont,
    QTextCursor,
    QIcon
)
from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QHeaderView,
    QFileIconProvider,
    QPlainTextEdit,
    QLineEdit,
    QProgressBar,
    QSplitter,
    QTextEdit,
    QMenu,
    QAction,
    QCheckBox
)

import requests

# ============================================================
# CONFIG
# ============================================================

load_dotenv()

TOKEN = os.getenv("GITHUB_TOKEN", "")
REPO_NAME = os.getenv("GITHUB_REPO_NAME", "TradingBot")
BRANCH = "main"
MAX_FILE_SIZE_MB = 100
HTTP_TIMEOUT = 30
STATE_FILE = ".last_push_state.json"

# ============================================================
# HELPERS
# ============================================================

class GitStatus:
    MODIFIED = "modified"
    NEW = "new"
    DELETED = "deleted"
    CLEAN = "clean"

def get_safe_log_text(text: str) -> str:
    if TOKEN and TOKEN in text:
        return text.replace(TOKEN, "***HIDDEN_TOKEN***")
    return text

def open_file_explorer(path: Path):
    if sys.platform == "win32":
        os.startfile(str(path))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(path)])
    else:
        subprocess.run(["xdg-open", str(path)])

def compute_file_hash(file_path: Path) -> str:
    hasher = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest()
    except Exception:
        return ""

# ============================================================
# УПРАВЛЕНИЕ СОСТОЯНИЕМ ПОСЛЕДНЕГО ПУША
# ============================================================

class PushStateManager:
    def __init__(self, root_dir: Path):
        self.state_path = root_dir / STATE_FILE

    def load_state(self) -> Dict[str, str]:
        if not self.state_path.exists():
            return {}
        try:
            with open(self.state_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data.get("files", {})
        except Exception:
            return {}

    def save_state(self, files_hash: Dict[str, str]):
        data = {
            "timestamp": datetime.now().isoformat(),
            "files": files_hash
        }
        try:
            with open(self.state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Ошибка сохранения состояния: {e}")

    def compute_current_state(self, root_dir: Path, pathspec: Optional[PathSpec]) -> Dict[str, str]:
        current_state = {}
        for root, dirs, files in os.walk(root_dir):
            if ".git" in dirs:
                dirs.remove(".git")
            for file in files:
                abs_path = Path(root) / file
                rel_path = str(abs_path.relative_to(root_dir)).replace("\\", "/")
                if rel_path == STATE_FILE or rel_path == ".gitignore":
                    continue
                if pathspec and pathspec.match_file(rel_path):
                    continue
                if abs_path.stat().st_size / (1024 * 1024) > MAX_FILE_SIZE_MB:
                    continue
                file_hash = compute_file_hash(abs_path)
                if file_hash:
                    current_state[rel_path] = file_hash
        return current_state

# ============================================================
# GIT WORKER (с автоматическим восстановлением remote)
# ============================================================

class GitWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, root_dir: Path, to_add: List[str], to_rm: List[str],
                 commit_message: str, private_repo: bool, branch: str,
                 git_user_name: str = "", git_user_email: str = ""):
        super().__init__()
        self.root_dir = root_dir
        self.to_add = to_add
        self.to_rm = to_rm
        self.commit_message = commit_message
        self.private_repo = private_repo
        self.branch = branch
        self.git_user_name = git_user_name
        self.git_user_email = git_user_email
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def log(self, text: str):
        self.log_signal.emit(get_safe_log_text(text))

    def run_git(self, args: List[str], check: bool = True, capture: bool = False) -> Optional[str]:
        self.log(f"$ git {' '.join(args)}")
        try:
            result = subprocess.run(
                ["git"] + args,
                cwd=self.root_dir,
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.stdout.strip():
                self.log(result.stdout)
            if result.stderr.strip():
                self.log(result.stderr)
            if check and result.returncode != 0:
                raise Exception(result.stderr)
            if capture:
                return result.stdout.strip()
            return None
        except subprocess.TimeoutExpired:
            raise Exception("Команда Git превысила таймаут 60 секунд")

    def ensure_git_config_local(self):
        local_name = self.run_git(["config", "--local", "user.name"], check=False, capture=True)
        local_email = self.run_git(["config", "--local", "user.email"], check=False, capture=True)
        if local_name and local_email:
            return
        if not local_name and self.git_user_name:
            self.run_git(["config", "--local", "user.name", self.git_user_name])
            self.log(f"Установлено локальное user.name = {self.git_user_name}")
        if not local_email and self.git_user_email:
            self.run_git(["config", "--local", "user.email", self.git_user_email])
            self.log(f"Установлено локальное user.email = {self.git_user_email}")
        new_name = self.run_git(["config", "--local", "user.name"], check=False, capture=True)
        new_email = self.run_git(["config", "--local", "user.email"], check=False, capture=True)
        if not new_name or not new_email:
            raise Exception("Не удалось установить user.name/user.email для репозитория.\n"
                            "Укажите их в .env (GIT_USER_NAME, GIT_USER_EMAIL)")

    def create_github_repo(self) -> str:
        headers = {
            "Authorization": f"token {TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        }
        data = {"name": REPO_NAME, "private": self.private_repo, "auto_init": False}
        self.log("Создание GitHub репозитория...")
        try:
            resp = requests.post("https://api.github.com/user/repos", json=data,
                                 headers=headers, timeout=HTTP_TIMEOUT)
        except requests.Timeout:
            raise Exception("Таймаут при создании репозитория")
        if resp.status_code == 201:
            repo_url = resp.json()["clone_url"]
            self.log(f"Репозиторий создан: {repo_url}")
            return repo_url
        elif resp.status_code == 422:
            try:
                user_resp = requests.get("https://api.github.com/user", headers=headers, timeout=HTTP_TIMEOUT)
                user_resp.raise_for_status()
                username = user_resp.json()["login"]
            except Exception:
                username = None
            candidates = [
                f"https://github.com/{username}/{REPO_NAME}.git" if username else None,
                f"https://github.com/{REPO_NAME}/{REPO_NAME}.git"
            ]
            for url in candidates:
                if url and self.repo_exists(url, headers):
                    self.log(f"Репозиторий уже существует: {url}")
                    return url
            raise Exception("Не удалось определить URL существующего репозитория")
        else:
            raise Exception(f"Ошибка создания репозитория: {resp.text}")

    def repo_exists(self, url: str, headers: dict) -> bool:
        try:
            resp = requests.head(url, headers=headers, timeout=HTTP_TIMEOUT)
            return resp.status_code == 200
        except:
            return False

    def setup_remote_and_push(self) -> bool:
        remote_url = self.run_git(["remote", "get-url", "origin"], check=False, capture=True)
        if not remote_url:
            repo_url = self.create_github_repo()
            self.run_git(["remote", "add", "origin", repo_url])
            remote_url = repo_url

        try:
            self.run_git(["push", "-u", "origin", self.branch])
            return True
        except Exception as e:
            error_msg = str(e)
            if "Repository not found" in error_msg or "404" in error_msg:
                self.log("Репозиторий не найден, пробуем создать заново...")
                self.run_git(["remote", "remove", "origin"], check=False)
                repo_url = self.create_github_repo()
                self.run_git(["remote", "add", "origin", repo_url])
                self.run_git(["push", "-u", "origin", self.branch])
                return True
            else:
                raise e

    def run(self):
        try:
            self.ensure_git_config_local()
            if self._cancel:
                return

            total = len(self.to_rm) + len(self.to_add)
            processed = 0

            if self.to_rm:
                self.log(f"Удаление файлов: {', '.join(self.to_rm)}")
                self.run_git(["rm"] + self.to_rm)
                processed += len(self.to_rm)
                self.progress_signal.emit(processed, total)

            if self.to_add:
                chunk_size = 50
                for i in range(0, len(self.to_add), chunk_size):
                    if self._cancel:
                        return
                    chunk = self.to_add[i:i+chunk_size]
                    self.log(f"Добавление: {', '.join(chunk)}")
                    self.run_git(["add"] + chunk)
                    processed += len(chunk)
                    self.progress_signal.emit(processed, total)

            diff_check = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=self.root_dir)
            if diff_check.returncode == 0:
                self.finished_signal.emit(False, "Нет изменений для коммита")
                return

            self.run_git(["commit", "-m", self.commit_message])
            self.setup_remote_and_push()
            self.finished_signal.emit(True, "Успешно выгружено на GitHub")
        except Exception as e:
            self.finished_signal.emit(False, str(e))

# ============================================================
# КЭШ ИКОНОК
# ============================================================

class CachedIconProvider:
    def __init__(self):
        self.provider = QFileIconProvider()

    @lru_cache(maxsize=500)
    def get_icon(self, suffix: str, is_dir: bool) -> QIcon:
        if is_dir:
            return self.provider.icon(QFileIconProvider.Folder)
        tmp_file = QFileInfo(f"dummy{suffix}")
        return self.provider.icon(tmp_file)

    def icon_for_path(self, path: Path) -> QIcon:
        is_dir = path.is_dir()
        suffix = path.suffix.lower() if not is_dir else ""
        return self.get_icon(suffix, is_dir)

# ============================================================
# ПОТОК ПОСТРОЕНИЯ ДЕРЕВА
# ============================================================

class TreeBuilderThread(QThread):
    finished_signal = pyqtSignal(object)

    def __init__(self, root_dir: Path, state_manager: PushStateManager, pathspec: Optional[PathSpec],
                 checked_paths: Set[str], icon_provider: CachedIconProvider):
        super().__init__()
        self.root_dir = root_dir
        self.state_manager = state_manager
        self.pathspec = pathspec
        self.checked_paths = checked_paths
        self.icon_provider = icon_provider

    def run(self):
        last_state = self.state_manager.load_state()
        current_state = self.state_manager.compute_current_state(self.root_dir, self.pathspec)

        changes = {}
        for rel_path in current_state:
            if rel_path not in last_state:
                changes[rel_path] = GitStatus.NEW
            elif current_state[rel_path] != last_state[rel_path]:
                changes[rel_path] = GitStatus.MODIFIED
            else:
                changes[rel_path] = GitStatus.CLEAN
        for rel_path in last_state:
            if rel_path not in current_state:
                changes[rel_path] = GitStatus.DELETED

        root_item = QTreeWidgetItem()
        root_item.setText(0, self.root_dir.name)
        root_item.setData(0, Qt.UserRole, str(self.root_dir))
        root_item.setIcon(0, self.icon_provider.icon_for_path(self.root_dir))
        root_item.setFlags(root_item.flags() | Qt.ItemIsUserCheckable)
        root_path = str(self.root_dir)
        if self.checked_paths:
            root_item.setCheckState(0, Qt.Checked if root_path in self.checked_paths else Qt.Unchecked)
        else:
            root_item.setCheckState(0, Qt.Checked)

        self._add_directory(root_item, self.root_dir, changes)
        self._update_all_folder_states(root_item)
        self.finished_signal.emit(root_item)

    def _add_directory(self, parent_item: QTreeWidgetItem, directory: Path, changes: Dict[str, str]):
        try:
            entries = sorted(directory.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
            for entry in entries:
                if entry.name == ".git" or entry.is_symlink():
                    continue
                rel_path = str(entry.relative_to(self.root_dir)).replace("\\", "/")
                item = QTreeWidgetItem()
                item.setText(0, entry.name)
                item.setData(0, Qt.UserRole, str(entry))
                item.setIcon(0, self.icon_provider.icon_for_path(entry))
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                if rel_path in self.checked_paths:
                    item.setCheckState(0, Qt.Checked)
                else:
                    item.setCheckState(0, Qt.Checked)
                if entry.is_dir():
                    parent_item.addChild(item)
                    self._add_directory(item, entry, changes)
                else:
                    self._configure_file_item(item, entry, rel_path, changes.get(rel_path, GitStatus.CLEAN))
                    parent_item.addChild(item)
        except PermissionError:
            pass

    def _configure_file_item(self, item: QTreeWidgetItem, path: Path, rel_path: str, status: str):
        size_mb = path.stat().st_size / (1024 * 1024)
        is_too_big = size_mb > MAX_FILE_SIZE_MB
        ignored = self.pathspec is not None and self.pathspec.match_file(rel_path)

        if ignored or is_too_big:
            item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            if is_too_big:
                item.setText(1, f"слишком большой ({size_mb:.1f}MB)")
            elif ignored:
                item.setText(1, "ignored")
            item.setForeground(0, QColor("#666"))
        else:
            if status == GitStatus.NEW:
                item.setText(1, "new")
                item.setForeground(0, QColor("#44ff44"))
            elif status == GitStatus.MODIFIED:
                item.setText(1, "modified")
                item.setForeground(0, QColor("#ffaa00"))
            elif status == GitStatus.DELETED:
                item.setText(1, "deleted (удалить на GitHub)")
                item.setForeground(0, QColor("#ff4444"))
                item.setFlags(item.flags() & ~Qt.ItemIsUserCheckable)
            else:
                item.setText(1, "clean")
                item.setForeground(0, QColor("#bbbbbb"))

    def _update_all_folder_states(self, item: QTreeWidgetItem):
        for i in range(item.childCount()):
            child = item.child(i)
            if child.childCount() > 0:
                self._update_all_folder_states(child)
        if item.parent() is not None:
            path_str = item.data(0, Qt.UserRole)
            if path_str and Path(path_str).is_dir():
                self._update_folder_check_state(item)
                self._update_folder_text_status(item)

    def _update_folder_check_state(self, folder_item: QTreeWidgetItem):
        total = 0
        checked = 0
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            if child.flags() & Qt.ItemIsUserCheckable:
                total += 1
                state = child.checkState(0)
                if state == Qt.Checked:
                    checked += 1
                elif state == Qt.PartiallyChecked:
                    checked += 0.5
        if total == 0:
            folder_item.setCheckState(0, Qt.Unchecked)
            folder_item.setText(1, "нет выбираемых")
            return
        if checked == total:
            folder_item.setCheckState(0, Qt.Checked)
        elif checked == 0:
            folder_item.setCheckState(0, Qt.Unchecked)
        else:
            folder_item.setCheckState(0, Qt.PartiallyChecked)

    def _update_folder_text_status(self, folder_item: QTreeWidgetItem):
        total = 0
        checked = 0
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            if child.flags() & Qt.ItemIsUserCheckable:
                total += 1
                state = child.checkState(0)
                if state == Qt.Checked:
                    checked += 1
                elif state == Qt.PartiallyChecked:
                    checked += 0.5
        if total == 0:
            folder_item.setText(1, "")
            return
        if checked == total:
            folder_item.setText(1, "все")
        elif checked == 0:
            folder_item.setText(1, "пусто")
        else:
            folder_item.setText(1, f"частично ({int(checked)}/{total})")

# ============================================================
# ГЛАВНОЕ ОКНО
# ============================================================

class DeployGUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.root_dir = Path(__file__).parent.absolute()
        self.icon_provider = CachedIconProvider()
        self.pathspec: Optional[PathSpec] = None
        self.state_manager = PushStateManager(self.root_dir)
        self.load_gitignore()
        self.init_ui()
        self.check_git()
        self.check_github_token()
        self.check_git_repo()
        self.worker: Optional[GitWorker] = None
        self.tree_builder: Optional[TreeBuilderThread] = None
        self.expanded_paths: Set[str] = set()
        self.checked_paths: Set[str] = set()
        self.start_building_tree()

    def init_ui(self):
        self.setWindowTitle("GitHub Deploy Manager (с памятью последнего пуша)")
        self.resize(1600, 950)
        self.setMinimumSize(QSize(1200, 700))
        self.setStyleSheet(self._get_stylesheet())
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        top_bar = QHBoxLayout()
        self.project_label = QLabel(f"📁 {self.root_dir}")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Поиск файлов...")
        self.search_input.textChanged.connect(self.filter_tree)
        self.private_checkbox = QCheckBox("Private Repo")
        self.branch_input = QLineEdit()
        self.branch_input.setPlaceholderText("Ветка (main)")
        self.branch_input.setText(BRANCH)
        self.branch_input.setMaximumWidth(150)
        top_bar.addWidget(self.project_label)
        top_bar.addStretch()
        top_bar.addWidget(QLabel("Ветка:"))
        top_bar.addWidget(self.branch_input)
        top_bar.addWidget(self.private_checkbox)
        top_bar.addWidget(self.search_input)
        layout.addLayout(top_bar)

        splitter = QSplitter()
        layout.addWidget(splitter)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Файл/Папка", "Статус"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.itemClicked.connect(self.on_item_clicked)
        self.tree.itemSelectionChanged.connect(self.show_diff_preview)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        splitter.addWidget(self.tree)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        diff_label = QLabel("Diff Preview (относительно последнего пуша)")
        self.diff_preview = QTextEdit()
        self.diff_preview.setReadOnly(True)
        self.diff_preview.setFont(QFont("Consolas", 10))
        log_label = QLabel("Console Log")
        self.log_console = QPlainTextEdit()
        self.log_console.setReadOnly(True)
        self.log_console.setMaximumHeight(250)
        right_layout.addWidget(diff_label)
        right_layout.addWidget(self.diff_preview)
        right_layout.addWidget(log_label)
        right_layout.addWidget(self.log_console)
        splitter.addWidget(right_widget)
        splitter.setSizes([700, 600])

        bottom = QHBoxLayout()
        self.commit_input = QLineEdit()
        self.commit_input.setPlaceholderText("Commit message...")
        self.commit_input.setText(f"Обновление от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        self.upload_button = QPushButton("🚀 PUSH TO GITHUB")
        self.upload_button.clicked.connect(self.upload_selected)
        self.cancel_button = QPushButton("❌ CANCEL")
        self.cancel_button.clicked.connect(self.cancel_upload)
        self.cancel_button.setEnabled(False)
        self.refresh_button = QPushButton("🔄 REFRESH")
        self.refresh_button.clicked.connect(self.refresh_all)
        self.select_all_button = QPushButton("✅ Выбрать всё")
        self.select_all_button.clicked.connect(self.select_all_items)
        self.deselect_all_button = QPushButton("❌ Снять всё")
        self.deselect_all_button.clicked.connect(self.deselect_all_items)

        bottom.addWidget(self.commit_input)
        bottom.addWidget(self.refresh_button)
        bottom.addWidget(self.select_all_button)
        bottom.addWidget(self.deselect_all_button)
        bottom.addWidget(self.cancel_button)
        bottom.addWidget(self.upload_button)
        layout.addLayout(bottom)

        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)

    def _get_stylesheet(self) -> str:
        return """
            QWidget { background-color: #151515; color: #d0d0d0; font-size: 13px; }
            QTreeWidget { background-color: #1b1b1b; border: 1px solid #2d2d2d; padding: 5px; }
            QTreeWidget::item { padding: 4px; }
            QTreeWidget::item:selected { background-color: #5a1d1d; }
            QTextEdit, QPlainTextEdit { background-color: #101010; border: 1px solid #333; color: #d0d0d0; }
            QPushButton { background-color: #7a1f1f; border: none; padding: 10px; border-radius: 6px; font-weight: bold; }
            QPushButton:hover { background-color: #a82828; }
            QPushButton:disabled { background-color: #333; }
            QLineEdit { background-color: #222; border: 1px solid #444; padding: 6px; border-radius: 4px; }
            QHeaderView::section { background-color: #202020; padding: 5px; border: none; }
            QProgressBar { background-color: #222; border: 1px solid #333; text-align: center; }
            QProgressBar::chunk { background-color: #a82828; }
        """

    def log(self, text: str):
        self.log_console.appendPlainText(get_safe_log_text(text))
        self.log_console.moveCursor(QTextCursor.End)

    def check_git(self):
        if shutil.which("git") is None:
            QMessageBox.critical(self, "Ошибка", "Git не установлен")
            sys.exit(1)

    def check_github_token(self):
        if not TOKEN:
            QMessageBox.critical(self, "Ошибка", "GITHUB_TOKEN не найден в .env")
            sys.exit(1)
        try:
            resp = requests.get("https://api.github.com/user",
                                headers={"Authorization": f"token {TOKEN}"},
                                timeout=HTTP_TIMEOUT)
            if resp.status_code != 200:
                QMessageBox.critical(self, "Ошибка", "Неверный GitHub токен")
                sys.exit(1)
            self.log("GitHub токен валиден")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", f"Не удалось проверить токен: {e}")
            sys.exit(1)

    def check_git_repo(self):
        result = subprocess.run(["git", "rev-parse", "--is-inside-work-tree"],
                                cwd=self.root_dir, capture_output=True)
        if result.returncode != 0:
            reply = QMessageBox.question(self, "Git", "Это не Git репозиторий.\nСоздать?",
                                         QMessageBox.Yes | QMessageBox.No)
            if reply == QMessageBox.Yes:
                subprocess.run(["git", "init"], cwd=self.root_dir)
                self.log("Git репозиторий инициализирован")
            else:
                sys.exit(0)

    def load_gitignore(self):
        gitignore = self.root_dir / ".gitignore"
        if gitignore.exists():
            try:
                with open(gitignore, "r", encoding="utf-8") as f:
                    self.pathspec = PathSpec.from_lines(GitWildMatchPattern, f)
            except UnicodeDecodeError:
                try:
                    with open(gitignore, "r", encoding="cp1251") as f:
                        self.pathspec = PathSpec.from_lines(GitWildMatchPattern, f)
                except Exception as e:
                    self.log(f"Ошибка чтения .gitignore: {e}")
                    self.pathspec = None
        else:
            self.pathspec = None

    def start_building_tree(self):
        self.progress.show()
        self.progress.setRange(0, 0)
        self.tree_builder = TreeBuilderThread(
            self.root_dir, self.state_manager, self.pathspec,
            self.checked_paths, self.icon_provider
        )
        self.tree_builder.finished_signal.connect(self.on_tree_built)
        self.tree_builder.start()

    def on_tree_built(self, root_item: QTreeWidgetItem):
        self.tree.clear()
        self.tree.addTopLevelItem(root_item)
        self.progress.hide()
        self._restore_expanded_state(root_item)
        self.log("Дерево загружено. Изменения определены относительно последнего пуша.")
        self._save_all_check_states()

    def on_item_clicked(self, item: QTreeWidgetItem, column: int):
        if column == 0 and (item.flags() & Qt.ItemIsUserCheckable):
            new_state = item.checkState(0)
            self._set_recursive_check_state(item, new_state)
            self._update_parents_check_and_text(item)
            self._save_all_check_states()

    def _set_recursive_check_state(self, item: QTreeWidgetItem, state: Qt.CheckState):
        for i in range(item.childCount()):
            child = item.child(i)
            if child.flags() & Qt.ItemIsUserCheckable:
                child.setCheckState(0, state)
            if child.childCount() > 0:
                self._set_recursive_check_state(child, state)

    def _update_parents_check_and_text(self, item: QTreeWidgetItem):
        parent = item.parent()
        while parent:
            self._update_folder_check_state(parent)
            self._update_folder_text_status(parent)
            parent = parent.parent()

    def _update_folder_check_state(self, folder_item: QTreeWidgetItem):
        total = 0
        checked = 0
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            if child.flags() & Qt.ItemIsUserCheckable:
                total += 1
                state = child.checkState(0)
                if state == Qt.Checked:
                    checked += 1
                elif state == Qt.PartiallyChecked:
                    checked += 0.5
        if total == 0:
            folder_item.setCheckState(0, Qt.Unchecked)
            folder_item.setText(1, "нет выбираемых")
            return
        if checked == total:
            folder_item.setCheckState(0, Qt.Checked)
        elif checked == 0:
            folder_item.setCheckState(0, Qt.Unchecked)
        else:
            folder_item.setCheckState(0, Qt.PartiallyChecked)

    def _update_folder_text_status(self, folder_item: QTreeWidgetItem):
        total = 0
        checked = 0
        for i in range(folder_item.childCount()):
            child = folder_item.child(i)
            if child.flags() & Qt.ItemIsUserCheckable:
                total += 1
                state = child.checkState(0)
                if state == Qt.Checked:
                    checked += 1
                elif state == Qt.PartiallyChecked:
                    checked += 0.5
        if total == 0:
            folder_item.setText(1, "")
            return
        if checked == total:
            folder_item.setText(1, "все")
        elif checked == 0:
            folder_item.setText(1, "пусто")
        else:
            folder_item.setText(1, f"частично ({int(checked)}/{total})")

    def select_all_items(self):
        root = self.tree.topLevelItem(0)
        if root:
            self._set_recursive_check_state(root, Qt.Checked)
            self._update_parents_check_and_text(root)
            self._save_all_check_states()

    def deselect_all_items(self):
        root = self.tree.topLevelItem(0)
        if root:
            self._set_recursive_check_state(root, Qt.Unchecked)
            self._update_parents_check_and_text(root)
            self._save_all_check_states()

    def _save_all_check_states(self):
        self.checked_paths.clear()
        root = self.tree.topLevelItem(0)
        if root:
            self._collect_checked_paths(root)

    def _collect_checked_paths(self, item: QTreeWidgetItem):
        path_str = item.data(0, Qt.UserRole)
        if path_str and (item.flags() & Qt.ItemIsUserCheckable) and item.checkState(0) == Qt.Checked:
            self.checked_paths.add(path_str)
        for i in range(item.childCount()):
            self._collect_checked_paths(item.child(i))

    def filter_tree(self):
        text = self.search_input.text().lower()
        root = self.tree.topLevelItem(0)
        if root:
            self._filter_recursive(root, text)

    def _filter_recursive(self, item: QTreeWidgetItem, text: str) -> bool:
        visible = False
        for i in range(item.childCount()):
            child = item.child(i)
            child_visible = self._filter_recursive(child, text)
            visible = visible or child_visible
        item_visible = text in item.text(0).lower()
        visible = visible or item_visible
        item.setHidden(not visible)
        return visible

    def show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        menu = QMenu()
        check_all = QAction("✅ Отметить всё", self)
        uncheck_all = QAction("❌ Снять всё", self)
        open_exp = QAction("📂 Открыть папку", self)
        check_all.triggered.connect(lambda: self._set_recursive_check_state(item, Qt.Checked))
        uncheck_all.triggered.connect(lambda: self._set_recursive_check_state(item, Qt.Unchecked))
        open_exp.triggered.connect(lambda: open_file_explorer(Path(item.data(0, Qt.UserRole))))
        menu.addAction(check_all)
        menu.addAction(uncheck_all)
        menu.addSeparator()
        menu.addAction(open_exp)
        menu.exec_(self.tree.viewport().mapToGlobal(pos))

    def show_diff_preview(self):
        items = self.tree.selectedItems()
        if not items:
            return
        item = items[0]
        path = Path(item.data(0, Qt.UserRole))
        if not path.is_file():
            return
        rel_path = str(path.relative_to(self.root_dir)).replace("\\", "/")
        status = item.text(1).lower()
        if status in ("new", "modified"):
            last_state = self.state_manager.load_state()
            if rel_path in last_state:
                self.diff_preview.setPlainText(
                    f"Файл {rel_path} помечен как '{status}'.\n"
                    "Для просмотра различий используйте внешние инструменты (IDE, git diff)."
                )
            else:
                try:
                    content = path.read_text(encoding='utf-8', errors='replace')
                    self.diff_preview.setPlainText(f"Новый файл {rel_path}:\n\n{content[:5000]}")
                except Exception as e:
                    self.diff_preview.setPlainText(f"Ошибка чтения: {e}")
        elif status == "deleted":
            self.diff_preview.setPlainText(f"Файл {rel_path} удалён локально и будет удалён на GitHub.")
        else:
            self.diff_preview.setPlainText(f"Файл {rel_path} не изменялся (clean).")

    def get_selected_changes(self) -> Tuple[List[str], List[str]]:
        to_add = []
        to_rm = []
        root = self.tree.topLevelItem(0)
        if root:
            self._collect_selected_changes(root, to_add, to_rm)
        return to_add, to_rm

    def _collect_selected_changes(self, item: QTreeWidgetItem, to_add: List[str], to_rm: List[str]):
        for i in range(item.childCount()):
            child = item.child(i)
            path = Path(child.data(0, Qt.UserRole))
            rel = str(path.relative_to(self.root_dir)).replace("\\", "/")
            if path.is_file():
                if child.flags() & Qt.ItemIsUserCheckable and child.checkState(0) == Qt.Checked:
                    status = child.text(1).lower()
                    if status in ("new", "modified"):
                        to_add.append(rel)
                    elif status == "deleted":
                        to_rm.append(rel)
            else:
                self._collect_selected_changes(child, to_add, to_rm)

    def upload_selected(self):
        to_add, to_rm = self.get_selected_changes()
        if not to_add and not to_rm:
            QMessageBox.warning(self, "Ошибка", "Нет выбранных изменений для загрузки")
            return

        commit_message = self.commit_input.text().strip()
        if not commit_message:
            commit_message = f"Обновление от {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

        branch = self.branch_input.text().strip() or "main"

        self.progress.show()
        self.progress.setRange(0, len(to_add) + len(to_rm))
        self.progress.setValue(0)
        self.upload_button.setEnabled(False)
        self.cancel_button.setEnabled(True)

        git_user_name = os.getenv("GIT_USER_NAME", "")
        git_user_email = os.getenv("GIT_USER_EMAIL", "")

        self.worker = GitWorker(
            self.root_dir, to_add, to_rm, commit_message,
            self.private_checkbox.isChecked(), branch,
            git_user_name, git_user_email
        )
        self.worker.log_signal.connect(self.log)
        self.worker.progress_signal.connect(self.progress.setValue)
        self.worker.finished_signal.connect(self.on_upload_finished)
        self.worker.start()

    def cancel_upload(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.log("Отмена операции...")
            self.cancel_button.setEnabled(False)

    def on_upload_finished(self, success: bool, message: str):
        self.progress.hide()
        self.upload_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if success:
            current_state = self.state_manager.compute_current_state(self.root_dir, self.pathspec)
            self.state_manager.save_state(current_state)
            self.log("Состояние последнего пуша сохранено.")
            QMessageBox.information(self, "Успех", message)
        else:
            QMessageBox.critical(self, "Ошибка", message)
        self.refresh_all()

    def refresh_all(self):
        self._save_all_check_states()
        self.expanded_paths.clear()
        root = self.tree.topLevelItem(0)
        if root:
            self._save_expanded_state(root)
        self.start_building_tree()
        self.log("Обновление статуса...")

    def _save_expanded_state(self, item: QTreeWidgetItem):
        path_str = item.data(0, Qt.UserRole)
        if path_str and item.isExpanded():
            self.expanded_paths.add(path_str)
        for i in range(item.childCount()):
            self._save_expanded_state(item.child(i))

    def _restore_expanded_state(self, item: QTreeWidgetItem):
        path_str = item.data(0, Qt.UserRole)
        if path_str and path_str in self.expanded_paths:
            item.setExpanded(True)
        for i in range(item.childCount()):
            self._restore_expanded_state(item.child(i))

# ============================================================
# MAIN
# ============================================================
def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    window = DeployGUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()