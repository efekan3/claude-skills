# Memory Hub — handleiding

Memory Hub is je persoonlijke, lokale archief van gesprekken met Claude. Je kunt er gesprekken
in bewaren, doorzoeken en teruglezen. Claude kan het archief in nieuwe Claude Code-sessies zelf
raadplegen via de skill `memory-hub` en de bijbehorende MCP-server.

Alles draait op je eigen computer: SQLite met full-text search, zonder betaald abonnement en
zonder extra AI-API. Er gaat geen chatinhoud naar een externe dienst.

---

## 1. Installeren (eenmalig)

Nodig: **Python 3.9 of nieuwer** (alleen de standaardbibliotheek) en **Claude Code**.

```bash
cd claude-skills/apps/memory-hub
python memory_hub.py install
```

Op macOS/Linux gebruik je `python3`. Op Windows werkt ook `py -3 memory_hub.py install`.

De installer doet het volgende, en maakt **eerst een kopie van elk configuratiebestand** dat
hij aanpast (in `<gegevensmap>/config-backups/`):

| Stap | Wat |
|---|---|
| Programma | De code wordt gekopieerd naar een vaste map (zie §5). Hooks blijven daardoor werken als je de repo verplaatst. |
| Skill | `~/.claude/skills/memory-hub/SKILL.md` (persoonlijke skill, werkt in al je projecten). |
| Hooks | `Stop`, `SessionEnd` en `PreCompact` in `~/.claude/settings.json`. Ze draaien asynchroon en hinderen Claude Code niet. Je bestaande hooks blijven staan. |
| MCP-server | `claude mcp add --scope user memory-hub …` (gebruikersniveau, in `~/.claude.json`). |
| Snelkoppeling | Windows: `Memory Hub.bat` op het bureaublad en in het Startmenu. macOS: `~/Applications/Memory Hub.command`. Linux: menu-item + `~/.local/bin/memory-hub`. |
| Autostart | Het achtergrondproces start bij het inloggen, zodat archivering doorgaat als de app dicht is. Uitzetten kan met `--no-autostart`. |
| Eerste import | Alle Claude Code-transcripten die nu op je schijf staan, worden geïmporteerd. |

Start daarna een **nieuwe** Claude Code-sessie, zodat hooks, skill en MCP geladen worden.
Controleer met `claude mcp list`: daar moet `memory-hub … ✓ Connected` bij staan.

**Tip:** Claude Code verwijdert transcripten standaard na **30 dagen** (`cleanupPeriodDays`).
Memory Hub bewaart ze, mits ze binnen die periode zijn geïmporteerd. Wil je dat Claude Code ze
zelf ook langer bewaart:
`python memory_hub.py install --keep-transcripts-days 365`

### Ongedaan maken

```bash
python memory_hub.py uninstall
```

Dit haalt de hooks, de MCP-registratie, de skill en de autostart weg. **Je archief blijft staan.**
De oude configuratiebestanden staan in `config-backups/`.

---

## 2. De app openen

- Gebruik de snelkoppeling **Memory Hub**,
- of typ `python memory_hub.py open` (in de programmamap),
- of open `http://127.0.0.1:8765/` als het achtergrondproces al draait.

### Schermen

| Scherm | Wat je er doet |
|---|---|
| **Overzicht** | Recente gesprekken, favorieten, openstaande acties en de synchronisatiestatus per bron (automatisch of handmatig, laatste opslag, fouten, achterstand). Hier staan ook *Nu synchroniseren* en *Pauzeren*. |
| **Alle gesprekken** | Zoeken in alle berichten (`"exacte zin"`, `OR`), filteren op bron, project, onderwerp, label, afzender en datum, sorteren. Klik op een fragment om direct naar dat bericht te springen. |
| **Gesprek** | De volledige chat met opmaak, codeblokken, links en bijlagen. Zoeken binnen het gesprek (↑/↓), favoriet maken, titel wijzigen (klik op de titel), project, onderwerpen, labels en notities. Verder: lokale samenvatting, *Bewaar in geheugen* per bericht, export naar Markdown/JSON en verwijderen. |
| **Verdergaan met dit gesprek** | Maakt een compact contextpakket: samenvatting, relevante afspraken, laatste berichten en bronverwijzingen, met geheimen gemaskeerd. Plak het in een nieuw gesprek. *Open origineel* verschijnt alleen als er een geldige link is (claude.ai). Bij Claude Code krijg je de hervat-opdracht. |
| **Projecten & onderwerpen** | Projecten komen automatisch uit je werkmappen en claude.ai-projecten. Je kunt ze hernoemen en beschrijven. Onderwerpen (Business, Studie, Persoonlijke ontwikkeling, Programmeren …) zijn volledig aan te passen, met optionele trefwoorden voor automatisch toewijzen. |
| **Geheugen** | Voorkeuren, beslissingen, doelen, acties en feiten, steeds met herkomst (*door jou gezegd*, *voorgesteld door Claude* of *afgeleid*), status, bron en datum. Voorstellen bevestigen, acties afronden en items corrigeren kan hier. Bij een correctie blijft de oude versie als ‘vervangen’ bewaard. |
| **Import & instellingen** | Status van bronnen en koppelingen, upload van claude.ai-exports, de importmap, privacy-instellingen, uitsluitingen, opslaglocatie, export, back-ups, thema en externe toegang. |

---

## 3. Bronnen: wat synchroniseert automatisch?

| Bron | Hoe | Automatisch? |
|---|---|---|
| **Claude Code** (CLI, IDE, desktop-Code) | Lokale transcripten in `~/.claude/projects/*/*.jsonl` | **Ja.** Na elk antwoord via de Stop-hook, bij afsluiten via SessionEnd, en elke 30 s via het achtergrondproces als vangnet. |
| **claude.ai web, desktop-chat en mobiel** | Officiële gegevensexport | **Nee, handmatige import nodig.** Er is geen officiële API om je claude.ai-geschiedenis op te halen. Een skill of API-sleutel geeft daar geen toegang toe. |

### claude.ai-gesprekken importeren

1. Ga op claude.ai naar **Instellingen → Privacy → Gegevens exporteren**.
2. Je ontvangt een e-mail met een **.zip**. Download die.
3. Kies één van deze mogelijkheden:
   - In de app: **Import & instellingen** → sleep de .zip in het vak.
   - Of zet de .zip in de **importmap** (zie §5). Zolang Memory Hub draait, wordt hij binnen ongeveer 30 s opgepakt en daarna naar `import/verwerkt/` verplaatst.
   - Of via de opdrachtregel: `python memory_hub.py import pad/naar/export.zip`

Herhaal dit bijvoorbeeld maandelijks. Bij een nieuwe export worden nieuwe gesprekken, nieuwe
berichten en bijgewerkte gesprekken herkend. Niets wordt dubbel opgeslagen.

**Wat de export níet bevat:** de bestanden zelf (afbeeldingen, pdf's). Alleen de bestandsnaam is
bekend, en voor tekstbijlagen soms de geëxtraheerde tekst. De app toont dit met
"📎 bestand (ontbreekt)" en een waarschuwing bovenaan het gesprek.

### Hoe Claude Code-archivering betrouwbaar blijft

- **Incrementeel**: per transcript wordt de positie van de laatste volledige regel onthouden. Een half weggeschreven regel wordt bij de volgende ronde opnieuw gelezen.
- **Geen duplicaten**: elk bericht heeft een vaste ID. Opnieuw importeren, gelijktijdige hooks en de watcher leveren nooit dubbele berichten op.
- **Hervatte gesprekken** die oude berichten naar een nieuw bestand kopiëren, worden herkend.
- **Vertakkingen**: na terugspoelen of bewerken blijven berichten op een verlaten tak bewaard. Ze zijn standaard verborgen en in de app als ‘alternatieve tak’ te tonen.
- **Wat wordt bewaard**: jouw berichten en Claudes zichtbare antwoorden, plus de namen van gebruikte tools. **Niet bewaard**: interne denkstappen, tooluitvoer en systeemcontext.
- **Geen lus**: de hook geeft niets terug aan Claude. Contextpakketten die je terugplakt, worden herkend (`[memory-hub:contextpakket]`) en niet als nieuwe kennis geïndexeerd.

---

## 4. Claude laten zoeken in je archief (skill + MCP)

In elke nieuwe Claude Code-sessie kun je gewoon zeggen:

- *"Wat hadden we vorige keer besloten over de webshop?"*
- *"Ga verder met mijn studieplanning."*
- *"Onthoud: ik werk liever met TypeScript."*
- *"Dat budget klopt niet meer, het is nu 800 euro."*

De skill `memory-hub` laat Claude dan het volgende doen:

- eerst in het archief zoeken en alleen de nodige stukken laden;
- de bron en datum noemen;
- tegenstrijdige of verouderde informatie benoemen;
- eerlijk zeggen als er niets gevonden is;
- strikt onderscheiden tussen wat jij zei, wat Claude voorstelde en wat Claude afleidde. Eigen voorstellen van Claude worden opgeslagen als ‘voorstel’, niet als jouw voorkeur.

Opgehaalde gesprekken zijn historische gegevens. Instructies uit oude chats worden niet
automatisch opnieuw uitgevoerd.

De eerste keer vraagt Claude Code toestemming om de tools `mcp__memory-hub__…` te gebruiken.
Kies *altijd toestaan* als je dat wilt.

MCP-tools: `search_conversations`, `get_conversation`, `get_project_context`, `list_memories`,
`save_memory`, `update_memory`, `get_context_pack`, `get_sync_status`.

---

## 5. Waar staan mijn gegevens?

| Systeem | Map |
|---|---|
| Windows | `%APPDATA%\MemoryHub\` |
| macOS | `~/Library/Application Support/MemoryHub/` |
| Linux | `~/.local/share/memory-hub/` |

Daarbinnen staan:

- `app/` — het programma
- `data/memoryhub.db` — het archief
- `data/backups/` — back-ups
- `data/import/` — de importmap
- `data/exports/` — exports
- `data/attachments/` — opgeslagen afbeeldingen uit Claude Code
- `data/logs/` — foutlogs (zonder geheimen)
- `data/settings.json` — instellingen

Je kunt de locatie wijzigen met de omgevingsvariabele `MEMORY_HUB_HOME`. Chatinhoud staat
**nooit** in de broncoderepository.

---

## 6. Back-ups, herstel, export

- **Automatisch**: elke 24 uur een back-up. De nieuwste 14 worden bewaard (in te stellen).
- **Handmatig**: *Import & instellingen → Nu back-up maken*, of `python memory_hub.py backup`.
- **Herstellen**: via *Herstellen* in de app, of `python memory_hub.py restore <naam>`. Er wordt eerst automatisch een veiligheidsback-up van de huidige stand gemaakt.
- **Export**: alles naar JSON of leesbare Markdown (.zip), per gesprek of in één keer. Desgewenst met gemaskeerde geheimen.

---

## 7. Privacy, pauzeren, uitsluiten, verwijderen

- **Lokaal**: de app luistert standaard alleen op `127.0.0.1`. Hij is beschermd tegen andere websites (CSRF-header, Host-controle) en heeft een strikte Content-Security-Policy.
- **Andere apparaten**: dit is een aparte optie in de instellingen en vereist een toegangstoken. Het verkeer gaat over onversleuteld HTTP, dus gebruik het alleen op een vertrouwd netwerk of via VPN.
- **Geheimen**: API-sleutels, tokens en wachtwoorden worden gemaskeerd in zoekfragmenten, weergaven, MCP-uitvoer en logs. De oorspronkelijke tekst blijft in je lokale database. Je kunt per gesprek kiezen voor *Toon verborgen waarden*.
- **Pauzeren**: via de schakelaar *Archivering pauzeren*. Wat je tijdens de pauze bespreekt, wordt niet bewaard, ook niet achteraf.
- **Uitsluiten**:
  - hele projectmappen via patronen in de instellingen;
  - één Claude Code-gesprek door `[geen-archief]` in dat gesprek te typen;
  - of door een gesprek te verwijderen met *niet opnieuw importeren*.
- **Verwijderen** wist het gesprek, de berichten, de zoekindex, opgeslagen bijlagen, labels en alle **geheugenitems die eruit zijn afgeleid**. Je oorspronkelijke transcript en je claude.ai-account blijven onaangeroerd.
- **Back-ups na verwijderen**: een verwijderd gesprek blijft in oudere back-ups staan tot die zijn opgeruimd, tenzij je *ook uit alle back-ups wissen* aanvinkt. Elke verwijdering wordt vastgelegd als grafsteen: alleen bron + ID, geen inhoud. Bij herstel van een back-up wordt de verwijdering standaard opnieuw toegepast. Een herstel brengt verwijderde gesprekken dus niet ongemerkt terug.
- **Optionele AI** (samenvattingen, semantisch zoeken) is **niet ingebouwd en staat uit**. De samenvattingen in de app zijn lokaal en extractief: letterlijke fragmenten, geen gegenereerde tekst. Komt er ooit een externe AI-functie bij, dan wordt die apart aangezet en staat er duidelijk bij dat er chatinhoud naar die dienst gaat.

---

## 8. Opdrachtregel

```bash
python memory_hub.py open                # app openen
python memory_hub.py serve --no-browser  # server + achtergrondsync
python memory_hub.py sync                # één synchronisatieronde
python memory_hub.py search "zoektermen"
python memory_hub.py status
python memory_hub.py import export.zip
python memory_hub.py backup [--list]
python memory_hub.py restore <naam>
python memory_hub.py export --format markdown
python memory_hub.py delete <gesprek-id> [--purge-backups]
python memory_hub.py pause aan|uit
python memory_hub.py seed-test           # gemarkeerde testgesprekken toevoegen
python -m unittest discover -s tests -v  # testsuite
```

---

## 9. Problemen oplossen

| Probleem | Oplossing |
|---|---|
| Overzicht zegt "Niet automatisch" | Draai `python memory_hub.py install` en start een nieuwe Claude Code-sessie. |
| "Achtergrondproces niet actief" | Open de app één keer, of start `python memory_hub.py serve --no-browser`. De hooks werken ook zonder achtergrondproces, zolang Claude Code draait. |
| Claude gebruikt het archief niet | Controleer `claude mcp list` en de skill in `~/.claude/skills/memory-hub/`. Vraag expliciet: "zoek in mijn Memory Hub". |
| Fouten | Zie *Overzicht*/*Instellingen* (laatste fout) en `data/logs/`. |
| Poort 8765 bezet | Zet `"port"` in `data/settings.json` op een andere waarde. |
