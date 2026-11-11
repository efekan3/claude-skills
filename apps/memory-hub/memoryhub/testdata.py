"""Duidelijk gemarkeerde testgegevens. Deze zijn NIET afkomstig uit je echte Claude-geschiedenis."""
import json
import zipfile
from pathlib import Path

from . import db

TEST_EXPORT = [
    {
        "uuid": "test-0000-0000-0000-000000000001",
        "name": "[TEST] Lanceerplan webshop",
        "created_at": "2026-03-02T09:00:00.000000Z",
        "updated_at": "2026-03-02T09:20:00.000000Z",
        "account": {"uuid": "test-account"},
        "chat_messages": [
            {"uuid": "test-m-1", "sender": "human", "created_at": "2026-03-02T09:00:00Z", "updated_at": "2026-03-02T09:00:00Z",
             "text": "", "content": [{"type": "text", "text": "Ik wil de webshop op 15 april lanceren. Budget voor advertenties is maximaal 500 euro per maand."}],
             "attachments": [{"file_name": "planning.txt", "file_size": 42, "file_type": "text/plain", "extracted_content": "Week 1: productfoto's\nWeek 2: teksten"}],
             "files": []},
            {"uuid": "test-m-2", "sender": "assistant", "created_at": "2026-03-02T09:01:00Z", "updated_at": "2026-03-02T09:01:00Z",
             "text": "", "content": [{"type": "text", "text": "Goed plan. Ik stel voor om **eerst een e-maillijst** op te bouwen.\n\n```python\nprint('lancering 15 april')\n```\n\nZie ook https://example.com/gids"}],
             "attachments": [], "files": [{"file_name": "logo.png"}]},
        ],
    },
    {
        "uuid": "test-0000-0000-0000-000000000002",
        "name": "[TEST] Studieplanning statistiek",
        "created_at": "2026-04-10T18:00:00.000000Z",
        "updated_at": "2026-04-10T18:05:00.000000Z",
        "account": {"uuid": "test-account"},
        "chat_messages": [
            {"uuid": "test-m-3", "sender": "human", "created_at": "2026-04-10T18:00:00Z", "updated_at": "2026-04-10T18:00:00Z",
             "text": "", "content": [{"type": "text", "text": "Mijn tentamen statistiek is op 3 juni; ik leer het liefst 's ochtends in blokken van 50 minuten."}],
             "attachments": [], "files": []},
            {"uuid": "test-m-4", "sender": "assistant", "created_at": "2026-04-10T18:01:00Z", "updated_at": "2026-04-10T18:01:00Z",
             "text": "", "content": [{"type": "text", "text": "Dan plannen we vier ochtendblokken per week tot 3 juni."}],
             "attachments": [], "files": []},
        ],
    },
]


def write_test_export(path: Path, conversations=None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("conversations.json", json.dumps(conversations or TEST_EXPORT, ensure_ascii=False))
        z.writestr("projects.json", "[]")
        z.writestr("users.json", json.dumps([{"uuid": "test-account", "full_name": "TEST"}]))
    return path


def seed(conn):
    """Importeer de testexport als bron 'test' (gemarkeerd met is_test=1 en [TEST] in de titel)."""
    from . import config, importer_export
    p = write_test_export(config.data_dir() / "testdata" / "claude-export-TEST.zip")
    res = importer_export.import_path(conn, p, "test")
    with db.transaction(conn):
        conn.execute("UPDATE conversations SET is_test=1, source='test', url=NULL WHERE ext_id LIKE 'test-%'")
    return {"note": "Testgesprekken toegevoegd (bron 'test', niet je echte geschiedenis)", **res}
