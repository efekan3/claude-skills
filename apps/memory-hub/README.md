# Memory Hub

Lokaal, persoonlijk archief van je Claude-gesprekken: bewaren, doorzoeken, teruglezen. Claude kan
het archief zelf raadplegen via een skill en een MCP-server.

- **App**: Nederlandstalige webapp op `http://127.0.0.1:8765` (licht/donker), met snelkoppeling.
- **Opslag**: SQLite + FTS5 in je gebruikersmap (niet in deze repo). Alleen de Python-standaardbibliotheek, geen AI-API nodig.
- **Claude Code**: automatisch en incrementeel via hooks (`Stop`, `SessionEnd`, `PreCompact`) plus een achtergrondproces.
- **claude.ai (web/desktop/mobiel)**: import van de officiële gegevensexport (upload of importmap).
- **Skill** `memory-hub` + **MCP-server** `memory-hub` (stdio, eigen implementatie).

```bash
python memory_hub.py install   # eenmalig: skill, hooks, MCP, snelkoppeling, autostart, eerste import
python memory_hub.py open      # app openen
```

Volledige uitleg: **[HANDLEIDING.md](HANDLEIDING.md)**.

| Map | Inhoud |
|---|---|
| `memory_hub.py` | Startpunt / CLI |
| `memoryhub/` | Database, importers, zoeken, geheugen, back-ups, webserver, MCP-server, hook, installer |
| `ui/` | De app (HTML/CSS/JS, geen externe afhankelijkheden) |
| `skill/SKILL.md` | De persoonlijke skill (wordt naar `~/.claude/skills/memory-hub/` gekopieerd) |
| `tests/` | End-to-end tests (`python -m unittest discover -s tests -v`) |
| `start-memory-hub.*` | Startscripts voor Windows, macOS en Linux |
