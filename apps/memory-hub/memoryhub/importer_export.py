"""Import van de officiële Claude-gegevensexport (claude.ai → Instellingen → Privacy → Gegevens exporteren).

De export is een .zip met o.a. conversations.json (en vaak projects.json, users.json,
memories.json). Web, desktop en mobiel delen hetzelfde account, dus deze export bevat
gesprekken uit alle drie. Er is geen officiële API om claude.ai-gesprekken rechtstreeks
te synchroniseren; daarom werkt deze bron via (herhaalde) handmatige export.

Een volgende import herkent nieuwe gesprekken, nieuwe berichten en bijgewerkte gesprekken.
"""
import hashlib
import json
import shutil
import time
import zipfile
from pathlib import Path

from . import config, db

SOURCE = "claude_ai_export"
CHAT_URL = "https://claude.ai/chat/{}"


def _load_bundle(path: Path) -> dict:
    """Geeft {'conversations': [...], 'projects': [...], 'memories': ...} terug."""
    path = Path(path)
    out = {"conversations": None, "projects": [], "memories": None}

    def take(name, data):
        low = name.lower().split("/")[-1]
        try:
            obj = json.loads(data)
        except ValueError:
            return
        if low == "conversations.json":
            out["conversations"] = obj
        elif low == "projects.json":
            out["projects"] = obj
        elif low == "memories.json":
            out["memories"] = obj

    if path.is_dir():
        for p in path.rglob("*.json"):
            take(p.name, p.read_bytes())
    elif zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            for n in z.namelist():
                if n.lower().endswith(".json") and not n.startswith("__MACOSX"):
                    take(n, z.read(n))
    else:
        data = path.read_bytes()
        try:
            obj = json.loads(data)
        except ValueError as e:
            raise ValueError("Geen geldig JSON-bestand of zip-archief") from e
        if isinstance(obj, list):
            out["conversations"] = obj
        elif isinstance(obj, dict) and "conversations" in obj:
            out["conversations"] = obj["conversations"]
    if out["conversations"] is None:
        raise ValueError("conversations.json niet gevonden. Gebruik de .zip uit de officiële Claude-export.")
    return out


def _message_text(m):
    parts, tools = [], []
    for b in m.get("content") or []:
        t = b.get("type")
        if t == "text" and b.get("text"):
            parts.append(b["text"])
        elif t == "tool_use":
            tools.append(b.get("name", "tool"))
    text = "\n\n".join(parts).strip()
    if not text and isinstance(m.get("text"), str):
        text = m["text"].strip()
    return text, tools


def import_path(conn, path, trigger="handmatig") -> dict:
    bundle = _load_bundle(Path(path))
    res = {"new_conversations": 0, "updated_conversations": 0, "unchanged": 0, "new_messages": 0,
           "excluded": 0, "projects": 0, "memories": 0}
    proj_by_uuid = {}
    with db.transaction(conn):
        for p in bundle["projects"] or []:
            if isinstance(p, dict) and p.get("uuid"):
                pid = db.get_or_create_project(conn, SOURCE, p["uuid"], p.get("name") or "claude.ai-project")
                if p.get("description"):
                    conn.execute("UPDATE projects SET description=? WHERE id=? AND (description IS NULL OR description='')",
                                 (p["description"], pid))
                proj_by_uuid[p["uuid"]] = pid
                res["projects"] += 1

        for c in bundle["conversations"]:
            if not isinstance(c, dict) or not c.get("uuid"):
                continue
            ext = c["uuid"]
            if conn.execute("SELECT 1 FROM exclusions WHERE source=? AND ext_id=?", (SOURCE, ext)).fetchone():
                res["excluded"] += 1
                continue
            msgs = c.get("chat_messages") or []
            title = (c.get("name") or "").strip() or None
            if not title:
                first = next((_message_text(m)[0] for m in msgs if m.get("sender") == "human"), "")
                title = (first.splitlines()[0][:80] if first else "Naamloos gesprek")
            proj = c.get("project") if isinstance(c.get("project"), dict) else {}
            proj_uuid = c.get("project_uuid") or proj.get("uuid")
            project_id = proj_by_uuid.get(proj_uuid) if proj_uuid else None
            if proj_uuid and not project_id:
                project_id = db.get_or_create_project(conn, SOURCE, proj_uuid, proj.get("name"))
            row = conn.execute("SELECT * FROM conversations WHERE source=? AND ext_id=?", (SOURCE, ext)).fetchone()
            missing = []
            if not msgs:
                missing.append("De export bevat geen berichten voor dit gesprek.")
            if row:
                conv_id = row["id"]
                if row["source_updated_at"] == c.get("updated_at") and row["message_count"] >= len(msgs):
                    res["unchanged"] += 1
                    continue
                conn.execute("UPDATE conversations SET title=?, updated_at=?, source_updated_at=?, project_id=COALESCE(?,project_id) WHERE id=?",
                             (title, c.get("updated_at"), c.get("updated_at"), project_id, conv_id))
                is_new = False
            else:
                cur = conn.execute(
                    "INSERT INTO conversations(source,ext_id,title,project_id,created_at,updated_at,imported_at,source_updated_at,url,summary,summary_kind)"
                    " VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (SOURCE, ext, title, project_id, c.get("created_at"), c.get("updated_at"), db.now(), c.get("updated_at"),
                     CHAT_URL.format(ext), c.get("summary") or "", "claude.ai" if c.get("summary") else ""),
                )
                conv_id = cur.lastrowid
                is_new = True

            seq = conn.execute("SELECT COALESCE(MAX(seq),0) FROM messages WHERE conversation_id=?", (conv_id,)).fetchone()[0]
            added = 0
            for m in msgs:
                mid_ext = m.get("uuid")
                if not mid_ext:
                    continue
                parent = m.get("parent_message_uuid")
                conn.execute("INSERT OR IGNORE INTO cc_nodes(conversation_id,uuid,parent_uuid,ts) VALUES(?,?,?,?)",
                             (conv_id, mid_ext, parent, m.get("created_at")))
                text, tools = _message_text(m)
                role = "user" if m.get("sender") == "human" else "assistant"
                existing = conn.execute("SELECT id, content FROM messages WHERE conversation_id=? AND ext_id=?",
                                        (conv_id, mid_ext)).fetchone()
                meta = ""
                if not text:
                    text = "[Geen tekstinhoud in de export voor dit bericht]"
                    meta = db.dumps({"missing": True})
                if existing:
                    if existing["content"] != text and not meta:
                        conn.execute("UPDATE messages SET content=?, meta=? WHERE id=?",
                                     (text, db.dumps({"bijgewerkt_bij_import": db.now()}), existing["id"]))
                    continue
                seq += 1
                cur = conn.execute(
                    "INSERT INTO messages(conversation_id,ext_id,parent_ext_id,seq,role,content,created_at,tools,meta)"
                    " VALUES(?,?,?,?,?,?,?,?,?)",
                    (conv_id, mid_ext, parent, seq, role, text, m.get("created_at"), ",".join(tools), meta),
                )
                msg_id = cur.lastrowid
                added += 1
                for a in m.get("attachments") or []:
                    content = a.get("extracted_content")
                    conn.execute(
                        "INSERT INTO attachments(message_id,file_name,file_type,file_size,extracted_text,available) VALUES(?,?,?,?,?,?)",
                        (msg_id, a.get("file_name"), a.get("file_type"), a.get("file_size"), content, 1 if content else 0),
                    )
                for f in m.get("files") or m.get("files_v2") or []:
                    conn.execute(
                        "INSERT INTO attachments(message_id,file_name,file_type,available) VALUES(?,?,?,0)",
                        (msg_id, f.get("file_name") or f.get("file_uuid") or "bestand", f.get("file_kind") or "bestand"),
                    )
                    if "Bestanden (afbeeldingen/pdf's) zitten niet in de export; alleen de bestandsnaam is bekend." not in missing:
                        missing.append("Bestanden (afbeeldingen/pdf's) zitten niet in de export; alleen de bestandsnaam is bekend.")
            from .importer_cc import _recompute_branches
            _recompute_branches(conn, conv_id)
            n = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conv_id,)).fetchone()[0]
            conn.execute("UPDATE conversations SET message_count=?, missing_info=? WHERE id=?", (n, db.dumps(missing), conv_id))
            res["new_messages"] += added
            if is_new:
                res["new_conversations"] += 1
            elif added:
                res["updated_conversations"] += 1
            else:
                res["unchanged"] += 1

        res["memories"] = _import_claude_memories(conn, bundle.get("memories"))
        db.log_sync(conn, SOURCE, trigger, True, f"Import uit {Path(path).name}", res["new_messages"],
                    res["new_conversations"], res["updated_conversations"])
        db.set_meta(conn, "last_export_import", db.now())
    return res


def _import_claude_memories(conn, mem):
    """memories.json (claude.ai-geheugen) als 'afgeleid' geheugenitem opslaan — niet als jouw uitspraak."""
    if not mem:
        return 0
    items = []
    if isinstance(mem, list):
        for m in mem:
            if isinstance(m, dict):
                if m.get("conversations_memory"):
                    items.append(m["conversations_memory"])
                for v in (m.get("project_memories") or {}).values():
                    if isinstance(v, str):
                        items.append(v)
    elif isinstance(mem, dict) and mem.get("conversations_memory"):
        items.append(mem["conversations_memory"])
    n = 0
    for text in items:
        text = text.strip()
        if not text or conn.execute("SELECT 1 FROM memories WHERE text=?", (text,)).fetchone():
            continue
        conn.execute(
            "INSERT INTO memories(kind,text,origin,status,source_label,source_date,created_by,created_at,updated_at)"
            " VALUES('feit',?,'inferred','actief','claude.ai-geheugen (uit officiële export)',?,'import',?,?)",
            (text, db.now(), db.now(), db.now()),
        )
        n += 1
    return n


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def scan_import_folder(conn, trigger="importmap") -> list:
    """Verwerk nieuwe exports in de importmap; verplaats ze daarna naar 'verwerkt/'."""
    folder = config.import_dir()
    done = folder / "verwerkt"
    done.mkdir(exist_ok=True)
    results = []
    for p in sorted(folder.iterdir()):
        if p.name in ("verwerkt", "mislukt") or p.name.startswith("."):
            continue
        if not (p.suffix.lower() in (".zip", ".json") or p.is_dir()):
            continue
        # wacht tot het bestand niet meer groeit (nog aan het kopiëren)
        try:
            s1 = p.stat().st_size
            time.sleep(0.5)
            if p.stat().st_size != s1:
                continue
        except OSError:
            continue
        try:
            r = import_path(conn, p, trigger)
            target = done / f"{time.strftime('%Y%m%d-%H%M%S')}-{p.name}"
            shutil.move(str(p), str(target))
            results.append({"file": p.name, "ok": True, **r})
        except Exception as e:  # noqa: BLE001
            bad = folder / "mislukt"
            bad.mkdir(exist_ok=True)
            shutil.move(str(p), str(bad / p.name))
            with db.transaction(conn):
                db.log_sync(conn, SOURCE, trigger, False, f"{p.name}: {e}")
            results.append({"file": p.name, "ok": False, "error": str(e)})
    return results


def import_upload(conn, filename: str, data: bytes) -> dict:
    """Upload vanuit de app: eerst in de importmap bewaren (origineel blijft bewaard)."""
    safe = "".join(ch for ch in Path(filename).name if ch.isalnum() or ch in "._- ") or "export.zip"
    target = config.import_dir() / "verwerkt" / f"{time.strftime('%Y%m%d-%H%M%S')}-upload-{safe}"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    try:
        return import_path(conn, target, "upload")
    except Exception as e:
        with db.transaction(conn):
            db.log_sync(conn, SOURCE, "upload", False, f"{safe}: {e}")
        raise

