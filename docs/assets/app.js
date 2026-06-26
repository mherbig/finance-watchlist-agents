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

      if (!r.available) {
        el.innerHTML = `
          <div class="col-label">${escapeHtml(r.display)}<span class="col-sub">${escapeHtml(r.symbol || "")}</span></div>
          <div class="col-price">–</div>
          <div class="col-change">–</div>
          <div class="chip chip-na">n/v</div>
          <div class="col-rsi">–</div>
          <div class="col-headline">Daten n/v</div>`;
      } else {
        el.innerHTML = `
          <div class="col-label">${escapeHtml(r.display)}<span class="col-sub">${escapeHtml(r.symbol || "")}</span></div>
          <div class="col-price">${fmtNum(r.price)}</div>
          <div class="col-change ${changeClass(r.change_pct)}">${fmtPct(r.change_pct)}</div>
          <div>${trendChip(r.trend)}</div>
          <div class="col-rsi">RSI ${r.rsi == null ? "–" : fmtNum(r.rsi, 1)}</div>
          <div class="col-headline">${escapeHtml(r.headline || "")}</div>`;
        el.addEventListener("click", () => openDetail(r));
      }
      rowsWrap.appendChild(el);
    }
    group.appendChild(rowsWrap);
    root.appendChild(group);
  }
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

  html += `
    <div class="headline-box">${escapeHtml(rep.headline || "")}</div>
    <div class="disclaimer-box">${escapeHtml(rep.disclaimer || "")}</div>`;

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

    renderGrid(rows);
  } catch (err) {
    root.innerHTML = `<p class="error">index.json konnte nicht geladen werden: ${escapeHtml(err.message)}.<br>
      Hinweis: fetch() lokaler Dateien braucht einen Webserver (nicht file://). Starte z. B. <code>python -m http.server</code> im <code>docs/</code>-Ordner.</p>`;
  }
}

document.addEventListener("DOMContentLoaded", init);
