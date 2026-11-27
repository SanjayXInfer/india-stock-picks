"use strict";
// Dashboard logic. Reads data.json (served live by the local FastAPI app, or as a static file on
// GitHub Pages) and does all grouping/ranking client-side so the lookback selector works offline.
// All scraped text is inserted with textContent / el() — never innerHTML — to prevent injection.

const GROUP = { Buy: "bull", Accumulate: "bull", Sell: "bear", Reduce: "bear", Hold: "neutral" };
const GROUP_LABEL = { bull: "Buy", bear: "Sell", neutral: "Hold" };
const ist = new Intl.DateTimeFormat("en-IN", {
  timeZone: "Asia/Kolkata", day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit", hour12: false,
});
const inr = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 2 });

let DATA = null;
let sortKey = "published", sortDir = -1;

// ---------- helpers ----------
function el(tag, attrs = {}, ...children) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") n.className = v;
    else if (k === "text") n.textContent = v;
    else n.setAttribute(k, v);
  }
  for (const c of children.flat(Infinity)) if (c != null && c !== false) n.append(c instanceof Node ? c : String(c));
  return n;
}
const safeUrl = (u) => (typeof u === "string" && /^https:\/\//.test(u) ? u : null);
const fmtPrice = (v) => (v == null ? "—" : "₹" + inr.format(v));
const fmtTime = (iso) => (iso ? ist.format(new Date(iso)) : "—");
const pct = (v) => (v == null || !isFinite(v) ? "—" : (v > 0 ? "+" : "") + v.toFixed(1) + "%");
const mean = (a) => (a.length ? a.reduce((x, y) => x + y, 0) / a.length : null);
const median = (a) => { if (!a.length) return null; const s = [...a].sort((x, y) => x - y); const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; };
const actClass = (a) => "act act-" + (GROUP[a] || "neutral");
const who = (r) => [r.analyst, r.brokerage].filter(Boolean).join(", ") || "—";

// "Today" = since the previous weekday's 15:30 IST close, so evening/weekend "stocks to buy tomorrow"
// pieces count towards the next session (Monday includes Friday evening + weekend). Holidays are ignored.
function cutoff(mode) {
  const now = Date.now();
  if (mode === "24h") return now - 24 * 3600e3;
  if (mode === "72h") return now - 72 * 3600e3;
  const istNow = new Date(now + 5.5 * 3600e3); // shift so UTC getters read IST wall-clock
  const prev = new Date(Date.UTC(istNow.getUTCFullYear(), istNow.getUTCMonth(), istNow.getUTCDate() - 1, 15, 30));
  while (prev.getUTCDay() === 0 || prev.getUTCDay() === 6) prev.setUTCDate(prev.getUTCDate() - 1);
  return prev.getTime() - 5.5 * 3600e3;
}

function refPrice(symbol, recs) {
  const s = DATA.stocks[symbol];
  if (s && s.cmp) return { price: s.cmp, live: true };
  const m = median(recs.map((r) => r.cmp_at_reco).filter((v) => v));
  return m ? { price: m, live: false } : null;
}

// ---------- aggregation ----------
// opinion = one analyst/brokerage's call (action) on one stock, possibly syndicated to several sites.
function groupStocks(recs) {
  const bySym = new Map();
  for (const r of recs) {
    if (!bySym.has(r.symbol)) bySym.set(r.symbol, []);
    bySym.get(r.symbol).push(r);
  }
  const out = [];
  for (const [symbol, rs] of bySym) {
    const groups = { bull: new Map(), bear: new Map(), neutral: new Map() };
    for (const r of rs) {
      const g = groups[GROUP[r.action] || "neutral"];
      if (!g.has(r.opinion)) g.set(r.opinion, []);
      g.get(r.opinion).push(r);
    }
    const counts = Object.fromEntries(Object.entries(groups).map(([k, m]) => [k, {
      analysts: m.size,
      sites: new Set([...m.values()].flat().map((r) => r.source)).size,
    }]));
    const primary = ["bull", "bear", "neutral"].sort((a, b) =>
      counts[b].analysts - counts[a].analysts || counts[b].sites - counts[a].sites)[0];
    const prim = [...groups[primary].values()];
    const primRecs = prim.flat();
    const targets = primRecs.flatMap((r) => [r.target, r.target_high]).filter((v) => v);
    const ref = refPrice(symbol, rs);
    // average upside per opinion (each analyst's mean target), not per syndicated copy
    const opTargets = prim.map((ops) => mean(ops.flatMap((r) => [r.target, r.target_high]).filter((v) => v))).filter((v) => v);
    out.push({
      symbol,
      company: rs[0].company,
      primary,
      counts,
      opinions: prim,
      allRecs: rs,
      sites: [...new Set(primRecs.map((r) => r.source_label))],
      tmin: targets.length ? Math.min(...targets) : null,
      tmax: targets.length ? Math.max(...targets) : null,
      upside: ref && opTargets.length ? (mean(opTargets) / ref.price - 1) * 100 : null,
      ref,
      latest: Math.max(...rs.map((r) => Date.parse(r.published) || 0)),
    });
  }
  return out;
}

// ---------- rendering ----------
function renderHeader() {
  const u = document.getElementById("updated");
  u.textContent = DATA.last_run ? `Updated ${fmtTime(DATA.last_run)} IST` : "No scrape yet";
  document.getElementById("disclaimer").textContent = DATA.disclaimer;
  document.getElementById("refresh").hidden = DATA.mode !== "local";
  document.getElementById("extractor-note").textContent = DATA.extractor === "heuristic"
    ? "Extraction ran in regex mode (no LLM): reasons are short excerpts and some fields may be missing."
    : "";
}

function renderConsensus(stocks) {
  const box = document.getElementById("consensus");
  box.replaceChildren();
  const picks = stocks.filter((s) => s.counts[s.primary].analysts >= 2)
    .sort((a, b) => b.counts[b.primary].analysts - a.counts[a.primary].analysts
      || b.counts[b.primary].sites - a.counts[a.primary].sites || b.latest - a.latest);
  if (!picks.length) {
    box.append(el("div", { class: "empty", text:
      "No stock has 2 or more independent analysts in this window yet. Try a longer lookback, or see all recommendations below." }));
    return;
  }
  for (const s of picks) box.append(card(s));
}

function card(s) {
  const c = s.counts[s.primary];
  const others = ["bull", "bear", "neutral"].filter((g) => g !== s.primary && s.counts[g].analysts);
  const actions = [...new Set(s.opinions.flat().map((r) => r.action))];
  const horizons = [...new Set(s.opinions.flat().map((r) => r.horizon).filter(Boolean))];

  const ops = el("ul", { class: "opinions" });
  for (const group of ["bull", "bear", "neutral"]) {
    const m = new Map();
    for (const r of s.allRecs.filter((r) => (GROUP[r.action] || "neutral") === group)) {
      if (!m.has(r.opinion)) m.set(r.opinion, []);
      m.get(r.opinion).push(r);
    }
    for (const rs of m.values()) {
      const r = rs.find((x) => x.reason) || rs[0];
      const parts = [
        r.target ? "Target " + fmtPrice(r.target) + (r.target_high ? "–" + inr.format(r.target_high) : "") : null,
        r.stop_loss ? "SL " + fmtPrice(r.stop_loss) : null,
        r.cmp_at_reco ? "at " + fmtPrice(r.cmp_at_reco) : null,
        r.horizon,
        fmtTime(r.published),
      ].filter(Boolean);
      ops.append(el("li", {},
        el("div", { class: "op-head" }, el("span", { class: actClass(r.action), text: r.action }), " ", who(r)),
        el("div", { class: "op-meta", text: parts.join(" · ") }),
        r.reason ? el("p", { class: "op-reason", text: r.reason }) : null,
        el("div", { class: "op-links" }, rs.map((x) => safeUrl(x.url)
          ? el("a", { href: x.url, target: "_blank", rel: "noopener noreferrer nofollow", title: x.title, text: x.source_label + " ↗" })
          : el("span", { text: x.source_label }))),
      ));
    }
  }

  return el("article", { class: "card" },
    el("div", { class: "card-top" },
      el("div", {}, el("div", { class: "sym", text: s.symbol }), el("div", { class: "company", text: s.company || "" })),
      el("div", { class: "badges" },
        el("span", { class: "badge", title: "Distinct analysts/brokerages" }, el("b", { text: c.analysts }), " analysts"),
        el("span", { class: "badge", title: "Websites carrying these calls" }, el("b", { text: c.sites }), " sites"))),
    el("div", {},
      actions.map((a) => [el("span", { class: actClass(a), text: a }), " "]),
      others.map((g) => el("span", { class: "conflict", text: ` ⚠ ${s.counts[g].analysts} ${GROUP_LABEL[g]}` })),
      horizons.length ? el("span", { class: "company", text: "  " + horizons.join(", ") }) : null),
    el("div", { class: "stats" },
      el("div", { class: "stat" }, el("div", { class: "l", text: "Target range" }),
        el("div", { class: "v", text: s.tmin == null ? "—" : s.tmin === s.tmax ? fmtPrice(s.tmin) : `${fmtPrice(s.tmin)}–${inr.format(s.tmax)}` })),
      el("div", { class: "stat" }, el("div", { class: "l", text: "Avg upside" }),
        el("div", { class: "v " + (s.upside > 0 ? "up" : s.upside < 0 ? "down" : ""), text: pct(s.upside) })),
      el("div", { class: "stat", title: s.ref && s.ref.live ? "Delayed price" : "Median price at recommendation" },
        el("div", { class: "l", text: s.ref && s.ref.live ? "CMP (delayed)" : "Price at reco" }),
        el("div", { class: "v", text: s.ref ? fmtPrice(s.ref.price) : "—" }))),
    el("div", { class: "chips" }, s.sites.map((x) => el("span", { class: "chip", text: x }))),
    el("details", {}, el("summary", { text: "Reasons & sources" }), ops),
  );
}

function renderTable(recs, stocks) {
  const info = new Map(stocks.map((s) => [s.symbol, s]));
  const q = document.getElementById("f-search").value.trim().toLowerCase();
  const fa = document.getElementById("f-action").value;
  const fh = document.getElementById("f-horizon").value;
  const fs = document.getElementById("f-source").value;
  const fmin = +document.getElementById("f-min").value;

  let rows = recs.map((r) => {
    const s = info.get(r.symbol);
    const g = GROUP[r.action] || "neutral";
    const ref = s && s.ref;
    return { ...r, n: s ? s.counts[g].analysts : 1, who: who(r),
      upside: ref && r.target ? (r.target / ref.price - 1) * 100 : null };
  }).filter((r) =>
    (!q || r.symbol.toLowerCase().includes(q) || (r.company || "").toLowerCase().includes(q))
    && (!fa || r.action === fa) && (!fh || r.horizon === fh) && (!fs || r.source === fs) && r.n >= fmin);

  rows.sort((a, b) => {
    const x = a[sortKey], y = b[sortKey];
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    return (typeof x === "number" ? x - y : String(x).localeCompare(String(y))) * sortDir;
  });
  document.getElementById("all-count").textContent = `(${rows.length})`;
  document.querySelectorAll("#all-table th[data-k]").forEach((th) => {
    th.classList.toggle("asc", th.dataset.k === sortKey && sortDir === 1);
    th.classList.toggle("desc", th.dataset.k === sortKey && sortDir === -1);
  });

  const tb = document.querySelector("#all-table tbody");
  tb.replaceChildren(...rows.map((r) => el("tr", {},
    el("td", { class: "small", text: fmtTime(r.published) }),
    el("td", {}, el("b", { text: r.symbol }), el("div", { class: "small", text: r.company || "" })),
    el("td", {}, el("span", { class: actClass(r.action), text: r.action })),
    el("td", { class: "num", text: r.target ? fmtPrice(r.target) + (r.target_high ? "–" + inr.format(r.target_high) : "") : "—" }),
    el("td", { class: "num", text: fmtPrice(r.stop_loss) }),
    el("td", { class: "num " + (r.upside > 0 ? "up" : r.upside < 0 ? "down" : ""), text: pct(r.upside) }),
    el("td", { text: r.horizon || "—" }),
    el("td", { text: r.who }),
    el("td", {}, safeUrl(r.url)
      ? el("a", { href: r.url, target: "_blank", rel: "noopener noreferrer nofollow", title: r.title, text: r.source_label + " ↗" })
      : r.source_label),
    el("td", { class: "num", text: r.n }),
    el("td", { class: "reason", text: r.reason || "" }),
  )));
  if (!rows.length) tb.append(el("tr", {}, el("td", { colspan: 11, class: "small", text: "No recommendations match." })));
}

function renderHealth() {
  const tb = document.querySelector("#health tbody");
  tb.replaceChildren(...DATA.sources.map((s) => {
    const status = !s.enabled ? ["Disabled", "status-off"] : s.error && !s.last_success ? ["Failing", "status-err"]
      : s.error ? ["Partial", "status-err"] : s.last_success ? ["OK", "status-ok"] : ["Never run", "status-off"];
    return el("tr", {},
      el("td", { text: s.label }),
      el("td", { class: status[1], text: status[0] }),
      el("td", { text: fmtTime(s.last_success) }),
      el("td", { class: "num", text: s.new_articles ?? 0 }),
      el("td", { class: "num", text: s.picks ?? 0 }),
      el("td", { class: "small", text: s.error || "" }));
  }));
}

function fillSelect(id, values, labels = {}) {
  const sel = document.getElementById(id);
  const cur = sel.value;
  sel.replaceChildren(sel.options[0]);
  for (const v of values) sel.append(el("option", { value: v, text: labels[v] || v }));
  sel.value = values.includes(cur) ? cur : "";
}

function render() {
  if (!DATA) return;
  renderHeader();
  const since = cutoff(document.getElementById("lookback").value);
  const recs = DATA.recommendations.filter((r) => (Date.parse(r.published) || 0) >= since);
  const stocks = groupStocks(recs);
  renderConsensus(stocks);
  const uniq = (k) => [...new Set(DATA.recommendations.map((r) => r[k]).filter(Boolean))].sort();
  fillSelect("f-action", uniq("action"));
  fillSelect("f-horizon", uniq("horizon"));
  fillSelect("f-source", uniq("source"), Object.fromEntries(DATA.sources.map((s) => [s.name, s.label])));
  renderTable(recs, stocks);
  renderHealth();
}

async function load() {
  try {
    const res = await fetch("data.json", { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    DATA = await res.json();
    render();
  } catch (e) {
    document.getElementById("updated").textContent = "Could not load data (" + e.message + ")";
  }
}

async function refresh() {
  const btn = document.getElementById("refresh");
  btn.disabled = true;
  btn.textContent = "Refreshing…";
  try {
    await fetch("api/refresh", { method: "POST" });
    for (;;) {
      await new Promise((r) => setTimeout(r, 3000));
      const st = await (await fetch("api/status", { cache: "no-store" })).json();
      if (!st.running) break;
    }
    await load();
  } finally {
    btn.disabled = false;
    btn.textContent = "Refresh now";
  }
}

// ---------- wiring ----------
{
  // ?lookback=today|24h|72h in the URL wins (shareable), else the viewer's last choice.
  let v = new URLSearchParams(location.search).get("lookback");
  try { v = v || localStorage.getItem("lookback"); } catch (_) {}
  if (["today", "24h", "72h"].includes(v)) document.getElementById("lookback").value = v;
}
document.getElementById("lookback").addEventListener("change", (e) => {
  try { localStorage.setItem("lookback", e.target.value); } catch (_) {}
  render();
});
for (const id of ["f-search", "f-action", "f-horizon", "f-source", "f-min"]) {
  document.getElementById(id).addEventListener("input", render);
}
document.querySelectorAll("#all-table th[data-k]").forEach((th) => th.addEventListener("click", () => {
  if (sortKey === th.dataset.k) sortDir = -sortDir; else { sortKey = th.dataset.k; sortDir = th.dataset.k === "published" || th.dataset.k === "n" ? -1 : 1; }
  render();
}));
document.getElementById("refresh").addEventListener("click", refresh);
load();
setInterval(load, 5 * 60 * 1000); // pick up scheduled scrapes without a manual reload
