/* betterHACs front end.
 * No framework and no table library on purpose: 4,200 rows need a scroll window, and
 * that is less code than wiring up a dependency would be. The page therefore has no
 * external requirement beyond the webfont. */
(function () {
"use strict";

/* ---------------------------------------------------------------- i18n ----
 * English is always loaded and is the fallback for every individual key, so a
 * half-finished translation is useful from the first pull request instead of
 * producing a half-empty interface. */
var EN = {}, L = {}, LOCALE = "en";
var AVAILABLE = [["en", "English"], ["de", "Deutsch"]];

function t(key, params) {
  var s = (L[key] !== undefined ? L[key] : EN[key]);
  if (s === undefined) return key;
  if (params) s = s.replace(/\{(\w+)\}/g, function (m, k) {
    return params[k] !== undefined ? params[k] : m;
  });
  return s;
}
function pickLocale() {
  var q = new URLSearchParams(location.search).get("lang");
  var codes = AVAILABLE.map(function (a) { return a[0]; });
  if (q && codes.indexOf(q) >= 0) return q;
  try { var st = localStorage.getItem("lang"); if (st && codes.indexOf(st) >= 0) return st; } catch (e) {}
  var nav = (navigator.language || "en").slice(0, 2);
  return codes.indexOf(nav) >= 0 ? nav : "en";
}

var NF, DF;
function setupFormats() {
  NF = new Intl.NumberFormat(LOCALE);
  DF = new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "short", year: "numeric" });
}
function n(v) { return v === undefined || v === null ? null : NF.format(v); }
function d(iso) { return iso ? DF.format(new Date(iso + (iso.length === 10 ? "T00:00:00" : ""))) : ""; }
function addDays(iso, days) {
  var x = new Date(iso + "T00:00:00Z"); x.setUTCDate(x.getUTCDate() + days);
  return x.toISOString().slice(0, 10);
}
var ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return ESC[c]; }); }

/* --------------------------------------------------------------- views ----
 * Each view is a question somebody actually arrives with, not a data dimension.
 * `windowed` marks the ones whose ranking depends on the selected period. */
var VIEWS = {
  trending:   { key: "trending",   windowed: true,  sort: function (w) { return "d" + w; },
                cols: ["repo", "cat", "stars", "gained", "growth", "installs", "health"] },
  installed:  { key: "installed",  windowed: false, sort: function () { return "inst"; },
                filter: function (r) { return r.inst !== undefined; },
                cols: ["repo", "cat", "installs", "instGained", "stars", "health"] },
  breakout:   { key: "breakout",   windowed: true,  sort: function (w) { return "p" + w; },
                filter: function (r, w) { return r["p" + w] !== undefined; },
                cols: ["repo", "cat", "growth", "gained", "stars", "installs", "health"] },
  momentum:   { key: "momentum",   windowed: true,  sort: function () { return "_mom"; },
                filter: function (r, w) { return r._mom !== undefined && r["d" + w] !== undefined; },
                cols: ["repo", "cat", "starRank", "instRank", "gained", "installs", "health"] },
  maintenance:{ key: "maintenance",windowed: false, sort: function () { return "age"; },
                cols: ["repo", "cat", "health", "version", "stars", "installs"] },
  "new":      { key: "new",        windowed: false, sort: function () { return "fs"; },
                cols: ["repo", "cat", "stars", "installs", "health"] }
};
var VIEW_ORDER = ["trending", "installed", "breakout", "momentum", "maintenance", "new"];

/* Column definitions. `head` may depend on the active period. */
var COLS = {
  repo:      { w: "minmax(250px,3fr)", i18n: "col.repository", sort: "n", str: true },
  cat:       { w: "132px", i18n: "col.category", sort: "c", str: true, cls: "hide-sm" },
  stars:     { w: "94px", i18n: "col.stars", sort: "s", right: true },
  gained:    { w: "112px", i18n: "col.starsGained", sort: function (w) { return "d" + w; }, right: true, win: true },
  growth:    { w: "108px", i18n: "col.growth", sort: function (w) { return "p" + w; }, right: true, win: true },
  installs:  { w: "138px", i18n: "col.installs", sort: "inst", right: true, cls: "hide-sm" },
  instGained:{ w: "116px", i18n: "col.installsGained", sort: function (w) { return "i" + w; }, right: true, win: true, install: true },
  version:   { w: "112px", i18n: "col.version", sort: "v", str: true, cls: "hide-md" },
  starRank:  { w: "100px", i18n: "col.starRank", sort: "_srank", right: true },
  instRank:  { w: "104px", i18n: "col.installRank", sort: "_irank", right: true },
  health:    { w: "184px", i18n: "col.lastCommit", sort: "age" }
};

var WINDOWS = [7, 30, 90, 365];

/* --------------------------------------------------------------- state ----- */
var DATA = null, ROWS = [], VIEW = [], view = "trending", win = 30;
var sortKey = null, sortDir = -1, query = "", cat = null;
var $ = function (id) { return document.getElementById(id); };
var viewport, spacer, pool = [], maxInstall = 1;

/* --------------------------------------------------- availability ---------
 * Stars are exact for every period because the full history was fetched once.
 * Installations and downloads have to accumulate, so a period is only honest
 * once we have been collecting for that long. */
function starWindowOk() { return true; }
function installWindowOk(w) {
  var m = DATA.meta;
  if (!m.first_snapshot) return false;
  return (m.history_days || 1) - 1 >= w;
}
function installAvailableFrom(w) { return addDays(DATA.meta.first_snapshot, w); }

/* ------------------------------------------------------------ momentum ----
 * Percentile of star rate and of installation rate, ranked on the lower of the
 * two so a repository has to be strong in both. Component ranks are kept on the
 * row and shown in their own columns - the placement is never a black box. */
function computeMomentum(w) {
  ROWS.forEach(function (r) { delete r._mom; delete r._srank; delete r._irank; });
  var elig = ROWS.filter(function (r) {
    return r.inst !== undefined && !r.amb && r["d" + w] !== undefined && r["i" + w] !== undefined;
  });
  if (elig.length < 5) return;
  function rankBy(list, fn) {
    var sorted = list.slice().sort(function (a, b) { return fn(b) - fn(a); });
    var map = new Map();
    sorted.forEach(function (r, i) { map.set(r, Math.round((1 - i / (sorted.length - 1)) * 100)); });
    return map;
  }
  var sr = rankBy(elig, function (r) { return r["d" + w] / Math.max(1, (r.s || 1) - r["d" + w]); });
  var ir = rankBy(elig, function (r) { return r["i" + w] / Math.max(1, r.inst - r["i" + w]); });
  elig.forEach(function (r) {
    r._srank = sr.get(r); r._irank = ir.get(r);
    r._mom = Math.min(r._srank, r._irank);
  });
}

/* ------------------------------------------------------------ filtering ---- */
function apply() {
  var v = VIEWS[view];
  if (view === "momentum") computeMomentum(win);
  var q = query.trim().toLowerCase();
  VIEW = ROWS.filter(function (r) {
    if (v.filter && !v.filter(r, win)) return false;
    if (cat && r.c !== cat) return false;
    if (q) {
      if (!((r.n && r.n.toLowerCase().indexOf(q) >= 0) ||
            (r.t && r.t.toLowerCase().indexOf(q) >= 0) ||
            (r.d && r.d.toLowerCase().indexOf(q) >= 0) ||
            (r.dom && r.dom.toLowerCase().indexOf(q) >= 0))) return false;
    }
    return true;
  });
  var key = sortKey || v.sort(win);
  var isStr = key === "n" || key === "c" || key === "v";
  var dir = sortDir;
  VIEW.sort(function (a, b) {
    var x = a[key], y = b[key];
    var ax = x === undefined || x === null, ay = y === undefined || y === null;
    /* Rows without a value always sink, whichever way the column is sorted -
       otherwise an ascending sort fills the top of the table with gaps. */
    if (ax && ay) return (b.s || 0) - (a.s || 0);
    if (ax) return 1;
    if (ay) return -1;
    if (isStr) return dir * String(x).localeCompare(String(y), LOCALE);
    return dir > 0 ? x - y : y - x;
  });
  maxInstall = VIEW.reduce(function (m, r) { return Math.max(m, r.inst || 0); }, 1);
  render(); renderFoot();
}

/* ------------------------------------------------------------- cells ------ */
function naCell(hint) {
  return '<span class="na" title="' + esc(hint || t("hint.noValue")) + '">&ndash;</span>';
}
function deltaCell(v, hint) {
  if (v === undefined || v === null) return naCell(hint);
  var cls = v > 0 ? "p" : (v < 0 ? "n" : "");
  return '<span class="delta ' + cls + '" title="' + esc(t("hint.starsAdded")) + '">' +
         (v > 0 ? "+" : "") + n(v) + "</span>";
}
function cellHTML(c, r) {
  switch (c) {
    case "repo":
      return '<div class="repo"><div class="top">' +
        '<a href="https://github.com/' + esc(r.n) + '" target="_blank" rel="noopener">' +
        esc(r.t || r.n.split("/")[1]) + "</a>" +
        '<span class="slug">' + esc(r.n) + "</span></div>" +
        '<div class="desc">' + esc(r.d || "") + "</div></div>";
    case "cat":
      return '<span class="cat">' + esc(t("cat." + r.c)) + "</span>";
    case "stars":
      return r.s === undefined ? naCell() : '<span class="num">' + n(r.s) + "</span>";
    case "gained":
      return deltaCell(r["d" + win]);
    case "growth": {
      var p = r["p" + win];
      if (p === undefined) return naCell();
      return '<span class="delta ' + (p > 0 ? "p" : p < 0 ? "n" : "") + '">' +
             (p > 0 ? "+" : "") + n(Math.round(p * 10) / 10) + "%</span>";
    }
    case "installs": {
      if (r.inst === undefined) return naCell();
      var pct = Math.max(2, Math.round(r.inst / maxInstall * 46));
      var warn = r.amb ? '<span class="amb" title="' + esc(t("hint.ambiguousDomain")) + '">&#9888;</span>' : "";
      return '<span class="bar num">' + n(r.inst) + '<i style="width:' + pct + 'px"></i></span>' + warn;
    }
    case "instGained":
      return installWindowOk(win)
        ? deltaCell(r["i" + win])
        : naCell(t("window.unavailableFrom", { date: d(installAvailableFrom(win)) }));
    case "version":
      return '<span class="v">' + esc(r.v || "–") + "</span>";
    case "starRank":
      return r._srank === undefined ? naCell() : '<span class="rank">' + r._srank + "</span>";
    case "instRank":
      return r._irank === undefined ? naCell() : '<span class="rank">' + r._irank + "</span>";
    case "health": {
      var age = r.age !== undefined ? '<span class="age num">' + t("health.days", { n: n(r.age) }) + "</span>" : "";
      return '<span class="health h-' + r.h + '" title="' + (r.lu ? esc(d(r.lu)) : "") + '">' +
             '<span class="dot"></span>' + esc(t("health." + r.h)) + "</span> " + age;
    }
  }
  return "";
}

/* ------------------------------------------------------------ rendering --- */
function visibleCols() {
  return VIEWS[view].cols.filter(function (c) {
    var def = COLS[c];
    if (def.cls === "hide-sm" && innerWidth <= 780) return false;
    if (def.cls === "hide-md" && innerWidth <= 1180) return false;
    return true;
  });
}
function template() {
  return visibleCols().map(function (c) { return COLS[c].w; }).join(" ");
}
function rowH() { return innerWidth <= 780 ? 52 : 58; }

function render() {
  var cols = visibleCols(), tpl = template(), h = rowH();
  spacer.style.height = (VIEW.length * h) + "px";
  if (!VIEW.length) {
    spacer.innerHTML = '<div class="empty">' + esc(t("foot.empty")) + "</div>";
    pool = []; return;
  }
  if (pool.length === 0) spacer.innerHTML = "";
  var top = viewport.scrollTop;
  var first = Math.max(0, Math.floor(top / h) - 4);
  var last = Math.min(VIEW.length, Math.ceil((top + viewport.clientHeight) / h) + 4);
  var need = last - first;
  while (pool.length < need) {
    var el = document.createElement("div"); el.className = "row";
    spacer.appendChild(el); pool.push(el);
  }
  for (var i = 0; i < pool.length; i++) {
    var node = pool[i];
    if (i >= need) { node.hidden = true; continue; }
    var r = VIEW[first + i];
    node.hidden = false;
    node.style.top = ((first + i) * h) + "px";
    node.style.gridTemplateColumns = tpl;
    node.innerHTML = cols.map(function (c) {
      return '<div class="cell' + (COLS[c].right ? " r" : "") + '">' + cellHTML(c, r) + "</div>";
    }).join("");
  }
}

function buildHead() {
  var cols = visibleCols(), th = $("thead");
  th.style.gridTemplateColumns = template();
  var active = sortKey || VIEWS[view].sort(win);
  th.innerHTML = cols.map(function (c) {
    var def = COLS[c];
    var key = typeof def.sort === "function" ? def.sort(win) : def.sort;
    var on = key === active;
    var sub = def.win ? '<span class="sub">' + esc(t("window." + win)) + "</span>" : "";
    return '<button data-k="' + key + '" data-str="' + (def.str ? 1 : 0) + '" data-active="' +
           (on ? 1 : 0) + '" class="' + (def.right ? "r" : "") + '">' +
           '<span class="lbl">' + esc(t(def.i18n)) +
           (on ? '<span class="arrow">' + (sortDir < 0 ? "▼" : "▲") + "</span>" : "") +
           "</span>" + sub + "</button>";
  }).join("");
  th.querySelectorAll("button").forEach(function (b) {
    b.onclick = function () {
      var k = b.dataset.k;
      if ((sortKey || VIEWS[view].sort(win)) === k) sortDir = -sortDir;
      else { sortKey = k; sortDir = b.dataset.str === "1" ? 1 : -1; }
      buildHead(); apply();
    };
  });
}

function buildCards() {
  $("cards").innerHTML = VIEW_ORDER.map(function (k) {
    return '<button class="card" data-v="' + k + '" aria-pressed="' + (k === view) + '">' +
      '<span class="t">' + esc(t("view." + k + ".title")) + "</span>" +
      '<span class="h">' + esc(t("view." + k + ".help")) + "</span></button>";
  }).join("");
  $("cards").querySelectorAll(".card").forEach(function (b) {
    b.onclick = function () {
      view = b.dataset.v; sortKey = null; sortDir = -1;
      buildCards(); buildWindows(); buildHead(); renderCaveat(); apply();
      viewport.scrollTop = 0;
    };
  });
}

function buildWindows() {
  var v = VIEWS[view];
  var box = $("windows");
  /* Hide the label with the control - a lone "Period" caption next to nothing
     reads like something failed to load. */
  box.hidden = !v.windowed;
  $("winlabel").hidden = !v.windowed;
  if (!v.windowed) return;
  box.innerHTML = WINDOWS.map(function (w) {
    return '<button data-w="' + w + '" aria-pressed="' + (w === win) + '"' +
           (starWindowOk(w) ? "" : " disabled") + ">" + esc(t("window." + w)) + "</button>";
  }).join("");
  box.querySelectorAll("button").forEach(function (b) {
    b.onclick = function () {
      win = parseInt(b.dataset.w, 10); sortKey = null;
      buildWindows(); buildHead(); renderCaveat(); apply();
    };
  });
}

function renderCaveat() {
  var m = DATA.meta, extra = "";
  var note = t("view." + view + ".note", {
    installed: t("view.installed.title"),
    matched: n(m.analytics.matched),
    withDomain: n(m.analytics.repos_with_domain),
    minBase: 25,
    median: view === "maintenance" ? m.activity_percentiles.p50 : 13,
    p90: m.activity_percentiles.p90,
    archived: t("health.archived")
  });
  if (VIEWS[view].windowed) extra = " <em>" + esc(t("window.starsExact")) + "</em>";
  if (view === "momentum" && !installWindowOk(win)) {
    extra = " <em>" + esc(t("window.installsGrowing", { date: d(installAvailableFrom(win)) })) + "</em>";
  }
  $("caveat").innerHTML = esc(note).replace(/&lt;/g, "<") + extra;
}

function buildCats() {
  var counts = {};
  ROWS.forEach(function (r) { counts[r.c] = (counts[r.c] || 0) + 1; });
  var order = ["integration", "plugin", "theme", "template", "python_script", "appdaemon", "netdaemon"];
  $("cats").innerHTML = '<button class="chip" data-c="" aria-pressed="' + (!cat) + '">' +
    esc(t("filter.allCategories")) + "</button>" +
    order.filter(function (c) { return counts[c]; }).map(function (c) {
      return '<button class="chip" data-c="' + c + '" aria-pressed="' + (cat === c) + '">' +
             esc(t("cat." + c)) + '<span class="c">' + counts[c] + "</span></button>";
    }).join("");
  $("cats").querySelectorAll(".chip").forEach(function (b) {
    b.onclick = function () { cat = b.dataset.c || null; buildCats(); apply(); };
  });
}

function renderFoot() {
  var c = DATA.meta.coverage;
  $("foot").innerHTML =
    '<span><span class="count">' + n(VIEW.length) + "</span> " +
      esc(t("foot.showing", { shown: "", total: n(ROWS.length) }).replace(/^\s*\{?shown\}?\s*/, "")) + "</span>" +
    "<span>" + esc(t("foot.starCoverage", { n: n(c.with_stars), pct: Math.round(c.with_stars / c.total * 100) })) + "</span>" +
    "<span>" + esc(t("foot.downloadCoverage", { n: n(c.with_downloads), pct: Math.round(c.with_downloads / c.total * 100) })) + "</span>" +
    "<span>" + esc(t("app.sources")) + "</span>" +
    "<span>" + esc(t("app.notOfficial")) + "</span>";
}

function applyStaticText() {
  document.documentElement.lang = LOCALE;
  document.querySelectorAll("[data-i18n]").forEach(function (el) {
    el.textContent = t(el.dataset.i18n);
  });
  $("q").placeholder = t("filter.searchPlaceholder");
  $("stamp").textContent = t("app.updated", { date: d(DATA.meta.day) });
}

/* --------------------------------------------------------------- boot ----- */
function paint() {
  setupFormats(); applyStaticText();
  buildCards(); buildWindows(); buildHead(); buildCats(); renderCaveat(); apply();
}

/* When the page is published as a single self-contained file, the language packs
   travel with it in an inline block; served normally they are fetched on demand so
   only the active language is downloaded. */
var BUNDLED = null;
(function () {
  var el = document.getElementById("inline-i18n");
  if (el && el.textContent.trim()) { try { BUNDLED = JSON.parse(el.textContent); } catch (e) {} }
})();

function loadLocale(code) {
  LOCALE = code;
  try { localStorage.setItem("lang", code); } catch (e) {}
  if (code === "en") { L = {}; paint(); return; }
  if (BUNDLED) { L = BUNDLED[code] || {}; paint(); return; }
  fetch("./i18n/" + code + ".json")
    .then(function (r) { return r.json(); })
    .then(function (j) { L = j; paint(); })
    .catch(function () { L = {}; paint(); });
}

function boot(data) {
  DATA = data; ROWS = data.repos;
  viewport = $("viewport"); spacer = $("spacer");
  viewport.addEventListener("scroll", render, { passive: true });
  addEventListener("resize", function () { pool = []; spacer.innerHTML = ""; buildHead(); render(); });
  $("q").addEventListener("input", function (e) {
    query = e.target.value; apply(); viewport.scrollTop = 0;
  });
  var sel = $("lang");
  sel.innerHTML = AVAILABLE.map(function (a) {
    return '<option value="' + a[0] + '">' + a[1] + "</option>";
  }).join("");
  var start = pickLocale();
  sel.value = start;
  sel.onchange = function () { loadLocale(sel.value); };

  if (BUNDLED) { EN = BUNDLED.en || {}; loadLocale(start); return; }
  fetch("./i18n/en.json").then(function (r) { return r.json(); })
    .then(function (j) { EN = j; loadLocale(start); })
    .catch(function () { EN = {}; loadLocale("en"); });
}

var inlineEl = document.getElementById("inline-data");
var inlineTxt = inlineEl ? inlineEl.textContent.trim() : "";
if (inlineTxt) {
  boot(JSON.parse(inlineTxt));
} else {
  fetch("./data.json").then(function (r) { return r.json(); }).then(boot).catch(function () {
    document.getElementById("spacer").innerHTML =
      '<div class="empty">data.json not found. Run <code>./run.sh export</code> first.</div>';
  });
}
})();
