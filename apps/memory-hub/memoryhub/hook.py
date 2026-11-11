"""Ingang voor Claude Code-hooks (Stop, SessionEnd, PreCompact).

Leest de hook-JSON van stdin en importeert alleen het transcript van díe sessie
(incrementeel). Faalt nooit hard: fouten gaan naar het synclog en hook.log, en de
hook eindigt altijd met exitcode 0 zodat Claude Code nooit wordt gehinderd.
Stdout blijft leeg: niets uit het archief wordt in het gesprek teruggestopt (geen lus).
"""
import json
import os
import sys
import time
from pathlib import Path

from . import config, db, importer_cc
from .redact import redact


def _log(msg):
    try:
        p = config.logs_dir() / "hook.log"
        if p.exists() and p.stat().st_size > 1_000_000:
            p.replace(p.with_suffix(".log.1"))
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{db.now()} {redact(msg)}\n")
    except OSError:
        pass


def main():
    if os.environ.get("MEMORY_HUB_DISABLE_HOOK") == "1":
        return 0
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        data = {}
    path = data.get("transcript_path")
    event = data.get("hook_event_name", "hook")
    try:
        conn = db.connect()
        if not path:
            r = importer_cc.sync_all(conn, "hook")
            n = r["new_messages"]
        else:
            p = Path(path)
            r = importer_cc.import_file(conn, p, "hook")
            n = r["new_messages"]
            # Vertraagd weggeschreven berichten: kort wachten en nog één keer lezen
            time.sleep(1.5)
            r2 = importer_cc.import_file(conn, p, "hook")
            n += r2["new_messages"]
        with db.transaction(conn):
            if n or event == "SessionEnd":
                db.log_sync(conn, "claude_code", f"hook:{event}", True, f"sessie {data.get('session_id', '?')}", n,
                            1 if (isinstance(r, dict) and r.get("new_conversation")) else 0)
            db.set_meta(conn, "last_hook_run", db.now())
        conn.close()
    except Exception as e:  # noqa: BLE001
        _log(f"{event} fout: {e}")
        try:
            conn = db.connect()
            with db.transaction(conn):
                db.log_sync(conn, "claude_code", f"hook:{event}", False, redact(str(e)))
        except Exception:  # noqa: BLE001
            pass
    return 0
