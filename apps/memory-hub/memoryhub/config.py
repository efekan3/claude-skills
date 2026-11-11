"""Paden en instellingen. Alle gegevens staan buiten de broncode-repository."""
import json
import os
import platform
import sys
import threading
from pathlib import Path

APP_NAME = "MemoryHub"


def root_dir() -> Path:
    """Vaste gebruikersmap. Te overschrijven met MEMORY_HUB_HOME."""
    env = os.environ.get("MEMORY_HUB_HOME")
    if env:
        return Path(env).expanduser()
    system = platform.system()
    if system == "Windows":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / APP_NAME
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "memory-hub"


def data_dir() -> Path:
    return root_dir() / "data"


def app_dir() -> Path:
    """Geïnstalleerde kopie van de code (zodat hooks niet afhangen van de repo-map)."""
    return root_dir() / "app"


def db_path() -> Path:
    return data_dir() / "memoryhub.db"


def backups_dir() -> Path:
    return data_dir() / "backups"


def import_dir() -> Path:
    return data_dir() / "import"


def exports_dir() -> Path:
    return data_dir() / "exports"


def attachments_dir() -> Path:
    return data_dir() / "attachments"


def logs_dir() -> Path:
    return data_dir() / "logs"


def settings_path() -> Path:
    return data_dir() / "settings.json"


def tombstones_path() -> Path:
    return data_dir() / "tombstones.json"


def claude_config_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


DEFAULTS = {
    "paused": False,
    "paused_since": None,
    "claude_projects_dirs": [],          # leeg = <claude_config_dir>/projects
    "exclude_project_patterns": [],      # bv. ["*geheim*", "/home/ik/prive"]
    "include_subagents": False,
    "watch_interval_seconds": 30,
    "auto_backup_hours": 24,
    "keep_backups": 14,
    "redact_secrets_in_views": True,
    "host": "127.0.0.1",
    "port": 8765,
    "allow_remote": False,
    "remote_token": "",
    "theme": "auto",
    "optional_ai_enabled": False,        # niet gebouwd: er gaat niets naar externe diensten
}

_lock = threading.Lock()


def ensure_dirs() -> None:
    for d in (root_dir(), data_dir(), backups_dir(), import_dir(), exports_dir(), attachments_dir(), logs_dir()):
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform != "win32":
            try:
                os.chmod(d, 0o700)
            except OSError:
                pass


def load_settings() -> dict:
    ensure_dirs()
    s = dict(DEFAULTS)
    p = settings_path()
    if p.exists():
        try:
            s.update(json.loads(p.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
    return s


def save_settings(updates: dict) -> dict:
    with _lock:
        s = load_settings()
        for k, v in updates.items():
            if k in DEFAULTS:
                s[k] = v
        tmp = settings_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, settings_path())
        return s


def projects_dirs() -> list:
    s = load_settings()
    dirs = [Path(d).expanduser() for d in s.get("claude_projects_dirs") or []]
    return dirs or [claude_config_dir() / "projects"]
