"""Installatie en de-installatie, herstelbaar.

* Kopieert de code naar <root>/app (hooks blijven werken als je de repo verplaatst).
* Installeert de persoonlijke skill naar ~/.claude/skills/memory-hub/.
* Voegt hooks toe aan ~/.claude/settings.json (Stop, SessionEnd, PreCompact; async).
* Registreert de MCP-server op gebruikersniveau (`claude mcp add --scope user`).
* Maakt een snelkoppeling/startopdracht en (optioneel) autostart van het achtergrondproces.

Vóór elke wijziging wordt een kopie van het bestaande configuratiebestand gemaakt in
<data>/config-backups/, en alles wordt vastgelegd in <data>/install-manifest.json.
`memory_hub.py uninstall` draait de wijzigingen terug; je archief blijft staan.
"""
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

from . import config

HOOK_EVENTS = ("Stop", "SessionEnd", "PreCompact")
MARK = "memory_hub.py"
SRC_ROOT = Path(__file__).resolve().parent.parent  # apps/memory-hub


def _settings_file():
    return config.claude_config_dir() / "settings.json"


def _claude_json():
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env) / ".claude.json" if env else Path.home() / ".claude.json"


def _skill_dir():
    return config.claude_config_dir() / "skills" / "memory-hub"


def _python():
    exe = Path(sys.executable)
    return exe.as_posix()


def _pythonw():
    exe = Path(sys.executable)
    if platform.system() == "Windows":
        w = exe.with_name("pythonw.exe")
        if w.exists():
            return w.as_posix()
    return exe.as_posix()


def _entry():
    return (config.app_dir() / "memory_hub.py").as_posix()


def hook_command():
    return f'"{_python()}" "{_entry()}" hook'


def _backup_file(p: Path):
    if not p.exists():
        return None
    d = config.data_dir() / "config-backups"
    d.mkdir(parents=True, exist_ok=True)
    target = d / f"{p.name}.{time.strftime('%Y%m%d-%H%M%S')}.bak"
    shutil.copy2(p, target)
    return str(target)


def _manifest():
    p = config.data_dir() / "install-manifest.json"
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            pass
    return {"history": []}


def _save_manifest(m):
    (config.data_dir() / "install-manifest.json").write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")


def _is_ours(h):
    return MARK in (h.get("command") or "") and " hook" in (h.get("command") or "")


# ---------------------------------------------------------------- onderdelen

def copy_app():
    dst = config.app_dir()
    if dst.resolve() == SRC_ROOT.resolve():
        return str(dst)
    dst.mkdir(parents=True, exist_ok=True)
    for name in ("memoryhub", "ui", "skill"):
        s = SRC_ROOT / name
        if (dst / name).exists():
            shutil.rmtree(dst / name)
        shutil.copytree(s, dst / name, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    for f in ("memory_hub.py", "README.md", "HANDLEIDING.md"):
        if (SRC_ROOT / f).exists():
            shutil.copy2(SRC_ROOT / f, dst / f)
    return str(dst)


def install_skill():
    d = _skill_dir()
    d.parent.mkdir(parents=True, exist_ok=True)
    if d.exists():
        shutil.rmtree(d)
    shutil.copytree(SRC_ROOT / "skill", d)
    # vul het echte pad naar de CLI in (fallback als MCP niet beschikbaar is)
    sk = d / "SKILL.md"
    sk.write_text(sk.read_text(encoding="utf-8").replace("{{MEMORY_HUB_CLI}}", f'"{_python()}" "{_entry()}"'), encoding="utf-8")
    return str(d)


def install_hooks():
    p = _settings_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    backup = _backup_file(p)
    data = {}
    if p.exists():
        txt = p.read_text(encoding="utf-8").strip()
        data = json.loads(txt) if txt else {}
    hooks = data.setdefault("hooks", {})
    cmd = hook_command()
    for ev in HOOK_EVENTS:
        groups = hooks.setdefault(ev, [])
        # oude Memory Hub-items verwijderen (bijv. ander pad), andere hooks ongemoeid laten
        for g in groups:
            g["hooks"] = [h for h in g.get("hooks", []) if not _is_ours(h)]
        groups[:] = [g for g in groups if g.get("hooks")]
        groups.append({"hooks": [{"type": "command", "command": cmd, "async": True, "timeout": 60}]})
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return {"file": str(p), "backup": backup}


def uninstall_hooks():
    p = _settings_file()
    if not p.exists():
        return None
    backup = _backup_file(p)
    data = json.loads(p.read_text(encoding="utf-8") or "{}")
    hooks = data.get("hooks") or {}
    for ev in list(hooks):
        for g in hooks[ev]:
            g["hooks"] = [h for h in g.get("hooks", []) if not _is_ours(h)]
        hooks[ev] = [g for g in hooks[ev] if g.get("hooks")]
        if not hooks[ev]:
            del hooks[ev]
    if not hooks and "hooks" in data:
        del data["hooks"]
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"file": str(p), "backup": backup}


def _claude_cli():
    return shutil.which("claude")


def register_mcp():
    backup = _backup_file(_claude_json())
    cli = _claude_cli()
    if cli:
        subprocess.run([cli, "mcp", "remove", "--scope", "user", "memory-hub"], capture_output=True, text=True, timeout=60)
        r = subprocess.run([cli, "mcp", "add", "--scope", "user", "memory-hub", "--", _python(), _entry(), "mcp"],
                           capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return {"method": "claude mcp add --scope user", "backup": backup}
    # terugval: ~/.claude.json zelf aanpassen
    p = _claude_json()
    data = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    data.setdefault("mcpServers", {})["memory-hub"] = {"type": "stdio", "command": _python(), "args": [_entry(), "mcp"], "env": {}}
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)
    return {"method": "~/.claude.json bewerkt", "backup": backup}


def unregister_mcp():
    cli = _claude_cli()
    if cli:
        subprocess.run([cli, "mcp", "remove", "--scope", "user", "memory-hub"], capture_output=True, text=True, timeout=60)
    p = _claude_json()
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        if "memory-hub" in (data.get("mcpServers") or {}):
            _backup_file(p)
            del data["mcpServers"]["memory-hub"]
            p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def create_launchers():
    made = []
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        bat = config.app_dir() / "Memory Hub.bat"
        bat.write_text(f'@echo off\r\nstart "" "{_pythonw()}" "{_entry()}" open\r\n', encoding="utf-8")
        made.append(str(bat))
        desktop = Path(os.environ.get("USERPROFILE", home)) / "Desktop"
        if desktop.exists():
            shutil.copy2(bat, desktop / "Memory Hub.bat")
            made.append(str(desktop / "Memory Hub.bat"))
        startmenu = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
        if startmenu.exists():
            shutil.copy2(bat, startmenu / "Memory Hub.bat")
            made.append(str(startmenu / "Memory Hub.bat"))
    elif system == "Darwin":
        apps = home / "Applications"
        apps.mkdir(exist_ok=True)
        cmd = apps / "Memory Hub.command"
        cmd.write_text(f'#!/bin/bash\n"{_python()}" "{_entry()}" open\n', encoding="utf-8")
        cmd.chmod(0o755)
        made.append(str(cmd))
    else:
        bindir = home / ".local" / "bin"
        bindir.mkdir(parents=True, exist_ok=True)
        sh = bindir / "memory-hub"
        sh.write_text(f'#!/bin/sh\nexec "{_python()}" "{_entry()}" "$@"\n', encoding="utf-8")
        sh.chmod(0o755)
        made.append(str(sh))
        appdir = home / ".local" / "share" / "applications"
        appdir.mkdir(parents=True, exist_ok=True)
        desk = appdir / "memory-hub.desktop"
        desk.write_text("[Desktop Entry]\nType=Application\nName=Memory Hub\nComment=Archief van je Claude-gesprekken\n"
                        f'Exec="{_python()}" "{_entry()}" open\nTerminal=false\nCategories=Utility;\n', encoding="utf-8")
        made.append(str(desk))
    return made


def _autostart_paths():
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "MemoryHub-achtergrond.vbs"
    if system == "Darwin":
        return home / "Library" / "LaunchAgents" / "nl.memoryhub.server.plist"
    return home / ".config" / "autostart" / "memory-hub.desktop"


def install_autostart():
    p = _autostart_paths()
    p.parent.mkdir(parents=True, exist_ok=True)
    system = platform.system()
    if system == "Windows":
        p.write_text(f'CreateObject("WScript.Shell").Run """{_pythonw()}"" ""{_entry()}"" serve --no-browser", 0, False\r\n', encoding="utf-8")
    elif system == "Darwin":
        p.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>nl.memoryhub.server</string>
<key>ProgramArguments</key><array><string>{_python()}</string><string>{_entry()}</string><string>serve</string><string>--no-browser</string></array>
<key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
<key>StandardErrorPath</key><string>{(config.logs_dir() / 'server.err.log').as_posix()}</string>
</dict></plist>
""", encoding="utf-8")
        subprocess.run(["launchctl", "load", "-w", str(p)], capture_output=True)
    else:
        p.write_text("[Desktop Entry]\nType=Application\nName=Memory Hub (achtergrond)\n"
                     f'Exec="{_python()}" "{_entry()}" serve --no-browser\nX-GNOME-Autostart-enabled=true\nNoDisplay=true\n', encoding="utf-8")
    return str(p)


def uninstall_autostart():
    p = _autostart_paths()
    if p.exists():
        if platform.system() == "Darwin":
            subprocess.run(["launchctl", "unload", "-w", str(p)], capture_output=True)
        p.unlink()
        return str(p)
    return None


def set_cleanup_period(days: int):
    """Optioneel: Claude Code transcripten langer laten bewaren (standaard 30 dagen)."""
    p = _settings_file()
    backup = _backup_file(p)
    data = json.loads(p.read_text(encoding="utf-8") or "{}") if p.exists() else {}
    old = data.get("cleanupPeriodDays")
    data["cleanupPeriodDays"] = int(days)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return {"old": old, "new": int(days), "backup": backup}


# ---------------------------------------------------------------- hoofdacties

def install(autostart=True, mcp=True, hooks=True, keep_transcripts_days=None):
    config.ensure_dirs()
    m = _manifest()
    step = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "action": "install", "python": _python()}
    step["app_dir"] = copy_app()
    step["skill"] = install_skill()
    if hooks:
        step["hooks"] = install_hooks()
    if mcp:
        step["mcp"] = register_mcp()
    step["launchers"] = create_launchers()
    if autostart:
        step["autostart"] = install_autostart()
    if keep_transcripts_days:
        step["cleanupPeriodDays"] = set_cleanup_period(keep_transcripts_days)
    m["history"].append(step)
    _save_manifest(m)
    return step


def uninstall(remove_skill=True):
    m = _manifest()
    step = {"at": time.strftime("%Y-%m-%d %H:%M:%S"), "action": "uninstall"}
    step["hooks"] = uninstall_hooks()
    unregister_mcp()
    step["autostart_removed"] = uninstall_autostart()
    if remove_skill and _skill_dir().exists():
        shutil.rmtree(_skill_dir())
        step["skill_removed"] = True
    m["history"].append(step)
    _save_manifest(m)
    step["note"] = f"Je archief blijft bewaard in {config.data_dir()}. Back-ups van configuratie: {config.data_dir() / 'config-backups'}"
    return step


def installation_state():
    hooks_ok = False
    p = _settings_file()
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8") or "{}")
            hooks_ok = any(_is_ours(h) for g in (data.get("hooks") or {}).get("Stop", []) for h in g.get("hooks", []))
        except ValueError:
            pass
    mcp_ok = False
    cj = _claude_json()
    if cj.exists():
        try:
            data = json.loads(cj.read_text(encoding="utf-8"))
            mcp_ok = "memory-hub" in (data.get("mcpServers") or {})
        except (ValueError, OSError):
            pass
    return {"hooks": hooks_ok, "mcp": mcp_ok, "skill": (_skill_dir() / "SKILL.md").exists(),
            "autostart": _autostart_paths().exists(), "settings_file": str(p), "claude_json": str(cj)}
