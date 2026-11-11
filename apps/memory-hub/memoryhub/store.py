"""Gedeelde logica voor app, MCP-server en CLI: zoeken, ophalen, geheugen, contextpakket, verwijderen, status."""
import json
import re
import shutil
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config, db
from .importer_cc import CONTEXT_PACK_MARKER
from .redact import redact

HL_START, HL_END = "\u0002", "\u0003"
MEMORY_KINDS = ("voorkeur", "beslissing", "doel", "actie", "feit")
MEMORY_ORIGINS = ("user_stated", "assistant_suggested", "inferred")
MEMORY_STATUSES = ("actief", "voorstel", "vervangen", "afgerond", "verworpen")
ORIGIN_LABEL = {"user_stated": "door jou gezegd", "assistant_suggested": "voorgesteld door Claude", "inferred": "afgeleid"}
SOURCE_LABEL = {"claude_code": "Claude Code", "claude_code_cloud": "Claude Code (cloud)", "claude_ai_export": "claude.ai (export)", "test": "Testgesprek"}
STALE_DAYS = 180


def _r(text, enabled=True):
    return redact(text) if enabled else text


def fts_query(q: str) -> str:
    """Zet gewone zoektekst veilig om naar een FTS5-query (AND tussen termen, prefix op woorden)."""
    out = []
    for tok in re.findall(r'"[^"]+"|\S+', q or ""):
        if tok.startswith('"') and tok.endswith('"') and len(tok) > 2:
            phrase = re.sub(r'["]', "", tok[1:-1]).strip()
            if phrase:
                out.append(f'"{phrase}"')
            continue
        upper = tok.upper()
        if upper in ("OR", "OF"):
            out.append("OR")
            continue
        words = re.findall(r"\w+", tok, re.UNICODE)
        for w in words:
            out.append(f'"{w}"*')
    while out and out[-1] == "OR":
        out.pop()
    while out and out[0] == "OR":
        out.pop(0)
    return " ".join(out)


def _filters(f: dict, alias_c="c", alias_m="m"):
    where, params = [], []
    if f.get("source"):
        where.append(f"{alias_c}.source=?"); params.append(f["source"])
    if f.get("project_id"):
        where.append(f"{alias_c}.project_id=?"); params.append(int(f["project_id"]))
    if f.get("project"):
        where.append(f"{alias_c}.project_id IN (SELECT id FROM projects WHERE name LIKE ? OR path LIKE ?)")
        params += [f"%{f['project']}%", f"%{f['project']}%"]
    if f.get("topic_id"):
        where.append(f"{alias_c}.id IN (SELECT conversation_id FROM conversation_topics WHERE topic_id=?)"); params.append(int(f["topic_id"]))
    if f.get("tag"):
        where.append(f"{alias_c}.id IN (SELECT conversation_id FROM tags WHERE tag=?)"); params.append(f["tag"])
    if f.get("favorite"):
        where.append(f"{alias_c}.favorite=1")
    if f.get("date_from"):
        where.append(f"COALESCE({alias_c}.updated_at,{alias_c}.created_at)>=?"); params.append(f["date_from"])
    if f.get("date_to"):
        where.append(f"COALESCE({alias_c}.created_at,{alias_c}.updated_at)<=?"); params.append(f["date_to"] + "T23:59:59Z" if len(f["date_to"]) == 10 else f["date_to"])
    if alias_m:
        if f.get("role"):
            where.append(f"{alias_m}.role=?"); params.append(f["role"])
        if not f.get("include_context_packs"):
            where.append(f"{alias_m}.is_context_pack=0")
    return where, params


def search_messages(conn, q, limit=20, offset=0, **filters):
    fq = fts_query(q)
    if not fq:
        return []
    where, params = _filters(filters)
    sql = (
        "SELECT m.id AS message_id, m.conversation_id, m.role, m.created_at, m.seq, m.on_main_branch,"
        f" snippet(messages_fts, 0, '{HL_START}', '{HL_END}', ' … ', 24) AS snippet, bm25(messages_fts) AS rank,"
        " c.title, c.source, c.url, c.created_at AS conv_created, c.updated_at AS conv_updated, p.name AS project"
        " FROM messages_fts JOIN messages m ON m.id=messages_fts.rowid"
        " JOIN conversations c ON c.id=m.conversation_id LEFT JOIN projects p ON p.id=c.project_id"
        " WHERE messages_fts MATCH ?" + "".join(" AND " + w for w in where) +
        " ORDER BY rank LIMIT ? OFFSET ?"
    )
    try:
        res = db.rows(conn.execute(sql, [fq, *params, int(limit), int(offset)]))
    except sqlite3.OperationalError:
        return []
    red = config.load_settings().get("redact_secrets_in_views", True)
    for r in res:
        r["snippet"] = _r(r["snippet"], red)
        r["source_label"] = SOURCE_LABEL.get(r["source"], r["source"])
    return res


def search_conversations(conn, q="", limit=50, offset=0, sort="recent", **filters):
    """Gesprekken met per gesprek de best passende fragmenten. Zonder q: gefilterde lijst."""
    order = {
        "recent": "COALESCE(c.updated_at,c.created_at) DESC",
        "oud": "COALESCE(c.created_at,c.updated_at) ASC",
        "titel": "c.title COLLATE NOCASE ASC",
        "lengte": "c.message_count DESC",
    }.get(sort, "COALESCE(c.updated_at,c.created_at) DESC")
    where, params = _filters(filters, alias_m=None)
    base = ("SELECT c.id, c.title, c.source, c.created_at, c.updated_at, c.message_count, c.favorite, c.url, c.is_test,"
            " c.project_id, p.name AS project, c.summary"
            " FROM conversations c LEFT JOIN projects p ON p.id=c.project_id")
    if not q.strip():
        sql = base + (" WHERE " + " AND ".join(where) if where else "") + f" ORDER BY {order} LIMIT ? OFFSET ?"
        convs = db.rows(conn.execute(sql, [*params, int(limit), int(offset)]))
        total = conn.execute("SELECT COUNT(*) FROM conversations c" + (" WHERE " + " AND ".join(where) if where else ""), params).fetchone()[0]
        _decorate(conn, convs)
        return {"total": total, "items": convs}
    hits = search_messages(conn, q, limit=400, **filters)
    by_conv = {}
    for h in hits:
        by_conv.setdefault(h["conversation_id"], []).append(h)
    # titels ook doorzoeken
    tw, tp = [], []
    for w in re.findall(r"\w+", q, re.UNICODE):
        tw.append("c.title LIKE ?"); tp.append(f"%{w}%")
    title_ids = []
    if tw:
        title_ids = [r[0] for r in conn.execute(
            "SELECT c.id FROM conversations c WHERE " + " AND ".join(tw + where), tp + params)]
    ids = list(by_conv.keys()) + [i for i in title_ids if i not in by_conv]
    if not ids:
        return {"total": 0, "items": []}
    convs = {r["id"]: r for r in db.rows(conn.execute(
        base + f" WHERE c.id IN ({','.join('?' * len(ids))})", ids))}
    ranked = sorted(ids, key=lambda i: (min((h["rank"] for h in by_conv.get(i, [])), default=0) - (5 if i in title_ids else 0)))
    if sort != "relevantie" and sort in ("recent", "oud", "titel", "lengte"):
        keyf = {
            "recent": lambda i: convs[i]["updated_at"] or convs[i]["created_at"] or "",
            "oud": lambda i: convs[i]["created_at"] or "",
            "titel": lambda i: (convs[i]["title"] or "").lower(),
            "lengte": lambda i: convs[i]["message_count"] or 0,
        }[sort]
        ranked = sorted(ids, key=keyf, reverse=sort in ("recent", "lengte"))
    items = []
    for i in ranked[int(offset): int(offset) + int(limit)]:
        c = convs[i]
        c["hits"] = by_conv.get(i, [])[:3]
        c["hit_count"] = len(by_conv.get(i, []))
        items.append(c)
    _decorate(conn, items)
    return {"total": len(ids), "items": items}


def _decorate(conn, convs):
    for c in convs:
        c["source_label"] = SOURCE_LABEL.get(c["source"], c["source"])
        c["topics"] = db.rows(conn.execute(
            "SELECT t.id,t.name,t.color FROM topics t JOIN conversation_topics ct ON ct.topic_id=t.id WHERE ct.conversation_id=?", (c["id"],)))
        c["tags"] = [r[0] for r in conn.execute("SELECT tag FROM tags WHERE conversation_id=? ORDER BY tag", (c["id"],))]


def get_conversation(conn, conv_id, start=None, limit=None, around_message_id=None, include_alt=True, redact_secrets=None):
    c = conn.execute("SELECT c.*, p.name AS project, p.path AS project_path FROM conversations c"
                     " LEFT JOIN projects p ON p.id=c.project_id WHERE c.id=?", (int(conv_id),)).fetchone()
    if not c:
        return None
    c = dict(c)
    red = config.load_settings().get("redact_secrets_in_views", True) if redact_secrets is None else redact_secrets
    where = "conversation_id=?" + ("" if include_alt else " AND on_main_branch=1")
    msgs = db.rows(conn.execute(f"SELECT * FROM messages WHERE {where} ORDER BY seq", (c["id"],)))
    total = len(msgs)
    if around_message_id:
        idx = next((i for i, m in enumerate(msgs) if m["id"] == int(around_message_id)), 0)
        span = int(limit or 10)
        msgs = msgs[max(0, idx - span // 2): idx + span // 2 + 1]
    elif start is not None or limit is not None:
        s = int(start or 0)
        msgs = msgs[s: s + int(limit)] if limit else msgs[s:]
    for m in msgs:
        m["content"] = _r(m["content"], red)
        m["attachments"] = db.rows(conn.execute(
            "SELECT id,file_name,file_type,file_size,available,stored_path IS NOT NULL AS has_file,"
            " substr(extracted_text,1,4000) AS extracted_text FROM attachments WHERE message_id=?", (m["id"],)))
        for a in m["attachments"]:
            if a.get("extracted_text"):
                a["extracted_text"] = _r(a["extracted_text"], red)
    c["messages"] = msgs
    c["total_messages"] = total
    c["source_label"] = SOURCE_LABEL.get(c["source"], c["source"])
    try:
        c["missing_info"] = json.loads(c.get("missing_info") or "[]")
    except ValueError:
        c["missing_info"] = []
    c["topics"] = db.rows(conn.execute(
        "SELECT t.id,t.name,t.color FROM topics t JOIN conversation_topics ct ON ct.topic_id=t.id WHERE ct.conversation_id=?", (c["id"],)))
    c["tags"] = [r[0] for r in conn.execute("SELECT tag FROM tags WHERE conversation_id=? ORDER BY tag", (c["id"],))]
    c["memories"] = list_memories(conn, conversation_id=c["id"], status=None)
    c["alt_branch_count"] = conn.execute(
        "SELECT COUNT(*) FROM messages WHERE conversation_id=? AND on_main_branch=0", (c["id"],)).fetchone()[0]
    return c


def update_conversation(conn, conv_id, data):
    fields = {}
    for k in ("title", "favorite", "notes", "summary", "project_id"):
        if k in data:
            fields[k] = data[k]
    with db.transaction(conn):
        if fields:
            if "summary" in fields:
                fields["summary_kind"] = "handmatig"
            sets = ",".join(f"{k}=?" for k in fields)
            conn.execute(f"UPDATE conversations SET {sets} WHERE id=?", (*fields.values(), int(conv_id)))
        if "tags" in data:
            conn.execute("DELETE FROM tags WHERE conversation_id=?", (int(conv_id),))
            for t in {t.strip() for t in data["tags"] if t and t.strip()}:
                conn.execute("INSERT OR IGNORE INTO tags(conversation_id,tag) VALUES(?,?)", (int(conv_id), t[:60]))
        if "topic_ids" in data:
            conn.execute("DELETE FROM conversation_topics WHERE conversation_id=?", (int(conv_id),))
            for t in data["topic_ids"]:
                conn.execute("INSERT OR IGNORE INTO conversation_topics VALUES(?,?)", (int(conv_id), int(t)))
    return get_conversation(conn, conv_id, limit=0)


# ---------------------------------------------------------------- samenvatting (lokaal)

def local_summary(conn, conv_id):
    """Eenvoudige extractieve samenvatting zonder AI: oorspronkelijke zinnen, geen nieuwe inhoud."""
    msgs = db.rows(conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id=? AND on_main_branch=1 AND is_context_pack=0 ORDER BY seq", (int(conv_id),)))
    users = [m["content"] for m in msgs if m["role"] == "user" and m["content"].strip()]
    assistants = [m["content"] for m in msgs if m["role"] == "assistant" and m["content"].strip()]

    def clip(t, n):
        t = re.sub(r"```[\s\S]*?```", "[code]", t)
        t = re.sub(r"\s+", " ", t).strip()
        return t[:n] + ("…" if len(t) > n else "")
    parts = []
    if users:
        parts.append("Eerste vraag: " + clip(users[0], 280))
    if len(users) > 1:
        parts.append("Laatste vraag: " + clip(users[-1], 200))
    if assistants:
        parts.append("Laatste antwoord (begin): " + clip(assistants[-1], 300))
    return "\n".join(parts)


def ensure_summary(conn, conv_id):
    c = conn.execute("SELECT summary, summary_kind FROM conversations WHERE id=?", (int(conv_id),)).fetchone()
    if c and c["summary_kind"] in ("handmatig", "claude.ai") and c["summary"]:
        return c["summary"], c["summary_kind"]
    s = local_summary(conn, conv_id)
    with db.transaction(conn):
        conn.execute("UPDATE conversations SET summary=?, summary_kind='lokaal-extractief' WHERE id=?", (s, int(conv_id)))
    return s, "lokaal-extractief"


# ---------------------------------------------------------------- geheugen

def _source_label(conn, conv_id, msg_id=None):
    if not conv_id:
        return "", None
    c = conn.execute("SELECT title, source, created_at, updated_at FROM conversations WHERE id=?", (int(conv_id),)).fetchone()
    if not c:
        return "", None
    date = None
    if msg_id:
        m = conn.execute("SELECT created_at FROM messages WHERE id=?", (int(msg_id),)).fetchone()
        date = m["created_at"] if m else None
    date = date or c["updated_at"] or c["created_at"]
    return f"{SOURCE_LABEL.get(c['source'], c['source'])} · “{c['title']}” (gesprek #{conv_id})", date


def save_memory(conn, text, kind="feit", origin="user_stated", project=None, project_id=None, conversation_id=None,
                message_id=None, status=None, source_note="", created_by="app", confirmed=False, source_date=None):
    text = (text or "").strip()
    if not text:
        raise ValueError("Tekst is verplicht")
    if kind not in MEMORY_KINDS:
        raise ValueError(f"kind moet een van {MEMORY_KINDS} zijn")
    if origin not in MEMORY_ORIGINS:
        raise ValueError(f"origin moet een van {MEMORY_ORIGINS} zijn")
    if status is None:
        # Suggesties van Claude worden nooit automatisch jouw voorkeur
        status = "actief" if origin == "user_stated" else "voorstel"
    if status not in MEMORY_STATUSES:
        raise ValueError(f"status moet een van {MEMORY_STATUSES} zijn")
    if project and not project_id:
        r = conn.execute("SELECT id FROM projects WHERE name=? OR path=? ORDER BY id LIMIT 1", (project, project)).fetchone()
        project_id = r[0] if r else db.get_or_create_project(conn, "handmatig", project, project)
    if message_id and not conversation_id:
        r = conn.execute("SELECT conversation_id FROM messages WHERE id=?", (int(message_id),)).fetchone()
        conversation_id = r[0] if r else None
    if conversation_id and not conn.execute("SELECT 1 FROM conversations WHERE id=?", (int(conversation_id),)).fetchone():
        raise ValueError(f"Gesprek #{conversation_id} bestaat niet")
    label, date = _source_label(conn, conversation_id, message_id)
    if source_note:
        label = (label + " — " if label else "") + source_note
    conflicts = find_conflicts(conn, text, kind, project_id)
    with db.transaction(conn):
        cur = conn.execute(
            "INSERT INTO memories(kind,text,origin,status,confirmed,project_id,source_conversation_id,source_message_id,"
            "source_label,source_date,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kind, text, origin, status, 1 if confirmed else 0, project_id, conversation_id, message_id, label,
             source_date or date or db.now(), created_by, db.now(), db.now()),
        )
        mid = cur.lastrowid
        conn.execute("INSERT INTO memory_history(memory_id,changed_at,change,changed_by) VALUES(?,?,?,?)",
                     (mid, db.now(), db.dumps({"actie": "aangemaakt"}), created_by))
    m = get_memory(conn, mid)
    m["mogelijk_tegenstrijdig"] = conflicts
    return m


def find_conflicts(conn, text, kind, project_id=None, exclude_id=None):
    words = [w for w in re.findall(r"\w{4,}", text.lower(), re.UNICODE)][:12]
    if not words:
        return []
    q = " OR ".join(f'"{w}"' for w in words)
    sql = ("SELECT m.id, m.text, m.kind, m.status, m.origin, m.source_date FROM memories_fts f JOIN memories m ON m.id=f.rowid"
           " WHERE memories_fts MATCH ? AND m.status IN ('actief','voorstel') AND m.kind=?")
    params = [q, kind]
    if project_id:
        sql += " AND (m.project_id=? OR m.project_id IS NULL)"; params.append(project_id)
    if exclude_id:
        sql += " AND m.id<>?"; params.append(exclude_id)
    sql += " ORDER BY bm25(memories_fts) LIMIT 5"
    try:
        return db.rows(conn.execute(sql, params))
    except sqlite3.OperationalError:
        return []


def get_memory(conn, mid):
    r = conn.execute("SELECT m.*, p.name AS project FROM memories m LEFT JOIN projects p ON p.id=m.project_id WHERE m.id=?", (int(mid),)).fetchone()
    if not r:
        return None
    m = dict(r)
    m["origin_label"] = ORIGIN_LABEL.get(m["origin"], m["origin"])
    m["mogelijk_verouderd"] = _is_stale(m.get("source_date"))
    m["history"] = db.rows(conn.execute("SELECT changed_at, change, changed_by FROM memory_history WHERE memory_id=? ORDER BY id", (m["id"],)))
    return m


def _is_stale(date):
    if not date:
        return False
    try:
        d = datetime.fromisoformat(date.replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - d).days > STALE_DAYS
    except ValueError:
        return False


def update_memory(conn, mid, reason="", changed_by="app", **changes):
    """Werk een geheugenitem bij. Bij een inhoudelijke correctie (nieuwe tekst) blijft het oude item
    bewaard met status 'vervangen' en ontstaat een nieuw item dat ernaar verwijst."""
    old = get_memory(conn, mid)
    if not old:
        raise ValueError(f"Geheugenitem #{mid} bestaat niet")
    new_text = changes.get("text")
    if new_text and new_text.strip() != old["text"]:
        with db.transaction(conn):
            conn.execute("UPDATE memories SET status='vervangen', updated_at=? WHERE id=?", (db.now(), old["id"]))
            conn.execute("INSERT INTO memory_history(memory_id,changed_at,change,changed_by) VALUES(?,?,?,?)",
                         (old["id"], db.now(), db.dumps({"actie": "vervangen", "reden": reason}), changed_by))
        new = save_memory(conn, new_text, kind=changes.get("kind") or old["kind"], origin=changes.get("origin") or "user_stated",
                          project_id=old["project_id"], conversation_id=changes.get("conversation_id") or old["source_conversation_id"],
                          message_id=changes.get("message_id"), status=changes.get("status"),
                          source_note=("Correctie: " + reason) if reason else "Correctie", created_by=changed_by,
                          confirmed=changes.get("confirmed", False))
        with db.transaction(conn):
            conn.execute("UPDATE memories SET supersedes_id=? WHERE id=?", (old["id"], new["id"]))
        return get_memory(conn, new["id"])
    fields = {k: v for k, v in changes.items() if k in ("kind", "status", "origin", "confirmed", "project_id") and v is not None}
    if "status" in fields and fields["status"] not in MEMORY_STATUSES:
        raise ValueError(f"status moet een van {MEMORY_STATUSES} zijn")
    if "kind" in fields and fields["kind"] not in MEMORY_KINDS:
        raise ValueError(f"kind moet een van {MEMORY_KINDS} zijn")
    if "origin" in fields and fields["origin"] not in MEMORY_ORIGINS:
        raise ValueError(f"origin moet een van {MEMORY_ORIGINS} zijn")
    if fields.get("confirmed") and old["status"] == "voorstel" and "status" not in fields:
        fields["status"] = "actief"
    if not fields:
        return old
    with db.transaction(conn):
        sets = ",".join(f"{k}=?" for k in fields)
        conn.execute(f"UPDATE memories SET {sets}, updated_at=? WHERE id=?", (*fields.values(), db.now(), old["id"]))
        conn.execute("INSERT INTO memory_history(memory_id,changed_at,change,changed_by) VALUES(?,?,?,?)",
                     (old["id"], db.now(), db.dumps({"oud": {k: old.get(k) for k in fields}, "nieuw": fields, "reden": reason}), changed_by))
    return get_memory(conn, mid)


def delete_memory(conn, mid):
    with db.transaction(conn):
        conn.execute("DELETE FROM memories WHERE id=?", (int(mid),))


def list_memories(conn, q=None, kind=None, status="actief", project_id=None, project=None, conversation_id=None, origin=None, limit=200):
    where, params = [], []
    if q:
        fq = fts_query(q)
        if fq:
            where.append("m.id IN (SELECT rowid FROM memories_fts WHERE memories_fts MATCH ?)"); params.append(fq)
    if kind:
        where.append("m.kind=?"); params.append(kind)
    if status:
        sts = status if isinstance(status, (list, tuple)) else [status]
        where.append(f"m.status IN ({','.join('?' * len(sts))})"); params += list(sts)
    if project_id:
        where.append("(m.project_id=? OR m.project_id IS NULL)"); params.append(int(project_id))
    if project:
        where.append("(m.project_id IN (SELECT id FROM projects WHERE name LIKE ? OR path LIKE ?) OR m.project_id IS NULL)")
        params += [f"%{project}%", f"%{project}%"]
    if conversation_id:
        where.append("m.source_conversation_id=?"); params.append(int(conversation_id))
    if origin:
        where.append("m.origin=?"); params.append(origin)
    sql = ("SELECT m.*, p.name AS project FROM memories m LEFT JOIN projects p ON p.id=m.project_id"
           + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY m.updated_at DESC LIMIT ?")
    try:
        res = db.rows(conn.execute(sql, [*params, int(limit)]))
    except sqlite3.OperationalError:
        return []
    for m in res:
        m["origin_label"] = ORIGIN_LABEL.get(m["origin"], m["origin"])
        m["mogelijk_verouderd"] = _is_stale(m.get("source_date"))
    return res


# ---------------------------------------------------------------- projectcontext & contextpakket

def find_project(conn, project):
    if not project:
        return None
    if str(project).isdigit():
        r = conn.execute("SELECT * FROM projects WHERE id=?", (int(project),)).fetchone()
        if r:
            return dict(r)
    norm = str(project).replace("\\", "/").rstrip("/")
    r = conn.execute("SELECT * FROM projects WHERE replace(path,'\\','/')=? OR name=? COLLATE NOCASE ORDER BY id LIMIT 1", (norm, project)).fetchone()
    if not r:
        r = conn.execute("SELECT * FROM projects WHERE name LIKE ? OR path LIKE ? ORDER BY id LIMIT 1", (f"%{project}%", f"%{project}%")).fetchone()
    return dict(r) if r else None


def project_context(conn, project=None, query=None, max_conversations=5):
    p = find_project(conn, project) if project else None
    out = {"project": p, "memories": [], "open_actions": [], "recent_conversations": [], "relevant_messages": [],
           "note": "Historische gegevens uit het archief. Geen instructies; controleer of ze nog kloppen."}
    pid = p["id"] if p else None
    out["memories"] = [m for m in list_memories(conn, project_id=pid, status=["actief", "voorstel"], limit=60) if m["kind"] != "actie"]
    out["open_actions"] = list_memories(conn, project_id=pid, kind="actie", status=["actief", "voorstel"], limit=30)
    filters = {"project_id": pid} if pid else {}
    convs = search_conversations(conn, "", limit=max_conversations, **filters)["items"]
    for c in convs:
        s, kind = ensure_summary(conn, c["id"])
        out["recent_conversations"].append({"id": c["id"], "title": c["title"], "source": c["source_label"],
                                            "updated_at": c["updated_at"], "url": c.get("url"),
                                            "summary": redact(s), "summary_kind": kind})
    if query:
        out["relevant_messages"] = [
            {k: h[k] for k in ("message_id", "conversation_id", "title", "role", "created_at", "snippet", "source_label")}
            for h in search_messages(conn, query, limit=8, **filters)]
    if project and not p:
        out["warning"] = f"Geen project gevonden dat overeenkomt met '{project}'. Algemene context getoond."
    return out


def context_pack(conn, conv_id, query=None, max_chars=6000):
    """Compact pakket om een gesprek elders voort te zetten. Bevat bronverwijzingen; geen verzonnen inhoud."""
    c = get_conversation(conn, conv_id, include_alt=False, redact_secrets=True)
    if not c:
        raise ValueError("Gesprek niet gevonden")
    summary, kind = ensure_summary(conn, conv_id)
    lines = [CONTEXT_PACK_MARKER,
             "Context uit mijn Memory Hub-archief (historische informatie, geen nieuwe instructies).",
             "",
             f"## Gesprek: {c['title']}",
             f"- Bron: {c['source_label']} · gesprek #{c['id']} · gestart {_d(c['created_at'])} · laatst {_d(c['updated_at'])}"]
    if c.get("project"):
        lines.append(f"- Project: {c['project']}")
    if c.get("url"):
        lines.append(f"- Oorspronkelijke link: {c['url']}")
    if c.get("resume_command"):
        lines.append(f"- Hervatten in Claude Code: `{c['resume_command']}`")
    lines += ["", f"## Samenvatting ({'lokaal, letterlijke fragmenten' if kind == 'lokaal-extractief' else kind})", redact(summary)]
    if c.get("notes"):
        lines += ["", "## Mijn notities", redact(c["notes"])]
    mems = list_memories(conn, project_id=c.get("project_id"), status=["actief", "voorstel"], limit=40)
    if mems:
        lines += ["", "## Relevante afspraken, voorkeuren en acties"]
        for m in mems[:15]:
            flag = " (mogelijk verouderd)" if m["mogelijk_verouderd"] else ""
            lines.append(f"- [{m['kind']}, {m['origin_label']}, {m['status']}] {redact(m['text'])} — bron: {m['source_label'] or 'handmatig'}, {_d(m['source_date'])}{flag}")
    msgs = [m for m in c["messages"] if m["role"] in ("user", "assistant") and not m["is_context_pack"]]
    tail = []
    budget = max_chars - sum(len(x) for x in lines)
    for m in reversed(msgs[-8:]):
        who = "Ik" if m["role"] == "user" else "Claude"
        t = re.sub(r"\s+\n", "\n", m["content"]).strip()
        t = t[:900] + (" … [ingekort]" if len(t) > 900 else "")
        entry = f"**{who}** ({_d(m['created_at'])}, bericht #{m['id']}):\n{t}"
        if budget - len(entry) < 0:
            break
        budget -= len(entry)
        tail.insert(0, entry)
    if tail:
        lines += ["", "## Laatste berichten (letterlijk, mogelijk ingekort)"] + tail
    if query:
        hits = search_messages(conn, query, limit=5)
        hits = [h for h in hits if h["conversation_id"] != c["id"]]
        if hits:
            lines += ["", f"## Gerelateerd in andere gesprekken (zoekterm: {query})"]
            for h in hits:
                lines.append(f"- {h['title']} (#{h['conversation_id']}, {_d(h['created_at'])}): {h['snippet'].replace(HL_START, '').replace(HL_END, '')}")
    if c["missing_info"]:
        lines += ["", "## Ontbrekend in het archief"] + [f"- {x}" for x in c["missing_info"]]
    return "\n".join(lines)


def _d(ts):
    return (ts or "?")[:10]


# ---------------------------------------------------------------- verwijderen

def _write_tombstone(source, ext_id, title):
    p = config.tombstones_path()
    data = []
    if p.exists():
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except ValueError:
            data = []
    data.append({"source": source, "ext_id": ext_id, "deleted_at": db.now()})
    p.write_text(json.dumps(data, indent=1), encoding="utf-8")


def read_tombstones():
    p = config.tombstones_path()
    if not p.exists():
        return []
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError:
        return []


def delete_conversation(conn, conv_id, prevent_reimport=True, purge_backups=False):
    """Verwijdert gesprek, berichten, zoekindex, bijlagen, afgeleide geheugenitems en labels."""
    c = conn.execute("SELECT id, source, ext_id, title FROM conversations WHERE id=?", (int(conv_id),)).fetchone()
    if not c:
        raise ValueError("Gesprek niet gevonden")
    files = [r[0] for r in conn.execute(
        "SELECT a.stored_path FROM attachments a JOIN messages m ON m.id=a.message_id WHERE m.conversation_id=? AND a.stored_path IS NOT NULL", (c["id"],))]
    n_mem = conn.execute("SELECT COUNT(*) FROM memories WHERE source_conversation_id=?", (c["id"],)).fetchone()[0]
    with db.transaction(conn):
        conn.execute("DELETE FROM memories WHERE source_conversation_id=?", (c["id"],))
        conn.execute("DELETE FROM conversations WHERE id=?", (c["id"],))  # cascade: berichten, fts (trigger), bijlagen, tags, nodes
        if prevent_reimport:
            conn.execute("INSERT OR REPLACE INTO exclusions(source,ext_id,reason,at) VALUES(?,?,?,?)",
                         (c["source"], c["ext_id"], "verwijderd door gebruiker", db.now()))
    for f in files:
        try:
            Path(f).unlink(missing_ok=True)
        except OSError:
            pass
    _write_tombstone(c["source"], c["ext_id"], c["title"] or "")
    purged = 0
    if purge_backups:
        from .backup import purge_from_backups
        purged = purge_from_backups([(c["source"], c["ext_id"])])
    return {"deleted": True, "memories_deleted": n_mem, "attachments_deleted": len(files), "backups_cleaned": purged,
            "reimport_blocked": prevent_reimport}


def unexclude(conn, source, ext_id):
    with db.transaction(conn):
        conn.execute("DELETE FROM exclusions WHERE source=? AND ext_id=?", (source, ext_id))
        # forceer herlezen van het transcript bij de volgende synchronisatie
        conn.execute("UPDATE source_files SET offset=0, size=-1 WHERE session_id=?", (ext_id,))


# ---------------------------------------------------------------- status

def sync_status(conn):
    s = config.load_settings()
    from .install import installation_state
    inst = installation_state()
    now = time.time()
    hb = db.get_meta(conn, "watcher_heartbeat")
    hb_age = (now - float(hb)) if hb else None
    last_ok_cc = conn.execute("SELECT MAX(at) FROM sync_log WHERE source='claude_code' AND ok=1").fetchone()[0]
    last_err_cc = conn.execute("SELECT at, detail FROM sync_log WHERE source='claude_code' AND ok=0 ORDER BY id DESC LIMIT 1").fetchone()
    file_errors = db.rows(conn.execute("SELECT path, last_error FROM source_files WHERE last_error IS NOT NULL AND last_error<>'' LIMIT 20"))
    from .importer_cc import discover_files
    behind = []
    known = {r["path"]: r for r in db.rows(conn.execute("SELECT path,size,offset FROM source_files"))}
    files = discover_files(s.get("include_subagents"))
    for f in files:
        try:
            size = f.stat().st_size
        except OSError:
            continue
        k = known.get(str(f))
        if not k or k["size"] != size:
            behind.append(str(f))
    oldest_transcript = None
    for f in files:
        try:
            mt = f.stat().st_mtime
            oldest_transcript = mt if oldest_transcript is None else min(oldest_transcript, mt)
        except OSError:
            pass
    pending_exports = [p.name for p in config.import_dir().iterdir()
                       if p.name not in ("verwerkt", "mislukt") and (p.suffix.lower() in (".zip", ".json") or p.is_dir())] if config.import_dir().exists() else []
    last_export = db.get_meta(conn, "last_export_import")
    counts = {r["source"]: r["n"] for r in db.rows(conn.execute("SELECT source, COUNT(*) n FROM conversations GROUP BY source"))}
    msgcounts = {r["source"]: r["n"] for r in db.rows(conn.execute(
        "SELECT c.source, COUNT(*) n FROM messages m JOIN conversations c ON c.id=m.conversation_id GROUP BY c.source"))}
    last_backup = db.get_meta(conn, "last_backup")
    return {
        "paused": bool(s.get("paused")),
        "paused_since": s.get("paused_since"),
        "data_dir": str(config.data_dir()),
        "database": str(config.db_path()),
        "database_size": config.db_path().stat().st_size if config.db_path().exists() else 0,
        "totals": {"conversations": sum(counts.values()), "messages": sum(msgcounts.values()),
                   "memories": conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]},
        "sources": [
            {
                "id": "claude_code", "name": "Claude Code (lokale transcripten)",
                "mode": "automatisch" if (inst["hooks"] or (hb_age is not None and hb_age < 300)) else "handmatig",
                "automatic_via": [x for x, ok in (("hooks", inst["hooks"]), ("achtergrondproces", hb_age is not None and hb_age < 300)) if ok],
                "hooks_installed": inst["hooks"],
                "watcher_active": hb_age is not None and hb_age < max(120, s.get("watch_interval_seconds", 30) * 4),
                "watcher_last_seen": _age_text(hb_age),
                "transcript_dirs": [str(p) for p in config.projects_dirs()],
                "transcript_files": len(files),
                "files_behind": len(behind),
                "conversations": counts.get("claude_code", 0),
                "messages": msgcounts.get("claude_code", 0),
                "last_success": last_ok_cc,
                "last_error": dict(last_err_cc) if last_err_cc else None,
                "file_errors": file_errors,
                "warning": ("Claude Code wist transcripten standaard na 30 dagen (instelling cleanupPeriodDays). "
                            "Memory Hub bewaart ze, mits ze vóór die tijd zijn geïmporteerd."),
            },
            {
                "id": "claude_ai_export", "name": "claude.ai web / desktop / mobiel",
                "mode": "handmatige import",
                "why": ("Er is geen officiële API om je claude.ai-gesprekken automatisch op te halen. "
                        "Exporteer via claude.ai → Instellingen → Privacy → Gegevens exporteren en importeer de .zip."),
                "conversations": counts.get("claude_ai_export", 0),
                "messages": msgcounts.get("claude_ai_export", 0),
                "last_import": last_export,
                "days_since_import": _days_since(last_export),
                "pending_in_import_folder": pending_exports,
                "import_folder": str(config.import_dir()),
            },
        ],
        "test_conversations": counts.get("test", 0),
        "mcp_registered": inst["mcp"],
        "skill_installed": inst["skill"],
        "last_backup": last_backup,
        "recent_log": [dict(r, detail=redact(r["detail"] or "")) for r in db.rows(conn.execute("SELECT * FROM sync_log ORDER BY id DESC LIMIT 15"))],
        "oldest_transcript_on_disk": datetime.fromtimestamp(oldest_transcript, timezone.utc).isoformat()[:10] if oldest_transcript else None,
        "external_services": "Geen. Alle opslag, zoekfuncties en samenvattingen zijn lokaal; er gaat geen chatinhoud naar externe diensten.",
    }


def _age_text(sec):
    if sec is None:
        return "nooit"
    if sec < 90:
        return f"{int(sec)} s geleden"
    if sec < 5400:
        return f"{int(sec // 60)} min geleden"
    return f"{int(sec // 3600)} uur geleden"


def _days_since(ts):
    if not ts:
        return None
    try:
        d = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - d).days
    except ValueError:
        return None


# ---------------------------------------------------------------- export

def conversation_markdown(conn, conv_id, redact_secrets=False):
    c = get_conversation(conn, conv_id, redact_secrets=redact_secrets)
    lines = [f"# {c['title']}", "",
             f"- Bron: {c['source_label']}", f"- ID: {c['ext_id']}", f"- Gestart: {c['created_at']}", f"- Laatst: {c['updated_at']}"]
    if c.get("project"):
        lines.append(f"- Project: {c['project']}")
    if c.get("url"):
        lines.append(f"- Link: {c['url']}")
    if c["tags"]:
        lines.append("- Labels: " + ", ".join(c["tags"]))
    if c.get("notes"):
        lines += ["", "## Notities", c["notes"]]
    for x in c["missing_info"]:
        lines.append(f"> Let op: {x}")
    lines.append("")
    for m in c["messages"]:
        who = {"user": "Ik", "assistant": "Claude", "system": "Systeem"}.get(m["role"], m["role"])
        alt = " _(alternatieve tak)_" if not m["on_main_branch"] else ""
        lines += [f"### {who} — {m['created_at'] or ''}{alt}", "", m["content"], ""]
        for a in m["attachments"]:
            lines.append(f"- Bijlage: {a['file_name']} ({'beschikbaar' if a['available'] else 'ontbreekt in bron'})")
    return "\n".join(lines)


def export_all(conn, fmt="json", redact_secrets=False):
    config.ensure_dirs()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    ids = [r[0] for r in conn.execute("SELECT id FROM conversations ORDER BY id")]
    if fmt == "json":
        out = config.exports_dir() / f"memoryhub-export-{stamp}.json"
        data = {"exported_at": db.now(), "format": "memory-hub-v1", "conversations": [], "memories": list_memories(conn, status=None, limit=100000),
                "topics": db.rows(conn.execute("SELECT * FROM topics")), "projects": db.rows(conn.execute("SELECT * FROM projects"))}
        for i in ids:
            data["conversations"].append(get_conversation(conn, i, redact_secrets=redact_secrets))
        out.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        return out
    folder = config.exports_dir() / f"memoryhub-markdown-{stamp}"
    folder.mkdir(parents=True)
    for i in ids:
        c = conn.execute("SELECT title, created_at FROM conversations WHERE id=?", (i,)).fetchone()
        slug = re.sub(r"[^\w\-]+", "-", (c["title"] or "gesprek").lower(), flags=re.UNICODE).strip("-")[:60]
        (folder / f"{(c['created_at'] or '')[:10]}-{i}-{slug}.md").write_text(conversation_markdown(conn, i, redact_secrets), encoding="utf-8")
    zip_path = shutil.make_archive(str(folder), "zip", folder)
    shutil.rmtree(folder)
    return Path(zip_path)
