"""Lokale webserver voor de Memory Hub-app (standaard alleen 127.0.0.1)."""
import hmac
import ipaddress
import json
import mimetypes
import re
import secrets
import threading
import traceback
import urllib.parse
import webbrowser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, backup, config, db, importer_cc, importer_export, store, sync
from .redact import redact

UI_DIR = Path(__file__).resolve().parent.parent / "ui"
_local = threading.local()
MAX_UPLOAD = 1024 * 1024 * 1024  # 1 GB


def conn():
    c = getattr(_local, "conn", None)
    if c is None:
        c = _local.conn = db.connect()
    return c


class ApiError(Exception):
    def __init__(self, status, msg):
        super().__init__(msg)
        self.status = status


ROUTES = []


def route(method, pattern):
    rx = re.compile("^" + pattern + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn))
        return fn
    return deco


def _int(v, d=None):
    try:
        return int(v)
    except (TypeError, ValueError):
        return d


def _filters(q):
    keys = ("source", "project_id", "topic_id", "tag", "date_from", "date_to", "role")
    f = {k: q[k] for k in keys if q.get(k)}
    if q.get("favorite") in ("1", "true"):
        f["favorite"] = True
    return f


# ---------------------------------------------------------------- API

@route("GET", r"/api/overview")
def overview(h, q, body):
    c = conn()
    return {
        "recent": store.search_conversations(c, "", limit=8)["items"],
        "favorites": store.search_conversations(c, "", limit=12, favorite=True)["items"],
        "status": store.sync_status(c),
        "open_actions": store.list_memories(c, kind="actie", status=["actief", "voorstel"], limit=10),
        "version": __version__,
    }


@route("GET", r"/api/status")
def status(h, q, body):
    return store.sync_status(conn())


@route("GET", r"/api/conversations")
def conversations(h, q, body):
    return store.search_conversations(conn(), q.get("q", ""), limit=_int(q.get("limit"), 50), offset=_int(q.get("offset"), 0),
                                      sort=q.get("sort", "recent"), **_filters(q))


@route("GET", r"/api/conversations/(\d+)")
def conversation(h, q, body, cid):
    c = store.get_conversation(conn(), cid, redact_secrets=False if q.get("reveal") == "1" else None)
    if not c:
        raise ApiError(404, "Gesprek niet gevonden")
    return c


@route("POST", r"/api/conversations/(\d+)")
def conversation_update(h, q, body, cid):
    return store.update_conversation(conn(), cid, body or {})


@route("DELETE", r"/api/conversations/(\d+)")
def conversation_delete(h, q, body, cid):
    return store.delete_conversation(conn(), cid, prevent_reimport=q.get("prevent", "1") == "1",
                                     purge_backups=q.get("purge_backups") == "1")


@route("GET", r"/api/conversations/(\d+)/context-pack")
def conversation_pack(h, q, body, cid):
    return {"text": store.context_pack(conn(), cid, q.get("q") or None)}


@route("POST", r"/api/conversations/(\d+)/summary")
def conversation_summary(h, q, body, cid):
    c = conn()
    with db.transaction(c):
        c.execute("UPDATE conversations SET summary_kind='' WHERE id=? AND summary_kind='lokaal-extractief'", (int(cid),))
    s, kind = store.ensure_summary(c, cid)
    return {"summary": s, "summary_kind": kind}


@route("GET", r"/api/conversations/(\d+)/markdown")
def conversation_md(h, q, body, cid):
    md = store.conversation_markdown(conn(), cid, redact_secrets=q.get("redact") == "1")
    return ("file", md.encode("utf-8"), "text/markdown; charset=utf-8", f"gesprek-{cid}.md")


@route("GET", r"/api/conversations/(\d+)/json")
def conversation_json(h, q, body, cid):
    c = store.get_conversation(conn(), cid, redact_secrets=q.get("redact") == "1")
    return ("file", json.dumps(c, ensure_ascii=False, indent=1).encode("utf-8"), "application/json", f"gesprek-{cid}.json")


@route("GET", r"/api/messages/search")
def message_search(h, q, body):
    return store.search_messages(conn(), q.get("q", ""), limit=_int(q.get("limit"), 30), **_filters(q))


@route("GET", r"/api/attachments/(\d+)")
def attachment(h, q, body, aid):
    r = conn().execute("SELECT stored_path, file_type, file_name FROM attachments WHERE id=?", (int(aid),)).fetchone()
    if not r or not r["stored_path"]:
        raise ApiError(404, "Bestand niet beschikbaar")
    p = Path(r["stored_path"]).resolve()
    if config.attachments_dir().resolve() not in p.parents or not p.exists():
        raise ApiError(404, "Bestand niet beschikbaar")
    return ("file", p.read_bytes(), r["file_type"] or "application/octet-stream", None)


@route("GET", r"/api/projects")
def projects(h, q, body):
    return db.rows(conn().execute(
        "SELECT p.*, (SELECT COUNT(*) FROM conversations c WHERE c.project_id=p.id) AS conversations,"
        " (SELECT MAX(COALESCE(updated_at,created_at)) FROM conversations c WHERE c.project_id=p.id) AS last_activity,"
        " (SELECT COUNT(*) FROM memories m WHERE m.project_id=p.id AND m.status IN ('actief','voorstel')) AS memories"
        " FROM projects p ORDER BY last_activity DESC"))


@route("POST", r"/api/projects")
def project_create(h, q, body):
    c = conn()
    with db.transaction(c):
        pid = db.get_or_create_project(c, "handmatig", body.get("name"), body.get("name"))
        c.execute("UPDATE projects SET description=?, color=? WHERE id=?", (body.get("description", ""), body.get("color", ""), pid))
    return {"id": pid}


@route("POST", r"/api/projects/(\d+)")
def project_update(h, q, body, pid):
    c = conn()
    with db.transaction(c):
        for k in ("name", "description", "color"):
            if k in body:
                c.execute(f"UPDATE projects SET {k}=? WHERE id=?", (body[k], int(pid)))
    return {"ok": True}


@route("DELETE", r"/api/projects/(\d+)")
def project_delete(h, q, body, pid):
    c = conn()
    with db.transaction(c):
        c.execute("DELETE FROM projects WHERE id=?", (int(pid),))  # gesprekken blijven, project_id → NULL
    return {"ok": True}


@route("GET", r"/api/topics")
def topics(h, q, body):
    return db.rows(conn().execute(
        "SELECT t.*, (SELECT COUNT(*) FROM conversation_topics ct WHERE ct.topic_id=t.id) AS conversations FROM topics t ORDER BY name"))


@route("POST", r"/api/topics")
def topic_create(h, q, body):
    c = conn()
    if not (body.get("name") or "").strip():
        raise ApiError(400, "Naam is verplicht")
    with db.transaction(c):
        cur = c.execute("INSERT INTO topics(name,color,keywords,created_at) VALUES(?,?,?,?)",
                        (body["name"].strip(), body.get("color", "#6b8afd"), body.get("keywords", ""), db.now()))
    return {"id": cur.lastrowid}


@route("POST", r"/api/topics/(\d+)")
def topic_update(h, q, body, tid):
    c = conn()
    with db.transaction(c):
        for k in ("name", "color", "keywords"):
            if k in body:
                c.execute(f"UPDATE topics SET {k}=? WHERE id=?", (body[k], int(tid)))
    return {"ok": True}


@route("DELETE", r"/api/topics/(\d+)")
def topic_delete(h, q, body, tid):
    c = conn()
    with db.transaction(c):
        c.execute("DELETE FROM topics WHERE id=?", (int(tid),))
    return {"ok": True}


@route("POST", r"/api/topics/apply-rules")
def topic_rules(h, q, body):
    """Wijs onderwerpen toe op basis van trefwoorden (alleen toevoegen, nooit weghalen)."""
    c = conn()
    added = 0
    for t in db.rows(c.execute("SELECT * FROM topics WHERE keywords<>''")):
        kws = [k.strip() for k in t["keywords"].split(",") if k.strip()]
        if not kws:
            continue
        fq = " OR ".join(f'"{re.sub(chr(34), "", k)}"*' for k in kws)
        try:
            ids = {r[0] for r in c.execute("SELECT DISTINCT m.conversation_id FROM messages_fts JOIN messages m ON m.id=messages_fts.rowid"
                                           " WHERE messages_fts MATCH ?", (fq,))}
        except Exception:  # noqa: BLE001
            continue
        like = [r[0] for k in kws for r in c.execute("SELECT id FROM conversations WHERE title LIKE ?", (f"%{k}%",))]
        with db.transaction(c):
            for cid in ids | set(like):
                cur = c.execute("INSERT OR IGNORE INTO conversation_topics VALUES(?,?)", (cid, t["id"]))
                added += cur.rowcount
    return {"added": added}


@route("GET", r"/api/tags")
def tags(h, q, body):
    return [dict(r) for r in conn().execute("SELECT tag, COUNT(*) AS n FROM tags GROUP BY tag ORDER BY tag")]


@route("GET", r"/api/memories")
def memories(h, q, body):
    st = q.get("status", "actief")
    return store.list_memories(conn(), q=q.get("q"), kind=q.get("kind"), status=None if st == "alle" else st.split(","),
                               project_id=_int(q.get("project_id")), origin=q.get("origin"), limit=_int(q.get("limit"), 300))


@route("GET", r"/api/memories/(\d+)")
def memory(h, q, body, mid):
    m = store.get_memory(conn(), mid)
    if not m:
        raise ApiError(404, "Niet gevonden")
    return m


@route("POST", r"/api/memories")
def memory_create(h, q, body):
    return store.save_memory(conn(), body.get("text"), kind=body.get("kind", "feit"), origin=body.get("origin", "user_stated"),
                             project_id=_int(body.get("project_id")), conversation_id=_int(body.get("conversation_id")),
                             message_id=_int(body.get("message_id")), source_note=body.get("source_note", ""),
                             created_by="app", confirmed=bool(body.get("confirmed", body.get("origin", "user_stated") == "user_stated")))


@route("POST", r"/api/memories/(\d+)")
def memory_update(h, q, body, mid):
    changes = {k: body[k] for k in ("text", "status", "kind", "confirmed", "origin", "project_id") if k in body}
    return store.update_memory(conn(), mid, reason=body.get("reason", "aangepast in de app"), changed_by="app", **changes)


@route("DELETE", r"/api/memories/(\d+)")
def memory_delete(h, q, body, mid):
    store.delete_memory(conn(), mid)
    return {"ok": True}


@route("POST", r"/api/sync")
def do_sync(h, q, body):
    return sync.run_once(conn(), "handmatig")


@route("POST", r"/api/import/upload")
def upload(h, q, body):
    name = urllib.parse.unquote(h.headers.get("X-Filename", "export.zip"))
    if not isinstance(body, (bytes, bytearray)) or not body:
        raise ApiError(400, "Leeg bestand")
    try:
        return importer_export.import_upload(conn(), name, bytes(body))
    except ValueError as e:
        raise ApiError(400, str(e)) from e


@route("POST", r"/api/import/scan")
def import_scan(h, q, body):
    return {"results": importer_export.scan_import_folder(conn(), "handmatig")}


@route("POST", r"/api/import/rescan-claude-code")
def rescan_cc(h, q, body):
    c = conn()
    with db.transaction(c):
        c.execute("UPDATE source_files SET size=-1 WHERE source='claude_code'")
    return importer_cc.sync_all(c, "handmatig")


@route("GET", r"/api/backups")
def backups(h, q, body):
    return {"backups": backup.list_backups(), "dir": str(config.backups_dir()),
            "policy": ("Verwijderde gesprekken blijven in oudere back-ups tot die worden opgeruimd, tenzij je bij verwijderen "
                       "'ook uit back-ups wissen' kiest. Bij herstel worden eerdere verwijderingen standaard opnieuw toegepast.")}


@route("POST", r"/api/backups")
def backup_create(h, q, body):
    return {"name": backup.create_backup(conn(), "handmatig").name}


@route("POST", r"/api/backups/([\w\-\.]+)/restore")
def backup_restore(h, q, body, name):
    try:
        return backup.restore_backup(conn(), name, reapply_deletions=(body or {}).get("reapply_deletions", True))
    except ValueError as e:
        raise ApiError(400, str(e)) from e


@route("DELETE", r"/api/backups/([\w\-\.]+)")
def backup_delete(h, q, body, name):
    backup.delete_backup(name)
    return {"ok": True}


@route("POST", r"/api/export")
def export(h, q, body):
    p = store.export_all(conn(), (body or {}).get("format", "json"), redact_secrets=bool((body or {}).get("redact")))
    return {"path": str(p), "name": p.name}


@route("GET", r"/api/export/download")
def export_download(h, q, body):
    p = (config.exports_dir() / Path(q.get("name", "")).name).resolve()
    if p.parent != config.exports_dir().resolve() or not p.exists():
        raise ApiError(404, "Niet gevonden")
    ctype = "application/zip" if p.suffix == ".zip" else "application/json"
    return ("file", p.read_bytes(), ctype, p.name)


@route("GET", r"/api/settings")
def settings_get(h, q, body):
    s = config.load_settings()
    s = dict(s, remote_token="•••" if s.get("remote_token") else "")
    from .install import installation_state
    return {"settings": s, "paths": {"root": str(config.root_dir()), "data": str(config.data_dir()), "database": str(config.db_path()),
                                     "backups": str(config.backups_dir()), "import": str(config.import_dir()),
                                     "exports": str(config.exports_dir()), "claude_projects": [str(p) for p in config.projects_dirs()]},
            "installation": installation_state()}


@route("POST", r"/api/settings")
def settings_set(h, q, body):
    body = dict(body or {})
    body.pop("remote_token", None)
    if body.get("allow_remote") and not config.load_settings().get("remote_token"):
        body["remote_token"] = secrets.token_urlsafe(24)
    s = config.save_settings(body)
    return {"settings": dict(s, remote_token="•••" if s.get("remote_token") else ""),
            "restart_needed": any(k in body for k in ("host", "port", "allow_remote"))}


@route("POST", r"/api/settings/remote-token")
def settings_token(h, q, body):
    if not h.is_loopback():
        raise ApiError(403, "Alleen vanaf deze computer")
    s = config.save_settings({"remote_token": secrets.token_urlsafe(24)})
    return {"token": s["remote_token"]}


@route("POST", r"/api/pause")
def pause(h, q, body):
    want = bool((body or {}).get("paused"))
    c = conn()
    if not want and config.load_settings().get("paused"):
        importer_cc.skip_ahead_all(c)  # wat tijdens de pauze gebeurde, wordt niet alsnog gearchiveerd
    s = config.save_settings({"paused": want, "paused_since": db.now() if want else None})
    with db.transaction(c):
        db.log_sync(c, "systeem", "pauze", True, "archivering gepauzeerd" if want else "archivering hervat")
    return {"paused": s["paused"]}


@route("GET", r"/api/exclusions")
def exclusions(h, q, body):
    return db.rows(conn().execute("SELECT * FROM exclusions ORDER BY at DESC"))


@route("POST", r"/api/exclusions/remove")
def exclusion_remove(h, q, body):
    store.unexclude(conn(), body["source"], body["ext_id"])
    return {"ok": True}


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    server_version = "MemoryHub/" + __version__

    def log_message(self, fmt, *args):  # geen inhoud in logs
        pass

    def is_loopback(self):
        try:
            return ipaddress.ip_address(self.client_address[0]).is_loopback
        except ValueError:
            return False

    def _allowed(self):
        s = config.load_settings()
        host = (self.headers.get("Host") or "").split(":")[0].strip("[]").lower()
        if self.is_loopback():
            # DNS-rebinding voorkomen
            if host not in ("127.0.0.1", "localhost", "::1") and not s.get("allow_remote"):
                return False
            if host in ("127.0.0.1", "localhost", "::1"):
                return True
        if not s.get("allow_remote") or not s.get("remote_token"):
            return False
        token = s["remote_token"]
        ck = SimpleCookie(self.headers.get("Cookie", ""))
        given = ck["mh_token"].value if "mh_token" in ck else ""
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if not given and qs.get("token"):
            given = qs["token"][0]
            self._set_cookie = f"mh_token={given}; HttpOnly; SameSite=Strict; Path=/"
        return hmac.compare_digest(given.encode(), token.encode())

    def _send(self, status, data, ctype="application/json; charset=utf-8", filename=None):
        if not isinstance(data, (bytes, bytearray)):
            data = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
        if filename:
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{urllib.parse.quote(filename)}")
        if getattr(self, "_set_cookie", None):
            self.send_header("Set-Cookie", self._set_cookie)
        self.end_headers()
        self.wfile.write(data)

    def _handle(self, method):
        self._set_cookie = None
        if not self._allowed():
            return self._send(403, {"error": "Geen toegang. Memory Hub is standaard alleen vanaf deze computer bereikbaar."})
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        q = {k: v[-1] for k, v in urllib.parse.parse_qs(parsed.query).items()}
        if method != "GET" and self.headers.get("X-MemoryHub") != "1":
            return self._send(403, {"error": "Ontbrekende X-MemoryHub-header (CSRF-bescherming)"})
        if not path.startswith("/api/"):
            return self._static(path)
        body = None
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_UPLOAD:
            return self._send(413, {"error": "Bestand te groot"})
        if length:
            raw = self.rfile.read(length)
            if (self.headers.get("Content-Type") or "").startswith("application/json"):
                try:
                    body = json.loads(raw.decode("utf-8"))
                except ValueError:
                    return self._send(400, {"error": "Ongeldige JSON"})
            else:
                body = raw
        for m, rx, fn in ROUTES:
            if m != method:
                continue
            mt = rx.match(path)
            if mt:
                try:
                    res = fn(self, q, body, *mt.groups())
                    if isinstance(res, tuple) and res and res[0] == "file":
                        return self._send(200, res[1], res[2], res[3])
                    return self._send(200, res)
                except ApiError as e:
                    return self._send(e.status, {"error": str(e)})
                except ValueError as e:
                    return self._send(400, {"error": redact(str(e))})
                except Exception as e:  # noqa: BLE001
                    _log_error(f"{method} {path}: {e}\n{traceback.format_exc()}")
                    return self._send(500, {"error": "Interne fout: " + redact(str(e))})
        return self._send(404, {"error": "Onbekende route"})

    def _static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        p = (UI_DIR / path.lstrip("/")).resolve()
        if UI_DIR.resolve() not in p.parents or not p.is_file():
            p = UI_DIR / "index.html"
        ctype = mimetypes.guess_type(str(p))[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in ("application/javascript",):
            ctype += "; charset=utf-8"
        return self._send(200, p.read_bytes(), ctype)

    def do_GET(self):
        self._handle("GET")

    def do_POST(self):
        self._handle("POST")

    def do_DELETE(self):
        self._handle("DELETE")


def _log_error(msg):
    try:
        with open(config.logs_dir() / "server.log", "a", encoding="utf-8") as f:
            f.write(f"{db.now()} {redact(msg)}\n")
    except OSError:
        pass


def url():
    s = config.load_settings()
    return f"http://127.0.0.1:{s.get('port', 8765)}/"


def is_running(timeout=1.0):
    import urllib.request
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # nooit via een proxy
        req = urllib.request.Request(url() + "api/status")
        with opener.open(req, timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def serve(open_browser=True, port=None):
    s = config.load_settings()
    host = "0.0.0.0" if s.get("allow_remote") else "127.0.0.1"
    port = int(port or s.get("port", 8765))
    db.connect().close()
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    sync.start_background("watcher")
    print(f"Memory Hub draait op http://127.0.0.1:{port}/  (gegevens: {config.data_dir()})", flush=True)
    if s.get("allow_remote"):
        print("Let op: externe toegang staat aan en vereist het toegangstoken.", flush=True)
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(f"http://127.0.0.1:{port}/")).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
