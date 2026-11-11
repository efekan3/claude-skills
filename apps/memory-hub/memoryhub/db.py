"""SQLite-opslag met FTS5 full-text search."""
import json
import sqlite3
import time
from contextlib import contextmanager

from . import config

SCHEMA_VERSION = 2

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    path TEXT,                       -- werkmap (Claude Code) of claude.ai-project-UUID
    source TEXT,
    description TEXT DEFAULT '',
    color TEXT DEFAULT '',
    created_at TEXT,
    UNIQUE(source, path)
);

CREATE TABLE IF NOT EXISTS topics (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    color TEXT DEFAULT '#6b8afd',
    keywords TEXT DEFAULT '',        -- komma-gescheiden; voor automatisch voorstellen
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,            -- claude_code | claude_ai_export | test
    ext_id TEXT NOT NULL,            -- sessionId / gesprek-UUID
    title TEXT,
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    cwd TEXT,
    git_branch TEXT,
    created_at TEXT,
    updated_at TEXT,
    imported_at TEXT,
    source_updated_at TEXT,          -- updated_at volgens de bron (voor bijgewerkte exports)
    url TEXT,                        -- alleen als er een geldige link bestaat
    resume_command TEXT,
    transcript_path TEXT,
    message_count INTEGER DEFAULT 0,
    favorite INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    summary TEXT DEFAULT '',
    summary_kind TEXT DEFAULT '',    -- 'lokaal-extractief' | 'handmatig'
    missing_info TEXT DEFAULT '',    -- eerlijk: wat ontbreekt er (JSON-lijst)
    is_test INTEGER DEFAULT 0,
    UNIQUE(source, ext_id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    ext_id TEXT NOT NULL,            -- bericht-UUID uit de bron
    parent_ext_id TEXT,
    seq REAL NOT NULL,               -- volgorde binnen het gesprek
    role TEXT NOT NULL,              -- user | assistant | system
    content TEXT NOT NULL,           -- oorspronkelijke tekst (Markdown)
    created_at TEXT,
    on_main_branch INTEGER DEFAULT 1,
    is_context_pack INTEGER DEFAULT 0,
    tools TEXT DEFAULT '',           -- namen van gebruikte tools (alleen metadata)
    meta TEXT DEFAULT '',
    UNIQUE(conversation_id, ext_id)
);
CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, seq);
CREATE INDEX IF NOT EXISTS idx_messages_ext ON messages(ext_id);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    file_name TEXT,
    file_type TEXT,
    file_size INTEGER,
    stored_path TEXT,                -- als het bestand zelf beschikbaar is
    extracted_text TEXT,
    available INTEGER DEFAULT 0      -- 0 = alleen verwijzing, bestand ontbreekt
);

-- Boom van alle Claude Code-records (ook niet-zichtbare) voor vertakkingen
CREATE TABLE IF NOT EXISTS cc_nodes (
    conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    uuid TEXT NOT NULL,
    parent_uuid TEXT,
    ts TEXT,
    PRIMARY KEY(conversation_id, uuid)
);

CREATE TABLE IF NOT EXISTS conversation_topics (
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    topic_id INTEGER REFERENCES topics(id) ON DELETE CASCADE,
    PRIMARY KEY(conversation_id, topic_id)
);

CREATE TABLE IF NOT EXISTS tags (
    conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    PRIMARY KEY(conversation_id, tag)
);

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,              -- voorkeur | beslissing | doel | actie | feit
    text TEXT NOT NULL,
    origin TEXT NOT NULL,            -- user_stated | assistant_suggested | inferred
    status TEXT NOT NULL DEFAULT 'actief',  -- actief | vervangen | afgerond | verworpen
    confirmed INTEGER DEFAULT 0,     -- door de gebruiker bevestigd
    project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
    source_conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE,
    source_message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
    source_label TEXT DEFAULT '',    -- leesbare bronvermelding
    source_date TEXT,
    supersedes_id INTEGER REFERENCES memories(id) ON DELETE SET NULL,
    created_by TEXT DEFAULT 'app',   -- app | mcp
    created_at TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS memory_history (
    id INTEGER PRIMARY KEY,
    memory_id INTEGER REFERENCES memories(id) ON DELETE CASCADE,
    changed_at TEXT,
    change TEXT,                     -- JSON met oude waarden + reden
    changed_by TEXT
);

-- Incrementele importstatus per bronbestand
CREATE TABLE IF NOT EXISTS source_files (
    path TEXT PRIMARY KEY,
    source TEXT,
    size INTEGER,
    mtime REAL,
    offset INTEGER DEFAULT 0,
    session_id TEXT,
    last_import_at TEXT,
    last_error TEXT
);

CREATE TABLE IF NOT EXISTS sync_log (
    id INTEGER PRIMARY KEY,
    at TEXT,
    source TEXT,
    trigger TEXT,                    -- hook | watcher | handmatig | upload | importmap
    ok INTEGER,
    detail TEXT,
    new_messages INTEGER DEFAULT 0,
    new_conversations INTEGER DEFAULT 0,
    updated_conversations INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS exclusions (
    source TEXT,
    ext_id TEXT,
    reason TEXT,
    at TEXT,
    PRIMARY KEY(source, ext_id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    content, content='messages', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE OF content ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    text, content='memories', content_rowid='id',
    tokenize='unicode61 remove_diacritics 2'
);
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, text) VALUES('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE OF text ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, text) VALUES('delete', old.id, old.text);
    INSERT INTO memories_fts(rowid, text) VALUES (new.id, new.text);
END;
"""

DEFAULT_TOPICS = [
    ("Business", "#e0a43a", "klant,omzet,bedrijf,marketing,sales,factuur,business,onderneming"),
    ("Studie", "#5aa9e6", "tentamen,studie,college,opdracht,scriptie,leren,cursus"),
    ("Persoonlijke ontwikkeling", "#8bc98b", "gewoonte,doel,motivatie,ontwikkeling,reflectie,gezondheid"),
    ("Programmeren", "#b48ef0", "code,python,javascript,bug,api,git,database,functie,deploy"),
]


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()) + "Z"


def connect(path=None) -> sqlite3.Connection:
    config.ensure_dirs()
    # isolation_level=None: geen impliciete transacties; alleen expliciete BEGIN IMMEDIATE (zie transaction())
    conn = sqlite3.connect(str(path or config.db_path()), timeout=30, check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.execute("PRAGMA synchronous=NORMAL")
    init(conn)
    return conn


def init(conn: sqlite3.Connection) -> None:
    row = None
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    except sqlite3.OperationalError:
        pass
    if row and int(row[0]) >= SCHEMA_VERSION:
        return
    conn.executescript(SCHEMA)
    with transaction(conn):
        if row and int(row[0]) < 2:
            _migrate_tool_only(conn)
        conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (str(SCHEMA_VERSION),))
        if not conn.execute("SELECT 1 FROM topics LIMIT 1").fetchone():
            for name, color, kw in DEFAULT_TOPICS:
                conn.execute("INSERT INTO topics(name,color,keywords,created_at) VALUES(?,?,?,?)", (name, color, kw, now()))


def _migrate_tool_only(conn):
    """v1 → v2: lege antwoorden met alleen toolnamen samenvoegen met het voorgaande antwoord."""
    for m in conn.execute("SELECT id, conversation_id, seq, tools FROM messages WHERE role='assistant' AND content='' "
                          "AND id NOT IN (SELECT message_id FROM attachments) ORDER BY conversation_id, seq").fetchall():
        prev = conn.execute("SELECT id, tools FROM messages WHERE conversation_id=? AND role='assistant' AND seq<? AND content<>'' "
                            "ORDER BY seq DESC LIMIT 1", (m[1], m[2])).fetchone()
        if prev:
            names = [t for t in (prev[1] or "").split(",") if t]
            names += [t for t in (m[3] or "").split(",") if t and t not in names]
            conn.execute("UPDATE messages SET tools=? WHERE id=?", (",".join(names), prev[0]))
        conn.execute("DELETE FROM messages WHERE id=?", (m[0],))
    conn.execute("UPDATE conversations SET message_count=(SELECT COUNT(*) FROM messages WHERE conversation_id=conversations.id)")


@contextmanager
def transaction(conn: sqlite3.Connection):
    """BEGIN IMMEDIATE zodat gelijktijdige hooks/watcher elkaar netjes afwachten."""
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def get_meta(conn, key, default=None):
    r = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return r[0] if r else default


def set_meta(conn, key, value):
    conn.execute("INSERT OR REPLACE INTO meta(key,value) VALUES(?,?)", (key, str(value)))


def log_sync(conn, source, trigger, ok, detail="", new_messages=0, new_conversations=0, updated_conversations=0):
    conn.execute(
        "INSERT INTO sync_log(at,source,trigger,ok,detail,new_messages,new_conversations,updated_conversations)"
        " VALUES(?,?,?,?,?,?,?,?)",
        (now(), source, trigger, 1 if ok else 0, detail[:2000], new_messages, new_conversations, updated_conversations),
    )
    conn.execute("DELETE FROM sync_log WHERE id < (SELECT MAX(id) - 2000 FROM sync_log)")


def get_or_create_project(conn, source, path, name=None):
    if not path:
        return None
    r = conn.execute("SELECT id FROM projects WHERE source=? AND path=?", (source, path)).fetchone()
    if r:
        return r[0]
    if not name:
        name = path.replace("\\", "/").rstrip("/").split("/")[-1] or path
    cur = conn.execute(
        "INSERT INTO projects(name,path,source,created_at) VALUES(?,?,?,?)", (name, path, source, now())
    )
    return cur.lastrowid


def rows(cur):
    return [dict(r) for r in cur.fetchall()]


def dumps(o):
    return json.dumps(o, ensure_ascii=False)
