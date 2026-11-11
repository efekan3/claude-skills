"""Eén synchronisatieronde en de achtergrondlus (gebruikt door de app-server en 'watch')."""
import threading
import time
import traceback

from . import backup, config, db, importer_cc, importer_export
from .redact import redact

_run_lock = threading.Lock()


def run_once(conn, trigger="watcher") -> dict:
    with _run_lock:
        s = config.load_settings()
        out = {"claude_code": None, "exports": [], "backup": None, "paused": bool(s.get("paused"))}
        try:
            r = importer_cc.sync_all(conn, trigger)
            out["claude_code"] = r
            if r["new_messages"] or r["errors"] or trigger != "watcher":
                with db.transaction(conn):
                    db.log_sync(conn, "claude_code", trigger, not r["errors"],
                                redact("; ".join(r["errors"])[:1500]) if r["errors"] else ("gepauzeerd" if s.get("paused") else "ok"),
                                r["new_messages"], r["new_conversations"])
            else:
                with db.transaction(conn):
                    db.set_meta(conn, "last_cc_check", db.now())
                    if not conn.execute("SELECT 1 FROM sync_log WHERE source='claude_code' AND ok=1 LIMIT 1").fetchone():
                        db.log_sync(conn, "claude_code", trigger, True, "ok (geen nieuwe berichten)")
        except Exception as e:  # noqa: BLE001
            with db.transaction(conn):
                db.log_sync(conn, "claude_code", trigger, False, redact(f"{e}\n{traceback.format_exc()[-800:]}"))
        if not s.get("paused"):
            try:
                out["exports"] = importer_export.scan_import_folder(conn)
            except Exception as e:  # noqa: BLE001
                out["exports"] = [{"ok": False, "error": str(e)}]
        try:
            b = backup.auto_backup_if_due(conn)
            out["backup"] = b.name if b else None
        except Exception as e:  # noqa: BLE001
            with db.transaction(conn):
                db.log_sync(conn, "systeem", "auto-backup", False, str(e))
        with db.transaction(conn):
            db.set_meta(conn, "watcher_heartbeat", time.time())
        return out


def loop(stop_event: threading.Event, trigger="watcher"):
    conn = db.connect()
    while not stop_event.is_set():
        try:
            run_once(conn, trigger)
        except Exception:  # noqa: BLE001
            pass
        interval = max(5, int(config.load_settings().get("watch_interval_seconds", 30)))
        stop_event.wait(interval)


def start_background(trigger="watcher") -> threading.Event:
    ev = threading.Event()
    threading.Thread(target=loop, args=(ev, trigger), daemon=True, name="memoryhub-sync").start()
    return ev
