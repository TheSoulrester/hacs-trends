/* HACS Trends front end - console layout.
 * No framework and no table library: 4,193 rows need a scroll window, and that is
 * less code than wiring up a dependency. The only external requirement is the webfont. */
(function () {
"use strict";

/* ------------------------------------------------------------------ i18n ---
 * English is always loaded and is the fallback for every individual key, so a
 * half-finished translation is useful from the first pull request rather than
 * producing a half-empty interface. */
var EN = {}, L = {}, LOCALE = "en";
var LANGS = [["en", "English"], ["de", "Deutsch"]];
var BUNDLED = null;
(function () {
  var el = document.getElementById("inline-i18n");
  if (el && el.textContent.trim()) { try { BUNDLED = JSON.parse(el.textContent); } catch (e) {} }
})();
function t(key, p) {
  var s = L[key] !== undefined ? L[key] : EN[key];
  if (s === undefined) return key;
  return p ? s.replace(/\{(\w+)\}/g, function (m, k) { return p[k] !== undefined ? p[k] : m; }) : s;
}
function pickLocale() {
  var codes = LANGS.map(function (a) { return a[0]; });
  var q = new URLSearchParams(location.search).get("lang");
  if (q && codes.indexOf(q) >= 0) return q;
  try { var st = localStorage.getItem("lang"); if (st && codes.indexOf(st) >= 0) return st; } catch (e) {}
  var nav = (navigator.language || "en").slice(0, 2);
  return codes.indexOf(nav) >= 0 ? nav : "en";
}
var NF, DF;
function n(v) { return v === undefined || v === null ? null : NF.format(v); }
function dt(iso) { return iso ? DF.format(new Date(iso + "T00:00:00")) : ""; }
function addDays(iso, k) {
  var x = new Date(iso + "T00:00:00Z"); x.setUTCDate(x.getUTCDate() + k);
  return x.toISOString().slice(0, 10);
}
/* The export carries minute resolution, so the distance is computed against the
   visitor's clock rather than baked in at export time. A repository pushed to an hour
   ago reads "1 h", not "0 d", and the figure stays right between the twice-daily runs.
   Older exports carry a bare date; those are read as midday UTC so the day is right. */
function rel(iso) {
  if (!iso) return "";
  var ms = Date.now() - Date.parse(iso.length <= 10 ? iso + "T12:00:00Z" : iso);
  if (!isFinite(ms)) return "";
  if (ms < 0) ms = 0;
  var min = Math.floor(ms / 60000);
  if (min < 1) return t("unit.now");
  if (min < 60) return t("unit.min", { n: n(min) });
  var h = Math.floor(min / 60);
  if (h < 24) return t("unit.hours", { n: n(h) });
  var d = Math.floor(h / 24);
  if (d < 60) return t("unit.days", { n: n(d) });
  return t("unit.months", { n: n(Math.round(d / 30.44)) });
}
function ago(iso) { var v = rel(iso); return v ? t("unit.ago", { v: v }) : ""; }

var ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" };
function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return ESC[c]; }); }

var ICONS = {
  trending: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>',
  installed: '<path d="M3 12h4l3 8 4-16 3 8h4"/>',
  breakout: '<path d="M12 20V5"/><path d="M6 11l6-6 6 6"/>',
  momentum: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/>',
  ships: '<path d="M4 8l8-4 8 4-8 4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/>',
  maintenance: '<path d="M12 9v4"/><path d="M12 17h.01"/><path d="M10.3 3.9L2.4 18a2 2 0 0 0 1.7 3h15.8a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/>',
  fresh: '<path d="M12 5v14"/><path d="M5 12h14"/>'
};

/* One mark per HACS category, for the 2,055 repositories brands has no icon for. */
var CAT_MARK = { integration: "\u25C6", plugin: "\u25A4", theme: "\u25D1", template: "\u2261",
  python_script: "\u00BB", appdaemon: "\u25A3", netdaemon: "\u25A3" };
/* Domains whose icon 404s. Remembered so a recycled row does not ask again. */
var ICON_GONE = {};
function iconHtml(r) {
  if (r.dom && !ICON_GONE[r.dom]) {
    return '<span class="ic" data-cat="' + esc(r.c) +
      '"><img src="https://brands.home-assistant.io/' + encodeURIComponent(r.dom) +
      '/icon.png" alt="" loading="lazy" data-dom="' + esc(r.dom) + '"></span>';
  }
  return '<span class="ic fb" aria-hidden="true">' + (CAT_MARK[r.c] || "\u25C6") + "</span>";
}

/* GitHub Pages serves everything with max-age=600, so a browser that loaded the page
   ten minutes before a deploy will happily use its stored copy without asking. For the
   two files that change with every run that is wrong, and "no-cache" does not mean "do
   not cache" - it means revalidate first, which costs one conditional request and
   returns 304 with no body when nothing changed. index.html and app.js are kept
   consistent by the build stamp the workflow writes instead. */
var FRESH = { cache: "no-cache" };

var WINDOWS = [7, 30, 90, 365];
/* Must match --row in the stylesheet: the renderer positions rows absolutely and cannot
   ask the DOM for a height it has not drawn yet. The phone layout is a card, not a table
   row, and needs the space. */
function narrow() { return innerWidth <= 900; }
function rowH() { return narrow() ? 96 : 56; }

/* ----------------------------------------------------------------- views --- */
var VIEWS = {
  trending: { windowed: true, sort: function (w) { return "d" + w; },
    cols: ["rank", "repo", "cat", "stars", "gained", "growth", "installs", "rhythm", "health"] },
  installed: { windowed: false, sort: function () { return "inst"; },
    filter: function (r) { return r.inst !== undefined; },
    cols: ["rank", "repo", "cat", "installs", "adoption", "instGained", "stars", "rhythm", "health"] },
  breakout: { windowed: true, sort: function (w) { return "p" + w; },
    filter: function (r, w) { return r["p" + w] !== undefined; },
    cols: ["rank", "repo", "cat", "growth", "gained", "stars", "installs", "rhythm", "health"] },
  momentum: { windowed: true, sort: function () { return "_mom"; }, needsInstallHistory: true,
    filter: function (r, w) { return r._mom !== undefined && r["d" + w] !== undefined; },
    cols: ["rank", "repo", "cat", "starRank", "instRank", "gained", "installs", "health"] },
  ships: { windowed: false, sort: function () { return "ry"; },
    filter: function (r) { return r.ry !== undefined; },
    /* 52 repositories sit at the 100-release fetch ceiling, so the top of this list is
       a block of ties. Within it, the one that shipped most recently ranks higher, then
       the one more people run - otherwise the order inside the block is arbitrary. */
    tie: function (a, b) {
      return (a.ra === undefined ? 9999 : a.ra) - (b.ra === undefined ? 9999 : b.ra) ||
             (b.inst || 0) - (a.inst || 0) || (b.s || 0) - (a.s || 0);
    },
    cols: ["rank", "repo", "cat", "releases", "commits", "released", "adoption", "stars", "installs"] },
  maintenance: { windowed: false, sort: function () { return "age"; },
    cols: ["rank", "repo", "cat", "health", "released", "rhythm", "stars", "installs"] },
  fresh: { windowed: false, sort: function () { return "ha"; },
    cols: ["rank", "repo", "addedAt", "cat", "stars", "gained", "installs", "health"] }
};
var ORDER = ["trending", "installed", "breakout", "momentum", "ships", "maintenance", "fresh"];

var COLS = {
  rank:      { w: "44px", i18n: null, nosort: true },
  repo:      { w: "minmax(230px,3fr)", i18n: "col.repository", sort: "n", str: true },
  cat:       { w: "124px", i18n: "col.category", sort: "c", str: true, cls: "hide-sm" },
  stars:     { w: "84px", i18n: "col.stars", sort: "s", right: true },
  gained:    { w: "98px", i18n: "col.starsGained", sort: function (w) { return "d" + w; }, right: true, win: true },
  growth:    { w: "92px", i18n: "col.growth", sort: function (w) { return "p" + w; }, right: true, win: true },
  installs:  { w: "116px", i18n: "col.installs", sort: "inst", right: true, cls: "hide-sm" },
  instGained:{ w: "100px", i18n: "col.installsGained", sort: function (w) { return "i" + w; }, right: true, win: true },
  adoption:  { w: "146px", i18n: "col.adoption", sort: "va", right: true, cls: "hide-md" },
  releases:  { w: "104px", i18n: "col.releases", sort: "ry", right: true },
  commits:   { w: "104px", i18n: "col.commits", sort: "cy", right: true, cls: "hide-md" },
  released:  { w: "128px", i18n: "col.lastRelease", sort: "ra" },
  rhythm:    { w: "134px", i18n: "col.rhythm", sort: "_rh", cls: "hide-md" },
  starRank:  { w: "96px", i18n: "col.starRank", sort: "_srank", right: true },
  instRank:  { w: "100px", i18n: "col.installRank", sort: "_irank", right: true },
  health:    { w: "146px", i18n: "col.lastCommit", sort: "age" },
  addedAt:   { w: "142px", i18n: "col.addedAt", sort: "ha", str: true }
};

var RH_ORDER = { continuous: 0, regular: 1, occasional: 2, dormant: 3, never: 4 };

/* ----------------------------------------------------------------- state --- */
var DATA = null, ROWS = [], VIEW = [], view = "trending", win = 30;
var sortKey = null, sortDir = -1, query = "", cat = null, rhythm = null;
var viewport, spacer, pool = [], maxInstall = 1;
/* The ranked list depends on the view, the window and the sort - not on what is typed
   into the search box. Re-sorting 4,193 rows on every keystroke was work thrown away. */
var baseList = null, baseKey = "", renderGen = 0;
/* Lowercasing 4,193 descriptions on every keystroke costs 79 ms, measured. The same
   search against a prepared haystack costs 3.5 ms; building it costs 213 ms once, in
   idle time after the first paint. Until it exists, the old path answers - a search
   typed in the first moment is slower, never wrong. */
var INDEXED = false;
function buildIndex() {
  for (var i = 0; i < ROWS.length; i++) {
    var r = ROWS[i];
    var slug = r.n.toLowerCase();
    r._k = (r.n + " " + (r.t || "") + " " + (r.dom || "")).toLowerCase();
    r._d = (r.d || "").toLowerCase();
    /* The suggestion list needs the fields separately, to tell a name that STARTS with
       the query from one that merely contains it. Lowercasing them here rather than on
       every keystroke: the same 4,193-row mistake the search itself used to make. */
    r._sl = slug;
    r._sn = slug.slice(slug.indexOf("/") + 1);
    r._n2 = (r.t || r._sn).toLowerCase();
    r._dm = (r.dom || "").toLowerCase();
  }
  INDEXED = true;
}
function hit(r, q) {
  if (INDEXED) return r._k.indexOf(q) >= 0 || r._d.indexOf(q) >= 0;
  return (r.n && r.n.toLowerCase().indexOf(q) >= 0) ||
         (r.t && r.t.toLowerCase().indexOf(q) >= 0) ||
         (r.d && r.d.toLowerCase().indexOf(q) >= 0) ||
         (r.dom && r.dom.toLowerCase().indexOf(q) >= 0);
}
function $(id) { return document.getElementById(id); }

function installWindowOk(w) {
  var m = DATA.meta;
  return !!m.first_snapshot && (m.history_days || 1) - 1 >= w;
}
function installFrom(w) { return addDays(DATA.meta.first_snapshot, w); }

/* Momentum: percentile of star rate and of installation rate, ranked on the LOWER
   of the two so a repository has to be strong in both. Component ranks stay on the
   row and get their own columns - a placement is never a black box. */
function computeMomentum(w) {
  ROWS.forEach(function (r) { delete r._mom; delete r._srank; delete r._irank; });
  var elig = ROWS.filter(function (r) {
    return r.inst !== undefined && !r.amb && r["d" + w] !== undefined && r["i" + w] !== undefined;
  });
  if (elig.length < 5) return;
  function rank(fn) {
    var s = elig.slice().sort(function (a, b) { return fn(b) - fn(a); });
    var m = new Map();
    s.forEach(function (r, i) { m.set(r, Math.round((1 - i / (s.length - 1)) * 100)); });
    return m;
  }
  var sr = rank(function (r) { return r["d" + w] / Math.max(1, (r.s || 1) - r["d" + w]); });
  var ir = rank(function (r) { return r["i" + w] / Math.max(1, r.inst - r["i" + w]); });
  elig.forEach(function (r) {
    r._srank = sr.get(r); r._irank = ir.get(r); r._mom = Math.min(r._srank, r._irank);
  });
}

function apply() {
  var v = VIEWS[view];
  if (view === "momentum") computeMomentum(win);
  renderGen++;
  ROWS.forEach(function (r) { r._rh = RH_ORDER[r.rh] === undefined ? 9 : RH_ORDER[r.rh]; });
  /* The ranking is numbered BEFORE the user's filters are applied, so a search result
     keeps the place it holds in the whole list: finding a repository at 412 tells you
     something that finding it at 1 does not. Only the view's own eligibility rule
     (an installation figure, a growth figure) takes part in the numbering - a row that
     cannot be ranked at all has no place to keep. */
  var key = sortKey || v.sort(win);
  var bk = [view, win, key, sortDir, LOCALE].join("|");
  var base;
  if (baseList && baseKey === bk) {
    base = baseList;
  } else {
    base = ROWS.filter(function (r) { return !v.filter || v.filter(r, win); });
    var str = key === "n" || key === "c" || key === "ha";
    var dir = sortDir;
    var tie = (!sortKey && v.tie) ? v.tie : null;
    base.sort(function (a, b) {
    var x = a[key], y = b[key];
    var ax = x === undefined || x === null, ay = y === undefined || y === null;
    /* Rows without a value sink in BOTH directions - otherwise an ascending sort
       fills the top of the table with gaps. */
    if (ax && ay) return (b.s || 0) - (a.s || 0);
    if (ax) return 1;
    if (ay) return -1;
    if (str) return dir * String(x).localeCompare(String(y), LOCALE);
    var d = dir > 0 ? x - y : y - x;
    if (d === 0 && tie) return tie(a, b);
    return d;
  });
    for (var i = 0; i < base.length; i++) base[i]._rank = i + 1;
    baseList = base; baseKey = bk;
  }

  var q = query.trim().toLowerCase();
  VIEW = (q || cat || rhythm) ? base.filter(function (r) {
    if (cat && r.c !== cat) return false;
    if (rhythm && r.rh !== rhythm) return false;
    if (q && !hit(r, q)) return false;
    return true;
  }) : base;
  maxInstall = VIEW.reduce(function (m, r) { return Math.max(m, r.inst || 0); }, 1);
  renderStrip(); render(); renderFoot();
}

/* ----------------------------------------------------------------- cells --- */
function na(hint) {
  return '<span class="na" title="' + esc(hint || t("hint.noValue")) + '">&ndash;</span>';
}
function delta(v, hint) {
  if (v === undefined || v === null) return na(hint);
  return '<span class="delta ' + (v > 0 ? "p" : v < 0 ? "n" : "") + '" title="' +
    esc(t("hint.starsAdded")) + '">' + (v > 0 ? "+" : "") + n(v) + "</span>";
}
function dotline(cls, label, extra) {
  return '<span class="dotline ' + cls + '"><span class="dot"></span>' + esc(label) + "</span>" +
    (extra ? ' <span class="age">' + extra + "</span>" : "");
}
function cell(c, r, idx) {
  switch (c) {
    case "rank": {
      var pos = r._rank || idx + 1;
      return '<span class="rn"' +
        (pos === idx + 1 ? "" : ' title="' + esc(t("hint.rankKept")) + '"') +
        ">" + pos + "</span>";
    }
    case "repo":
      return '<span class="repo">' + iconHtml(r) +
        '<span class="stack"><span class="l1">' +
        '<a href="https://github.com/' + esc(r.n) + '" target="_blank" rel="noopener">' +
        esc(r.t || r.n.split("/")[1]) + "</a>" +
        '<span class="slug" title="' + esc(r.n) + '">' + esc(r.n) + "</span>" +
        (r.v ? '<span class="ver" title="' + esc(t("hint.version")) + '">' +
               esc(r.v) + "</span>" : "") + "</span>" +
        '<span class="desc">' + (r.d ? esc(r.d) : "") + "</span></span></span>";
    case "cat": return '<span class="cat">' + esc(t("cat." + r.c)) + "</span>";
    case "stars": return r.s === undefined ? na() : '<span class="num">' + n(r.s) + "</span>";
    case "gained": return delta(r["d" + win]);
    case "growth": {
      var p = r["p" + win];
      if (p === undefined) return na();
      return '<span class="delta ' + (p > 0 ? "p" : p < 0 ? "n" : "") + '">' +
        (p > 0 ? "+" : "") + n(Math.round(p * 10) / 10) + "%</span>";
    }
    case "installs": {
      if (r.inst === undefined) return na(t("hint.integrationsOnly"));
      var w = Math.max(2, Math.round(r.inst / maxInstall * 42));
      return '<span class="bar num">' + n(r.inst) + '<i style="width:' + w + 'px"></i></span>' +
        (r.amb ? '<span class="amb" title="' + esc(t("hint.ambiguousDomain")) + '">&#9888;</span>' : "");
    }
    case "instGained":
      return installWindowOk(win) ? delta(r["i" + win])
        : na(t("window.unavailableFrom", { date: dt(installFrom(win)) }));
    case "adoption":
      return r.va === undefined ? na(t("hint.noAdoption"))
        : '<span class="num" title="' + esc(t("hint.adoption", { v: r.v || "?" })) + '">' +
          n(r.va) + "%</span>";
    case "releases": {
      if (r.ry === undefined) return na();
      /* Only 30 releases are fetched per repository, 100 on the second pass. A value
         that hit the ceiling shows as 100+ rather than as a number we cannot stand behind. */
      return '<span class="num"' + (r.ryc ? ' title="' + esc(t("hint.releasesCapped")) + '"' : "") +
        ">" + n(r.ry) + (r.ryc ? "+" : "") + "</span>";
    }
    case "commits": return r.cy === undefined ? na() : '<span class="num">' + n(r.cy) + "</span>";
    case "released":
      return r.rd === undefined ? na(t("hint.noRelease"))
        : '<span class="num">' + esc(ago(r.rd)) + "</span>";
    case "rhythm":
      return dotline("rh-" + (r.rh || "never"), t("rhythm." + (r.rh || "never")),
        r.ry !== undefined ? t("unit.perYear", { n: n(r.ry) + (r.ryc ? "+" : "") }) : "");
    case "starRank": return r._srank === undefined ? na() : '<span class="num">' + r._srank + "</span>";
    case "instRank": return r._irank === undefined ? na() : '<span class="num">' + r._irank + "</span>";
    case "addedAt":
      /* Repositories carried over when the HACS list was first written have no real date
         - the record starts after they were already in. Saying so beats printing the day
         the list was created as if it were theirs. */
      if (r.hb) return '<span class="na" title="' + esc(t("hint.sinceStart")) + '">' +
        esc(t("unit.sinceStart")) + "</span>";
      return r.ha === undefined ? na(t("hint.noAddedDate"))
        : '<span class="num">' + esc(dt(r.ha)) + "</span>";
    case "health":
      /* "over a year   14 mo" said the same thing twice. The colour of the dot carries the
         state, the figure carries the fact, and the word is on the tooltip for anyone who
         cannot read the colour. */
      return '<span title="' + esc(t("health." + r.h)) + '">' +
        dotline("h-" + r.h, rel(r.lu) || t("health." + r.h)) + "</span>";
  }
  return "";
}

/* -------------------------------------------------------------- the card ---
 * A phone gets one figure in large type - the one the current view ranks by - because a
 * ranking whose reason is not visible is just a list. Everything else stays, in the size
 * it deserves. */
function bigFor(r) {
  switch (view) {
    case "breakout": {
      var p = r["p" + win];
      return { v: p === undefined ? na() : '<span class="delta ' + (p > 0 ? "p" : p < 0 ? "n" : "") +
        '">' + (p > 0 ? "+" : "") + n(Math.round(p * 10) / 10) + "%</span>", k: t("window." + win) };
    }
    case "installed":
      return { v: r.inst === undefined ? na(t("hint.integrationsOnly"))
        : '<span class="num">' + n(r.inst) + "</span>", k: t("col.installs") };
    case "momentum":
      return { v: r._mom === undefined ? na() : '<span class="num">' + r._mom + "</span>",
        k: t("view.momentum.title") };
    case "ships":
      return { v: r.ry === undefined ? na()
        : '<span class="num">' + n(r.ry) + (r.ryc ? "+" : "") + "</span>", k: t("col.releases") };
    case "maintenance":
      return { v: '<span class="num h-' + r.h + '">' + esc(rel(r.lu) || "-") + "</span>",
        k: t("col.lastCommit") };
    default:
      return { v: delta(r["d" + win]), k: t("window." + win) };
  }
}

/* Two values under the description, never three: a third one wraps to a second line on a
   360px screen for exactly those repositories that have installation figures, and a row
   whose height depends on whether a number happens to exist looks broken. Whatever the
   big figure already says is left out, and the rest is taken in order of usefulness. */
function subFor(r) {
  var out = [];
  if (view !== "maintenance") out.push(dotline("h-" + r.h, rel(r.lu) || t("health." + r.h)));
  if (r.s !== undefined) out.push("<span>" + n(r.s) + "\u2605</span>");
  if (view !== "installed" && r.inst !== undefined) {
    out.push("<span>" + n(r.inst) + " " + esc(t("unit.installsShort")) + "</span>");
  }
  return out.slice(0, 2).join("");
}

function cardHtml(r, idx) {
  var b = bigFor(r);
  return '<div class="mcard"><span class="rn">' + (r._rank || idx + 1) + "</span>" +
    iconHtml(r) +
    '<span class="mbody"><span class="l1">' +
    '<a href="https://github.com/' + esc(r.n) + '" target="_blank" rel="noopener">' +
    esc(r.t || r.n.split("/")[1]) + "</a>" +
    (r.v ? '<span class="ver">' + esc(r.v) + "</span>" : "") + "</span>" +
    '<span class="mdesc">' + (r.d ? esc(r.d) : "") + "</span>" +
    '<span class="msub">' + subFor(r) + "</span></span>" +
    '<span class="mbig"><span class="bv">' + b.v + '</span><span class="bk">' +
    esc(b.k) + "</span></span></div>";
}

/* ------------------------------------------------------------- rendering --- */
function visibleCols() {
  return VIEWS[view].cols.filter(function (c) {
    var d = COLS[c];
    if (d.cls === "hide-sm" && innerWidth <= 900) return false;
    if (d.cls === "hide-md" && innerWidth <= 1240) return false;
    return true;
  });
}
function tpl() { return visibleCols().map(function (c) { return COLS[c].w; }).join(" "); }

/* Below 900px the stylesheet gives the viewport its content height, so its clientHeight
   is the height of all 4,193 rows and the renderer would build every one of them -
   71,405 DOM nodes, measured. On that layout the page itself scrolls, so the window is
   read from where the spacer sits relative to the screen. */
function metrics() {
  if (narrow()) {
    var r = spacer.getBoundingClientRect();
    return { top: Math.max(0, -r.top), h: innerHeight };
  }
  return { top: viewport.scrollTop, h: viewport.clientHeight };
}

function render() {
  var cols = visibleCols(), grid = tpl(), h = rowH(), card = narrow();
  spacer.style.height = (VIEW.length * h) + "px";
  if (!VIEW.length) {
    /* Two different kinds of nothing: a filter that matched nothing, and a column that
       cannot have values yet. The second one used to be explained in the header while
       the table sat there wordlessly empty. */
    var why = (!query && !cat && !rhythm && VIEWS[view].needsInstallHistory && !installWindowOk(win))
      ? t("empty.installsGrowing", { date: dt(installFrom(win)) })
      : t("foot.empty");
    spacer.innerHTML = '<div class="empty">' + esc(why) + "</div>"; pool = []; return;
  }
  if (!pool.length) spacer.innerHTML = "";
  var m = metrics(), top = m.top;
  var first = Math.max(0, Math.floor(top / h) - 4);
  var last = Math.min(VIEW.length, Math.ceil((top + m.h) / h) + 4);
  var need = last - first;
  /* Two spare slots so a row leaving the top and one arriving at the bottom never
     compete for the same element. */
  var want = need + 2;
  if (pool.length < want) {
    while (pool.length < want) {
      var el = document.createElement("div"); el.className = "row";
      spacer.appendChild(el); pool.push(el);
    }
    renderGen++;  // the modulo mapping below moved, so every slot is stale
  }
  var size = pool.length, used = {};

  /* Rows keep their element while they stay on screen. Scrolling one row used to rewrite
     all thirty of them; with the slot chosen by index modulo pool size, only the one that
     actually entered the window is written. The generation counter invalidates everything
     at once when the data, the columns or the pool size change. */
  var written = [];
  for (var idx = first; idx < last; idx++) {
    var slot = idx % size;
    used[slot] = 1;
    var node = pool[slot];
    if (node._idx === idx && node._gen === renderGen) continue;
    var r = VIEW[idx];
    node._idx = idx; node._gen = renderGen;
    node.hidden = false;
    node.style.top = (idx * h) + "px";
    node.style.gridTemplateColumns = card ? "" : grid;
    node.innerHTML = card ? cardHtml(r, idx) : cols.map(function (c) {
      return '<div class="cell' + (COLS[c].right ? " r" : "") + '">' + cell(c, r, idx) + "</div>";
    }).join("");
    written.push(node);
  }
  for (var i = 0; i < size; i++) {
    /* Emptying the surplus as well: a row that is hidden but still carries the old
       repository is one CSS rule away from being a phantom duplicate on screen. */
    if (!used[i] && !pool[i].hidden) {
      pool[i].hidden = true; pool[i].innerHTML = ""; pool[i]._idx = -1;
    }
  }
  /* The version must not shrink, so the path absorbs every missing pixel and can end up
     as a two-pixel sliver of ellipsis - noise where a path used to be. Below the width
     of about five characters it says nothing, so it is dropped and the full path stays
     on the tooltip. All widths are read before any of them is acted on: hiding one inside
     the reading loop invalidates the layout and forces the browser to compute it again
     for the next read, which measured 26 ms per render against 9 ms for the same work
     split in two. */
  if (card) return;
  var slugs = [], widths = [];
  for (var j = 0; j < written.length; j++) {
    var sl = written[j].querySelector(".slug");
    if (sl) slugs.push(sl);
  }
  for (j = 0; j < slugs.length; j++) widths.push(slugs[j].getBoundingClientRect().width);
  for (j = 0; j < slugs.length; j++) slugs[j].hidden = widths[j] < 46;
}

function buildHead() {
  var cols = visibleCols(), th = $("thead");
  th.style.gridTemplateColumns = tpl();
  var active = sortKey || VIEWS[view].sort(win);
  th.innerHTML = cols.map(function (c) {
    var d = COLS[c];
    if (d.nosort) return "<button disabled></button>";
    var key = typeof d.sort === "function" ? d.sort(win) : d.sort;
    var on = key === active;
    return '<button data-k="' + key + '" data-str="' + (d.str ? 1 : 0) + '" data-active="' +
      (on ? 1 : 0) + '" class="' + (d.right ? "r" : "") + '"><span>' + esc(t(d.i18n)) +
      (on ? " " + (sortDir < 0 ? "▼" : "▲") : "") + "</span>" +
      (d.win ? '<span class="sub">' + esc(t("window." + win)) + "</span>" : "") + "</button>";
  }).join("");
  th.querySelectorAll("button[data-k]").forEach(function (b) {
    b.onclick = function () {
      var k = b.dataset.k;
      if ((sortKey || VIEWS[view].sort(win)) === k) sortDir = -sortDir;
      else { sortKey = k; sortDir = b.dataset.str === "1" ? 1 : -1; }
      buildHead(); apply();
    };
  });
}

function buildNav() {
  $("nav").innerHTML = ORDER.map(function (k) {
    return '<button data-v="' + k + '" aria-current="' + (k === view) + '">' +
      '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
      'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' + ICONS[k] + "</svg>" +
      "<span>" + esc(t("view." + k + ".title")) + "</span></button>";
  }).join("");
  $("nav").querySelectorAll("button").forEach(function (b) {
    b.onclick = function () {
      view = b.dataset.v; sortKey = null; sortDir = -1;
      buildNav(); buildWindows(); buildHead(); renderHead(); apply();
      viewport.scrollTop = 0;
    };
  });
}

function buildWindows() {
  var box = $("windows"), v = VIEWS[view];
  box.hidden = !v.windowed;
  /* Cleared, not merely hidden: a leftover button keeps its click handler, and clicking
     it used to change the period silently while the highlight stayed where it was. */
  box.innerHTML = "";
  if (!v.windowed) return;
  box.innerHTML = WINDOWS.map(function (w) {
    return '<button data-w="' + w + '" aria-pressed="' + (w === win) + '">' +
      esc(t("window." + w)) + "</button>";
  }).join("");
  box.querySelectorAll("button").forEach(function (b) {
    b.onclick = function () {
      win = parseInt(b.dataset.w, 10); sortKey = null;
      buildWindows(); buildHead(); renderHead(); apply();
    };
  });
}

function renderHead() {
  var m = DATA.meta;
  $("view-title").textContent = t("view." + view + ".title");
  var note = t("view." + view + ".note", {
    matched: n(m.analytics.matched), withDomain: n(m.analytics.repos_with_domain),
    minBase: 25, median: m.activity_percentiles.p50, p90: m.activity_percentiles.p90,
    installed: t("view.installed.title")
  });
  $("view-note").innerHTML = esc(note).replace(/&lt;b&gt;/g, "<b>").replace(/&lt;\/b&gt;/g, "</b>");
}

/* Four figures that change with the view - the point of a console strip is that it
   answers the question you just asked, not that it shows the same four numbers. */
/* Counts over the whole corpus never change. Recomputing four of them on every
   keystroke was four more passes over 4,193 rows for an unchanging number. */
var STRIP_CACHE = {};
function corpus(key, fn) {
  if (STRIP_CACHE[key] === undefined) {
    var c = 0;
    for (var i = 0; i < ROWS.length; i++) if (fn(ROWS[i])) c++;
    STRIP_CACHE[key] = c;
  }
  return STRIP_CACHE[key];
}

function renderStrip() {
  var m = DATA.meta, s = [];
  function sum(key) { return VIEW.reduce(function (a, r) { return a + (r[key] || 0); }, 0); }
  if (view === "trending" || view === "breakout" || view === "fresh") {
    s = [["strip.starsGiven", "+" + n(sum("d" + win)), "pos"],
         ["strip.moving", n(VIEW.filter(function (r) { return r["d" + win]; }).length)],
         ["strip.dormantYear", n(corpus("dormantYear", function (r) { return (r.age || 0) > 365; })), "warn"],
         ["strip.withInstalls", n(m.analytics.matched)]];
  } else if (view === "installed" || view === "momentum") {
    s = [["strip.installsTotal", n(sum("inst"))],
         ["strip.withInstalls", n(VIEW.length)],
         ["strip.ambiguous", n(corpus("ambiguous", function (r) { return r.amb; })), "warn"],
         ["strip.adoptionKnown", n(corpus("adoptionKnown", function (r) { return r.va !== undefined; }))]];
  } else {
    s = [["strip.continuous", n(corpus("rhContinuous", function (r) { return r.rh === "continuous"; })), "pos"],
         ["strip.regular", n(corpus("rhRegular", function (r) { return r.rh === "regular"; }))],
         ["strip.noReleaseYear", n(corpus("rhDormant", function (r) { return r.rh === "dormant"; })), "warn"],
         ["strip.noRelease", n(corpus("rhNever", function (r) { return r.rh === "never"; })), "warn"]];
  }
  $("strip").innerHTML = s.map(function (x) {
    var color = x[2] === "pos" ? "var(--pos)" : x[2] === "warn" ? "var(--stale)" : "var(--ink)";
    return '<div class="stat"><span class="k">' + esc(t(x[0])) +
      '</span><span class="v" style="color:' + color + '">' + x[1] + "</span></div>";
  }).join("");
}

function buildFilters() {
  var cc = {}, rc = {};
  ROWS.forEach(function (r) { cc[r.c] = (cc[r.c] || 0) + 1; rc[r.rh] = (rc[r.rh] || 0) + 1; });
  var order = ["integration", "plugin", "theme", "template", "python_script", "appdaemon", "netdaemon"];
  $("cats").innerHTML = '<button class="chip" data-c="" aria-pressed="' + !cat + '">' +
    esc(t("filter.all")) + "</button>" +
    order.filter(function (c) { return cc[c]; }).map(function (c) {
      return '<button class="chip" data-c="' + c + '" aria-pressed="' + (cat === c) +
        '">' + esc(t("cat." + c)) + '<span class="c">' + cc[c] + "</span></button>";
    }).join("");
  $("cats").querySelectorAll(".chip").forEach(function (b) {
    b.onclick = function () { cat = b.dataset.c || null; buildFilters(); apply(); };
  });
  $("rhythms").innerHTML = ["continuous", "regular", "occasional", "dormant", "never"]
    .filter(function (k) { return rc[k]; }).map(function (k) {
      return '<button class="chip" data-r="' + k + '" aria-pressed="' + (rhythm === k) + '">' +
        esc(t("rhythm." + k)) + '<span class="c">' + rc[k] + "</span></button>";
    }).join("");
  $("rhythms").querySelectorAll(".chip").forEach(function (b) {
    b.onclick = function () {
      rhythm = rhythm === b.dataset.r ? null : b.dataset.r; buildFilters(); apply();
    };
  });
}

/* ---------------------------------------------------------- autocomplete ---
 * Over name, display name and repository path only. A substring hit inside a
 * description makes a poor suggestion even though the search itself covers it. */
var SUG = [], sugSel = -1;
function suggest(raw) {
  var q = raw.trim().toLowerCase();
  if (q.length < 2) return [];
  if (!INDEXED) return [];
  /* A two-letter query matches thousands of rows. Collecting them all and sorting was
     the most expensive thing a keystroke did; only eight of them are ever shown, so the
     best eight are kept as we go and nothing else is allocated. */
  var head = [], tail = [];
  function keep(list, r) {
    var v = r.s || 0;
    if (list.length === 8 && v <= (list[7].s || 0)) return;
    var i = list.length;
    while (i > 0 && (list[i - 1].s || 0) < v) i--;
    list.splice(i, 0, r);
    if (list.length > 8) list.pop();
  }
  for (var i = 0; i < ROWS.length; i++) {
    var r = ROWS[i];
    if (r._n2.indexOf(q) === 0 || r._sn.indexOf(q) === 0 || r._dm.indexOf(q) === 0) keep(head, r);
    else if (r._n2.indexOf(q) >= 0 || r._sl.indexOf(q) >= 0 || r._dm.indexOf(q) >= 0) keep(tail, r);
  }
  return head.concat(tail).slice(0, 8);
}
function renderSuggest() {
  var box = $("ac");
  if (!SUG.length) { closeSuggest(); return; }
  box.innerHTML = SUG.map(function (r, i) {
    return '<button type="button" role="option" data-i="' + i + '" aria-selected="' +
      (i === sugSel) + '">' + iconHtml(r) +
      '<span class="an">' + esc(r.t || r.n.split("/")[1]) + "</span>" +
      '<span class="as">' + esc(r.n) + "</span></button>";
  }).join("");
  box.hidden = false;
  $("q").setAttribute("aria-expanded", "true");
  box.querySelectorAll("button").forEach(function (b) {
    b.addEventListener("mousedown", function (ev) {
      ev.preventDefault();
      choose(SUG[parseInt(b.dataset.i, 10)]);
    });
  });
}
function closeSuggest() {
  SUG = []; sugSel = -1;
  $("ac").hidden = true; $("ac").innerHTML = "";
  $("q").setAttribute("aria-expanded", "false");
}
function choose(r) {
  if (!r) return;
  $("q").value = r.n;
  query = r.n;
  closeSuggest();
  apply();
  viewport.scrollTop = 0;
  if (innerWidth <= 900) scrollTo(0, 0);
}

function renderFoot() {
  var c = DATA.meta.coverage;
  $("foot").innerHTML =
    '<span class="hl">' + n(VIEW.length) + " / " + n(ROWS.length) + "</span>" +
    "<span>" + esc(t("foot.starCoverage", { n: n(c.with_stars), pct: Math.round(c.with_stars / c.total * 100) })) + "</span>" +
    "<span>" + esc(t("foot.downloadCoverage", { pct: Math.round(c.with_downloads / c.total * 100) })) + "</span>" +
    "<span>" + esc(t("foot.installsSample")) + "</span>";
}

function paint() {
  NF = new Intl.NumberFormat(LOCALE);
  DF = new Intl.DateTimeFormat(LOCALE, { day: "2-digit", month: "short", year: "numeric" });
  document.documentElement.lang = LOCALE;
  document.querySelectorAll("[data-i18n]").forEach(function (el) {
    el.textContent = t(el.dataset.i18n);
  });
  $("q").placeholder = t("filter.searchPlaceholder");
  $("disclose").textContent = t("mobile.info");
  $("brand-sub").textContent = t("app.repoStamp", {
    n: n(DATA.meta.counts.repos), date: dt(DATA.meta.day)
  });
  buildNav(); buildWindows(); buildHead(); buildFilters(); renderHead(); apply();
}

function loadLocale(code) {
  LOCALE = code;
  try { localStorage.setItem("lang", code); } catch (e) {}
  if (code === "en") { L = {}; paint(); return; }
  if (BUNDLED) { L = BUNDLED[code] || {}; paint(); return; }
  fetch("./i18n/" + code + ".json", FRESH).then(function (r) { return r.json(); })
    .then(function (j) { L = j; paint(); }).catch(function () { L = {}; paint(); });
}

function boot(data) {
  DATA = data; ROWS = data.repos;
  viewport = $("viewport"); spacer = $("spacer");
  viewport.addEventListener("scroll", render, { passive: true });
  /* The narrow layout scrolls the page, not the viewport element. */
  addEventListener("scroll", function () { if (innerWidth <= 900) render(); }, { passive: true });
  addEventListener("resize", function () {
    pool = []; spacer.innerHTML = ""; renderGen++; buildHead(); render();
  });
  /* Error events do not bubble, but they do capture. One listener, no inline handler,
     and a domain that 404s is asked for exactly once. */
  spacer.addEventListener("error", function (e) {
    var img = e.target;
    if (!img || img.tagName !== "IMG" || !img.dataset.dom) return;
    ICON_GONE[img.dataset.dom] = 1;
    var box = img.parentNode;
    box.className = "ic fb";
    box.setAttribute("aria-hidden", "true");
    box.textContent = CAT_MARK[box.dataset.cat] || "\u25C6";
  }, true);
  /* One line on the phone standing in for the explanation and the four summary figures,
     which together used to push the first row two thirds of the way down the screen. */
  var dis = $("disclose");
  dis.hidden = false;
  dis.onclick = function () {
    var open = document.body.classList.toggle("info-open");
    dis.setAttribute("aria-expanded", open ? "true" : "false");
    render();
  };

  var qi = $("q");
  qi.addEventListener("input", function (e) {
    query = e.target.value;
    SUG = suggest(query); sugSel = -1; renderSuggest();
    apply(); viewport.scrollTop = 0;
  });
  qi.addEventListener("keydown", function (e) {
    if (e.key === "Escape") { closeSuggest(); return; }
    if (!SUG.length) return;
    if (e.key === "ArrowDown") { e.preventDefault(); sugSel = (sugSel + 1) % SUG.length; renderSuggest(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); sugSel = (sugSel - 1 + SUG.length) % SUG.length; renderSuggest(); }
    else if (e.key === "Enter" && sugSel >= 0) { e.preventDefault(); choose(SUG[sugSel]); }
  });
  qi.addEventListener("blur", closeSuggest);
  var sel = $("lang");
  sel.innerHTML = LANGS.map(function (a) {
    return '<option value="' + a[0] + '">' + a[1] + "</option>";
  }).join("");
  var start = pickLocale();
  sel.value = start;
  sel.onchange = function () { loadLocale(sel.value); };
  var idle = window.requestIdleCallback || function (f) { return setTimeout(f, 250); };
  if (BUNDLED) { EN = BUNDLED.en || {}; loadLocale(start); idle(buildIndex); return; }
  fetch("./i18n/en.json", FRESH).then(function (r) { return r.json(); })
    .then(function (j) { EN = j; loadLocale(start); })
    .catch(function () { EN = {}; loadLocale("en"); })
    .then(function () { idle(buildIndex); });
}

var el = document.getElementById("inline-data");
var inline = el ? el.textContent.trim() : "";
if (inline) boot(JSON.parse(inline));
else fetch("./data.json", FRESH).then(function (r) { return r.json(); }).then(boot).catch(function () {
  document.getElementById("spacer").innerHTML =
    '<div class="empty">data.json not found. Run <code>./run.sh export</code> first.</div>';
});
})();
