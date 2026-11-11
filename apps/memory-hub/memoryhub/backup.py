"""Back-ups (SQLite backup-API), herstel en het opschonen van verwijderde gesprekken uit back-ups.

Back-upbeleid bij verwijderen:
* Een verwijderd gesprek blijft standaard in OUDERE back-ups staan tot die worden
  geroteerd (standaard 14 back-ups). Je kunt bij verwijderen kiezen om het ook
  direct uit alle back-ups te wissen.
* Elke verwijdering wordt als 'grafsteen' (alleen bron + ID, geen inhoud) vastgelegd in
  tombstones.json. Bij herstel van een back-up worden die verwijderingen standaard
  opnieuw toegepast, zodat herstel verwijderde gesprekken niet ongemerkt terugbrengt.
"""
import sqlite3
import time
from pathlib import Path

from . import config, db


def create_backup(conn, reason="handmatig") -> Path:
    config.ensure_dirs()
    safe = "".join(ch for ch in reason if ch.isalnum() or ch in "-_") or "backup"
    target = config.backups_dir() / f"memoryhub-{time.strftime('%Y%m%d-%H%M%S')}-{safe}.db"
    n = 1
    while target.exists():
        target = target.with_name(target.stem + f"-{n}.db"); n += 1
    dst = sqlite3.connect(str(target))
    try:
        conn.backup(dst)
    finally:
        dst.close()
    with db.transaction(conn):
        db.set_meta(conn, "last_backup", db.now())
    rotate()
    return target


def list_backups():
    config.ensure_dirs()
    out = []
    for p in sorted(config.backups_dir().glob("memoryhub-*.db"), reverse=True):
        st = p.stat()
        info = {"name": p.name, "size": st.st_size, "created": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}
        try:
            c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            info["conversations"] = c.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
            info["messages"] = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
            c.close()
        except sqlite3.Error:
            info["conversations"] = None
        out.append(info)
    return out


def rotate():
    keep = int(config.load_settings().get("keep_backups", 14))
    files = sorted(config.backups_dir().glob("memoryhub-*.db"), reverse=True)
    for p in files[keep:]:
        try:
            p.unlink()
        except OSError:
            pass


def _resolve(name) -> Path:
    p = (config.backups_dir() / Path(name).name).resolve()
    if p.parent != config.backups_dir().resolve() or not p.exists():
        raise ValueError("Back-up niet gevonden")
    return p


def restore_backup(conn, name, reapply_deletions=True) -> dict:
    src_path = _resolve(name)
    # controleer eerst of de back-up leesbaar is
    src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
    try:
        if src.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("Back-up is beschadigd (integrity_check mislukt)")
        safety = create_backup(conn, "voor-herstel")
        src.backup(conn)
    finally:
        src.close()
    db.init(conn)
    reapplied = 0
    if reapply_deletions:
        from .store import read_tombstones
        with db.transaction(conn):
            for t in read_tombstones():
                row = conn.execute("SELECT id FROM conversations WHERE source=? AND ext_id=?", (t["source"], t["ext_id"])).fetchone()
                if row:
                    conn.execute("DELETE FROM memories WHERE source_conversation_id=?", (row[0],))
                    conn.execute("DELETE FROM conversations WHERE id=?", (row[0],))
                    reapplied += 1
                conn.execute("INSERT OR IGNORE INTO exclusions(source,ext_id,reason,at) VALUES(?,?,?,?)",
                             (t["source"], t["ext_id"], "verwijderd door gebruiker", t.get("deleted_at")))
    with db.transaction(conn):
        conn.execute("INSERT INTO messages_fts(messages_fts) VALUES('rebuild')")
        conn.execute("INSERT INTO memories_fts(memories_fts) VALUES('rebuild')")
        db.log_sync(conn, "systeem", "herstel", True, f"Hersteld uit {src_path.name}; {reapplied} verwijderingen opnieuw toegepast")
    return {"restored_from": src_path.name, "safety_backup": safety.name, "deletions_reapplied": reapplied}


def purge_from_backups(pairs) -> int:
    """Wis gesprekken (source, ext_id) ook uit alle bestaande back-ups."""
    changed = 0
    for p in config.backups_dir().glob("memoryhub-*.db"):
        try:
            c = sqlite3.connect(str(p))
            c.execute("PRAGMA foreign_keys=ON")
            hit = False
            for source, ext in pairs:
                row = c.execute("SELECT id FROM conversations WHERE source=? AND ext_id=?", (source, ext)).fetchone()
                if row:
                    c.execute("DELETE FROM memories WHERE source_conversation_id=?", (row[0],))
                    c.execute("DELETE FROM conversations WHERE id=?", (row[0],))
                    hit = True
            if hit:
                c.commit()
                c.execute("VACUUM")
                changed += 1
            c.close()
        except sqlite3.Error:
            continue
    return changed


def delete_backup(name):
    _resolve(name).unlink()


def auto_backup_if_due(conn):
    hours = float(config.load_settings().get("auto_backup_hours", 24) or 0)
    if hours <= 0:
        return None
    last = db.get_meta(conn, "last_backup")
    if last:
        try:
            t = time.mktime(time.strptime(last[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
            if time.time() - t < hours * 3600:
                return None
        except ValueError:
            pass
    if not conn.execute("SELECT 1 FROM conversations LIMIT 1").fetchone():
        return None
    return create_backup(conn, "auto")
