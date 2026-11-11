/* Memory Hub — app (vanilla JS, geen externe afhankelijkheden) */
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const app = $("#app");
const HL_S = "\u0002", HL_E = "\u0003";
const KINDS = ["voorkeur", "beslissing", "doel", "actie", "feit"];
const STATUSES = ["actief", "voorstel", "vervangen", "afgerond", "verworpen"];
const ORIGINS = { user_stated: "door jou gezegd", assistant_suggested: "voorgesteld door Claude", inferred: "afgeleid" };
const SOURCES = { claude_code: "Claude Code", claude_ai_export: "claude.ai (export)", test: "Testgesprek" };
const state = { projects: [], topics: [], tags: [], viewClick: null };
const KIND_LABELS = { voorkeur: "Voorkeuren", beslissing: "Beslissingen", doel: "Doelen", actie: "Acties", feit: "Feiten" };

// ------------------------------------------------------------ helpers
async function api(path, opts = {}) {
  const o = { method: opts.method || "GET", headers: { "X-MemoryHub": "1" } };
  if (opts.body !== undefined) {
    if (opts.raw) { o.body = opts.body; Object.assign(o.headers, opts.headers || {}); }
    else { o.body = JSON.stringify(opts.body); o.headers["Content-Type"] = "application/json"; }
  }
  const r = await fetch(path, o);
  const ct = r.headers.get("Content-Type") || "";
  const data = ct.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.error) || `Fout ${r.status}`);
  return data;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function hl(s) { return esc(s).split(HL_S).join("<mark>").split(HL_E).join("</mark>"); }
function fmtDate(ts, withTime = true) {
  if (!ts) return "onbekend";
  const d = new Date(ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z");
  if (isNaN(d)) return ts.slice(0, 16);
  const opt = { day: "numeric", month: "short", year: "numeric" };
  if (withTime) Object.assign(opt, { hour: "2-digit", minute: "2-digit" });
  return d.toLocaleString("nl-NL", opt);
}
function rel(ts) {
  if (!ts) return "nooit";
  const d = new Date(ts.endsWith("Z") || ts.includes("+") ? ts : ts + "Z");
  const s = (Date.now() - d) / 1000;
  if (s < 60) return "zojuist";
  if (s < 3600) return `${Math.floor(s / 60)} min geleden`;
  if (s < 86400) return `${Math.floor(s / 3600)} uur geleden`;
  if (s < 86400 * 30) return `${Math.floor(s / 86400)} dagen geleden`;
  return fmtDate(ts, false);
}
function bytes(n) { if (n == null) return "?"; const u = ["B", "KB", "MB", "GB"]; let i = 0; while (n >= 1024 && i < 3) { n /= 1024; i++; } return `${n.toFixed(i ? 1 : 0)} ${u[i]}`; }
function toast(msg, bad = false) {
  const t = document.createElement("div");
  t.className = "toast" + (bad ? " bad" : "");
  t.textContent = msg;
  $("#toasts").appendChild(t);
  setTimeout(() => t.remove(), bad ? 6500 : 3200);
}
function plain(t, n = 300) {
  t = String(t || "").replace(/```[\s\S]*?```/g, " ").replace(/`([^`]+)`/g, "$1").replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").replace(/^#+\s*/gm, "").replace(/\s+/g, " ").trim();
  return t.length > n ? t.slice(0, n) + "…" : t;
}
function srcBadge(s) { return `<span class="badge ${s === "claude_code" ? "accent" : s === "test" ? "warn" : ""}">${esc(SOURCES[s] || s)}</span>`; }
function qs() { const i = location.hash.indexOf("?"); return new URLSearchParams(i >= 0 ? location.hash.slice(i + 1) : ""); }
function setQs(params) {
  const base = location.hash.split("?")[0] || "#/";
  const p = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== "" && v != null && v !== false) p.set(k, v);
  const s = p.toString();
  history.replaceState(null, "", base + (s ? "?" + s : ""));
}
async function copy(text) {
  try { await navigator.clipboard.writeText(text); toast("Gekopieerd naar klembord"); }
  catch { const ta = document.createElement("textarea"); ta.value = text; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); ta.remove(); toast("Gekopieerd"); }
}
function download(url) { const a = document.createElement("a"); a.href = url; a.download = ""; document.body.appendChild(a); a.click(); a.remove(); }

// Veilige, beperkte Markdown-weergave (eerst escapen, dan opmaak)
function md(src) {
  const blocks = [];
  let s = String(src ?? "").replace(/```([\w+\-.]*)\n?([\s\S]*?)```/g, (_, lang, code) => {
    blocks.push(`<pre><code${lang ? ` data-lang="${esc(lang)}"` : ""}>${esc(code.replace(/\n$/, ""))}</code></pre>`);
    return `\u0000B${blocks.length - 1}\u0000`;
  });
  s = esc(s);
  const inline = t => t
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>")
    .replace(/\[([^\]\n]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>')
    .replace(/(^|[\s(])(https?:\/\/[^\s<)]+)/g, '$1<a href="$2" target="_blank" rel="noopener noreferrer">$2</a>');
  const out = [];
  let list = null;
  const flush = () => { if (list) { out.push(`<${list.t}>${list.items.map(i => `<li>${inline(i)}</li>`).join("")}</${list.t}>`); list = null; } };
  let para = [];
  const flushP = () => { if (para.length) { out.push(`<p>${inline(para.join("<br>"))}</p>`); para = []; } };
  for (const line of s.split("\n")) {
    const b = line.match(/^\u0000B(\d+)\u0000$/);
    if (b) { flushP(); flush(); out.push(blocks[+b[1]]); continue; }
    const h = line.match(/^(#{1,4})\s+(.*)$/);
    const ul = line.match(/^\s*[-*•]\s+(.*)$/);
    const ol = line.match(/^\s*\d+[.)]\s+(.*)$/);
    const bq = line.match(/^&gt;\s?(.*)$/);
    if (h) { flushP(); flush(); out.push(`<h${h[1].length + 1}>${inline(h[2])}</h${h[1].length + 1}>`); }
    else if (ul || ol) { flushP(); const t = ul ? "ul" : "ol"; if (!list || list.t !== t) { flush(); list = { t, items: [] }; } list.items.push((ul || ol)[1]); }
    else if (bq) { flushP(); flush(); out.push(`<blockquote>${inline(bq[1])}</blockquote>`); }
    else if (!line.trim()) { flushP(); flush(); }
    else { flush(); para.push(line); }
  }
  flushP(); flush();
  return out.join("").replace(/\u0000B(\d+)\u0000/g, (_, i) => blocks[+i]);
}

function modal(html, onMount) {
  const back = document.createElement("div");
  back.className = "modal-back";
  back.innerHTML = `<div class="modal" role="dialog" aria-modal="true">${html}</div>`;
  const close = () => { back.remove(); document.removeEventListener("keydown", onKey); };
  const onKey = e => { if (e.key === "Escape") close(); };
  back.addEventListener("click", e => { if (e.target === back || e.target.closest("[data-close]")) close(); });
  document.addEventListener("keydown", onKey);
  document.body.appendChild(back);
  if (onMount) onMount(back.firstElementChild, close);
  return close;
}
function confirmBox(title, body, okLabel = "Bevestigen", danger = false) {
  return new Promise(res => {
    modal(`<h2>${esc(title)}</h2><div class="muted">${body}</div>
      <div class="row" style="justify-content:flex-end;margin-top:18px"><button data-close>Annuleren</button>
      <button class="${danger ? "danger" : "primary"}" id="cb-ok">${esc(okLabel)}</button></div>`,
      (m, close) => { $("#cb-ok", m).onclick = () => { close(); res(true); }; m.parentElement.addEventListener("click", e => { if (e.target.closest("[data-close]") || e.target === m.parentElement) res(false); }); });
  });
}

async function loadLookups() {
  [state.projects, state.topics, state.tags] = await Promise.all([api("/api/projects"), api("/api/topics"), api("/api/tags")]);
}

// ------------------------------------------------------------ router
const routes = { overzicht: viewOverview, gesprekken: viewConversations, gesprek: viewConversation, projecten: viewProjects, geheugen: viewMemories, instellingen: viewSettings };
async function router() {
  const path = (location.hash.split("?")[0] || "#/").replace(/^#\/?/, "");
  const [name, id] = path.split("/");
  const key = name || "overzicht";
  $$("#nav a").forEach(a => a.classList.toggle("active", a.dataset.r === key || (key === "gesprek" && a.dataset.r === "gesprekken")));
  app.innerHTML = `<div class="loading">Laden…</div>`;
  state.viewClick = null;
  try { await (routes[key] || viewOverview)(id); }
  catch (e) { app.innerHTML = `<div class="banner bad">Er ging iets mis: ${esc(e.message)}</div>`; }
  refreshPill();
}
window.addEventListener("hashchange", router);

async function refreshPill() {
  try {
    const s = await api("/api/status");
    const cc = s.sources[0];
    const cls = s.paused ? "warn" : (cc.last_error && (!cc.last_success || cc.last_error.at > cc.last_success)) ? "bad" : (cc.hooks_installed || cc.watcher_active) ? "ok" : "warn";
    const txt = s.paused ? "Gepauzeerd" : cls === "bad" ? "Synchronisatiefout" : cls === "ok" ? "Synchronisatie actief" : "Niet automatisch";
    $("#sync-pill").innerHTML = `<span class="dot ${cls}"></span> ${txt}`;
  } catch { $("#sync-pill").innerHTML = `<span class="dot bad"></span> Server niet bereikbaar`; }
}

// ------------------------------------------------------------ gedeelde weergaven
function convItem(c, q) {
  const hits = (c.hits || []).map(h => `<a class="hit" href="#/gesprek/${c.id}?m=${h.message_id}${q ? "&q=" + encodeURIComponent(q) : ""}">
      <span class="who">${h.role === "user" ? "Jij" : h.role === "assistant" ? "Claude" : "Systeem"} · ${fmtDate(h.created_at, false)}</span>${hl(h.snippet)}</a>`).join("");
  const topics = (c.topics || []).map(t => `<span class="badge" style="background:${esc(t.color)}22;color:${esc(t.color)}">${esc(t.name)}</span>`).join("");
  return `<div class="conv-item" data-open="${c.id}">
    <div class="title">${c.favorite ? '<span class="star">★</span>' : ""}${esc(c.title || "Naamloos")}</div>
    <div class="meta">${srcBadge(c.source)}${c.project ? `<span>▦ ${esc(c.project)}</span>` : ""}<span>${fmtDate(c.updated_at || c.created_at)}</span>
      <span>${c.message_count} berichten</span>${c.hit_count ? `<span>${c.hit_count} treffer${c.hit_count > 1 ? "s" : ""}</span>` : ""}${topics}
      ${(c.tags || []).map(t => `<span class="badge">#${esc(t)}</span>`).join("")}</div>${hits}</div>`;
}
app.addEventListener("click", e => {
  if (state.viewClick) state.viewClick(e);
  const hit = e.target.closest("a.hit");
  if (hit) return;
  const it = e.target.closest("[data-open]");
  if (it && !e.target.closest("button,a,input,select")) location.hash = `#/gesprek/${it.dataset.open}`;
});

function memRow(m, opts = {}) {
  const st = { actief: "ok", voorstel: "warn", vervangen: "", afgerond: "accent", verworpen: "bad" }[m.status] || "";
  return `<div class="mem" data-mem="${m.id}">
    <div style="flex:1">
      <div class="text">${esc(m.text)}</div>
      <div class="row small muted" style="margin-top:4px">
        <span class="badge">${esc(m.kind)}</span>
        <span class="badge ${m.origin === "user_stated" ? "ok" : m.origin === "assistant_suggested" ? "warn" : ""}">${esc(m.origin_label || ORIGINS[m.origin])}</span>
        <span class="badge ${st}">${esc(m.status)}</span>
        ${m.confirmed ? '<span class="badge ok">bevestigd</span>' : ""}
        ${m.mogelijk_verouderd ? '<span class="badge warn" title="Bron is ouder dan 180 dagen">mogelijk verouderd</span>' : ""}
        ${m.project ? `<span>▦ ${esc(m.project)}</span>` : ""}
        <span>${m.source_conversation_id ? `<a href="#/gesprek/${m.source_conversation_id}${m.source_message_id ? "?m=" + m.source_message_id : ""}">${esc(m.source_label || "bron")}</a>` : esc(m.source_label || "handmatig toegevoegd")}</span>
        <span>· ${fmtDate(m.source_date, false)}</span>
      </div>
    </div>
    ${opts.actions === false ? "" : `<div class="row" style="flex-shrink:0">
      ${m.status === "voorstel" ? `<button class="small" data-mact="confirm">Bevestigen</button>` : ""}
      ${m.kind === "actie" && m.status === "actief" ? `<button class="small" data-mact="done">Afgerond</button>` : ""}
      <button class="small ghost" data-mact="edit" title="Corrigeren (oude versie blijft bewaard)">Corrigeren</button>
      <button class="small ghost" data-mact="more">⋯</button></div>`}
  </div>`;
}
async function memAction(e, reload) {
  const b = e.target.closest("[data-mact]");
  if (!b) return;
  const id = b.closest("[data-mem]").dataset.mem;
  const act = b.dataset.mact;
  try {
    if (act === "confirm") { await api(`/api/memories/${id}`, { method: "POST", body: { confirmed: true, status: "actief", reason: "bevestigd door gebruiker in de app" } }); toast("Bevestigd"); }
    else if (act === "done") { await api(`/api/memories/${id}`, { method: "POST", body: { status: "afgerond", reason: "afgerond" } }); toast("Afgerond"); }
    else if (act === "edit") { return memoryEditor(id, reload); }
    else if (act === "more") { return memoryMore(id, reload); }
    reload();
  } catch (err) { toast(err.message, true); }
}
async function memoryEditor(id, reload) {
  const m = await api(`/api/memories/${id}`);
  modal(`<h2>Geheugenitem corrigeren</h2>
    <p class="muted small">Een correctie maakt een nieuw item; het oude blijft zichtbaar als ‘vervangen’. Historische gesprekstekst wordt nooit aangepast.</p>
    <div class="field"><label>Tekst</label><textarea id="me-text">${esc(m.text)}</textarea></div>
    <div class="grid grid-2"><div class="field"><label>Soort</label><select id="me-kind">${KINDS.map(k => `<option ${k === m.kind ? "selected" : ""}>${k}</option>`).join("")}</select></div>
    <div class="field"><label>Reden</label><input id="me-reason" placeholder="bv. ik ben van gedachten veranderd"></div></div>
    <div class="row" style="justify-content:flex-end"><button data-close>Annuleren</button><button class="primary" id="me-save">Opslaan</button></div>`,
    (el, close) => {
      $("#me-save", el).onclick = async () => {
        try {
          await api(`/api/memories/${id}`, { method: "POST", body: { text: $("#me-text", el).value, kind: $("#me-kind", el).value, reason: $("#me-reason", el).value || "gecorrigeerd in de app", confirmed: true } });
          close(); toast("Gecorrigeerd"); reload();
        } catch (err) { toast(err.message, true); }
      };
    });
}
async function memoryMore(id, reload) {
  const m = await api(`/api/memories/${id}`);
  modal(`<h2>Geheugenitem #${m.id}</h2><p>${esc(m.text)}</p>
    <div class="kv"><div>Herkomst</div><div>${esc(m.origin_label)}</div><div>Status</div><div>${esc(m.status)}</div>
    <div>Bron</div><div>${esc(m.source_label || "handmatig")}</div><div>Datum bron</div><div>${fmtDate(m.source_date)}</div>
    <div>Aangemaakt via</div><div>${esc(m.created_by)}</div>${m.supersedes_id ? `<div>Vervangt</div><div>#${m.supersedes_id}</div>` : ""}</div>
    <h3 style="margin-top:16px">Geschiedenis</h3>
    <div class="small">${m.history.map(h => `<div>${fmtDate(h.changed_at)} · ${esc(h.changed_by)} · <code>${esc(h.change)}</code></div>`).join("")}</div>
    <div class="field" style="margin-top:14px"><label>Status wijzigen</label><select id="mm-status">${STATUSES.map(s => `<option ${s === m.status ? "selected" : ""}>${s}</option>`).join("")}</select></div>
    <div class="field"><label>Herkomst wijzigen</label><select id="mm-origin">${Object.entries(ORIGINS).map(([k, v]) => `<option value="${k}" ${k === m.origin ? "selected" : ""}>${v}</option>`).join("")}</select></div>
    <div class="row spread" style="margin-top:16px"><button class="danger" id="mm-del">Verwijderen</button>
    <div class="row"><button data-close>Sluiten</button><button class="primary" id="mm-save">Opslaan</button></div></div>`,
    (el, close) => {
      $("#mm-save", el).onclick = async () => {
        try { await api(`/api/memories/${id}`, { method: "POST", body: { status: $("#mm-status", el).value, origin: $("#mm-origin", el).value, reason: "gewijzigd in de app" } }); close(); toast("Opgeslagen"); reload(); }
        catch (err) { toast(err.message, true); }
      };
      $("#mm-del", el).onclick = async () => { await api(`/api/memories/${id}`, { method: "DELETE" }); close(); toast("Verwijderd"); reload(); };
    });
}
function newMemoryModal(preset, reload) {
  modal(`<h2>Bewaren in geheugen</h2>
    <p class="muted small">Leg vast wat je wilt onthouden. Kies eerlijk de herkomst: een voorstel van Claude is niet automatisch jouw voorkeur.</p>
    <div class="field"><label>Tekst</label><textarea id="nm-text">${esc(preset.text || "")}</textarea></div>
    <div class="grid grid-3">
      <div class="field"><label>Soort</label><select id="nm-kind">${KINDS.map(k => `<option ${k === (preset.kind || "voorkeur") ? "selected" : ""}>${k}</option>`).join("")}</select></div>
      <div class="field"><label>Herkomst</label><select id="nm-origin">${Object.entries(ORIGINS).map(([k, v]) => `<option value="${k}" ${k === (preset.origin || "user_stated") ? "selected" : ""}>${v}</option>`).join("")}</select></div>
      <div class="field"><label>Project</label><select id="nm-proj"><option value="">(algemeen)</option>${state.projects.map(p => `<option value="${p.id}" ${p.id === preset.project_id ? "selected" : ""}>${esc(p.name)}</option>`).join("")}</select></div>
    </div>
    ${preset.conversation_id ? `<p class="small muted">Bron: gesprek #${preset.conversation_id}${preset.message_id ? `, bericht #${preset.message_id}` : ""}</p>` : ""}
    <div class="row" style="justify-content:flex-end"><button data-close>Annuleren</button><button class="primary" id="nm-save">Opslaan</button></div>`,
    (el, close) => {
      $("#nm-save", el).onclick = async () => {
        try {
          const r = await api("/api/memories", { method: "POST", body: { text: $("#nm-text", el).value, kind: $("#nm-kind", el).value, origin: $("#nm-origin", el).value, project_id: $("#nm-proj", el).value || null, conversation_id: preset.conversation_id, message_id: preset.message_id } });
          close();
          toast(r.status === "voorstel" ? "Opgeslagen als voorstel (nog niet jouw voorkeur)" : "Opgeslagen");
          if (r.mogelijk_tegenstrijdig && r.mogelijk_tegenstrijdig.length) toast(`Let op: ${r.mogelijk_tegenstrijdig.length} vergelijkbaar item(s) gevonden — controleer op tegenstrijdigheid in Geheugen.`);
          reload && reload();
        } catch (err) { toast(err.message, true); }
      };
    });
}

// ------------------------------------------------------------ Overzicht
async function viewOverview() {
  const [o] = await Promise.all([api("/api/overview"), loadLookups()]);
  const s = o.status, cc = s.sources[0], ex = s.sources[1];
  const ccErr = cc.last_error && (!cc.last_success || cc.last_error.at > cc.last_success);
  app.innerHTML = `
  <div class="page-head"><div><h1>Overzicht</h1><p>Je persoonlijke archief van gesprekken met Claude.</p></div>
    <div class="row"><button id="ov-sync">↻ Nu synchroniseren</button>
    <label class="switch"><input type="checkbox" id="ov-pause" ${s.paused ? "checked" : ""}> Archivering pauzeren</label></div></div>
  ${s.paused ? `<div class="banner warn">Archivering is gepauzeerd sinds ${fmtDate(s.paused_since)}. Wat je tijdens de pauze bespreekt, wordt niet bewaard.</div>` : ""}
  <div class="grid grid-4">
    <div class="card stat"><div class="num">${s.totals.conversations}</div><div class="lbl">gesprekken</div></div>
    <div class="card stat"><div class="num">${s.totals.messages}</div><div class="lbl">berichten</div></div>
    <div class="card stat"><div class="num">${s.totals.memories}</div><div class="lbl">geheugenitems</div></div>
    <div class="card stat"><div class="num">${bytes(s.database_size)}</div><div class="lbl">database</div></div>
  </div>
  <div class="section-title"><h2>Synchronisatiestatus</h2><a href="#/instellingen">Bronnen beheren →</a></div>
  <div class="grid grid-2">
    <div class="card">
      <div class="row spread"><h3 style="margin:0">Claude Code</h3>${cc.mode === "automatisch" ? '<span class="badge ok">Automatisch</span>' : '<span class="badge warn">Niet automatisch</span>'}</div>
      <div class="kv" style="margin-top:10px">
        <div>Via</div><div>${cc.automatic_via.length ? cc.automatic_via.join(" + ") : "—  (installeer de hooks)"}</div>
        <div>Laatste opslag</div><div>${cc.last_success ? rel(cc.last_success) : "nog niet"}</div>
        <div>Achtergrondproces</div><div>${cc.watcher_active ? '<span class="dot ok"></span> actief' : '<span class="dot warn"></span> niet actief'} (${esc(cc.watcher_last_seen)})</div>
        <div>Archief</div><div>${cc.conversations} gesprekken, ${cc.messages} berichten</div>
        <div>Achterstallig</div><div>${cc.files_behind ? `<span class="badge warn">${cc.files_behind} transcript(en) nog te verwerken</span>` : "geen"}</div>
      </div>
      ${ccErr ? `<div class="banner bad" style="margin-top:10px">Laatste fout (${rel(cc.last_error.at)}): ${esc(cc.last_error.detail.slice(0, 220))}</div>` : ""}
    </div>
    <div class="card">
      <div class="row spread"><h3 style="margin:0">claude.ai — web, desktop, mobiel</h3><span class="badge">Handmatige import</span></div>
      <div class="kv" style="margin-top:10px">
        <div>Laatste import</div><div>${ex.last_import ? rel(ex.last_import) : "nog nooit"}</div>
        <div>Archief</div><div>${ex.conversations} gesprekken, ${ex.messages} berichten</div>
        <div>Wachtend in importmap</div><div>${ex.pending_in_import_folder.length ? `<span class="badge warn">${ex.pending_in_import_folder.length}</span>` : "niets"}</div>
      </div>
      ${ex.days_since_import === null || ex.days_since_import > 30 ? `<div class="banner info" style="margin-top:10px">Tip: exporteer je gegevens op claude.ai en importeer de .zip om je web/mobiel-gesprekken bij te werken.</div>` : ""}
    </div>
  </div>
  ${s.test_conversations ? `<div class="banner warn" style="margin-top:12px">Er staan ${s.test_conversations} duidelijk gemarkeerde testgesprekken in het archief (bron ‘Testgesprek’). Je kunt ze verwijderen in Alle gesprekken.</div>` : ""}
  <div class="grid grid-2" style="margin-top:6px">
    <div><div class="section-title"><h2>Recente gesprekken</h2><a href="#/gesprekken">Alles →</a></div>
      <div class="conv-list">${o.recent.map(c => convItem(c)).join("") || `<div class="card empty">Nog geen gesprekken. Klik op ‘Nu synchroniseren’ of importeer een export.</div>`}</div></div>
    <div><div class="section-title"><h2>Favorieten</h2></div>
      <div class="conv-list">${o.favorites.map(c => convItem(c)).join("") || `<div class="card empty small">Markeer gesprekken met ☆ om ze hier te zien.</div>`}</div>
      <div class="section-title"><h2>Openstaande acties</h2><a href="#/geheugen?kind=actie">Alles →</a></div>
      <div class="card" id="ov-actions">${o.open_actions.map(m => memRow(m)).join("") || `<div class="muted small">Geen openstaande acties.</div>`}</div></div>
  </div>`;
  $("#ov-sync").onclick = async e => {
    e.target.disabled = true; e.target.textContent = "Bezig…";
    try { const r = await api("/api/sync", { method: "POST" }); toast(`Klaar: ${r.claude_code ? r.claude_code.new_messages : 0} nieuwe berichten`); router(); }
    catch (err) { toast(err.message, true); e.target.disabled = false; }
  };
  $("#ov-pause").onchange = async e => { await api("/api/pause", { method: "POST", body: { paused: e.target.checked } }); toast(e.target.checked ? "Archivering gepauzeerd" : "Archivering hervat"); router(); };
  $("#ov-actions").addEventListener("click", e => memAction(e, router));
}

// ------------------------------------------------------------ Alle gesprekken
async function viewConversations() {
  await loadLookups();
  const p = qs();
  app.innerHTML = `
  <div class="page-head"><div><h1>Alle gesprekken</h1><p>Zoek in alle berichten. Klik op een fragment om naar dat bericht te gaan.</p></div></div>
  <div class="searchbar"><input id="cs-q" type="search" placeholder="Zoek op woorden, of “een exacte zin”…" value="${esc(p.get("q") || "")}" autofocus></div>
  <div class="filters">
    <select id="cs-source"><option value="">Alle bronnen</option>${Object.entries(SOURCES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
    <select id="cs-project"><option value="">Alle projecten</option>${state.projects.map(x => `<option value="${x.id}">${esc(x.name)} (${x.conversations})</option>`).join("")}</select>
    <select id="cs-topic"><option value="">Alle onderwerpen</option>${state.topics.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join("")}</select>
    <select id="cs-tag"><option value="">Alle labels</option>${state.tags.map(x => `<option value="${esc(x.tag)}">#${esc(x.tag)}</option>`).join("")}</select>
    <select id="cs-role"><option value="">Iedereen</option><option value="user">Alleen mijn berichten</option><option value="assistant">Alleen Claude</option></select>
    <input type="date" id="cs-from" title="Vanaf"><input type="date" id="cs-to" title="Tot en met">
    <label class="switch"><input type="checkbox" id="cs-fav"> Favorieten</label>
    <select id="cs-sort"><option value="recent">Nieuwste eerst</option><option value="oud">Oudste eerst</option><option value="relevantie">Relevantie</option><option value="titel">Titel</option><option value="lengte">Langste</option></select>
  </div>
  <div id="cs-count" class="muted small" style="margin-bottom:8px"></div>
  <div class="conv-list" id="cs-list"></div>
  <div class="row" style="justify-content:center;margin-top:14px"><button id="cs-more" hidden>Meer laden</button></div>`;
  const map = { source: "#cs-source", project_id: "#cs-project", topic_id: "#cs-topic", tag: "#cs-tag", role: "#cs-role", date_from: "#cs-from", date_to: "#cs-to", sort: "#cs-sort" };
  for (const [k, sel] of Object.entries(map)) if (p.get(k)) $(sel).value = p.get(k);
  if (p.get("favorite")) $("#cs-fav").checked = true;
  let offset = 0, timer;
  const params = () => {
    const o = { q: $("#cs-q").value.trim() };
    for (const [k, sel] of Object.entries(map)) o[k] = $(sel).value;
    if ($("#cs-fav").checked) o.favorite = "1";
    return o;
  };
  const load = async (append = false) => {
    const o = params();
    setQs(o);
    if (!append) offset = 0;
    const u = new URLSearchParams({ ...o, limit: 30, offset });
    if (o.role && !o.q) u.delete("role");
    const r = await api("/api/conversations?" + u);
    const html = r.items.map(c => convItem(c, o.q)).join("");
    if (append) $("#cs-list").insertAdjacentHTML("beforeend", html);
    else $("#cs-list").innerHTML = html || `<div class="card empty">${o.q ? "Niets gevonden voor deze zoekopdracht. Probeer andere woorden of minder filters." : "Geen gesprekken met deze filters."}</div>`;
    offset += r.items.length;
    $("#cs-count").textContent = `${r.total} gesprek${r.total === 1 ? "" : "ken"}${o.q ? " met treffers" : ""}`;
    $("#cs-more").hidden = offset >= r.total;
  };
  $("#cs-q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load(), 250); });
  $$(".filters select, .filters input").forEach(el => el.addEventListener("change", () => load()));
  $("#cs-more").onclick = () => load(true);
  await load();
}

// ------------------------------------------------------------ Gesprek
async function viewConversation(id) {
  const p = qs();
  const reveal = p.get("reveal") === "1";
  const [c] = await Promise.all([api(`/api/conversations/${id}${reveal ? "?reveal=1" : ""}`), loadLookups()]);
  const showAlt = p.get("alt") === "1";
  const msgs = c.messages.filter(m => showAlt || m.on_main_branch);
  const who = r => r === "user" ? "Jij" : r === "assistant" ? "Claude" : "Systeem";
  app.innerHTML = `
  <div class="conv-head">
    <div class="row spread">
      <div class="row" style="min-width:0;flex:1">
        <a href="#/gesprekken" class="btn small ghost">← Terug</a>
        <button class="ghost" id="cv-fav" title="Favoriet" style="font-size:1.2rem">${c.favorite ? '<span class="star">★</span>' : "☆"}</button>
        <h1 style="margin:0;font-size:1.25rem;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" id="cv-title" title="Klik om te hernoemen">${esc(c.title)}</h1>
      </div>
      <div class="row">
        <div class="findbar"><input id="cv-find" type="search" placeholder="Zoek in dit gesprek" value="${esc(p.get("q") || "")}"><span id="cv-findcount" class="small muted"></span>
        <button class="small ghost" id="cv-prev" title="Vorige">↑</button><button class="small ghost" id="cv-next" title="Volgende">↓</button></div>
        <button class="primary" id="cv-continue">Verdergaan met dit gesprek</button>
      </div>
    </div>
    <div class="row small muted" style="margin-top:8px">${srcBadge(c.source)}${c.project ? `<span>▦ ${esc(c.project)}</span>` : ""}
      <span>Gestart ${fmtDate(c.created_at)}</span><span>· Laatst ${fmtDate(c.updated_at)}</span><span>· ${c.total_messages} berichten</span>
      ${c.git_branch ? `<span>· branch ${esc(c.git_branch)}</span>` : ""}
      ${c.url ? `<a class="btn small" href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">Open origineel ↗</a>` : ""}
      ${c.resume_command ? `<button class="small" id="cv-resume" title="${esc(c.resume_command)}">Kopieer hervat-opdracht</button>` : ""}
    </div>
  </div>
  ${c.missing_info.map(x => `<div class="banner warn">Let op: ${esc(x)}</div>`).join("")}
  ${c.alt_branch_count ? `<div class="banner info">Dit gesprek heeft ${c.alt_branch_count} bericht(en) op een verlaten tak (bijv. na terugspoelen of bewerken).
     <a href="#/gesprek/${c.id}?${showAlt ? "" : "alt=1"}">${showAlt ? "Verberg" : "Toon"} alternatieve takken</a></div>` : ""}
  <div class="conv-layout">
    <div class="messages" id="cv-msgs">
      ${msgs.map(m => `<div class="msg ${m.role} ${m.on_main_branch ? "" : "alt"}" id="m${m.id}" data-mid="${m.id}" data-role="${m.role}">
        <div class="msg-head"><span><span class="who">${who(m.role)}</span> · ${fmtDate(m.created_at)}${m.on_main_branch ? "" : " · alternatieve tak"}${m.is_context_pack ? ' · <span class="badge">contextpakket</span>' : ""}${m.tools ? ` · <span title="Gebruikte tools">⚒ ${esc(m.tools)}</span>` : ""}</span>
          <span class="msg-actions"><button class="small ghost" data-act="copy">Kopieer</button><button class="small ghost" data-act="remember">Bewaar in geheugen</button><button class="small ghost" data-act="link">Link</button></span></div>
        <div class="md">${md(m.content)}</div>
        ${m.attachments.length ? `<div class="attach">${m.attachments.map(a => a.has_file && (a.file_type || "").startsWith("image/")
          ? `<a href="/api/attachments/${a.id}" target="_blank"><img src="/api/attachments/${a.id}" alt="${esc(a.file_name)}"></a>`
          : `<span class="badge ${a.available ? "" : "warn"}" title="${a.available ? "" : "Alleen de bestandsnaam is bekend; het bestand zelf ontbreekt in de bron"}">📎 ${esc(a.file_name)}${a.available ? "" : " (ontbreekt)"}</span>${a.extracted_text ? `<details><summary class="small">tekst van bijlage</summary><pre class="small" style="white-space:pre-wrap">${esc(a.extracted_text)}</pre></details>` : ""}`).join("")}</div>` : ""}
      </div>`).join("") || `<div class="card empty">Dit gesprek heeft geen zichtbare berichten.</div>`}
    </div>
    <aside class="side-panel">
      <div class="card">
        <h3>Samenvatting</h3>
        <div class="small" id="cv-summary" style="white-space:pre-wrap">${c.summary ? esc(c.summary) : '<span class="muted">Nog geen samenvatting.</span>'}</div>
        <div class="small muted" style="margin-top:6px">${c.summary_kind === "lokaal-extractief" ? "Lokaal gemaakt uit letterlijke fragmenten (geen AI)." : c.summary_kind ? "Soort: " + esc(c.summary_kind) : ""}</div>
        <div class="row" style="margin-top:8px"><button class="small" id="cv-sum">Maak lokale samenvatting</button><button class="small ghost" id="cv-sumedit">Bewerken</button></div>
      </div>
      <div class="card">
        <h3>Ordenen</h3>
        <div class="field"><label>Project</label><select id="cv-project"><option value="">(geen)</option>${state.projects.map(x => `<option value="${x.id}" ${x.id === c.project_id ? "selected" : ""}>${esc(x.name)}</option>`).join("")}</select></div>
        <div class="field"><label>Onderwerpen</label><div class="chips" id="cv-topics">${state.topics.map(t => `<span class="chip ${c.topics.some(x => x.id === t.id) ? "on" : ""}" data-tid="${t.id}">${esc(t.name)}</span>`).join("")}</div></div>
        <div class="field"><label>Labels (komma-gescheiden)</label><input id="cv-tags" value="${esc(c.tags.join(", "))}" style="width:100%"></div>
        <div class="field"><label>Mijn notities</label><textarea id="cv-notes" placeholder="Eigen aantekeningen bij dit gesprek">${esc(c.notes || "")}</textarea></div>
        <button class="small primary" id="cv-save">Opslaan</button>
      </div>
      <div class="card">
        <h3>Geheugen uit dit gesprek</h3>
        <div id="cv-mems" class="small">${c.memories.map(m => memRow(m, { actions: false })).join("") || '<span class="muted">Nog niets. Gebruik ‘Bewaar in geheugen’ bij een bericht.</span>'}</div>
      </div>
      <div class="card">
        <h3>Exporteren &amp; privacy</h3>
        <div class="row">
          <a class="btn small" href="/api/conversations/${c.id}/markdown">Markdown</a>
          <a class="btn small" href="/api/conversations/${c.id}/json">JSON</a>
          <a class="btn small ghost" href="#/gesprek/${c.id}?${reveal ? "" : "reveal=1"}">${reveal ? "Verberg geheimen" : "Toon verborgen waarden"}</a>
        </div>
        <button class="small danger" id="cv-del" style="margin-top:10px">Gesprek verwijderen…</button>
      </div>
    </aside>
  </div>`;

  // focus op bericht
  const focusId = p.get("m");
  if (focusId) { const el = $("#m" + focusId); if (el) { el.classList.add("focus"); setTimeout(() => el.scrollIntoView({ block: "center" }), 50); } }

  // zoeken binnen gesprek
  let hits = [], hi = -1;
  const find = () => {
    const q = $("#cv-find").value.trim().toLowerCase();
    const words = [...new Set(q.replace(/["“”]/g, "").split(/\s+/).filter(w => w.length >= 2))].sort((a, b) => b.length - a.length);
    $$(".msg").forEach(m => m.classList.remove("search-hit"));
    $$("#cv-msgs mark.f").forEach(mk => mk.replaceWith(document.createTextNode(mk.textContent)));
    hits = []; hi = -1;
    if (!words.length) { $("#cv-findcount").textContent = ""; return; }
    const rx = new RegExp(words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|"), "gi");
    $$(".msg .md").forEach(el => {
      const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
      const nodes = []; while (walker.nextNode()) nodes.push(walker.currentNode);
      nodes.forEach(n => {
        const t = n.nodeValue; rx.lastIndex = 0;
        if (!rx.test(t)) return;
        rx.lastIndex = 0;
        const frag = document.createDocumentFragment(); let last = 0, mt;
        while ((mt = rx.exec(t))) { frag.append(t.slice(last, mt.index)); const mk = document.createElement("mark"); mk.className = "f"; mk.textContent = mt[0]; frag.append(mk); hits.push(mk); last = mt.index + mt[0].length; }
        frag.append(t.slice(last)); n.replaceWith(frag);
      });
    });
    new Set(hits.map(h => h.closest(".msg"))).forEach(m => m.classList.add("search-hit"));
    $("#cv-findcount").textContent = hits.length ? `${hits.length}×` : "0";
    if (hits.length && !focusId) step(1);
  };
  const step = d => { if (!hits.length) return; hi = (hi + d + hits.length) % hits.length; hits[hi].scrollIntoView({ block: "center" }); hits.forEach(h => h.style.outline = ""); hits[hi].style.outline = "2px solid var(--accent)"; $("#cv-findcount").textContent = `${hi + 1}/${hits.length}`; };
  let ft; $("#cv-find").addEventListener("input", () => { clearTimeout(ft); ft = setTimeout(find, 200); });
  $("#cv-find").addEventListener("keydown", e => { if (e.key === "Enter") step(e.shiftKey ? -1 : 1); });
  $("#cv-next").onclick = () => step(1); $("#cv-prev").onclick = () => step(-1);
  if (p.get("q")) find();

  // berichtacties
  $("#cv-msgs").addEventListener("click", e => {
    const b = e.target.closest("[data-act]"); if (!b) return;
    const m = b.closest(".msg"); const mid = +m.dataset.mid; const msg = c.messages.find(x => x.id === mid);
    if (b.dataset.act === "copy") copy(msg.content);
    if (b.dataset.act === "link") copy(`${location.origin}/#/gesprek/${c.id}?m=${mid}`);
    if (b.dataset.act === "remember") newMemoryModal({ text: plain(msg.content), origin: msg.role === "user" ? "user_stated" : "assistant_suggested", kind: msg.role === "user" ? "voorkeur" : "beslissing", conversation_id: c.id, message_id: mid, project_id: c.project_id }, () => router());
  });

  $("#cv-fav").onclick = async () => { await api(`/api/conversations/${c.id}`, { method: "POST", body: { favorite: c.favorite ? 0 : 1 } }); router(); };
  $("#cv-title").onclick = async () => {
    const t = prompt("Nieuwe titel", c.title); if (t && t.trim()) { await api(`/api/conversations/${c.id}`, { method: "POST", body: { title: t.trim() } }); router(); }
  };
  if ($("#cv-resume")) $("#cv-resume").onclick = () => copy(c.resume_command);
  $("#cv-topics").addEventListener("click", e => { const ch = e.target.closest(".chip"); if (ch) ch.classList.toggle("on"); });
  $("#cv-save").onclick = async () => {
    try {
      await api(`/api/conversations/${c.id}`, { method: "POST", body: {
        project_id: $("#cv-project").value ? +$("#cv-project").value : null,
        topic_ids: $$("#cv-topics .chip.on").map(x => +x.dataset.tid),
        tags: $("#cv-tags").value.split(",").map(x => x.trim()).filter(Boolean),
        notes: $("#cv-notes").value } });
      toast("Opgeslagen");
    } catch (err) { toast(err.message, true); }
  };
  $("#cv-sum").onclick = async () => { const r = await api(`/api/conversations/${c.id}/summary`, { method: "POST" }); $("#cv-summary").textContent = r.summary || "(geen tekst)"; toast("Lokale samenvatting gemaakt"); };
  $("#cv-sumedit").onclick = () => modal(`<h2>Samenvatting bewerken</h2><textarea id="se" style="min-height:180px">${esc(c.summary || "")}</textarea>
    <div class="row" style="justify-content:flex-end;margin-top:12px"><button data-close>Annuleren</button><button class="primary" id="se-ok">Opslaan</button></div>`,
    (el, close) => { $("#se-ok", el).onclick = async () => { await api(`/api/conversations/${c.id}`, { method: "POST", body: { summary: $("#se", el).value } }); close(); router(); }; });
  $("#cv-continue").onclick = async () => {
    const q = $("#cv-find").value.trim();
    const r = await api(`/api/conversations/${c.id}/context-pack${q ? "?q=" + encodeURIComponent(q) : ""}`);
    modal(`<h2>Verdergaan met dit gesprek</h2>
      <p class="muted small">Plak dit pakket in een nieuw gesprek met Claude. Het bevat alleen bestaande informatie met bronverwijzingen; geheimen zijn gemaskeerd.
      ${c.url ? "Je kunt het oorspronkelijke gesprek ook openen op claude.ai." : c.resume_command ? "Of hervat de Claude Code-sessie met de hervat-opdracht." : "Er is geen geldige link naar het oorspronkelijke gesprek."}</p>
      <pre class="pack">${esc(r.text)}</pre>
      <div class="row spread" style="margin-top:12px"><span class="small muted">${r.text.length} tekens</span>
      <div class="row">${c.url ? `<a class="btn" href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">Open origineel ↗</a>` : ""}
      ${c.resume_command ? `<button id="cp-resume">Kopieer hervat-opdracht</button>` : ""}
      <button data-close>Sluiten</button><button class="primary" id="cp-copy">Kopieer contextpakket</button></div></div>`,
      el => { $("#cp-copy", el).onclick = () => copy(r.text); if ($("#cp-resume", el)) $("#cp-resume", el).onclick = () => copy(c.resume_command); });
  };
  $("#cv-del").onclick = () => modal(`<h2>Gesprek verwijderen</h2>
    <p>“${esc(c.title)}” wordt verwijderd uit het archief, inclusief zoekindex, bijlagen, labels en <strong>${c.memories.length} afgeleide geheugenitem(s)</strong>. Het oorspronkelijke transcript of je claude.ai-account wordt niet aangeraakt.</p>
    <label class="switch" style="margin:10px 0"><input type="checkbox" id="dl-prevent" checked> Niet opnieuw importeren bij een volgende synchronisatie</label>
    <label class="switch" style="margin:10px 0"><input type="checkbox" id="dl-purge"> Ook direct uit alle bestaande back-ups wissen</label>
    <p class="small muted">Zonder die laatste optie blijft het gesprek in oudere back-ups staan tot ze worden opgeruimd. Bij herstel van een back-up wordt deze verwijdering automatisch opnieuw toegepast.</p>
    <div class="row" style="justify-content:flex-end"><button data-close>Annuleren</button><button class="danger" id="dl-ok">Definitief verwijderen</button></div>`,
    (el, close) => { $("#dl-ok", el).onclick = async () => {
      try {
        const r = await api(`/api/conversations/${c.id}?prevent=${$("#dl-prevent", el).checked ? 1 : 0}&purge_backups=${$("#dl-purge", el).checked ? 1 : 0}`, { method: "DELETE" });
        close(); toast(`Verwijderd (${r.memories_deleted} geheugenitems, ${r.backups_cleaned} back-ups opgeschoond)`); location.hash = "#/gesprekken";
      } catch (err) { toast(err.message, true); }
    }; });
}

// ------------------------------------------------------------ Projecten & onderwerpen
async function viewProjects() {
  await loadLookups();
  app.innerHTML = `
  <div class="page-head"><div><h1>Projecten &amp; onderwerpen</h1><p>Projecten komen automatisch uit je werkmappen (Claude Code) en claude.ai-projecten. Onderwerpen kies je zelf.</p></div></div>
  <div class="grid grid-2">
    <div>
      <div class="section-title"><h2>Projecten</h2><button class="small" id="pj-new">+ Project</button></div>
      <div class="card"><table class="list"><thead><tr><th>Naam</th><th>Gesprekken</th><th>Laatst</th><th></th></tr></thead><tbody>
      ${state.projects.map(p => `<tr data-pid="${p.id}"><td><strong>${esc(p.name)}</strong><div class="small muted">${esc(p.description || "")}</div><div class="small muted path" style="display:inline-block;margin-top:3px">${esc(p.path || "")}</div></td>
        <td><a href="#/gesprekken?project_id=${p.id}">${p.conversations}</a></td><td class="small">${p.last_activity ? rel(p.last_activity) : "—"}</td>
        <td><button class="small ghost" data-pact="edit">Bewerken</button></td></tr>`).join("") || `<tr><td colspan="4" class="muted">Nog geen projecten.</td></tr>`}
      </tbody></table></div>
    </div>
    <div>
      <div class="section-title"><h2>Onderwerpen</h2><div class="row"><button class="small" id="tp-rules" title="Voegt onderwerpen toe aan gesprekken waarin de trefwoorden voorkomen">Trefwoorden toepassen</button><button class="small" id="tp-new">+ Onderwerp</button></div></div>
      <div class="card">${state.topics.map(t => `<div class="mem" data-tid="${t.id}"><div style="flex:1"><div class="row"><span class="dot" style="background:${esc(t.color)}"></span><strong>${esc(t.name)}</strong>
        <a class="small" href="#/gesprekken?topic_id=${t.id}">${t.conversations} gesprekken</a></div>
        <div class="small muted">Trefwoorden: ${esc(t.keywords || "—")}</div></div><button class="small ghost" data-tact="edit">Bewerken</button></div>`).join("") || '<div class="muted">Geen onderwerpen.</div>'}</div>
    </div>
  </div>`;
  const projForm = (p = {}) => modal(`<h2>${p.id ? "Project bewerken" : "Nieuw project"}</h2>
    <div class="field"><label>Naam</label><input id="pf-name" value="${esc(p.name || "")}" style="width:100%"></div>
    <div class="field"><label>Omschrijving</label><textarea id="pf-desc">${esc(p.description || "")}</textarea></div>
    <div class="row spread">${p.id ? `<button class="danger" id="pf-del">Verwijderen</button>` : "<span></span>"}<div class="row"><button data-close>Annuleren</button><button class="primary" id="pf-ok">Opslaan</button></div></div>
    ${p.id ? '<p class="small muted">Verwijderen haalt alleen de projectindeling weg; gesprekken blijven bewaard.</p>' : ""}`,
    (el, close) => {
      $("#pf-ok", el).onclick = async () => { const body = { name: $("#pf-name", el).value.trim(), description: $("#pf-desc", el).value }; if (!body.name) return toast("Naam is verplicht", true);
        await api(p.id ? `/api/projects/${p.id}` : "/api/projects", { method: "POST", body }); close(); router(); };
      if ($("#pf-del", el)) $("#pf-del", el).onclick = async () => { await api(`/api/projects/${p.id}`, { method: "DELETE" }); close(); router(); };
    });
  const topicForm = (t = {}) => modal(`<h2>${t.id ? "Onderwerp bewerken" : "Nieuw onderwerp"}</h2>
    <div class="grid grid-2"><div class="field"><label>Naam</label><input id="tf-name" value="${esc(t.name || "")}"></div>
    <div class="field"><label>Kleur</label><input type="color" id="tf-color" value="${esc(t.color || "#6b8afd")}" style="height:40px;width:80px"></div></div>
    <div class="field"><label>Trefwoorden (komma-gescheiden, optioneel)</label><input id="tf-kw" value="${esc(t.keywords || "")}" style="width:100%"></div>
    <div class="row spread">${t.id ? `<button class="danger" id="tf-del">Verwijderen</button>` : "<span></span>"}<div class="row"><button data-close>Annuleren</button><button class="primary" id="tf-ok">Opslaan</button></div></div>`,
    (el, close) => {
      $("#tf-ok", el).onclick = async () => { try { await api(t.id ? `/api/topics/${t.id}` : "/api/topics", { method: "POST", body: { name: $("#tf-name", el).value, color: $("#tf-color", el).value, keywords: $("#tf-kw", el).value } }); close(); router(); } catch (e) { toast(e.message, true); } };
      if ($("#tf-del", el)) $("#tf-del", el).onclick = async () => { await api(`/api/topics/${t.id}`, { method: "DELETE" }); close(); router(); };
    });
  $("#pj-new").onclick = () => projForm();
  $("#tp-new").onclick = () => topicForm();
  $("#tp-rules").onclick = async () => { const r = await api("/api/topics/apply-rules", { method: "POST" }); toast(`${r.added} koppelingen toegevoegd`); router(); };
  state.viewClick = e => {
    const pe = e.target.closest("[data-pact]"); if (pe) projForm(state.projects.find(x => x.id === +pe.closest("[data-pid]").dataset.pid));
    const te = e.target.closest("[data-tact]"); if (te) topicForm(state.topics.find(x => x.id === +te.closest("[data-tid]").dataset.tid));
  };
}

// ------------------------------------------------------------ Geheugen
async function viewMemories() {
  await loadLookups();
  const p = qs();
  const kind = p.get("kind") || "";
  app.innerHTML = `
  <div class="page-head"><div><h1>Geheugen</h1><p>Voorkeuren, beslissingen, doelen en acties — altijd met herkomst en bron. Voorstellen van Claude tellen pas als jouw voorkeur na bevestiging.</p></div>
    <button class="primary" id="mm-new">+ Nieuw item</button></div>
  <div class="tabs" id="mm-tabs">${[["", "Alles"], ...KINDS.map(k => [k, KIND_LABELS[k]])].map(([k, l]) => `<button data-k="${k}" class="${k === kind ? "active" : ""}">${l}</button>`).join("")}</div>
  <div class="filters">
    <input id="mm-q" type="search" placeholder="Zoek in geheugen" value="${esc(p.get("q") || "")}">
    <select id="mm-status"><option value="actief,voorstel">Actief + voorstellen</option><option value="actief">Alleen actief</option><option value="voorstel">Alleen voorstellen</option><option value="afgerond">Afgerond</option><option value="vervangen">Vervangen (historie)</option><option value="verworpen">Verworpen</option><option value="alle">Alles</option></select>
    <select id="mm-origin"><option value="">Elke herkomst</option>${Object.entries(ORIGINS).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select>
    <select id="mm-proj"><option value="">Alle projecten</option>${state.projects.map(x => `<option value="${x.id}">${esc(x.name)}</option>`).join("")}</select>
  </div>
  <div class="card" id="mm-list"><div class="loading">Laden…</div></div>`;
  if (p.get("status")) $("#mm-status").value = p.get("status");
  let k = kind;
  const load = async () => {
    const u = new URLSearchParams({ status: $("#mm-status").value });
    if (k) u.set("kind", k);
    if ($("#mm-q").value.trim()) u.set("q", $("#mm-q").value.trim());
    if ($("#mm-origin").value) u.set("origin", $("#mm-origin").value);
    if ($("#mm-proj").value) u.set("project_id", $("#mm-proj").value);
    const list = await api("/api/memories?" + u);
    $("#mm-list").innerHTML = list.map(m => memRow(m)).join("") || `<div class="empty">Geen items. Bewaar iets vanuit een gesprek of maak een nieuw item.</div>`;
  };
  $("#mm-tabs").onclick = e => { const b = e.target.closest("button"); if (!b) return; k = b.dataset.k; $$("#mm-tabs button").forEach(x => x.classList.toggle("active", x === b)); setQs({ kind: k }); load(); };
  let t; $("#mm-q").oninput = () => { clearTimeout(t); t = setTimeout(load, 250); };
  ["#mm-status", "#mm-origin", "#mm-proj"].forEach(s => $(s).onchange = load);
  $("#mm-list").addEventListener("click", e => memAction(e, load));
  $("#mm-new").onclick = () => newMemoryModal({ kind: k || "voorkeur" }, load);
  await load();
}

// ------------------------------------------------------------ Import & instellingen
async function viewSettings() {
  const [st, set, bk, ex] = await Promise.all([api("/api/status"), api("/api/settings"), api("/api/backups"), api("/api/exclusions")]);
  const s = set.settings, inst = set.installation, cc = st.sources[0], exs = st.sources[1];
  const ok = b => b ? '<span class="badge ok">ja</span>' : '<span class="badge warn">nee</span>';
  app.innerHTML = `
  <div class="page-head"><div><h1>Import &amp; instellingen</h1><p>Bronnen, importeren, opslag, back-ups en privacy.</p></div></div>

  <div class="section-title"><h2>Bronnen</h2></div>
  <div class="grid grid-2">
    <div class="card">
      <div class="row spread"><h3 style="margin:0">Claude Code</h3>${cc.mode === "automatisch" ? '<span class="badge ok">Synchroniseert automatisch</span>' : '<span class="badge warn">Niet automatisch</span>'}</div>
      <p class="small muted">Lokale sessietranscripten. Nieuwe berichten worden na elk antwoord via hooks opgeslagen; het achtergrondproces vangt vertraagde of gemiste berichten op.</p>
      <div class="kv"><div>Hooks geïnstalleerd</div><div>${ok(inst.hooks)}</div><div>MCP-server geregistreerd</div><div>${ok(inst.mcp)}</div>
        <div>Skill geïnstalleerd</div><div>${ok(inst.skill)}</div><div>Autostart achtergrond</div><div>${ok(inst.autostart)}</div>
        <div>Transcriptmap(pen)</div><div>${cc.transcript_dirs.map(d => `<span class="path">${esc(d)}</span>`).join(" ")}</div>
        <div>Transcripten gevonden</div><div>${cc.transcript_files}</div>
        <div>Oudste nog op schijf</div><div>${esc(st.oldest_transcript_on_disk || "—")}</div></div>
      <div class="banner warn" style="margin-top:10px">${esc(cc.warning)}</div>
      ${!inst.hooks ? `<div class="banner info">Installeer de koppeling met: <code>python memory_hub.py install</code> (zie handleiding).</div>` : ""}
      <div class="row"><button id="st-sync">↻ Nu synchroniseren</button><button id="st-rescan" title="Leest alle transcripten opnieuw; dubbele berichten worden overgeslagen">Alles opnieuw controleren</button></div>
      ${cc.file_errors.length ? `<div class="banner bad" style="margin-top:10px">Fouten in ${cc.file_errors.length} bestand(en): ${cc.file_errors.map(f => esc(f.path.split(/[\\/]/).pop() + ": " + f.last_error)).join("; ")}</div>` : ""}
    </div>
    <div class="card">
      <div class="row spread"><h3 style="margin:0">claude.ai — web, desktop en mobiel</h3><span class="badge">Handmatige import nodig</span></div>
      <p class="small muted">${esc(exs.why)}</p>
      <ol class="small"><li>Ga op claude.ai naar <strong>Instellingen → Privacy → Gegevens exporteren</strong>.</li><li>Download de .zip uit de e-mail die je ontvangt.</li><li>Sleep hem hieronder, of zet hem in de importmap (wordt automatisch opgepakt zolang Memory Hub draait).</li></ol>
      <div class="dropzone" id="dz">Sleep je Claude-export (.zip of conversations.json) hierheen<br><span class="small">of klik om te kiezen</span><input type="file" id="dz-file" accept=".zip,.json" hidden></div>
      <div id="dz-result"></div>
      <div class="kv" style="margin-top:12px"><div>Importmap</div><div><span class="path">${esc(exs.import_folder)}</span></div>
        <div>Laatste import</div><div>${exs.last_import ? fmtDate(exs.last_import) : "nog nooit"}</div>
        <div>Wachtend</div><div>${exs.pending_in_import_folder.map(esc).join(", ") || "niets"}</div></div>
      <div class="row" style="margin-top:10px"><button id="st-scan">Importmap nu controleren</button></div>
      <p class="small muted">Bij een nieuwe export worden nieuwe en bijgewerkte gesprekken herkend; bestaande berichten worden niet dubbel opgeslagen. Bestanden zoals afbeeldingen en pdf's zitten niet in de export — alleen hun naam (en soms geëxtraheerde tekst).</p>
    </div>
  </div>

  <div class="section-title"><h2>Privacy</h2></div>
  <div class="card stack">
    <div class="banner ok">${esc(st.external_services)}</div>
    <label class="switch"><input type="checkbox" id="st-pause" ${s.paused ? "checked" : ""}> Archivering pauzeren (wat je tijdens de pauze bespreekt, wordt niet bewaard)</label>
    <label class="switch"><input type="checkbox" id="st-redact" ${s.redact_secrets_in_views ? "checked" : ""}> Wachtwoorden en API-sleutels maskeren in weergaven, zoekfragmenten en MCP-uitvoer</label>
    <label class="switch"><input type="checkbox" id="st-sub" ${s.include_subagents ? "checked" : ""}> Ook transcripten van subagents archiveren</label>
    <div class="field"><label>Projectmappen uitsluiten (één patroon per regel, bv. <code>*/geheim*</code> of een volledig pad)</label>
      <textarea id="st-excl">${esc((s.exclude_project_patterns || []).join("\n"))}</textarea></div>
    <p class="small muted">Eén gesprek uitsluiten: verwijder het met ‘niet opnieuw importeren’, of typ <code>[geen-archief]</code> in een Claude Code-gesprek.</p>
    <details><summary>Uitgesloten gesprekken (${ex.length})</summary>
      <table class="list"><tbody>${ex.map(x => `<tr><td class="small">${esc(SOURCES[x.source] || x.source)}</td><td class="small path">${esc(x.ext_id)}</td><td class="small">${esc(x.reason)}</td><td class="small">${fmtDate(x.at)}</td>
      <td><button class="small" data-unex="${esc(x.source)}|${esc(x.ext_id)}">Weer toestaan</button></td></tr>`).join("") || '<tr><td class="muted">Geen.</td></tr>'}</tbody></table></details>
    <div class="row"><button class="primary" id="st-save">Privacy-instellingen opslaan</button></div>
  </div>

  <div class="section-title"><h2>Opslag &amp; export</h2></div>
  <div class="card">
    <div class="kv"><div>Gegevensmap</div><div><span class="path">${esc(set.paths.data)}</span></div>
      <div>Database</div><div><span class="path">${esc(set.paths.database)}</span> (${bytes(st.database_size)})</div>
      <div>Programma</div><div><span class="path">${esc(set.paths.root)}</span></div>
      <div>Exports</div><div><span class="path">${esc(set.paths.exports)}</span></div></div>
    <p class="small muted">De gegevens staan in je eigen gebruikersmap, los van de broncode, en blijven bewaard na afsluiten of herstarten.</p>
    <div class="row"><button id="ex-json">Exporteer alles als JSON</button><button id="ex-md">Exporteer alles als Markdown (.zip)</button>
    <label class="switch small"><input type="checkbox" id="ex-red"> geheimen maskeren in export</label></div>
  </div>

  <div class="section-title"><h2>Back-ups</h2><button class="small primary" id="bk-new">Nu back-up maken</button></div>
  <div class="card">
    <p class="small muted">${esc(bk.policy)} Automatisch elke ${s.auto_backup_hours} uur; de nieuwste ${s.keep_backups} worden bewaard.</p>
    <div class="row small"><label>Automatisch elke</label><input type="number" id="bk-hours" value="${s.auto_backup_hours}" min="0" style="width:80px"> uur, bewaar <input type="number" id="bk-keep" value="${s.keep_backups}" min="1" style="width:80px"> back-ups <button class="small" id="bk-saveset">Opslaan</button></div>
    <table class="list" style="margin-top:10px"><thead><tr><th>Back-up</th><th>Gemaakt</th><th>Inhoud</th><th>Grootte</th><th></th></tr></thead><tbody>
    ${bk.backups.map(b => `<tr data-b="${esc(b.name)}"><td class="small path">${esc(b.name)}</td><td class="small">${esc(b.created)}</td><td class="small">${b.conversations ?? "?"} gesprekken, ${b.messages ?? "?"} berichten</td><td class="small">${bytes(b.size)}</td>
      <td class="row"><button class="small" data-bact="restore">Herstellen</button><button class="small ghost danger" data-bact="del">Verwijderen</button></td></tr>`).join("") || '<tr><td colspan="5" class="muted">Nog geen back-ups.</td></tr>'}
    </tbody></table>
  </div>

  <div class="section-title"><h2>Weergave &amp; toegang</h2></div>
  <div class="card stack">
    <div class="row"><label style="margin:0">Thema</label><select id="st-theme"><option value="auto">Automatisch</option><option value="light">Licht</option><option value="dark">Donker</option></select></div>
    <div class="row"><label style="margin:0">Synchronisatie-interval achtergrond (seconden)</label><input type="number" id="st-int" min="5" value="${s.watch_interval_seconds}" style="width:90px"><button class="small" id="st-intsave">Opslaan</button></div>
    <label class="switch"><input type="checkbox" id="st-remote" ${s.allow_remote ? "checked" : ""}> Toegang vanaf andere apparaten in je netwerk toestaan (vereist toegangstoken; herstart nodig)</label>
    <div class="small muted">Standaard is Memory Hub alleen bereikbaar via 127.0.0.1 op deze computer. Externe toegang gaat over onversleuteld HTTP; gebruik dit alleen op een vertrouwd netwerk of via een VPN.</div>
    ${s.allow_remote ? `<div class="row"><button class="small" id="st-token">Toon nieuw toegangstoken</button><span id="st-tokenout" class="path"></span></div>` : ""}
  </div>`;

  $("#st-theme").value = localTheme();
  $("#st-theme").onchange = e => setTheme(e.target.value);
  $("#st-sync").onclick = async () => { const r = await api("/api/sync", { method: "POST" }); toast(`${r.claude_code ? r.claude_code.new_messages : 0} nieuwe berichten`); router(); };
  $("#st-rescan").onclick = async () => { const r = await api("/api/import/rescan-claude-code", { method: "POST" }); toast(`Gecontroleerd: ${r.files} bestanden, ${r.new_messages} nieuwe berichten`); router(); };
  $("#st-scan").onclick = async () => { const r = await api("/api/import/scan", { method: "POST" }); toast(r.results.length ? r.results.map(x => `${x.file}: ${x.ok ? x.new_conversations + " nieuw, " + x.updated_conversations + " bijgewerkt" : x.error}`).join("; ") : "Geen nieuwe bestanden in de importmap"); router(); };
  const dz = $("#dz"), fi = $("#dz-file");
  const upload = async file => {
    $("#dz-result").innerHTML = `<div class="loading">Importeren van ${esc(file.name)}…</div>`;
    try {
      const r = await api("/api/import/upload", { method: "POST", raw: true, body: file, headers: { "X-Filename": encodeURIComponent(file.name), "Content-Type": "application/octet-stream" } });
      $("#dz-result").innerHTML = `<div class="banner ok" style="margin-top:10px">Geïmporteerd: ${r.new_conversations} nieuwe en ${r.updated_conversations} bijgewerkte gesprekken, ${r.new_messages} nieuwe berichten, ${r.unchanged} ongewijzigd${r.excluded ? `, ${r.excluded} uitgesloten` : ""}${r.memories ? `, ${r.memories} claude.ai-geheugenitems (als ‘afgeleid’)` : ""}.</div>`;
    } catch (e) { $("#dz-result").innerHTML = `<div class="banner bad" style="margin-top:10px">${esc(e.message)}</div>`; }
  };
  dz.onclick = () => fi.click();
  fi.onchange = () => fi.files[0] && upload(fi.files[0]);
  dz.ondragover = e => { e.preventDefault(); dz.classList.add("over"); };
  dz.ondragleave = () => dz.classList.remove("over");
  dz.ondrop = e => { e.preventDefault(); dz.classList.remove("over"); e.dataTransfer.files[0] && upload(e.dataTransfer.files[0]); };
  $("#st-pause").onchange = async e => { await api("/api/pause", { method: "POST", body: { paused: e.target.checked } }); toast(e.target.checked ? "Gepauzeerd" : "Hervat"); refreshPill(); };
  $("#st-save").onclick = async () => {
    await api("/api/settings", { method: "POST", body: { redact_secrets_in_views: $("#st-redact").checked, include_subagents: $("#st-sub").checked,
      exclude_project_patterns: $("#st-excl").value.split("\n").map(x => x.trim()).filter(Boolean) } });
    toast("Opgeslagen");
  };
  state.viewClick = async e => {
    const u = e.target.closest("[data-unex]");
    if (u) { const [source, ...rest] = u.dataset.unex.split("|"); await api("/api/exclusions/remove", { method: "POST", body: { source, ext_id: rest.join("|") } }); toast("Weer toegestaan; wordt bij de volgende synchronisatie opnieuw ingelezen (Claude Code) of bij een nieuwe import (claude.ai)."); router(); }
    const b = e.target.closest("[data-bact]");
    if (b) {
      const name = b.closest("[data-b]").dataset.b;
      if (b.dataset.bact === "restore") {
        modal(`<h2>Back-up herstellen</h2><p>De huidige database wordt vervangen door <span class="path">${esc(name)}</span>. Er wordt eerst automatisch een veiligheidsback-up van de huidige stand gemaakt.</p>
          <label class="switch"><input type="checkbox" id="rb-re" checked> Eerdere verwijderingen opnieuw toepassen (aanbevolen)</label>
          <div class="row" style="justify-content:flex-end;margin-top:16px"><button data-close>Annuleren</button><button class="primary" id="rb-ok">Herstellen</button></div>`,
          (el, close) => { $("#rb-ok", el).onclick = async () => { try { const r = await api(`/api/backups/${encodeURIComponent(name)}/restore`, { method: "POST", body: { reapply_deletions: $("#rb-re", el).checked } }); close(); toast(`Hersteld. Veiligheidsback-up: ${r.safety_backup}; ${r.deletions_reapplied} verwijderingen opnieuw toegepast.`); router(); } catch (err) { toast(err.message, true); } }; });
      } else if (await confirmBox("Back-up verwijderen", esc(name), "Verwijderen", true)) { await api(`/api/backups/${encodeURIComponent(name)}`, { method: "DELETE" }); router(); }
    }
  };
  $("#bk-new").onclick = async () => { const r = await api("/api/backups", { method: "POST" }); toast("Back-up gemaakt: " + r.name); router(); };
  $("#bk-saveset").onclick = async () => { await api("/api/settings", { method: "POST", body: { auto_backup_hours: +$("#bk-hours").value, keep_backups: Math.max(1, +$("#bk-keep").value) } }); toast("Opgeslagen"); router(); };
  const exp = async fmt => { const r = await api("/api/export", { method: "POST", body: { format: fmt, redact: $("#ex-red").checked } }); toast("Export gemaakt: " + r.name); download("/api/export/download?name=" + encodeURIComponent(r.name)); };
  $("#ex-json").onclick = () => exp("json"); $("#ex-md").onclick = () => exp("markdown");
  $("#st-intsave").onclick = async () => { await api("/api/settings", { method: "POST", body: { watch_interval_seconds: Math.max(5, +$("#st-int").value) } }); toast("Opgeslagen"); };
  $("#st-remote").onchange = async e => {
    if (e.target.checked && !(await confirmBox("Externe toegang", "Andere apparaten in je netwerk kunnen dan, met het toegangstoken, je archief openen. Herstart Memory Hub daarna.", "Inschakelen"))) { e.target.checked = false; return; }
    await api("/api/settings", { method: "POST", body: { allow_remote: e.target.checked } }); toast("Opgeslagen — herstart Memory Hub om dit toe te passen"); router();
  };
  if ($("#st-token")) $("#st-token").onclick = async () => { const r = await api("/api/settings/remote-token", { method: "POST" }); $("#st-tokenout").textContent = r.token; toast("Nieuw token; open http://<ip-van-deze-computer>:" + s.port + "/?token=…"); };
}

// ------------------------------------------------------------ thema
function localTheme() { try { return localStorage.getItem("mh-theme") || "auto"; } catch { return "auto"; } }
function setTheme(t) {
  try { localStorage.setItem("mh-theme", t); } catch { /* geen opslag beschikbaar */ }
  if (t === "auto") document.documentElement.removeAttribute("data-theme"); else document.documentElement.setAttribute("data-theme", t);
  $("#theme-select").value = t;
}
$("#theme-select").onchange = e => setTheme(e.target.value);
setTheme(localTheme());
router();
setInterval(refreshPill, 30000);
