"""End-to-end tests voor Memory Hub. Draaien met:  python -m unittest discover -s tests -v

Alle tests gebruiken een tijdelijke MEMORY_HUB_HOME en CLAUDE_CONFIG_DIR met duidelijk
gemarkeerde TEST-gegevens; je echte archief en ~/.claude worden niet aangeraakt.
"""
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

TMP = Path(tempfile.mkdtemp(prefix="memoryhub-test-"))
os.environ["MEMORY_HUB_HOME"] = str(TMP / "home")
os.environ["CLAUDE_CONFIG_DIR"] = str(TMP / "claude")
PROJ = TMP / "claude" / "projects" / "-tmp-testproject"
PROJ.mkdir(parents=True)

from memoryhub import backup, config, db, importer_cc, importer_export, store  # noqa: E402
from memoryhub.testdata import TEST_EXPORT, write_test_export  # noqa: E402


def rec(uuid, parent, typ, content, ts, **kw):
    r = {"type": typ, "uuid": uuid, "parentUuid": parent, "timestamp": ts, "sessionId": kw.pop("sid", "sess-1"),
         "cwd": "/tmp/testproject", "gitBranch": "main", "isSidechain": False,
         "message": {"role": typ, "content": content}}
    if typ == "assistant":
        r["message"]["id"] = kw.pop("mid", "msg_" + uuid)
    r.update(kw)
    return json.dumps(r) + "\n"


def write(path, lines, mode="a"):
    with open(path, mode, encoding="utf-8") as f:
        f.write("".join(lines))


class T01_ClaudeCodeImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = db.connect()
        cls.f = PROJ / "sess-1.jsonl"

    def test_a_full_import_visible_text_only(self):
        write(self.f, [
            json.dumps({"type": "queue-operation", "operation": "enqueue"}) + "\n",
            rec("u1", None, "user", "[TEST] Mijn favoriete database is PostgreSQL en ik deploy altijd op vrijdag niet.", "2026-01-05T10:00:00Z"),
            rec("a1", "u1", "assistant", [{"type": "thinking", "thinking": "geheim denkwerk"}], "2026-01-05T10:00:01Z", mid="m1"),
            rec("a2", "a1", "assistant", [{"type": "text", "text": "Begrepen. Hier is een voorbeeld:\n```sql\nSELECT 1;\n```"}], "2026-01-05T10:00:02Z", mid="m1"),
            rec("a3", "a2", "assistant", [{"type": "tool_use", "name": "Bash", "id": "t1", "input": {}}], "2026-01-05T10:00:03Z", mid="m1"),
            rec("r1", "a3", "user", [{"type": "tool_result", "tool_use_id": "t1", "content": "tool output"}], "2026-01-05T10:00:04Z", toolUseResult={}),
            rec("a4", "r1", "assistant", [{"type": "text", "text": "Klaar, zie https://example.com/docs"}], "2026-01-05T10:00:05Z", mid="m2"),
        ], "w")
        r = importer_cc.import_file(self.conn, self.f)
        self.assertTrue(r["new_conversation"])
        msgs = store.get_conversation(self.conn, 1)["messages"]
        self.assertEqual([m["role"] for m in msgs], ["user", "assistant", "assistant"])  # tool-only record → geen leeg bericht
        joined = "\n".join(m["content"] for m in msgs)
        self.assertNotIn("geheim denkwerk", joined)
        self.assertNotIn("tool output", joined)
        self.assertIn("```sql", joined)
        self.assertIn("https://example.com/docs", joined)
        self.assertIn("Bash", msgs[1]["tools"])

    def test_b_reimport_no_duplicates(self):
        before = self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        importer_cc.import_file(self.conn, self.f, force=True)
        importer_cc.sync_all(self.conn)
        self.assertEqual(before, self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0])

    def test_c_partial_line_then_completed(self):
        line = rec("u2", "a4", "user", "[TEST] Vertraagd bericht over Kubernetes", "2026-01-05T10:05:00Z")
        write(self.f, [line[:40]])  # half weggeschreven
        r = importer_cc.import_file(self.conn, self.f)
        self.assertEqual(r["new_messages"], 0)
        write(self.f, [line[40:]])
        r = importer_cc.import_file(self.conn, self.f)
        self.assertEqual(r["new_messages"], 1)
        self.assertTrue(store.search_messages(self.conn, "Kubernetes"))

    def test_d_branch_rewind(self):
        # terugspoelen: nieuw antwoord op u2's ouder (a4) → u2 ligt op verlaten tak
        write(self.f, [rec("u3", "a4", "user", "[TEST] Andere vraag na terugspoelen", "2026-01-05T10:10:00Z"),
                       rec("a5", "u3", "assistant", [{"type": "text", "text": "Antwoord op de nieuwe tak"}], "2026-01-05T10:10:01Z")])
        importer_cc.import_file(self.conn, self.f)
        rows = {r["ext_id"]: r["on_main_branch"] for r in db.rows(self.conn.execute("SELECT ext_id,on_main_branch FROM messages"))}
        self.assertEqual(rows["u2"], 0)
        self.assertEqual(rows["u3"], 1)
        self.assertEqual(rows["u1"], 1)

    def test_e_resumed_session_copy_not_duplicated(self):
        f2 = PROJ / "sess-2.jsonl"
        write(f2, [rec("u1", None, "user", "[TEST] Mijn favoriete database is PostgreSQL en ik deploy altijd op vrijdag niet.", "2026-01-05T10:00:00Z", sid="sess-2"),
                   rec("u9", "u1", "user", "[TEST] Vervolg in hervatte sessie", "2026-01-06T09:00:00Z", sid="sess-2")], "w")
        importer_cc.import_file(self.conn, f2)
        n = self.conn.execute("SELECT COUNT(*) FROM messages WHERE ext_id='u1'").fetchone()[0]
        self.assertEqual(n, 1)
        self.assertTrue(store.search_messages(self.conn, "hervatte sessie"))

    def test_f_concurrent_sessions(self):
        files = []
        for i in range(4):
            f = PROJ / f"par-{i}.jsonl"
            write(f, [rec(f"p{i}-{j}", None, "user", f"[TEST] parallel {i} bericht {j}", f"2026-02-01T10:0{j}:00Z", sid=f"par-{i}") for j in range(5)], "w")
            files.append(f)
        errors = []

        def worker(f):
            try:
                c = db.connect()
                for _ in range(3):
                    importer_cc.import_file(c, f, force=True)
                importer_cc.sync_all(c)
                c.close()
            except Exception as e:  # noqa: BLE001
                errors.append(e)
        ts = [threading.Thread(target=worker, args=(f,)) for f in files for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])
        n = self.conn.execute("SELECT COUNT(*) FROM messages WHERE content LIKE '[TEST] parallel%'").fetchone()[0]
        self.assertEqual(n, 20)

    def test_g_context_pack_not_reindexed_as_new_knowledge(self):
        f = PROJ / "sess-pack.jsonl"
        write(f, [rec("cp1", None, "user", importer_cc.CONTEXT_PACK_MARKER + "\n[TEST] oude context Zeppelinplan", "2026-03-01T10:00:00Z", sid="sess-pack")], "w")
        importer_cc.import_file(self.conn, f)
        self.assertEqual(store.search_messages(self.conn, "Zeppelinplan"), [])
        self.assertTrue(store.search_messages(self.conn, "Zeppelinplan", include_context_packs=True))

    def test_h_opt_out_marker(self):
        f = PROJ / "sess-private.jsonl"
        write(f, [rec("pv1", None, "user", "[TEST] dit is prive [geen-archief] Narwalgeheim", "2026-03-01T10:00:00Z", sid="sess-private")], "w")
        importer_cc.import_file(self.conn, f)
        self.assertEqual(store.search_messages(self.conn, "Narwalgeheim"), [])

    def test_i_hook_entry(self):
        f = PROJ / "sess-hook.jsonl"
        write(f, [rec("h1", None, "user", "[TEST] via hook opgeslagen Flamingo", "2026-03-02T10:00:00Z", sid="sess-hook")], "w")
        p = subprocess.run([sys.executable, str(ROOT / "memory_hub.py"), "hook"],
                           input=json.dumps({"hook_event_name": "Stop", "session_id": "sess-hook", "transcript_path": str(f)}),
                           capture_output=True, text=True, timeout=60)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout.strip(), "")  # niets terug in de context
        self.assertTrue(store.search_messages(self.conn, "Flamingo"))


class T02_ExportImport(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = db.connect()
        cls.zip = write_test_export(TMP / "export-TEST.zip")

    def test_a_full_import(self):
        r = importer_export.import_path(self.conn, self.zip)
        self.assertEqual(r["new_conversations"], 2)
        self.assertEqual(r["new_messages"], 4)
        c = self.conn.execute("SELECT * FROM conversations WHERE ext_id=?", (TEST_EXPORT[0]["uuid"],)).fetchone()
        self.assertEqual(c["url"], "https://claude.ai/chat/" + TEST_EXPORT[0]["uuid"])
        conv = store.get_conversation(self.conn, c["id"])
        self.assertEqual(len(conv["messages"]), 2)
        atts = [a for m in conv["messages"] for a in m["attachments"]]
        self.assertTrue(any(a["file_name"] == "planning.txt" and a["available"] for a in atts))
        self.assertTrue(any(a["file_name"] == "logo.png" and not a["available"] for a in atts))
        self.assertTrue(conv["missing_info"])  # eerlijk: bestanden ontbreken

    def test_b_reimport_and_update(self):
        r = importer_export.import_path(self.conn, self.zip)
        self.assertEqual((r["new_conversations"], r["new_messages"]), (0, 0))
        updated = json.loads(json.dumps(TEST_EXPORT))
        updated[1]["updated_at"] = "2026-05-01T00:00:00Z"
        updated[1]["chat_messages"].append({"uuid": "test-m-5", "sender": "human", "created_at": "2026-05-01T00:00:00Z",
                                            "content": [{"type": "text", "text": "[TEST] Nieuw bericht na export-update"}]})
        updated.append({"uuid": "test-new-conv", "name": "[TEST] Nieuw gesprek", "created_at": "2026-05-02T00:00:00Z",
                        "updated_at": "2026-05-02T00:00:00Z", "chat_messages": []})
        z2 = write_test_export(TMP / "export2-TEST.zip", updated)
        r = importer_export.import_path(self.conn, z2)
        self.assertEqual(r["new_conversations"], 1)
        self.assertEqual(r["updated_conversations"], 1)
        self.assertEqual(r["new_messages"], 1)

    def test_c_import_folder(self):
        shutil.copy(self.zip, config.import_dir() / "export-TEST.zip")
        res = importer_export.scan_import_folder(self.conn)
        self.assertTrue(res and res[0]["ok"])
        self.assertFalse((config.import_dir() / "export-TEST.zip").exists())


class T03_SearchMemoryPersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = db.connect()

    def test_a_search_old_statement(self):
        hits = store.search_messages(self.conn, "budget advertenties")
        self.assertTrue(hits)
        m = self.conn.execute("SELECT ext_id FROM messages WHERE id=?", (hits[0]["message_id"],)).fetchone()
        self.assertEqual(m["ext_id"], "test-m-1")
        self.assertIn("\u0002", hits[0]["snippet"])
        convs = store.search_conversations(self.conn, '"15 april"')
        self.assertTrue(convs["items"][0]["hits"])

    def test_b_memory_origin_and_correction(self):
        hit = store.search_messages(self.conn, "budget advertenties")[0]
        m = store.save_memory(self.conn, "[TEST] Advertentiebudget max 500 euro per maand", kind="beslissing", origin="user_stated",
                              message_id=hit["message_id"])
        self.assertEqual(m["status"], "actief")
        self.assertIn("Lanceerplan", m["source_label"])
        s = store.save_memory(self.conn, "[TEST] Begin met een e-maillijst", kind="beslissing", origin="assistant_suggested")
        self.assertEqual(s["status"], "voorstel")
        c = store.save_memory(self.conn, "[TEST] Advertentiebudget max 800 euro", kind="beslissing", origin="user_stated")
        self.assertTrue(c["mogelijk_tegenstrijdig"])
        new = store.update_memory(self.conn, m["id"], reason="gecorrigeerd", text="[TEST] Advertentiebudget max 800 euro per maand")
        self.assertEqual(store.get_memory(self.conn, m["id"])["status"], "vervangen")
        self.assertEqual(new["supersedes_id"], m["id"])
        # oorspronkelijke gesprekstekst blijft onveranderd
        self.assertIn("500 euro", self.conn.execute("SELECT content FROM messages WHERE id=?", (hit["message_id"],)).fetchone()[0])

    def test_c_redaction(self):
        f = PROJ / "sess-secret.jsonl"
        write(f, [rec("s1", None, "user", "[TEST] mijn key is sk-ant-api03-ABCDEFGHIJKLMNOPQRSTUV en password=Hunter2Hunter2", "2026-03-03T10:00:00Z", sid="sess-secret")], "w")
        importer_cc.import_file(self.conn, f)
        hit = store.search_messages(self.conn, "mijn key")[0]
        self.assertNotIn("sk-ant-api03", hit["snippet"])
        conv = store.get_conversation(self.conn, hit["conversation_id"])
        self.assertNotIn("Hunter2Hunter2", conv["messages"][0]["content"])
        raw = store.get_conversation(self.conn, hit["conversation_id"], redact_secrets=False)
        self.assertIn("Hunter2Hunter2", raw["messages"][0]["content"])  # origineel bewaard

    def test_d_persistence_new_process(self):
        out = subprocess.run([sys.executable, str(ROOT / "memory_hub.py"), "search", "Flamingo"], capture_output=True, text=True, timeout=60)
        self.assertIn("Flamingo", out.stdout)
        self.assertTrue(config.db_path().exists())
        self.assertTrue(str(config.db_path()).startswith(str(TMP / "home")))

    def test_e_context_pack(self):
        cid = self.conn.execute("SELECT id FROM conversations WHERE title LIKE '%Lanceerplan%'").fetchone()[0]
        pack = store.context_pack(self.conn, cid)
        self.assertTrue(pack.startswith(importer_cc.CONTEXT_PACK_MARKER))
        self.assertIn("https://claude.ai/chat/", pack)
        self.assertIn("800 euro", pack)


class T04_MCP(unittest.TestCase):
    def rpc(self, proc, msg):
        proc.stdin.write(json.dumps(msg) + "\n")
        proc.stdin.flush()
        if "id" not in msg:
            return None
        return json.loads(proc.stdout.readline())

    def test_mcp_roundtrip(self):
        p = subprocess.Popen([sys.executable, str(ROOT / "memory_hub.py"), "mcp"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             text=True, encoding="utf-8")
        try:
            r = self.rpc(p, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}})
            self.assertEqual(r["result"]["serverInfo"]["name"], "memory-hub")
            self.rpc(p, {"jsonrpc": "2.0", "method": "notifications/initialized"})
            tools = {t["name"] for t in self.rpc(p, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]}
            self.assertTrue({"search_conversations", "get_conversation", "get_project_context", "save_memory", "update_memory", "get_sync_status"} <= tools)

            def call(i, name, args):
                res = self.rpc(p, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": args}})["result"]
                self.assertFalse(res["isError"], res)
                return json.loads(res["content"][0]["text"])
            s = call(3, "search_conversations", {"query": "PostgreSQL"})
            self.assertIn("HISTORISCHE GEGEVENS", s["_let_op"])
            self.assertTrue(s["treffers"])
            g = call(4, "get_conversation", {"conversation_id": s["treffers"][0]["conversation_id"], "message_id": s["treffers"][0]["message_id"], "limit": 3})
            self.assertTrue(any("PostgreSQL" in m["text"] for m in g["messages"]))
            ctx = call(5, "get_project_context", {"project": "/tmp/testproject", "query": "database"})
            self.assertEqual(ctx["project"]["path"], "/tmp/testproject")
            sv = call(6, "save_memory", {"text": "[TEST] Gebruikt PostgreSQL", "kind": "voorkeur", "origin": "user_stated", "project": "/tmp/testproject",
                                         "conversation_id": s["treffers"][0]["conversation_id"]})
            # nieuw project dat nog niet bestaat (regressie: 'transaction within a transaction')
            sv2 = call(11, "save_memory", {"text": "[TEST] Voorkeur SQLite", "kind": "voorkeur", "origin": "user_stated", "project": "Gloednieuw testproject"})
            self.assertEqual(sv2["opgeslagen"]["project"], "Gloednieuw testproject")
            sv3 = call(12, "save_memory", {"text": "[TEST] Tweede item zelfde project", "kind": "doel", "origin": "inferred", "project": "Gloednieuw testproject"})
            self.assertEqual(sv3["opgeslagen"]["status"], "voorstel")
            up = call(7, "update_memory", {"memory_id": sv["opgeslagen"]["memory_id"], "status": "afgerond", "reason": "test"})
            self.assertEqual(up["bijgewerkt"]["status"], "afgerond")
            st = call(8, "get_sync_status", {})
            self.assertIn("sources", st)
            none = call(9, "search_conversations", {"query": "xyzzyniks"})
            self.assertIn("verzin", none["melding"])
            bad = self.rpc(p, {"jsonrpc": "2.0", "id": 10, "method": "tools/call", "params": {"name": "save_memory", "arguments": {"text": "x", "kind": "voorkeur", "origin": "verzonnen"}}})
            self.assertTrue(bad["result"]["isError"])
        finally:
            p.stdin.close()
            p.wait(timeout=10)


class T05_DeleteBackupRestore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = db.connect()

    def test_delete_backup_restore(self):
        conv = self.conn.execute("SELECT id, ext_id FROM conversations WHERE ext_id='sess-1'").fetchone()
        store.save_memory(self.conn, "[TEST] afgeleid uit sess-1", kind="feit", origin="inferred", conversation_id=conv["id"])
        b = backup.create_backup(self.conn, "test")
        self.assertTrue(b.exists())
        res = store.delete_conversation(self.conn, conv["id"])
        self.assertGreaterEqual(res["memories_deleted"], 1)
        self.assertEqual(store.search_messages(self.conn, "PostgreSQL"), [])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM memories WHERE text LIKE '%afgeleid uit sess-1%'").fetchone()[0], 0)
        # FTS-index echt leeg voor deze tekst
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH 'Kubernetes'").fetchone()[0], 0)
        # transcript bestaat nog, maar wordt niet opnieuw geïmporteerd
        importer_cc.import_file(self.conn, PROJ / "sess-1.jsonl", force=True)
        self.assertEqual(store.search_messages(self.conn, "Kubernetes"), [])
        # herstel: verwijdering wordt standaard opnieuw toegepast
        r = backup.restore_backup(self.conn, b.name)
        self.assertEqual(r["deletions_reapplied"], 1)
        self.assertEqual(store.search_messages(self.conn, "Kubernetes"), [])
        self.assertTrue(store.search_messages(self.conn, "Flamingo"))
        # herstel zonder opnieuw toepassen brengt het terug
        r = backup.restore_backup(self.conn, b.name, reapply_deletions=False)
        self.assertTrue(store.search_messages(self.conn, "Kubernetes"))
        # verwijderen mét opschonen van back-ups
        conv = self.conn.execute("SELECT id FROM conversations WHERE ext_id='sess-1'").fetchone()
        res = store.delete_conversation(self.conn, conv["id"], purge_backups=True)
        self.assertGreaterEqual(res["backups_cleaned"], 1)
        import sqlite3
        for bf in config.backups_dir().glob("*.db"):
            c = sqlite3.connect(bf)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM conversations WHERE ext_id='sess-1'").fetchone()[0], 0, bf.name)
            c.close()

    def test_export_json_markdown(self):
        j = store.export_all(self.conn, "json")
        data = json.loads(j.read_text(encoding="utf-8"))
        self.assertTrue(data["conversations"])
        z = store.export_all(self.conn, "markdown")
        self.assertTrue(z.exists() and z.suffix == ".zip")


class T06_WebAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s = socket.socket(); s.bind(("127.0.0.1", 0)); cls.port = s.getsockname()[1]; s.close()
        cls.proc = subprocess.Popen([sys.executable, str(ROOT / "memory_hub.py"), "serve", "--no-browser", "--port", str(cls.port)],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                socket.create_connection(("127.0.0.1", cls.port), timeout=0.2).close()
                break
            except OSError:
                time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=10)

    def req(self, method, path, body=None, headers=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        h = {"X-MemoryHub": "1", "Content-Type": "application/json"}
        h.update(headers or {})
        c.request(method, path, body=json.dumps(body) if body is not None else None, headers=h)
        r = c.getresponse()
        data = r.read()
        return r.status, (json.loads(data) if r.getheader("Content-Type", "").startswith("application/json") else data)

    def test_endpoints(self):
        st, d = self.req("GET", "/api/overview")
        self.assertEqual(st, 200)
        self.assertIn("status", d)
        st, d = self.req("GET", "/api/conversations?q=Flamingo")
        self.assertEqual(st, 200)
        self.assertTrue(d["items"])
        st, html = self.req("GET", "/")
        self.assertIn(b"Memory Hub", html)
        st, _ = self.req("POST", "/api/backups", {}, {"X-MemoryHub": ""})
        self.assertEqual(st, 403)  # CSRF-header verplicht
        st, _ = self.req("GET", "/api/status", headers={"Host": "evil.example"})
        self.assertEqual(st, 403)  # DNS-rebinding geblokkeerd
        st, d = self.req("POST", "/api/memories", {"text": "[TEST] via app", "kind": "doel", "origin": "user_stated"})
        self.assertEqual(st, 200)
        st, d = self.req("POST", "/api/pause", {"paused": True})
        self.assertTrue(d["paused"])
        st, d = self.req("POST", "/api/pause", {"paused": False})
        self.assertFalse(d["paused"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
