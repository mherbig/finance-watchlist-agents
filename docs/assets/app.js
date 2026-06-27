"use strict";

// Dashboard: laedt reports/index.json, rendert Grid gruppiert nach Assetklasse,
// Detail-Modal laedt reports/<safe_name>/<date>.json.
// Bias/Trend werden NUR als Analyse dargestellt, nie als Kauf-/Verkaufssignal.

const ASSET_LABELS = {
  index: "Indizes",
  forex: "Forex",
  crypto: "Crypto",
  energy: "Energie",
  metal: "Metalle",
  stock: "Aktien",
};
const ASSET_ORDER = ["index", "forex", "crypto", "energy", "metal", "stock"];

const TREND_LABELS = { up: "up", down: "down", side: "side" };

// safe_name muss src/data/symbol_map.safe_name spiegeln: display.replace("/", "-")
function safeName(display) {
  return String(display).split("/").join("-");
}

function fmtNum(x, digits) {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const n = Number(x);
  const d = digits === undefined ? (Math.abs(n) < 10 ? 4 : 2) : digits;
  return n.toLocaleString("de-DE", { minimumFractionDigits: d, maximumFractionDigits: d });
}

function fmtPct(x, digits) {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const d = digits === undefined ? 2 : digits;
  const n = Number(x);
  const sign = n > 0 ? "+" : "";
  return sign + n.toFixed(d) + " %";
}

function fmtStamp(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso);
  return d.toLocaleString("de-DE", {
    day: "numeric", month: "numeric", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

function fmtDate(d) {
  if (!d) return "";
  const dt = new Date(d);
  return Number.isNaN(dt.getTime()) ? String(d) : dt.toLocaleDateString("de-DE");
}

function trendChip(trend) {
  if (!trend) return '<span class="chip chip-na">n/v</span>';
  const cls = trend === "up" ? "chip-up" : trend === "down" ? "chip-down" : "chip-side";
  return `<span class="chip ${cls}">${TREND_LABELS[trend] || trend}</span>`;
}

function changeClass(change) {
  if (change === null || change === undefined || Number.isNaN(change)) return "";
  return Number(change) > 0 ? "up-text" : Number(change) < 0 ? "down-text" : "";
}

function escapeHtml(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// Kleines, sicheres Markdown-ish-Rendering: HTML wird ZUERST escaped, dann
// werden nur **bold**, Bullet-Listen und Absaetze auf erlaubte Tags abgebildet.
function renderAgentBody(text) {
  const blocks = String(text == null ? "" : text).split(/\n{2,}/);
  const out = [];
  for (const block of blocks) {
    const lines = block.split(/\n/);
    const isList = lines.every((l) => /^\s*[-*]\s+/.test(l) && l.trim() !== "");
    if (isList) {
      const items = lines
        .map((l) => `<li>${inlineMd(l.replace(/^\s*[-*]\s+/, ""))}</li>`)
        .join("");
      out.push(`<ul>${items}</ul>`);
    } else {
      // Einzel-Zeilenumbrueche innerhalb eines Absatzes als <br> erhalten.
      const para = lines.map((l) => inlineMd(l)).join("<br>");
      out.push(`<p>${para}</p>`);
    }
  }
  return out.join("");
}

// Inline-Markdown auf bereits-escaptem Text: nur **bold**.
function inlineMd(line) {
  return escapeHtml(line).replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
}

// Konviktion 1..5 als gefuellte/leere Punkte (●●●○○ fuer 3/5).
function convictionDots(conviction) {
  const n = Number(conviction);
  if (!Number.isFinite(n) || n < 1) return "";
  const filled = Math.max(0, Math.min(5, Math.round(n)));
  return "●".repeat(filled) + "○".repeat(5 - filled);
}

// Signal-Chip fuer das Grid: LONG ▲ (gruen) / SHORT ▼ (rot) + Konviktions-Punkte.
function signalChip(r) {
  if (!r.has_signal) return "";
  const dir = r.direction;
  if (dir !== "LONG" && dir !== "SHORT") return ""; // FLAT -> kein Chip
  const cls = dir === "LONG" ? "sig-long" : "sig-short";
  const arrow = dir === "LONG" ? "▲" : "▼";
  const dots = convictionDots(r.conviction);
  const dotsHtml = dots
    ? ` <span class="sig-dots" title="Konviktion ${escapeHtml(String(r.conviction))}/5">${dots}</span>`
    : "";
  return `<span class="signal-chip ${cls}">${dir} ${arrow}${dotsHtml}</span> `;
}

function agentBadge(r) {
  if (!r.has_agent_analysis) return "";
  const agents = Array.isArray(r.agents_run) ? r.agents_run : [];
  if (r.track === "fundamental") {
    const tip = "Volles Fundamental-Panel: " + agents.join(", ");
    return ` <span class="agent-badge agent-badge-panel" title="${escapeHtml(tip)}">🧩 Fundamental · ${agents.length}</span>`;
  }
  const tip = "Technical/Macro-Agent";
  return ` <span class="agent-badge agent-badge-tech" title="${escapeHtml(tip)}">📈 Technisch</span>`;
}

function renderGrid(rows) {
  const root = document.getElementById("grid");
  root.innerHTML = "";

  const byClass = {};
  for (const r of rows) {
    (byClass[r.asset_class] = byClass[r.asset_class] || []).push(r);
  }

  const classes = ASSET_ORDER.filter((c) => byClass[c]);
  for (const c of Object.keys(byClass)) {
    if (!classes.includes(c)) classes.push(c);
  }

  for (const cls of classes) {
    const group = document.createElement("section");
    group.className = "group";
    const heading = ASSET_LABELS[cls] || cls;
    group.innerHTML = `<h2>${escapeHtml(heading)}</h2>`;

    const rowsWrap = document.createElement("div");
    rowsWrap.className = "rows";

    for (const r of byClass[cls]) {
      const el = document.createElement("div");
      el.className = "row" + (r.available ? "" : " unavailable");

      const badge = agentBadge(r);
      const dataDate = r.date
        ? `<span class="col-time">Datenstand: ${escapeHtml(fmtDate(r.date))}</span>`
        : "";
      const anaTime = r.generated_at
        ? `<span class="col-time">Analyse: ${escapeHtml(fmtStamp(r.generated_at))}</span>`
        : "";
      const time = dataDate + anaTime;

      if (!r.available) {
        el.innerHTML = `
          <div class="col-label">${escapeHtml(r.display)}${badge}<span class="col-sub">${escapeHtml(r.symbol || "")}</span>${time}</div>
          <div class="col-price">–</div>
          <div class="col-change">–</div>
          <div class="chip chip-na">n/v</div>
          <div class="col-rsi">–</div>
          <div class="col-headline">Daten n/v</div>`;
      } else {
        el.innerHTML = `
          <div class="col-label">${escapeHtml(r.display)}${badge}<span class="col-sub">${escapeHtml(r.symbol || "")}</span>${time}</div>
          <div class="col-price">${fmtNum(r.price)}</div>
          <div class="col-change ${changeClass(r.change_pct)}">${fmtPct(r.change_pct)}</div>
          <div>${trendChip(r.trend)}</div>
          <div class="col-rsi">RSI ${r.rsi == null ? "–" : fmtNum(r.rsi, 1)}</div>
          <div class="col-headline">${signalChip(r)}${escapeHtml(r.headline || "")}</div>`;
        el.addEventListener("click", () => openDetail(r));
      }
      rowsWrap.appendChild(el);
    }
    group.appendChild(rowsWrap);
    root.appendChild(group);
  }
}

function renderAgentAnalysis(aa) {
  if (!aa || typeof aa !== "object") {
    return `<div class="agent-none">Noch keine Agent-Analyse.</div>`;
  }

  const sections = Array.isArray(aa.sections) ? aa.sections : [];
  const sectionsHtml = sections
    .map(
      (s) => `
      <div class="agent-section">
        <h5>${escapeHtml(s.title || "")}</h5>
        <div class="agent-body">${renderAgentBody(s.body || "")}</div>
      </div>`
    )
    .join("");

  const agentsRun = Array.isArray(aa.agents_run) ? aa.agents_run : [];
  const agentsStr = agentsRun.map((a) => escapeHtml(a)).join(", ");
  let stamp = aa.generated_at || "";
  if (stamp) {
    const d = new Date(stamp);
    if (!Number.isNaN(d.getTime())) stamp = d.toLocaleString("de-DE");
  }
  const metaParts = [];
  if (agentsStr) metaParts.push(`Agenten: ${agentsStr}`);
  if (stamp) metaParts.push(`erstellt ${escapeHtml(stamp)}`);
  if (aa.model) metaParts.push(`Modell ${escapeHtml(aa.model)}`);

  return `
    <div class="agent-analysis">
      <h4 class="agent-title">🤖 Agent-Analyse</h4>
      <div class="agent-summary">${escapeHtml(aa.summary || "")}</div>
      ${sectionsHtml}
      <div class="agent-meta">${metaParts.join(" · ")}</div>
    </div>`;
}

function renderSignal(sig) {
  if (!sig || typeof sig !== "object" || !sig.direction) {
    return `<div class="signal-none">Noch kein Signal.</div>`;
  }
  const dir = sig.direction;
  const dirCls = dir === "LONG" ? "up-text" : dir === "SHORT" ? "down-text" : "";
  const arrow = dir === "LONG" ? " ▲" : dir === "SHORT" ? " ▼" : "";
  const dots = convictionDots(sig.conviction);
  const entryType = sig.entry_type === "pullback" ? "Pullback" : "Market";

  let rows = "";
  if (dir === "FLAT") {
    rows = `<div class="signal-flat">Kein aktiver Trade (FLAT).</div>`;
  } else {
    rows = `
      <div class="kv">
        <div><div class="k">Einstiegsart</div><div class="v">${escapeHtml(entryType)}</div></div>
        <div><div class="k">Entry</div><div class="v">${fmtNum(sig.entry)}</div></div>
        <div><div class="k">Stop-Loss</div><div class="v">${fmtNum(sig.stop_loss)}</div></div>
        <div><div class="k">Take-Profit</div><div class="v">${fmtNum(sig.take_profit)}</div></div>
        <div><div class="k">Take-Profit 2</div><div class="v">${sig.take_profit_2 == null ? "–" : fmtNum(sig.take_profit_2)}</div></div>
        <div><div class="k">R:R</div><div class="v">${sig.rr == null ? "–" : fmtNum(sig.rr, 2)}</div></div>
        <div><div class="k">Horizont</div><div class="v">${sig.horizon_days == null ? "–" : escapeHtml(String(sig.horizon_days)) + " Tage"}</div></div>
      </div>`;
  }

  return `
    <div class="signal-box">
      <h4 class="signal-title">📍 Signal</h4>
      <div class="signal-head">
        <span class="signal-dir ${dirCls}">${escapeHtml(dir)}${arrow}</span>
        ${dots ? `<span class="sig-dots" title="Konviktion">${dots}</span>` : ""}
      </div>
      ${rows}
      ${sig.rationale ? `<div class="signal-rationale">${escapeHtml(sig.rationale)}</div>` : ""}
    </div>`;
}

async function openDetail(row) {
  const url = `reports/${safeName(row.display)}/${row.date}.json`;
  const body = document.getElementById("modal-body");
  body.innerHTML = `<p class="loading">Lade Detail …</p>`;
  showModal();

  let rep;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error("HTTP " + res.status);
    rep = await res.json();
  } catch (err) {
    body.innerHTML = `<p class="error">Detail konnte nicht geladen werden (${escapeHtml(url)}): ${escapeHtml(err.message)}</p>`;
    return;
  }

  const snap = rep.snapshot || {};
  const t = rep.technical;

  let html = `
    <h3>${escapeHtml(rep.display)}</h3>
    <p class="modal-sym">${escapeHtml(rep.symbol || "")} · ${escapeHtml(ASSET_LABELS[rep.asset_class] || rep.asset_class)} · ${escapeHtml(rep.date)}</p>

    <div class="detail-section">
      <h4>Snapshot</h4>
      <div class="kv">
        <div><div class="k">Preis</div><div class="v">${fmtNum(snap.price)} ${escapeHtml(snap.currency || "")}</div></div>
        <div><div class="k">Tagesänderung</div><div class="v ${changeClass(snap.change_pct)}">${fmtPct(snap.change_pct)}</div></div>
      </div>
    </div>`;

  if (t) {
    const macd = t.macd
      ? `MACD ${fmtNum(t.macd.macd, 4)} / Signal ${fmtNum(t.macd.signal, 4)} / Hist ${fmtNum(t.macd.hist, 4)}`
      : "–";
    const levels = Array.isArray(t.levels)
      ? t.levels.map((l) => `<li>${escapeHtml(l.type === "resistance" ? "Widerstand" : "Unterstützung")}: ${fmtNum(l.price)}</li>`).join("")
      : "";

    html += `
      <div class="detail-section">
        <h4>Technische Lesart (Analyse, kein Signal)</h4>
        <div class="kv">
          <div><div class="k">Trend</div><div class="v">${trendChip(t.trend)}</div></div>
          <div><div class="k">Bias</div><div class="v">${escapeHtml(t.bias || "–")}</div></div>
          <div><div class="k">RSI(14)</div><div class="v">${t.rsi14 == null ? "–" : fmtNum(t.rsi14, 2)}</div></div>
          <div><div class="k">SMA 20</div><div class="v">${t.sma20 == null ? "–" : fmtNum(t.sma20)}</div></div>
          <div><div class="k">SMA 50</div><div class="v">${t.sma50 == null ? "–" : fmtNum(t.sma50)}</div></div>
          <div><div class="k">SMA 200</div><div class="v">${t.sma200 == null ? "–" : fmtNum(t.sma200)}</div></div>
          <div><div class="k">ATR(14)</div><div class="v">${t.atr14 == null ? "–" : fmtNum(t.atr14)}</div></div>
          <div><div class="k">52W-Hoch</div><div class="v">${t.high_52w == null ? "–" : fmtNum(t.high_52w)}</div></div>
          <div><div class="k">52W-Tief</div><div class="v">${t.low_52w == null ? "–" : fmtNum(t.low_52w)}</div></div>
          <div><div class="k">Abstand 52W-Hoch</div><div class="v">${fmtPct(t.pct_from_high)}</div></div>
          <div><div class="k">Abstand 52W-Tief</div><div class="v">${fmtPct(t.pct_from_low)}</div></div>
        </div>
        <div class="kv" style="margin-top:8px"><div><div class="k">MACD</div><div class="v">${escapeHtml(macd)}</div></div></div>
      </div>

      <div class="detail-section">
        <h4>Schlüssel-Level</h4>
        <ul class="levels-list">${levels || "<li>–</li>"}</ul>
      </div>`;
  } else {
    html += `<div class="detail-section"><p class="error">Keine technischen Daten verfügbar.</p></div>`;
  }

  html += renderSignal(rep.signal);

  html += renderAgentAnalysis(rep.agent_analysis);

  html += `
    <div class="headline-box">${escapeHtml(rep.headline || "")}</div>`;

  body.innerHTML = html;
}

function showModal() {
  document.getElementById("modal").hidden = false;
}
function hideModal() {
  document.getElementById("modal").hidden = true;
}

function wireModal() {
  document.getElementById("modal-close").addEventListener("click", hideModal);
  document.getElementById("modal").addEventListener("click", (e) => {
    if (e.target.id === "modal") hideModal();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hideModal();
  });
}

// Forward-Test-Zusammenfassung (optional; track_record.json kann fehlen).
async function renderTrackRecord() {
  const el = document.getElementById("track-record");
  if (!el) return;
  let tr;
  try {
    const res = await fetch("signals/track_record.json");
    if (!res.ok) throw new Error("HTTP " + res.status);
    tr = await res.json();
  } catch (err) {
    el.textContent = "Forward-Test startet — noch keine Historie.";
    return;
  }
  const agg = (tr && tr.aggregates) || {};
  if (!agg.resolved) {
    el.textContent = "Forward-Test startet — noch keine Historie.";
    return;
  }
  const hit = agg.hit_rate == null ? "–" : Math.round(agg.hit_rate * 100) + " %";
  const avgR = agg.avg_R == null ? "–" : fmtNum(agg.avg_R, 2);
  el.textContent =
    `Forward-Test: ${agg.resolved} Signale · Trefferquote ${hit} · Ø R ${avgR}`;
}

async function init() {
  wireModal();
  const root = document.getElementById("grid");
  try {
    const res = await fetch("reports/index.json");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const rows = await res.json();

    if (!Array.isArray(rows) || rows.length === 0) {
      root.innerHTML = `<p class="error">Keine Reports gefunden. Bitte zuerst scripts/build_reports.py ausführen.</p>`;
      return;
    }

    // "Zuletzt aktualisiert" aus dem ersten Report holen (generated_at liegt nicht im Index;
    // wir laden den ersten Detail-Report, um den Zeitstempel anzuzeigen).
    const first = rows[0];
    fetch(`reports/${safeName(first.display)}/${first.date}.json`)
      .then((r) => (r.ok ? r.json() : null))
      .then((rep) => {
        if (rep && rep.generated_at) {
          const d = new Date(rep.generated_at);
          const stamp = Number.isNaN(d.getTime()) ? rep.generated_at : d.toLocaleString("de-DE");
          document.getElementById("updated").textContent = "Zuletzt aktualisiert: " + stamp;
        }
      })
      .catch(() => {});

    renderTrackRecord();
    renderGrid(rows);
  } catch (err) {
    root.innerHTML = `<p class="error">index.json konnte nicht geladen werden: ${escapeHtml(err.message)}.<br>
      Hinweis: fetch() lokaler Dateien braucht einen Webserver (nicht file://). Starte z. B. <code>python -m http.server</code> im <code>docs/</code>-Ordner.</p>`;
  }
}

document.addEventListener("DOMContentLoaded", init);
