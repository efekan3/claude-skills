"""Incrementele import van lokale Claude Code-sessietranscripten (~/.claude/projects/*/*.jsonl).

Ontwerp:
* Per bestand wordt de byte-offset van de laatste volledig gelezen regel bewaard. Een
  half weggeschreven laatste regel wordt bij de volgende ronde opnieuw gelezen.
* Elk record heeft een uuid; berichten zijn uniek per (gesprek, uuid). Opnieuw importeren
  maakt dus nooit duplicaten.
* Een hervat/geforkt gesprek dat oude berichten kopieert naar een nieuw bestand: berichten
  waarvan de uuid al in een ander Claude Code-gesprek staat, worden niet nog eens opgeslagen.
* Vertakkingen (terugspoelen/bewerken): alle records worden als boom bijgehouden; berichten
  op een verlaten tak krijgen on_main_branch=0 en blijven bewaard.
* Alleen zichtbare tekst wordt bewaard: jouw berichten en Claudes tekstantwoorden.
  Denkstappen, toolresultaten en systeemcontext niet (toolnamen alleen als metadata).
"""
import base64
import fnmatch
import json
import os
import re
from pathlib import Path

from . import config, db

SOURCE = "claude_code"
CONTEXT_PACK_MARKER = "[memory-hub:contextpakket]"
OPT_OUT_MARKERS = ("[geen-archief]", "#nietarchiveren", "[no-archive]")

_SYS_REMINDER = re.compile(r"<system-reminder>[\s\S]*?</system-reminder>", re.I)
_CMD_NAME = re.compile(r"<command-name>([\s\S]*?)</command-name>")
_CMD_ARGS = re.compile(r"<command-args>([\s\S]*?)</command-args>")
_LOCAL_STDOUT = re.compile(r"<local-command-(?:stdout|stderr)>[\s\S]*?</local-command-(?:stdout|stderr)>")


def _clean_user_text(text: str) -> str:
    text = _SYS_REMINDER.sub("", text)
    if "<command-name>" in text:
        name = _CMD_NAME.search(text)
        args = _CMD_ARGS.search(text)
        return ("Opdracht: " + (name.group(1).strip() if name else "") + " " + (args.group(1).strip() if args else "")).strip()
    text = _LOCAL_STDOUT.sub("", text)
    return text.strip()


def discover_files(include_subagents=False):
    files = []
    for base in config.projects_dirs():
        if not base.exists():
            continue
        for proj in base.iterdir():
            if not proj.is_dir():
                continue
            files.extend(sorted(proj.glob("*.jsonl")))
            if include_subagents:
                files.extend(sorted(proj.glob("*/subagents/*.jsonl")))
    return files


def _excluded_project(cwd: str, patterns) -> bool:
    if not cwd:
        return False
    norm = cwd.replace("\\", "/")
    for p in patterns or []:
        p2 = p.replace("\\", "/")
        if fnmatch.fnmatch(norm, p2) or norm.startswith(p2.rstrip("/") + "/") or norm == p2.rstrip("/"):
            return True
    return False


def _save_image(conv_ext, uuid, idx, block):
    src = block.get("source") or {}
    if src.get("type") != "base64" or not src.get("data"):
        return None, 0
    ext = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif", "image/webp": ".webp"}.get(src.get("media_type"), ".bin")
    d = config.attachments_dir() / SOURCE / conv_ext
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{uuid}-{idx}{ext}"
    raw = base64.b64decode(src["data"])
    if not p.exists():
        p.write_bytes(raw)
    return str(p), len(raw)


def import_file(conn, path: Path, trigger="watcher", force=False) -> dict:
    """Importeer nieuwe regels uit één transcriptbestand. Idempotent."""
    path = Path(path)
    settings = config.load_settings()
    res = {"file": str(path), "new_messages": 0, "new_conversation": False, "skipped": None}
    try:
        st = path.stat()
    except FileNotFoundError:
        res["skipped"] = "bestand bestaat niet (meer)"
        return res
    key = str(path)
    row = conn.execute("SELECT * FROM source_files WHERE path=?", (key,)).fetchone()
    offset = row["offset"] if row else 0
    if row and not force and row["size"] == st.st_size and abs((row["mtime"] or 0) - st.st_mtime) < 1e-6:
        res["skipped"] = "ongewijzigd"
        return res
    if st.st_size < offset or force:
        offset = 0  # bestand is ingekort/herschreven: opnieuw lezen, dedupe voorkomt duplicaten

    session_ext = path.stem
    is_subagent = path.parent.name == "subagents"
    if is_subagent:
        session_ext = path.parent.parent.name + "/" + path.stem

    excluded = conn.execute("SELECT 1 FROM exclusions WHERE source=? AND ext_id=?", (SOURCE, session_ext)).fetchone()

    with open(path, "rb") as fh:
        fh.seek(offset)
        chunk = fh.read()
    # Alleen volledige regels verwerken (laatste regel kan nog worden weggeschreven)
    last_nl = chunk.rfind(b"\n")
    if last_nl == -1:
        complete, consumed = b"", 0
    else:
        complete, consumed = chunk[: last_nl + 1], last_nl + 1
    new_offset = offset + consumed

    if settings.get("paused") or excluded:
        # Pauze/uitgesloten: niets opslaan, wel positie bijwerken zodat dit niet later alsnog binnenkomt
        with db.transaction(conn):
            _upsert_source(conn, key, st, new_offset, session_ext, None)
        res["skipped"] = "gepauzeerd" if settings.get("paused") else "uitgesloten"
        return res

    records = []
    for line in complete.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except ValueError:
            continue  # beschadigde regel overslaan

    with db.transaction(conn):
        conv = conn.execute("SELECT * FROM conversations WHERE source=? AND ext_id=?", (SOURCE, session_ext)).fetchone()
        conv_id = conv["id"] if conv else None
        meta = {"cwd": None, "branch": None, "title": None, "first_ts": None, "last_ts": None, "first_user": None}
        pending = []  # (record, role, text, tools, images)
        opt_out = False

        for r in records:
            ts = r.get("timestamp")
            if ts:
                meta["first_ts"] = meta["first_ts"] or ts
                meta["last_ts"] = ts
            if r.get("cwd") and not meta["cwd"]:
                meta["cwd"] = r["cwd"]  # eerste werkmap = project van de sessie
            if r.get("gitBranch"):
                meta["branch"] = r["gitBranch"]
            t = r.get("type")
            if t in ("summary",) and r.get("summary"):
                meta["title"] = r["summary"]
            for k in ("customTitle", "aiTitle", "title"):
                if t and "title" in t and isinstance(r.get(k), str) and r.get(k):
                    meta["title"] = r[k]
            if r.get("isSidechain") and not is_subagent:
                continue
            msg = r.get("message")
            if t not in ("user", "assistant") or not isinstance(msg, dict):
                if r.get("uuid"):
                    pending.append((r, None, None, None, None))
                continue
            content = msg.get("content")
            role, text, tools, images = None, "", [], []
            if t == "user":
                if r.get("isMeta") or "toolUseResult" in r:
                    pending.append((r, None, None, None, None))
                    continue
                parts = []
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for b in content:
                        if b.get("type") == "text":
                            parts.append(b.get("text", ""))
                        elif b.get("type") == "image":
                            images.append(b)
                        elif b.get("type") == "tool_result":
                            parts = None
                            break
                if parts is None:
                    pending.append((r, None, None, None, None))
                    continue
                text = _clean_user_text("\n".join(parts))
                origin = r.get("origin") if isinstance(r.get("origin"), dict) else {}
                if r.get("isCompactSummary"):
                    role = "system"
                    text = "[Samenvatting door Claude Code bij compacteren]\n" + text
                elif origin.get("kind") and origin.get("kind") != "human":
                    role = "system"
                else:
                    role = "user"
                if role == "user" and any(m in text.lower() for m in OPT_OUT_MARKERS):
                    opt_out = True
                if role == "user" and not meta["first_user"] and text and not text.startswith("Opdracht:"):
                    meta["first_user"] = text
            else:
                if isinstance(content, list):
                    tparts = []
                    for b in content:
                        if b.get("type") == "text":
                            tparts.append(b.get("text", ""))
                        elif b.get("type") == "tool_use":
                            tools.append(b.get("name", "tool"))
                    text = "\n".join(tparts).strip()
                elif isinstance(content, str):
                    text = content.strip()
                role = "assistant"
                if text == "No response requested.":
                    text = ""
            if not text and not images and not tools:
                pending.append((r, None, None, None, None))
                continue
            pending.append((r, role, text, tools, images))

        if opt_out:
            if conv_id:
                conn.execute("DELETE FROM conversations WHERE id=?", (conv_id,))
            conn.execute(
                "INSERT OR REPLACE INTO exclusions(source,ext_id,reason,at) VALUES(?,?,?,?)",
                (SOURCE, session_ext, "gebruiker vroeg om niet te archiveren (marker in chat)", db.now()),
            )
            _upsert_source(conn, key, st, new_offset, session_ext, None)
            res["skipped"] = "uitgesloten via marker"
            return res

        cwd = (conv["cwd"] if conv else None) or meta["cwd"]
        if _excluded_project(cwd, settings.get("exclude_project_patterns")):
            _upsert_source(conn, key, st, new_offset, session_ext, None)
            res["skipped"] = "project uitgesloten"
            return res

        has_visible = any(p[1] for p in pending)
        if not conv_id and not has_visible:
            _upsert_source(conn, key, st, new_offset, session_ext, None)
            return res

        if not conv_id:
            project_id = db.get_or_create_project(conn, SOURCE, cwd)
            title = meta["title"] or _title_from(meta["first_user"]) or "Claude Code-sessie"
            sid = session_ext.split("/")[-1]
            resume = f'cd "{cwd}" && claude --resume {sid}' if cwd and not is_subagent else None
            cur = conn.execute(
                "INSERT INTO conversations(source,ext_id,title,project_id,cwd,git_branch,created_at,updated_at,imported_at,"
                "resume_command,transcript_path,missing_info) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                (SOURCE, session_ext, title, project_id, cwd, meta["branch"], meta["first_ts"], meta["last_ts"], db.now(),
                 resume, key, db.dumps(["Denkstappen en tooluitvoer worden niet bewaard (alleen zichtbare tekst en toolnamen)."])),
            )
            conv_id = cur.lastrowid
            res["new_conversation"] = True
        else:
            upd = {"updated_at": meta["last_ts"] or conv["updated_at"], "git_branch": meta["branch"] or conv["git_branch"],
                   "transcript_path": key}
            if meta["title"] and conv["summary_kind"] != "handmatig-titel":
                upd["title"] = meta["title"]
            sets = ",".join(f"{k}=?" for k in upd)
            conn.execute(f"UPDATE conversations SET {sets} WHERE id=?", (*upd.values(), conv_id))

        seq = conn.execute("SELECT COALESCE(MAX(seq),0) FROM messages WHERE conversation_id=?", (conv_id,)).fetchone()[0]
        for r, role, text, tools, images in pending:
            uuid = r.get("uuid")
            if not uuid:
                continue
            parent = r.get("parentUuid") or r.get("logicalParentUuid")
            cur = conn.execute("INSERT OR IGNORE INTO cc_nodes(conversation_id,uuid,parent_uuid,ts) VALUES(?,?,?,?)",
                               (conv_id, uuid, parent, r.get("timestamp")))
            first_time = cur.rowcount == 1
            if not role:
                continue
            if role == "assistant" and not text and not images:
                # Alleen een toolaanroep: toolnaam toevoegen aan het vorige antwoord i.p.v. een leeg bericht
                if first_time:
                    prev = conn.execute("SELECT id, tools FROM messages WHERE conversation_id=? AND role='assistant' ORDER BY seq DESC LIMIT 1",
                                        (conv_id,)).fetchone()
                    if prev:
                        names = [t for t in (prev["tools"] or "").split(",") if t]
                        names += [t for t in tools if t not in names]
                        conn.execute("UPDATE messages SET tools=? WHERE id=?", (",".join(names), prev["id"]))
                continue
            if conn.execute("SELECT 1 FROM messages WHERE conversation_id=? AND ext_id=?", (conv_id, uuid)).fetchone():
                continue
            # Al opgeslagen in een ander Claude Code-gesprek (hervat/fork kopieert geschiedenis)?
            dup = conn.execute(
                "SELECT m.conversation_id FROM messages m JOIN conversations c ON c.id=m.conversation_id "
                "WHERE m.ext_id=? AND c.source=? AND m.conversation_id<>? LIMIT 1", (uuid, SOURCE, conv_id)).fetchone()
            if dup:
                continue
            seq += 1
            is_pack = 1 if CONTEXT_PACK_MARKER in (text or "") else 0
            cur = conn.execute(
                "INSERT INTO messages(conversation_id,ext_id,parent_ext_id,seq,role,content,created_at,is_context_pack,tools)"
                " VALUES(?,?,?,?,?,?,?,?,?)",
                (conv_id, uuid, parent, seq, role, text or "", r.get("timestamp"), is_pack, ",".join(tools or [])),
            )
            mid = cur.lastrowid
            res["new_messages"] += 1
            for i, img in enumerate(images or []):
                stored, size = _save_image(session_ext.replace("/", "_"), uuid, i, img)
                conn.execute(
                    "INSERT INTO attachments(message_id,file_name,file_type,file_size,stored_path,available) VALUES(?,?,?,?,?,?)",
                    (mid, f"afbeelding-{i + 1}", (img.get("source") or {}).get("media_type", "image"), size, stored, 1 if stored else 0),
                )

        if res["new_messages"] or res["new_conversation"]:
            _recompute_branches(conn, conv_id)
            n = conn.execute("SELECT COUNT(*) FROM messages WHERE conversation_id=?", (conv_id,)).fetchone()[0]
            conn.execute("UPDATE conversations SET message_count=? WHERE id=?", (n, conv_id))
        _upsert_source(conn, key, st, new_offset, session_ext, None)
    return res


def _title_from(text):
    if not text:
        return None
    line = text.strip().splitlines()[0]
    return (line[:80] + "…") if len(line) > 80 else line


def _upsert_source(conn, key, st, offset, session_ext, err):
    conn.execute(
        "INSERT INTO source_files(path,source,size,mtime,offset,session_id,last_import_at,last_error) VALUES(?,?,?,?,?,?,?,?) "
        "ON CONFLICT(path) DO UPDATE SET size=excluded.size, mtime=excluded.mtime, offset=excluded.offset, "
        "session_id=excluded.session_id, last_import_at=excluded.last_import_at, last_error=excluded.last_error",
        (key, SOURCE, st.st_size, st.st_mtime, offset, session_ext, db.now(), err),
    )


def _recompute_branches(conn, conv_id):
    nodes = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT uuid,parent_uuid,ts FROM cc_nodes WHERE conversation_id=?", (conv_id,))}
    if not nodes:
        return
    leaf = max(nodes, key=lambda u: nodes[u][1] or "")
    path = set()
    cur = leaf
    while cur and cur in nodes and cur not in path:
        path.add(cur)
        cur = nodes[cur][0]
    for (mid, ext) in conn.execute("SELECT id, ext_id FROM messages WHERE conversation_id=?", (conv_id,)).fetchall():
        on = 1
        if ext not in path:
            # Op een verlaten tak alleen als een voorouder wél op het hoofdpad ligt (echte vork)
            a, seen = nodes.get(ext, (None,))[0], set()
            while a and a in nodes and a not in seen:
                if a in path:
                    on = 0
                    break
                seen.add(a)
                a = nodes[a][0]
        conn.execute("UPDATE messages SET on_main_branch=? WHERE id=?", (on, mid))


def sync_all(conn, trigger="watcher") -> dict:
    s = config.load_settings()
    total = {"files": 0, "new_messages": 0, "new_conversations": 0, "errors": []}
    for f in discover_files(s.get("include_subagents")):
        try:
            r = import_file(conn, f, trigger)
            if r.get("skipped") != "ongewijzigd":
                total["files"] += 1
            total["new_messages"] += r["new_messages"]
            total["new_conversations"] += 1 if r["new_conversation"] else 0
        except Exception as e:  # noqa: BLE001 — één kapot bestand mag de rest niet blokkeren
            total["errors"].append(f"{f.name}: {e}")
            try:
                conn.execute("UPDATE source_files SET last_error=? WHERE path=?", (str(e)[:500], str(f)))
                conn.commit()
            except Exception:  # noqa: BLE001
                pass
    return total


def skip_ahead_all(conn):
    """Na een pauze: alles wat tijdens de pauze is weggeschreven niet alsnog archiveren."""
    for f in discover_files(config.load_settings().get("include_subagents")):
        try:
            st = f.stat()
        except OSError:
            continue
        with db.transaction(conn):
            _upsert_source(conn, str(f), st, st.st_size, f.stem, None)
