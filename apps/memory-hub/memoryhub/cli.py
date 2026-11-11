"""Opdrachtregel voor Memory Hub."""
import argparse
import json
import subprocess
import sys
import time
import webbrowser
from pathlib import Path

from . import __version__, backup, config, db, importer_cc, importer_export, store, sync


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="memory_hub.py", description="Memory Hub — lokaal archief van je Claude-gesprekken")
    ap.add_argument("--version", action="version", version=__version__)
    sub = ap.add_subparsers(dest="cmd")

    sub.add_parser("open", help="Start de app (indien nodig) en open hem in je browser")
    sp = sub.add_parser("serve", help="Start de app-server + achtergrondsynchronisatie")
    sp.add_argument("--no-browser", action="store_true")
    sp.add_argument("--port", type=int)
    sub.add_parser("watch", help="Alleen achtergrondsynchronisatie (zonder app)")
    sub.add_parser("sync", help="Eén synchronisatieronde (Claude Code + importmap)")
    sub.add_parser("hook", help="(intern) aangeroepen door Claude Code-hooks")
    sub.add_parser("mcp", help="(intern) MCP-server via stdio")

    ip = sub.add_parser("import", help="Importeer een officiële Claude-export (.zip / map / conversations.json)")
    ip.add_argument("path")

    s = sub.add_parser("search", help="Zoek in het archief")
    s.add_argument("query")
    s.add_argument("--limit", type=int, default=10)

    sub.add_parser("status", help="Toon synchronisatiestatus")

    b = sub.add_parser("backup", help="Maak een back-up")
    b.add_argument("--list", action="store_true")
    r = sub.add_parser("restore", help="Herstel een back-up")
    r.add_argument("name")
    r.add_argument("--keep-deleted", action="store_true", help="Pas eerdere verwijderingen niet opnieuw toe")

    e = sub.add_parser("export", help="Exporteer alles naar JSON of Markdown")
    e.add_argument("--format", choices=["json", "markdown"], default="json")
    e.add_argument("--redact", action="store_true", help="Geheimen maskeren in de export")

    d = sub.add_parser("delete", help="Verwijder een gesprek (incl. zoekindex en afgeleide geheugenitems)")
    d.add_argument("conversation_id", type=int)
    d.add_argument("--purge-backups", action="store_true")
    d.add_argument("--allow-reimport", action="store_true")

    p = sub.add_parser("pause", help="Pauzeer archivering")
    p.add_argument("state", choices=["aan", "uit", "on", "off"])

    i = sub.add_parser("install", help="Installeer skill, hooks, MCP, snelkoppeling en autostart")
    i.add_argument("--no-autostart", action="store_true")
    i.add_argument("--no-mcp", action="store_true")
    i.add_argument("--no-hooks", action="store_true")
    i.add_argument("--keep-transcripts-days", type=int, help="Zet Claude Code cleanupPeriodDays (standaard 30) hoger")
    i.add_argument("--no-initial-sync", action="store_true")
    sub.add_parser("uninstall", help="Draai configuratiewijzigingen terug (archief blijft bewaard)")

    t = sub.add_parser("seed-test", help="Voeg duidelijk gemarkeerde testgesprekken toe")

    a = ap.parse_args(argv)
    cmd = a.cmd or "open"

    if cmd == "hook":
        from .hook import main as hook_main
        return hook_main()
    if cmd == "mcp":
        from .mcp_server import serve
        serve()
        return 0
    if cmd == "serve":
        from .web import serve
        serve(open_browser=not a.no_browser, port=a.port)
        return 0
    if cmd == "open":
        from . import web
        if not web.is_running():
            kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
            if sys.platform == "win32":
                kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
            else:
                kwargs["start_new_session"] = True
            subprocess.Popen([sys.executable, str(Path(__file__).resolve().parent.parent / "memory_hub.py"), "serve", "--no-browser"], **kwargs)
            for _ in range(40):
                time.sleep(0.25)
                if web.is_running():
                    break
        print(f"Memory Hub: {web.url()}")
        webbrowser.open(web.url())
        return 0
    if cmd == "watch":
        ev = sync.start_background("watcher")
        print(f"Achtergrondsynchronisatie actief (gegevens: {config.data_dir()}). Ctrl+C om te stoppen.")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            ev.set()
        return 0

    conn = db.connect()
    if cmd == "sync":
        _print(sync.run_once(conn, "handmatig"))
    elif cmd == "import":
        _print(importer_export.import_path(conn, a.path, "handmatig"))
    elif cmd == "search":
        for h in store.search_messages(conn, a.query, limit=a.limit):
            snip = h["snippet"].replace(store.HL_START, "[").replace(store.HL_END, "]")
            print(f"#{h['conversation_id']}/{h['message_id']}  {h['created_at'] or ''}  {h['role']:9}  {h['title']}\n    {snip}\n")
    elif cmd == "status":
        _print(store.sync_status(conn))
    elif cmd == "backup":
        if a.list:
            _print(backup.list_backups())
        else:
            print(backup.create_backup(conn, "handmatig"))
    elif cmd == "restore":
        _print(backup.restore_backup(conn, a.name, reapply_deletions=not a.keep_deleted))
    elif cmd == "export":
        print(store.export_all(conn, a.format, a.redact))
    elif cmd == "delete":
        _print(store.delete_conversation(conn, a.conversation_id, prevent_reimport=not a.allow_reimport, purge_backups=a.purge_backups))
    elif cmd == "pause":
        on = a.state in ("aan", "on")
        if not on and config.load_settings().get("paused"):
            importer_cc.skip_ahead_all(conn)
        config.save_settings({"paused": on, "paused_since": db.now() if on else None})
        print("Archivering gepauzeerd" if on else "Archivering hervat")
    elif cmd == "install":
        from .install import install
        res = install(autostart=not a.no_autostart, mcp=not a.no_mcp, hooks=not a.no_hooks,
                      keep_transcripts_days=a.keep_transcripts_days)
        _print(res)
        if not a.no_initial_sync:
            print("Bestaande Claude Code-gesprekken importeren…")
            _print(sync.run_once(conn, "installatie"))
        if not a.no_autostart:
            from . import web
            if not web.is_running():
                kwargs = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
                if sys.platform == "win32":
                    kwargs["creationflags"] = 0x00000008 | 0x00000200
                else:
                    kwargs["start_new_session"] = True
                subprocess.Popen([sys.executable, str(config.app_dir() / "memory_hub.py"), "serve", "--no-browser"], **kwargs)
        print(f"\nKlaar. Open de app met:  \"{sys.executable}\" \"{config.app_dir() / 'memory_hub.py'}\" open")
        print("Start daarna een NIEUWE Claude Code-sessie zodat hooks, skill en MCP-server geladen worden.")
    elif cmd == "uninstall":
        from .install import uninstall
        _print(uninstall())
    elif cmd == "seed-test":
        from .testdata import seed
        _print(seed(conn))
    return 0
