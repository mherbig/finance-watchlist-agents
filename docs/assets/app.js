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

// Lookup display -> index-Zeile (track/agents_run fuer Badges in der Signal-Liste).
let INDEX_BY_DISPLAY = {};

// safe_name muss src/data/symbol_map.safe_name spiegeln: display.replace("/", "-")
function safeName(display) {
  return String(display).split("/").join("-");
}

// Cache-Busting fuer Daten-JSONs: erzwingt frische index/report/portfolio-Dateien,
// damit nach einem Push kein veralteter Index auf eine geprunte Report-Datei zeigt (404).
function noCache(url) {
  return url + (url.includes("?") ? "&" : "?") + "_=" + Date.now();
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
  // Immer den neuesten Report des Symbols laden. Aufrufer (z. B. die Depot-
  // Tabelle) uebergeben teils das Einstiegsdatum eines offenen Trades, fuer das
  // keine Report-Datei mehr existiert (nur der aktuelle Stand wird vorgehalten)
  // -> sonst HTTP 404. Datum daher aus dem Index aufloesen, Fallback row.date.
  const idxRow = INDEX_BY_DISPLAY[row.display];
  const date = (idxRow && idxRow.date) || row.date;
  const url = `reports/${safeName(row.display)}/${date}.json`;
  const body = document.getElementById("modal-body");
  body.innerHTML = `<p class="loading">Lade Detail …</p>`;
  showModal();

  let rep;
  try {
    const res = await fetch(noCache(url));
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
    const res = await fetch(noCache("signals/track_record.json"));
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

// ---------------------------------------------------------------------------
// Tab 2: "Signale & Depot" — Depot-Kopf, Equity-Kurve, Signal-Liste, Historie.
// Daten aus signals/portfolio.json (von scripts/build_portfolio.py erzeugt).
// ---------------------------------------------------------------------------

function fmtMoney(x) {
  if (x === null || x === undefined || Number.isNaN(Number(x))) return "–";
  return Number(x).toLocaleString("de-DE", {
    minimumFractionDigits: 0, maximumFractionDigits: 0,
  });
}

function dirChip(dir) {
  if (dir !== "LONG" && dir !== "SHORT") return '<span class="chip chip-na">–</span>';
  const cls = dir === "LONG" ? "sig-long" : "sig-short";
  const arrow = dir === "LONG" ? "▲" : "▼";
  return `<span class="signal-chip ${cls}">${dir} ${arrow}</span>`;
}

const ASSET_RANK = {
  index: 0, forex: 1, crypto: 2, energy: 3, metal: 4, stock: 5,
};

// Einfacher Inline-SVG-Linienchart der Equity-Kurve(n). Keine Libs.
// Bevorzugt die taegliche marked_curve (zwei Linien: realisiert + bewertet
// inkl. offener Positionen); Fallback: alte realisierte Event-Kurve.
function renderEquityChart(pf) {
  const p = pf || {};
  const mc = Array.isArray(p.marked_curve)
    ? p.marked_curve.filter((x) => x && typeof x.marked_equity === "number")
    : [];
  const ec = Array.isArray(p.equity_curve)
    ? p.equity_curve.filter((x) => x && typeof x.equity === "number")
    : [];

  const dates = (mc.length ? mc : ec).map((x) => x.date);
  let realized = (mc.length ? mc : ec).map((x) => x.equity);
  const marked = mc.map((x) => x.marked_equity);
  if (realized.length === 0) realized = [100000];

  // Benchmark (Equal-Weight Buy&Hold) auf die Kurven-Daten ausrichten;
  // fehlende Tage werden fortgeschrieben.
  const bmRaw = Array.isArray(p.benchmark_curve) ? p.benchmark_curve : [];
  const bmMap = {};
  for (const b of bmRaw) if (b && typeof b.equity === "number") bmMap[b.date] = b.equity;
  let bmLast = null;
  const bench = mc.length && bmRaw.length
    ? dates.map((d) => { if (bmMap[d] != null) bmLast = bmMap[d]; return bmLast; })
        .map((v) => (v == null ? 100000 : v))
    : [];

  const W = 720, H = 200, padL = 64, padR = 16, padT = 16, padB = 24;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const all = realized.concat(marked).concat(bench);
  let min = Math.min(...all);
  let max = Math.max(...all);
  if (min === max) { min -= min * 0.001 || 1; max += max * 0.001 || 1; }
  const span = max - min;
  min -= span * 0.1; max += span * 0.1;

  const n = Math.max(realized.length, marked.length, 2);
  const x = (i) => padL + (n === 1 ? innerW / 2 : (i * innerW) / (n - 1));
  const y = (v) => padT + innerH - ((v - min) / (max - min)) * innerH;

  const pathFor = (vals) => {
    if (vals.length === 0) return "";
    if (vals.length === 1) {
      const yv = y(vals[0]);
      return `M ${padL} ${yv} L ${W - padR} ${yv}`;
    }
    return vals
      .map((v, i) => `${i === 0 ? "M" : "L"} ${x(i).toFixed(1)} ${y(v).toFixed(1)}`)
      .join(" ");
  };

  const startVal = realized[0];
  const endReal = realized[realized.length - 1];
  const endMarked = marked.length ? marked[marked.length - 1] : null;
  const startLbl = dates.length ? (dates[0] || "Start") : "Start";
  const yTop = padT, yBot = padT + innerH;

  const markedPath = marked.length
    ? `<path d="${pathFor(marked)}" class="eq-line-marked" fill="none" />
       <circle cx="${x(marked.length - 1).toFixed(1)}" cy="${y(endMarked).toFixed(1)}" r="3" class="eq-dot-marked" />`
    : "";
  const benchPath = bench.length
    ? `<path d="${pathFor(bench)}" class="eq-line-bench" fill="none" />`
    : "";
  const endBench = bench.length ? bench[bench.length - 1] : null;
  const endLbl = endMarked != null
    ? `bewertet ${fmtMoney(endMarked)} $ · realisiert ${fmtMoney(endReal)} $`
      + (endBench != null ? ` · Benchmark ${fmtMoney(endBench)} $` : "")
    : `aktuell ${fmtMoney(endReal)} $`;
  const legend = marked.length
    ? `<div class="eq-legend">
         <span><span class="eq-key eq-key-marked"></span>Bewertet (inkl. offener Positionen)</span>
         <span><span class="eq-key eq-key-real"></span>Realisiert</span>
         ${bench.length ? '<span><span class="eq-key eq-key-bench"></span>Benchmark (Buy &amp; Hold, gleichgewichtet)</span>' : ""}
       </div>`
    : "";

  return `${legend}
    <svg class="equity-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="Equity-Kurve">
      <line x1="${padL}" y1="${yTop}" x2="${padL}" y2="${yBot}" class="eq-axis" />
      <line x1="${padL}" y1="${yBot}" x2="${W - padR}" y2="${yBot}" class="eq-axis" />
      <text x="${padL - 6}" y="${yTop + 4}" class="eq-axis-lbl" text-anchor="end">${escapeHtml(fmtMoney(max))}</text>
      <text x="${padL - 6}" y="${yBot}" class="eq-axis-lbl" text-anchor="end">${escapeHtml(fmtMoney(min))}</text>
      ${benchPath}
      <path d="${pathFor(realized)}" class="eq-line" fill="none" />
      <circle cx="${x(0).toFixed(1)}" cy="${y(startVal).toFixed(1)}" r="3" class="eq-dot" />
      <circle cx="${x(realized.length - 1).toFixed(1)}" cy="${y(endReal).toFixed(1)}" r="3" class="eq-dot" />
      ${markedPath}
      <text x="${padL}" y="${yBot + 16}" class="eq-axis-lbl" text-anchor="start">${escapeHtml(String(startLbl))} · ${escapeHtml(fmtMoney(startVal))} $</text>
      <text x="${W - padR}" y="${yBot + 16}" class="eq-axis-lbl" text-anchor="end">${escapeHtml(endLbl)}</text>
    </svg>`;
}

function renderOpenSignals(open) {
  const rows = Array.isArray(open) ? open.slice() : [];
  rows.sort((a, b) => {
    const c = (Number(b.conviction) || 0) - (Number(a.conviction) || 0);
    if (c !== 0) return c;
    return 0; // asset_class steht in open nicht zur Verfuegung -> stabil nach Konv.
  });

  if (rows.length === 0) {
    return `<p class="muted">Keine offenen Signale.</p>`;
  }

  const body = rows.map((o) => {
    const dots = convictionDots(o.conviction);
    const idxRow = INDEX_BY_DISPLAY[o.display];
    const badge = idxRow ? agentBadge(idxRow) : "";
    return `<tr class="sig-row" data-display="${escapeHtml(o.display)}" data-date="${escapeHtml(o.date || "")}">
      <td>${escapeHtml(o.display)}${badge}</td>
      <td>${dirChip(o.direction)}</td>
      <td><span class="sig-dots" title="Konviktion ${escapeHtml(String(o.conviction))}/5">${dots}</span></td>
      <td class="num">${fmtNum(o.entry)}</td>
      <td class="num">${o.date ? escapeHtml(fmtDate(o.date)) : "–"}</td>
      <td class="num">${o.current_price == null ? "–" : fmtNum(o.current_price)}</td>
      <td class="num ${o.pending ? "" : changeClass(o.unrealized_pct)}">${
        o.pending
          ? '<span class="muted" title="Pullback-Limit noch nicht erreicht – Position nicht im Markt">⏳ wartet</span>'
          : fmtPct(o.unrealized_pct)
      }</td>
      <td class="num">${fmtNum(o.stop_loss)}</td>
      <td class="num">${fmtNum(o.take_profit)}</td>
      <td class="num">${o.rr == null ? "–" : fmtNum(o.rr, 2)}</td>
      <td class="num">${o.risk_amount == null ? "–" : fmtMoney(o.risk_amount) + " $"}</td>
      <td class="num">${o.units == null ? "–" : fmtNum(o.units)}</td>
      <td class="num">${o.horizon_days == null ? "–" : escapeHtml(String(o.horizon_days)) + " T"}</td>
    </tr>`;
  }).join("");

  return `
    <table class="ptable">
      <thead><tr>
        <th>Symbol</th><th>Richtung</th><th>Konv</th><th>Entry</th>
        <th title="Datum der Eröffnung (Signal-Datum)">Eröffnet</th>
        <th title="Aktueller Kurs (letzter Tagesschluss)">Akt.</th>
        <th title="Unrealisierter Stand seit Entry">Status</th>
        <th>SL</th><th>TP</th><th>R:R</th><th>Risiko</th><th>Größe</th><th>Horizont</th>
      </tr></thead>
      <tbody>${body}</tbody>
    </table>`;
}

function renderClosedTrades(closed) {
  const rows = Array.isArray(closed) ? closed : [];
  if (rows.length === 0) {
    return `<p class="muted">Noch keine abgeschlossenen Trades.</p>`;
  }
  const body = rows.map((c) => {
    const pnlCls = c.pnl > 0 ? "up-text" : c.pnl < 0 ? "down-text" : "";
    const resCls = c.win ? "res-win" : "res-loss";
    const resLbl = c.win ? "Win" : "Loss";
    const sign = c.pnl > 0 ? "+" : "";
    return `<tr>
      <td>${escapeHtml(c.display || c.symbol || "")}</td>
      <td>${dirChip(c.direction)}</td>
      <td class="num">${fmtNum(c.entry)}</td>
      <td class="num">${c.date ? escapeHtml(fmtDate(c.date)) : "–"}</td>
      <td class="num">${fmtNum(c.exit_price)}</td>
      <td class="num">${c.exit_date ? escapeHtml(fmtDate(c.exit_date)) : "–"}</td>
      <td class="num">${c.realized_R == null ? "–" : fmtNum(c.realized_R, 2)}</td>
      <td class="num ${pnlCls}">${sign}${fmtMoney(c.pnl)} $</td>
      <td><span class="res-chip ${resCls}">${resLbl}</span></td>
    </tr>`;
  }).join("");

  return `
    <table class="ptable">
      <thead><tr>
        <th>Symbol</th><th>Richtung</th><th>Entry</th>
        <th title="Datum der Eröffnung (Signal-Datum)">Eröffnet</th>
        <th>Exit</th>
        <th title="Datum des Exits (SL/TP/Flip/Horizont)">Geschlossen</th>
        <th>R</th><th>P&amp;L</th><th>Ergebnis</th>
      </tr></thead>
      <tbody>${body}</tbody>
    </table>`;
}

function renderPortfolioHead(summary) {
  const s = summary || {};
  // Mark-to-Market: realisierte Equity + offene Positionen zum letzten
  // Tagesschluss bewertet. Fallback auf current_equity (alte portfolio.json).
  const marked = s.marked_equity != null ? s.marked_equity : s.current_equity;
  const equity = marked == null ? "–" : fmtMoney(marked);
  const mret = s.marked_return_pct != null ? s.marked_return_pct : s.return_pct;
  const retHtml = mret == null ? "" :
    ` <span class="${changeClass(mret)}">${fmtPct(mret)}</span>`;
  const unrl = s.unrealized_pnl;
  const unrlStr = unrl == null ? "–"
    : (unrl > 0 ? "+" : "") + fmtMoney(unrl) + " $";
  const valuation = `Realisiert: ${s.current_equity == null ? "–" : fmtMoney(s.current_equity)} $ `
    + `· Offene Positionen: ${unrlStr} unrealisiert (zum letzten Tagesschluss bewertet)`;
  const wr = s.win_rate == null ? 0 : Math.round(Number(s.win_rate) * 100);
  const meta = `Start 100.000 $ · ${s.closed_count || 0} Trades `
    + `(${s.wins || 0}W/${s.losses || 0}L, Trefferquote ${wr} %) · ${s.open_count || 0} offen`
    + (s.skipped_count ? ` · ${s.skipped_count} Signale durch Risiko-Limits übersprungen` : "")
    + (s.total_costs ? ` · Kosten ${fmtMoney(s.total_costs)} $` : "")
    + (s.ruleset_frozen_since ? ` · Regelstand eingefroren seit ${fmtDate(s.ruleset_frozen_since)}` : "");
  return `
    <div class="depot-head">
      <div class="depot-equity">Depot: ${escapeHtml(equity)} $${retHtml}</div>
      <div class="depot-meta">${escapeHtml(valuation)}</div>
      <div class="depot-meta">${escapeHtml(meta)}</div>
    </div>`;
}

async function renderPortfolio() {
  const root = document.getElementById("portfolio-view");
  if (!root) return;
  if (root.dataset.loaded === "1") return; // nur einmal laden
  root.dataset.loaded = "1";

  let pf = null;
  try {
    const res = await fetch(noCache("signals/portfolio.json"));
    if (!res.ok) throw new Error("HTTP " + res.status);
    pf = await res.json();
  } catch (err) {
    pf = null;
  }

  const summary = pf && pf.summary ? pf.summary : null;
  const closed = pf && Array.isArray(pf.closed) ? pf.closed : [];
  const open = pf && Array.isArray(pf.open) ? pf.open : [];

  if (!summary || (summary.closed_count || 0) === 0) {
    // Tag 1 / kein Depot: Hinweis statt Kennzahlen, aber Liste trotzdem zeigen.
    const head = summary
      ? renderPortfolioHead(summary)
      : `<div class="depot-head"><div class="depot-equity">Depot: 100.000 $</div></div>`;
    root.innerHTML = `
      ${head}
      <p class="depot-note">Forward-Test läuft seit heute — Trades schließen, sobald neue Kurse vorliegen.</p>
      <div class="pcard">
        <h3>Equity-Kurve</h3>
        ${renderEquityChart(pf)}
      </div>
      <div class="pcard">
        <h3>Aktive Signale</h3>
        ${renderOpenSignals(open)}
      </div>
      <div class="pcard">
        <h3>Trade-Historie</h3>
        ${renderClosedTrades(closed)}
      </div>`;
  } else {
    root.innerHTML = `
      ${renderPortfolioHead(summary)}
      <div class="pcard">
        <h3>Equity-Kurve</h3>
        ${renderEquityChart(pf)}
      </div>
      <div class="pcard">
        <h3>Aktive Signale</h3>
        ${renderOpenSignals(open)}
      </div>
      <div class="pcard">
        <h3>Trade-Historie</h3>
        ${renderClosedTrades(closed)}
      </div>`;
  }

  // Zeilen-Klick -> bestehendes Detail-Modal (per display + date).
  root.querySelectorAll(".sig-row").forEach((tr) => {
    tr.addEventListener("click", () => {
      openDetail({ display: tr.dataset.display, date: tr.dataset.date });
    });
  });
}

function wireTabs() {
  const tabOverview = document.getElementById("tab-overview");
  const tabPortfolio = document.getElementById("tab-portfolio");
  const gridView = document.getElementById("grid");
  const pfView = document.getElementById("portfolio-view");
  if (!tabOverview || !tabPortfolio) return;

  function activate(which) {
    const isOverview = which === "overview";
    gridView.hidden = !isOverview;
    pfView.hidden = isOverview;
    tabOverview.classList.toggle("is-active", isOverview);
    tabPortfolio.classList.toggle("is-active", !isOverview);
    tabOverview.setAttribute("aria-selected", String(isOverview));
    tabPortfolio.setAttribute("aria-selected", String(!isOverview));
    if (!isOverview) renderPortfolio();
  }

  tabOverview.addEventListener("click", () => activate("overview"));
  tabPortfolio.addEventListener("click", () => activate("portfolio"));
}

async function init() {
  wireModal();
  wireTabs();
  const root = document.getElementById("grid");
  try {
    const res = await fetch(noCache("reports/index.json"));
    if (!res.ok) throw new Error("HTTP " + res.status);
    const rows = await res.json();

    if (!Array.isArray(rows) || rows.length === 0) {
      root.innerHTML = `<p class="error">Keine Reports gefunden. Bitte zuerst scripts/build_reports.py ausführen.</p>`;
      return;
    }

    INDEX_BY_DISPLAY = {};
    for (const r of rows) INDEX_BY_DISPLAY[r.display] = r;

    // "Zuletzt aktualisiert" aus dem ersten Report holen (generated_at liegt nicht im Index;
    // wir laden den ersten Detail-Report, um den Zeitstempel anzuzeigen).
    const first = rows[0];
    fetch(noCache(`reports/${safeName(first.display)}/${first.date}.json`))
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
