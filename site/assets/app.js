// Section Anything site: renders every number and list from window.SA_DATA (data/results.js).
// No frameworks, no network requests. Text goes into the DOM via text nodes only.
(function () {
  "use strict";

  // ---- Theme: ?theme=dark|light (not saved) > saved choice > system ----
  var root = document.documentElement;
  var KEY = "sa-theme";
  var TEDS_MAX = 100; // Heading TEDS is a 0-100 scale; bars are drawn on the full scale

  function stored(value) {
    try {
      if (value === undefined) return window.localStorage.getItem(KEY);
      window.localStorage.setItem(KEY, value);
    } catch (e) { /* storage blocked: theme still works for this view */ }
    return null;
  }
  function systemDark() {
    return !!(window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  }
  function currentTheme() {
    var t = root.getAttribute("data-theme");
    return t || (systemDark() ? "dark" : "light");
  }
  var forced = (window.location.search.match(/[?&]theme=(dark|light)\b/) || [])[1];
  var saved = stored();
  if (forced) root.setAttribute("data-theme", forced);
  else if (saved === "dark" || saved === "light") root.setAttribute("data-theme", saved);

  // ---- Small DOM helpers ----
  function el(tag, attrs) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (attrs[k] !== undefined && attrs[k] !== null && attrs[k] !== false) node.setAttribute(k, attrs[k]);
    });
    for (var i = 2; i < arguments.length; i++) append(node, arguments[i]);
    return node;
  }
  function append(node, child) {
    if (child === undefined || child === null || child === false) return;
    if (Array.isArray(child)) { child.forEach(function (c) { append(node, c); }); return; }
    node.appendChild(typeof child === "object" ? child : document.createTextNode(String(child)));
  }
  function fill(id) {
    var node = document.getElementById(id);
    if (!node) return;
    node.textContent = "";
    for (var i = 1; i < arguments.length; i++) append(node, arguments[i]);
  }
  function safeUrl(url) {
    return typeof url === "string" && /^https?:\/\//i.test(url) ? url : "";
  }
  function money(n) {
    return n === 0 ? "$0" : "$" + Number(n).toFixed(2);
  }
  function score(n) {
    return typeof n === "number" ? n.toFixed(1) : "";
  }
  function oursTag(row) {
    return row && row.ours ? [" ", el("span", { "class": "tag" }, "ours")] : null;
  }
  function orList(items) {
    if (items.length < 2) return items.join("");
    return items.slice(0, -1).join(", ") + " or " + items[items.length - 1];
  }
  function docsText(docs, key) {
    var n = docs && typeof docs === "object" ? docs[key] : null;
    return typeof n === "number" ? n.toLocaleString("en-US") + " docs" : "";
  }

  // ---- Table renderer used by every results table ----
  // cols: [{ key, label, sub, num, bar, fmt }]
  function table(caption, cols, rows) {
    var head = el("tr", null, cols.map(function (c) {
      return el("th", { scope: "col", "class": c.num ? "num" : null },
        c.label, c.sub ? el("span", { "class": "th-sub" }, c.sub) : null);
    }));
    var body = rows.map(function (r) {
      return el("tr", { "class": r.ours ? "ours" : null }, cols.map(function (c, i) {
        var v = r[c.key];
        if (i === 0) return el("th", { scope: "row" }, v, oursTag(r));
        var text = c.fmt ? c.fmt(v, r) : String(v);
        if (!c.bar) return el("td", { "class": c.num ? "num" : null }, text);
        var pct = Math.max(0, Math.min(100, (v / c.bar) * 100));
        return el("td", { "class": "bar-cell" }, el("div", { "class": "bar-line" },
          el("span", { "class": "bar", "aria-hidden": "true" },
            el("span", { "class": "bar-fill", style: "width:" + pct + "%" })),
          el("span", { "class": "bar-value" }, text)));
      }));
    });
    return el("div", { "class": "table-wrap", tabindex: "0", role: "region", "aria-label": caption },
      el("table", null, el("caption", { "class": "visually-hidden" }, caption),
        el("thead", null, head), el("tbody", null, body)));
  }

  function block(t, cols, meta) {
    var parts = [t.date ? "Measured " + t.date : null].concat(meta || []).filter(Boolean);
    return el("article", { "class": "result" },
      el("h3", null, t.title),
      parts.length ? el("p", { "class": "meta" }, parts.join(" · ")) : null,
      table(t.title, cols, t.rows || []),
      t.note ? el("p", { "class": "note" }, t.note) : null);
  }

  function render() {
    var D = window.SA_DATA;
    if (!D) {
      fill("status", "Data file missing: data/results.js did not load.");
      return;
    }

    // Repo links: hidden unless repoUrl is set.
    var repo = safeUrl(D.repoUrl);
    Array.prototype.forEach.call(document.querySelectorAll("[data-repo]"), function (a) {
      if (repo) { a.setAttribute("href", repo); a.hidden = false; } else { a.hidden = true; }
    });

    // Demo links: hidden unless appUrl is set (the demo is not public yet).
    var app = safeUrl(D.appUrl);
    Array.prototype.forEach.call(document.querySelectorAll("[data-app]"), function (a) {
      if (app) { a.setAttribute("href", app); a.hidden = false; } else { a.hidden = true; }
    });

    // Try it with your own model
    var tryIt = D.tryIt || {};
    fill("try-intro", tryIt.intro || "");
    fill("try-steps", (tryIt.steps || []).map(function (s) { return el("li", null, s); }));
    fill("try-privacy", tryIt.privacy || "");

    // Hero
    var modes = D.modes || [];
    fill("status", D.status);
    fill("hero-modes", orList(modes.map(function (m) { return m.name; })));
    var lightrag = (D.integrations || []).filter(function (i) { return i.name === "LightRAG"; })[0];
    if (lightrag && lightrag.status) fill("hero-lightrag", " (" + lightrag.status + ")");

    // How it works
    fill("modes", modes.map(function (m) {
      var cost = money(m.costPer1000Pages);
      return el("article", { "class": "card mode" },
        el("h3", null, m.name),
        el("p", null, m.how),
        el("dl", { "class": "facts" },
          el("div", null, el("dt", null, "Model"), el("dd", null, m.model)),
          el("div", null, el("dt", null, "What is sent"), el("dd", null, m.sends)),
          el("div", null, el("dt", null, "Cost per 1,000 pages"),
            el("dd", null, el("strong", null, cost),
              typeof m.costPer1000PagesStrong === "number"
                ? el("span", { "class": "muted" }, " · " + money(m.costPer1000PagesStrong) + " with a stronger model")
                : null))));
    }));

    // Benchmarks
    var R = D.readoc || {};
    var link = safeUrl(R.link);
    fill("readoc-about", R.about, link ? [" ", el("a", { href: link, rel: "noopener noreferrer" }, "READoc on GitHub")] : null);

    var both = function (docs) {
      return [
        { key: "system", label: "System" },
        { key: "arxiv", label: "arXiv", sub: docsText(docs, "arxiv"), num: true, fmt: score },
        { key: "github", label: "GitHub", sub: docsText(docs, "github"), num: true, fmt: score }
      ];
    };
    var out = [];
    if (R.heldout) {
      var h = R.heldout;
      out.push(block(h, [
        { key: "system", label: "System" },
        { key: "score", label: "Heading TEDS", bar: TEDS_MAX, fmt: score }
      ], [typeof h.docs === "number" ? h.docs.toLocaleString("en-US") + " documents" : null, h.subset]));
      out[0].classList.add("headline");
    }
    if (R.heldoutMinerU) {
      var m = R.heldoutMinerU;
      out.push(block(m, [
        { key: "system", label: "System" },
        { key: "score", label: "Heading TEDS", bar: TEDS_MAX, fmt: score }
      ], [typeof m.docs === "number" ? m.docs.toLocaleString("en-US") + " documents" : null, m.subset]));
    }
    if (R.sample) out.push(block(R.sample, both(R.sample.docs)));
    if (R.full) out.push(block(R.full, both(R.full.docs)));
    if (R.published) out.push(block(R.published, both(R.published.docs)));
    fill("readoc-tables", out);

    // Where others win
    fill("others-list", (D.where_others_win || []).map(function (t) { return el("li", null, t); }));

    // RAG pilot
    var G = D.rag;
    if (G) {
      var outOf = function (v) { return v + " / " + G.of; };
      fill("rag-table",
        el("article", { "class": "result" },
          el("h3", null, G.title),
          G.date ? el("p", { "class": "meta" }, "Measured " + G.date) : null,
          el("p", null, G.about),
          table(G.title, [
            { key: "arm", label: "Chunking" },
            { key: "evidence", label: "Evidence page retrieved", num: true, fmt: outOf },
            { key: "correct", label: "Correct answers", num: true, fmt: outOf }
          ], G.rows || []),
          G.note ? el("p", { "class": "note" }, G.note) : null));
    }

    // Examples
    fill("examples-list", (D.examples || []).map(function (x) {
      var col = function (label, lines, cls) {
        return el("div", { "class": "tree " + (cls || "") },
          el("h4", null, label),
          el("ul", null, (lines || []).map(function (line) {
            var text = String(line), lead = text.match(/^\s*/)[0].length;
            var note = /^\(.*\)$/.test(text.trim());
            // Leading spaces in the data mean nesting: turn them into an indent that wrapped lines keep.
            return el("li", { "class": note ? "annot" : null, style: lead ? "margin-left:" + lead + "ch" : null }, text.trim());
          })));
      };
      var s = x.scores || {};
      return el("article", { "class": "example" },
        el("p", { "class": "example-id" }, el("code", null, x.id)),
        el("h3", null, x.title),
        el("p", null, el("strong", null, "Problem: "), x.problem),
        el("p", { "class": "scores" }, "Heading TEDS on this document: ",
          el("span", null, "Docling ", el("strong", null, String(s.docling))),
          " · ",
          el("span", null, "Section Anything ", el("strong", null, String(s.ours)))),
        el("div", { "class": "trees" },
          col("Answer key", x.key, "tree-key"),
          col("Docling", x.docling),
          col("Section Anything", x.ours, "tree-ours")));
    }));
    fill("examples-note", D.examplesNote);

    // Integrations
    fill("integrations-list", (D.integrations || []).map(function (i) {
      return el("article", { "class": "card" },
        el("div", { "class": "card-head" }, el("h3", null, i.name), el("span", { "class": "badge" }, i.status)),
        el("p", null, i.detail));
    }));

    // Limitations
    fill("limitations-list", (D.limitations || []).map(function (t) { return el("li", null, t); }));

    // Footer
    fill("updated", "Updated " + D.updated);

    // Theme toggle
    var btn = document.getElementById("theme-toggle");
    var label = function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      btn.textContent = next === "dark" ? "Dark mode" : "Light mode";
      btn.setAttribute("aria-label", "Switch to " + next + " mode");
    };
    label();
    if (window.matchMedia) {
      var mq = window.matchMedia("(prefers-color-scheme: dark)");
      if (mq.addEventListener) mq.addEventListener("change", label);
    }
    btn.addEventListener("click", function () {
      var next = currentTheme() === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      stored(next);
      label();
    });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", render);
  else render();
})();
