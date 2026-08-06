/**
 * Document Editor Workspace.
 *
 * The Humanize button calls the EXISTING StealthWriter pipeline:
 *   POST /api/browser/providers/stealthwriter/humanize  -> BrowserWorker ->
 *   BrowserService -> StealthWriterProvider -> StealthWriter website.
 * No browser architecture or backend routes are modified. AI / Cite / Comments /
 * Timeline are UI-only placeholders.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-workspace]");
  if (!root) return;

  var Mock = window.WSMock || {};
  var TOUR_KEY = "docmaxxing_ws_tour_done";
  var HUMANIZE_URL = "/api/browser/providers/stealthwriter/humanize";
  var MAX_WORDS_PER_CALL = 5000;
  var HUMANIZE_COST = Mock.HUMANIZE_COST || 10;
  var MARK_TOKEN = function (i) { return "⟦WS:" + i + "⟧"; };

  var $ = function (sel, ctx) { return (ctx || root).querySelector(sel); };
  var $all = function (sel, ctx) { return Array.prototype.slice.call((ctx || root).querySelectorAll(sel)); };

  var landing = $("[data-ws-landing]");
  var editorView = $("[data-ws-editor]");
  var surface = $("[data-ws-editor-surface]");
  var titleInput = $("[data-ws-doc-title]");
  var savedEl = $("[data-ws-saved]");
  var toast = $("[data-ws-toast]");

  var markCounter = 0;
  var aiHighlights = [];
  var aiIndex = -1;
  var comments = [];
  var lastEditorRange = null;
  var floatbar = $("[data-ws-floatbar]");

  /* ------------------------------------------------------------------ utils */
  function countWords(t) {
    var s = String(t || "").replace(/\u00a0/g, " ").trim();
    return s ? s.split(/\s+/).filter(Boolean).length : 0;
  }
  function showToast(msg) {
    if (!toast) return;
    toast.textContent = msg;
    toast.hidden = false;
    clearTimeout(showToast._t);
    showToast._t = setTimeout(function () { toast.hidden = true; }, 2600);
  }
  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  /* ----------------------------------------------------------------- auth */
  function isAuthed() {
    return !!(window.DM_AUTH && window.DM_AUTH.authenticated);
  }
  function requireAuth(reason) {
    if (isAuthed()) return Promise.resolve();
    if (window.DMAuth) return window.DMAuth.require({ reason: reason });
    return Promise.reject(new Error("AUTH_REQUIRED"));
  }

  /* --------------------------------------------------------------- coins */
  function setCoinDisplays(n) {
    $all("[data-ws-coins], [data-ws-coins-landing]").forEach(function (el) { el.textContent = n; });
    Array.prototype.forEach.call(document.querySelectorAll("[data-coin-balance]"), function (el) {
      el.textContent = n;
    });
  }
  function refreshCoins() {
    fetch("/api/economy/balance", { headers: { Accept: "application/json" } })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        var n = d && typeof d.balance === "number" ? d.balance : 0;
        setCoinDisplays(n);
      })
      .catch(function () {});
  }

  /* ------------------------------------------------------------ word count */
  function refreshCounts() {
    var text = surface ? (surface.innerText || surface.textContent || "") : "";
    var words = countWords(text);
    var chars = text.replace(/\s/g, "").length;
    var w = $("[data-ws-wordcount]"), c = $("[data-ws-charcount]");
    if (w) w.textContent = words.toLocaleString() + " words";
    if (c) c.textContent = chars.toLocaleString() + " chars";
    var rw = $("[data-ws-recent-words]");
    if (rw) rw.textContent = words.toLocaleString() + " words";
  }

  /* ------------------------------------------------------------- autosave */
  var saveTimer = null;
  function markDirty() {
    if (savedEl) savedEl.textContent = "Saving…";
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      if (Mock.saveDraft) {
        Mock.saveDraft({ title: titleInput ? titleInput.value : "Untitled", html: surface ? surface.innerHTML : "" });
      }
      if (savedEl) savedEl.textContent = "All changes saved";
    }, 700);
  }

  /* ----------------------------------------------------------- view switch */
  function openEditor(doc) {
    if (doc && surface) surface.innerHTML = doc.html || "";
    if (doc && titleInput && doc.title) titleInput.value = doc.title;
    if (landing) landing.hidden = true;
    if (editorView) editorView.hidden = false;
    refreshCounts();
    refreshAiHighlights();
    refreshPending();
  }
  function showLanding() {
    if (editorView) editorView.hidden = true;
    if (landing) landing.hidden = false;
    refreshCoins();
  }

  /* =========================== TOOLBAR / FORMATTING ======================= */
  function exec(cmd, value) {
    if (!isAuthed()) {
      requireAuth("Create a free account to edit your document.").catch(function () {});
      return;
    }
    surface.focus();
    try { document.execCommand(cmd, false, value == null ? null : value); } catch (e) {}
    refreshCounts();
    markDirty();
  }

  function handleToolClick(btn) {
    var cmd = btn.getAttribute("data-cmd");
    if (!cmd) return;
    if (cmd === "createLink") {
      var url = window.prompt("Link URL:", "https://");
      if (url) exec("createLink", url);
      return;
    }
    if (cmd === "insertImage") {
      var src = window.prompt("Image URL:", "https://");
      if (src) exec("insertImage", src);
      return;
    }
    if (cmd === "insertTable") {
      exec("insertHTML",
        '<table><tbody>' +
        '<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>' +
        '<tr><td>&nbsp;</td><td>&nbsp;</td><td>&nbsp;</td></tr>' +
        '</tbody></table><p>&nbsp;</p>');
      return;
    }
    if (cmd.indexOf("formatBlock:") === 0) { exec("formatBlock", cmd.split(":")[1]); return; }
    exec(cmd);
  }

  function bindToolbar() {
    $all("[data-cmd]").forEach(function (btn) {
      btn.addEventListener("mousedown", function (e) { e.preventDefault(); });
      btn.addEventListener("click", function () { handleToolClick(btn); });
    });
    var blockSel = $("[data-cmd-block]");
    if (blockSel) {
      blockSel.addEventListener("change", function () {
        exec("formatBlock", blockSel.value);
      });
    }
  }

  function updateToolbarStates() {
    if (!surface) return;
    ["bold", "italic", "underline", "strikeThrough"].forEach(function (c) {
      var btn = $('[data-cmd="' + c + '"]');
      if (!btn) return;
      var on = false;
      try { on = document.queryCommandState(c); } catch (e) {}
      btn.classList.toggle("is-active", on);
    });
  }

  /* =============================== MARKING =============================== */
  function selectionInSurface() {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed) return null;
    var range = sel.getRangeAt(0);
    if (!surface.contains(range.commonAncestorContainer)) return null;
    return range;
  }

  function wrapRange(range, className) {
    var span = document.createElement("span");
    span.className = className;
    span.dataset.markId = "m" + ++markCounter;
    try { range.surroundContents(span); }
    catch (e) { span.appendChild(range.extractContents()); range.insertNode(span); }
    return span;
  }

  // Wrap a range that may span multiple text nodes / inline elements, wrapping
  // only the text pieces so bold/italic/headings around them are preserved.
  function wrapRangeAcrossNodes(range, className, dataset) {
    var rootNode = range.commonAncestorContainer;
    if (rootNode.nodeType === 3) rootNode = rootNode.parentNode;
    var walker = document.createTreeWalker(rootNode, NodeFilter.SHOW_TEXT, null);
    var targets = [];
    while (walker.nextNode()) {
      var n = walker.currentNode;
      if (!range.intersectsNode(n)) continue;
      var s = n === range.startContainer ? range.startOffset : 0;
      var e = n === range.endContainer ? range.endOffset : n.nodeValue.length;
      if (e > s) targets.push({ node: n, s: s, e: e });
    }
    targets.reverse().forEach(function (t) {
      var node = t.node;
      if (t.e < node.nodeValue.length) node.splitText(t.e);
      var piece = t.s > 0 ? node.splitText(t.s) : node;
      var span = document.createElement("span");
      span.className = className;
      if (dataset) Object.keys(dataset).forEach(function (k) { span.dataset[k] = dataset[k]; });
      piece.parentNode.insertBefore(span, piece);
      span.appendChild(piece);
    });
    return targets.length > 0;
  }

  // Locate a character index within the concatenated editor text.
  function locateIndex(map, idx) {
    for (var i = map.length - 1; i >= 0; i--) {
      if (idx >= map[i].start) return { node: map[i].node, offset: idx - map[i].start };
    }
    return map.length ? { node: map[0].node, offset: 0 } : null;
  }

  // Find a DOM range for a (whitespace-flexible) sentence, skipping text that is
  // already inside an AI highlight.
  function findSentenceRange(rootEl, sentence) {
    var needle = String(sentence || "").replace(/\s+/g, " ").trim();
    if (needle.length < 4) return null;
    var walker = document.createTreeWalker(rootEl, NodeFilter.SHOW_TEXT, {
      acceptNode: function (n) {
        return n.parentElement && n.parentElement.closest(".ws-ai-highlight")
          ? NodeFilter.FILTER_REJECT
          : NodeFilter.FILTER_ACCEPT;
      },
    });
    var text = "", map = [];
    while (walker.nextNode()) { map.push({ node: walker.currentNode, start: text.length }); text += walker.currentNode.nodeValue; }

    function tryMatch(str) {
      var esc = str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/\s+/g, "\\s+");
      try { return new RegExp(esc).exec(text); } catch (e) { return null; }
    }
    var m = tryMatch(needle);
    if (!m) m = tryMatch(needle.slice(0, 80));
    if (!m || !m[0]) return null;

    var start = locateIndex(map, m.index);
    var end = locateIndex(map, m.index + m[0].length);
    if (!start || !end) return null;
    var range = document.createRange();
    try {
      range.setStart(start.node, Math.min(start.offset, start.node.nodeValue.length));
      range.setEnd(end.node, Math.min(end.offset, end.node.nodeValue.length));
    } catch (e) { return null; }
    return range;
  }

  function markSelection() {
    var range = selectionInSurface();
    if (!range) { showToast("Select some text in the document first."); return; }
    // Avoid double-wrapping an existing mark.
    var anc = range.commonAncestorContainer;
    var el = anc.nodeType === 1 ? anc : anc.parentElement;
    if (el && el.closest && el.closest(".ws-mark")) { showToast("That text is already marked."); return; }
    wrapRange(range, "ws-mark");
    window.getSelection().removeAllRanges();
    refreshPending();
    markDirty();
  }

  function unwrap(span) {
    var parent = span.parentNode;
    while (span.firstChild) parent.insertBefore(span.firstChild, span);
    parent.removeChild(span);
    parent.normalize();
  }

  // All marks that intersect the current selection (or the mark under the caret).
  function marksIntersectingSelection() {
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0) return [];
    var range = sel.getRangeAt(0);
    if (!surface.contains(range.commonAncestorContainer)) return [];
    if (range.collapsed) {
      var node = range.commonAncestorContainer;
      var el = node.nodeType === 1 ? node : node.parentElement;
      var m = el && el.closest ? el.closest(".ws-mark") : null;
      return m ? [m] : [];
    }
    return $all(".ws-mark", surface).filter(function (mark) {
      try { return range.intersectsNode(mark); } catch (e) { return false; }
    });
  }

  // Remove one mark. If the span is also an AI highlight, keep the violet
  // highlight and only drop the (blue) mark state.
  function unmarkOne(span) {
    if (span.classList.contains("ws-ai-highlight")) {
      span.classList.remove("ws-mark");
      span.removeAttribute("data-mark-id");
    } else {
      unwrap(span);
    }
  }

  function unmarkSelection() {
    var targets = marksIntersectingSelection();
    if (!targets.length) {
      var marks = $all(".ws-mark", surface);
      if (marks.length) targets = [marks[marks.length - 1]];
    }
    if (!targets.length) { showToast("No marked text to remove."); return; }
    targets.forEach(unmarkOne);
    var sel = window.getSelection();
    if (sel) sel.removeAllRanges();
    refreshPending();
    updateFloatbar();
    markDirty();
  }

  // Full reset to the initial state: removes every mark AND every AI highlight,
  // clearing all pending selections, counters and the estimated cost.
  function unmarkEverything() {
    $all(".ws-mark, .ws-ai-highlight", surface).forEach(unwrap);
    aiHighlights = [];
    aiIndex = -1;
    refreshAiHighlights();
    refreshPending();
    updateFloatbar();
    markDirty();
    showToast("Cleared all marks and highlights.");
  }

  function refreshPending() {
    var marks = $all(".ws-mark", surface);
    var words = marks.reduce(function (sum, m) { return sum + countWords(m.textContent); }, 0);
    var calls = marks.length ? buildMarkBatches(marks).length : 0;
    setText("[data-ws-pending-count]", marks.length);
    setText("[data-ws-pending-words]", words.toLocaleString());
    setText("[data-ws-pending-cost]", calls ? (calls * HUMANIZE_COST) + " credits" : "—");
    var run = $("[data-ws-humanize-run]");
    if (run) run.disabled = marks.length === 0;
  }
  function setText(sel, v) { var el = $(sel); if (el) el.textContent = v; }

  /* ===================== AI DETECTION — REAL ZeroGPT ===================== */
  var DETECT_URL = "/api/workspace/detect";

  function refreshAiHighlights(counts) {
    aiHighlights = $all(".ws-ai-highlight", surface);
    if (counts) {
      setText("[data-ws-flagged-parts]", counts.parts);
      setText("[data-ws-flagged-words]", counts.words);
    } else {
      var words = aiHighlights.reduce(function (s, h) { return s + countWords(h.textContent); }, 0);
      setText("[data-ws-flagged-parts]", aiHighlights.length);
      setText("[data-ws-flagged-words]", words);
    }
    setText("[data-ws-hl-index]", aiHighlights.length ? (aiIndex + 1) : 0);
  }

  // Wrap each flagged sentence returned by the detector in a violet highlight.
  function applyDetection(sentences, result) {
    // Clear previous AI highlights (keep marks intact).
    $all(".ws-ai-highlight", surface).forEach(function (s) {
      if (s.classList.contains("ws-mark")) { s.classList.remove("ws-ai-highlight"); s.removeAttribute("data-ai-part"); }
      else unwrap(s);
    });
    var applied = 0;
    (sentences || []).forEach(function (sent) {
      var range = findSentenceRange(surface, sent);
      if (range && wrapRangeAcrossNodes(range, "ws-ai-highlight", { aiPart: "1" })) applied++;
    });
    aiIndex = -1;
    // Counters come from the detector result; highlights are best-effort.
    var parts = result && typeof result.flagged_parts === "number" ? result.flagged_parts : applied;
    var words = result && typeof result.ai_words === "number"
      ? result.ai_words
      : (sentences || []).reduce(function (s, x) { return s + countWords(x); }, 0);
    refreshAiHighlights({ parts: parts, words: words });
    markDirty();
    return applied;
  }

  // Offline / unconfigured fallback so the editor still demos AI highlights.
  function fallbackDetection() {
    if (!$all(".ws-ai-highlight", surface).length) {
      var picked = 0;
      $all("p", surface).forEach(function (p) {
        if (picked >= 2) return;
        var t = p.textContent.trim();
        if (countWords(t) < 12) return;
        var first = t.split(". ")[0];
        var range = findSentenceRange(surface, first.length > 8 ? first : t);
        if (range && wrapRangeAcrossNodes(range, "ws-ai-highlight", { aiPart: "1" })) picked++;
      });
    }
    aiIndex = -1;
    refreshAiHighlights();
  }

  function detectAI() {
    var text = surface.innerText || surface.textContent || "";
    if (countWords(text) < 5) { showToast("Add more text before detecting."); return; }
    var btn = $("[data-ws-detect]");
    var restore = btn ? btn.innerHTML : "";
    if (btn) { btn.disabled = true; btn.textContent = "Detecting…"; }
    fetch(DETECT_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text }),
    })
      .then(function (res) { return res.json().then(function (p) { return { ok: res.ok, status: res.status, p: p }; }); })
      .then(function (r) {
        if (r.p && r.p.error === "AUTH_REQUIRED") { throw new Error("AUTH_REQUIRED"); }
        if (r.status === 402 || (r.p && r.p.error === "INSUFFICIENT_COINS")) {
          throw new Error((r.p && r.p.message) || "INSUFFICIENT_COINS");
        }
        if (!r.ok) throw new Error(r.p && r.p.error ? r.p.error : "detection failed");
        applyDetection(r.p.flagged_sentences || [], r.p);
        refreshCoins();
        showToast("AI detection: " + (r.p.flagged_parts || 0) + " parts · " + (r.p.ai_percentage || 0) + "% AI");
      })
      .catch(function (err) {
        var m = String(err && err.message);
        if (m === "AUTH_REQUIRED" || m === "REGISTER_REQUIRED") {
          requireAuth("Create a free account to run AI detection.")
            .then(function () { detectAI(); })
            .catch(function () {});
          return;
        }
        if (m.indexOf("credit") !== -1 || m.indexOf("coins") !== -1 || m === "INSUFFICIENT_COINS") {
          showToast(m === "INSUFFICIENT_COINS" ? "Not enough credits. Top up to continue." : m);
          return;
        }
        fallbackDetection();
        showToast("Detector unavailable (" + (err && err.message ? err.message : "error") + ") — sample highlights shown.");
      })
      .then(function () { if (btn) { btn.disabled = false; btn.innerHTML = restore; } });
  }

  function gotoHighlight(dir) {
    if (!aiHighlights.length) return;
    if (aiIndex >= 0 && aiHighlights[aiIndex]) aiHighlights[aiIndex].classList.remove("is-current");
    aiIndex = (aiIndex + dir + aiHighlights.length) % aiHighlights.length;
    var el = aiHighlights[aiIndex];
    el.classList.add("is-current");
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    setText("[data-ws-hl-index]", aiIndex + 1);
  }

  function markAllAi() {
    var flagged = $all(".ws-ai-highlight", surface);
    if (!flagged.length) { showToast("Run Detect AI first — nothing is flagged yet."); return; }
    flagged.forEach(function (h) {
      if (!h.classList.contains("ws-mark")) {
        h.classList.add("ws-mark");
        h.dataset.markId = "m" + ++markCounter;
      }
    });
    refreshPending();
    markDirty();
    showToast("Marked all AI-flagged parts.");
  }

  /* =============================== PROGRESS ============================== */
  var creep = null;
  function startProgress() {
    var box = $("[data-ws-progress]"), bar = $("[data-ws-progress-bar]");
    var run = $("[data-ws-humanize-run]");
    if (run) run.disabled = true;
    if (box) box.hidden = false;
    if (bar) bar.style.width = "6%";
    var pct = 6;
    clearInterval(creep);
    creep = setInterval(function () { pct = Math.min(90, pct + 1.5); if (bar) bar.style.width = pct + "%"; }, 700);
  }
  function setProgress(pct) { var bar = $("[data-ws-progress-bar]"); if (bar) bar.style.width = pct + "%"; }
  function stopProgress() {
    clearInterval(creep);
    var box = $("[data-ws-progress]"), bar = $("[data-ws-progress-bar]");
    if (bar) bar.style.width = "100%";
    setTimeout(function () { if (box) box.hidden = true; if (bar) bar.style.width = "0%"; refreshPending(); }, 400);
  }

  /* ===================== HUMANIZE — REAL STEALTHWRITER =================== */
  function humanizeOne(text) {
    return fetch(HUMANIZE_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text, source: "workspace_partial" }),
    }).then(function (res) {
      return res.text().then(function (body) {
        var p = {};
        try { p = body ? JSON.parse(body) : {}; } catch (e) {}
        return { status: res.status, ok: res.ok, payload: p };
      });
    });
  }

  /** Pack marks into batches that fit StealthWriter's per-call word budget. */
  function buildMarkBatches(marks) {
    var batches = [];
    var current = [];
    var words = 0;
    marks.forEach(function (mark) {
      var w = Math.max(1, countWords(mark.textContent));
      if (current.length && words + w > MAX_WORDS_PER_CALL) {
        batches.push(current);
        current = [];
        words = 0;
      }
      current.push(mark);
      words += w;
    });
    if (current.length) batches.push(current);
    return batches;
  }

  /**
   * Join scattered selections into one StealthWriter payload.
   * Markers stay on their own lines so we can split the rewritten text back
   * into the original DOM nodes even when wording/length changes.
   */
  function packMarkBatch(marks) {
    var parts = [
      "IMPORTANT: Keep every marker line like " + MARK_TOKEN(0) + " exactly unchanged on its own line. Only rewrite the prose under each marker. Do not merge sections.",
      "",
    ];
    marks.forEach(function (mark, i) {
      parts.push(MARK_TOKEN(i));
      parts.push(String(mark.textContent || "").replace(/\s+$/g, "").replace(/^\s+/g, ""));
      parts.push("");
    });
    return parts.join("\n");
  }

  function findMarkSplits(text) {
    var source = String(text || "");
    var patterns = [
      /⟦\s*WS\s*:\s*(\d+)\s*⟧/gi,
      /\[\s*WS\s*:\s*(\d+)\s*\]/gi,
      /(?:^|\n)\s*(?:#{1,3}\s*)?(?:\[+\s*)?WS\s*[:_\-]?\s*(\d+)\s*(?:\]+)?\s*(?=\n|$)/gi,
    ];
    for (var p = 0; p < patterns.length; p++) {
      var re = patterns[p];
      var matches = [];
      var m;
      re.lastIndex = 0;
      while ((m = re.exec(source)) !== null) {
        matches.push({ index: m.index, id: parseInt(m[1], 10), len: m[0].length });
      }
      if (matches.length) return matches;
    }
    return [];
  }

  /** Split a batched StealthWriter response back into per-mark strings. */
  function unpackMarkBatch(output, expectedCount) {
    var text = String(output || "");
    var matches = findMarkSplits(text);
    if (!matches.length) return null;

    matches.sort(function (a, b) { return a.index - b.index; });
    var chunks = matches.map(function (item, i) {
      var start = item.index + item.len;
      var end = i + 1 < matches.length ? matches[i + 1].index : text.length;
      return {
        id: item.id,
        text: text.slice(start, end).replace(/^\s+/, "").replace(/\s+$/, ""),
      };
    });

    var byId = new Array(expectedCount);
    chunks.forEach(function (chunk) {
      if (chunk.id >= 0 && chunk.id < expectedCount && byId[chunk.id] == null) {
        byId[chunk.id] = chunk.text;
      }
    });
    var filled = byId.filter(function (x) { return typeof x === "string"; }).length;
    if (filled === expectedCount) return byId;

    // StealthWriter sometimes renumbers / drops ids — fall back to document order.
    if (chunks.length === expectedCount) {
      return chunks.map(function (c) { return c.text; });
    }
    return null;
  }

  function applyHumanizedPart(mark, original, out) {
    var rewritten = String(out == null ? "" : out);
    mark.textContent = rewritten;
    mark.className =
      rewritten.trim() && rewritten.trim() !== String(original || "").trim()
        ? "ws-humanized"
        : "ws-humanized-unchanged";
    mark.removeAttribute("data-mark-id");
    return mark.className === "ws-humanized";
  }

  function runHumanize() {
    var marks = $all(".ws-mark", surface);
    if (!marks.length) { showToast("Mark some text first."); return; }

    var batches = buildMarkBatches(marks);
    startProgress();
    var doneMarks = 0;
    var changed = 0;
    var failed = 0;
    var loginRequired = false;
    var noChangeMsg = "";
    var authRequired = false;
    var insufficient = false;
    var insufficientMsg = "";
    var splitFailed = false;

    // One StealthWriter call per word-budget batch (not per selection).
    function nextBatch(i) {
      if (i >= batches.length) return Promise.resolve();
      var batch = batches[i];
      var originals = batch.map(function (m) { return m.textContent; });
      var packed = packMarkBatch(batch);

      return humanizeOne(packed).then(function (r) {
        if (r.payload && r.payload.error === "AUTH_REQUIRED") {
          authRequired = true;
          throw new Error("AUTH_REQUIRED");
        }
        if (r.status === 402 || (r.payload && r.payload.error === "INSUFFICIENT_COINS")) {
          insufficient = true;
          insufficientMsg = (r.payload && r.payload.message) || "Not enough credits.";
          throw new Error("INSUFFICIENT_COINS");
        }
        if (r.status === 401 || (r.payload && r.payload.error === "LOGIN_REQUIRED")) {
          loginRequired = true;
          throw new Error("LOGIN_REQUIRED");
        }
        if (r.status === 409 && r.payload && r.payload.error === "NO_CHANGE") {
          noChangeMsg = r.payload.message || "StealthWriter returned no change.";
          throw new Error("NO_CHANGE");
        }
        if (r.ok && r.payload && r.payload.success) {
          var parts = unpackMarkBatch(r.payload.humanized_text || "", batch.length);
          if (!parts) {
            splitFailed = true;
            batch.forEach(function (mark) { mark.classList.add("ws-humanized-failed"); });
            failed += batch.length;
          } else {
            batch.forEach(function (mark, j) {
              if (applyHumanizedPart(mark, originals[j], parts[j])) changed++;
            });
          }
        } else {
          batch.forEach(function (mark) { mark.classList.add("ws-humanized-failed"); });
          failed += batch.length;
        }
      }).catch(function (err) {
        var m = String(err && err.message);
        if (m === "LOGIN_REQUIRED" || m === "NO_CHANGE" || m === "AUTH_REQUIRED" || m === "INSUFFICIENT_COINS") {
          throw err;
        }
        batch.forEach(function (mark) { mark.classList.add("ws-humanized-failed"); });
        failed += batch.length;
      }).then(function () {
        doneMarks += batch.length;
        setProgress(Math.min(95, Math.round((doneMarks / marks.length) * 90) + 6));
        return nextBatch(i + 1);
      });
    }

    nextBatch(0).then(function () {
      stopProgress();
      markDirty();
      refreshCounts();
      refreshCoins();
      var msg =
        "Humanized " + changed + " of " + marks.length +
        (failed ? " · " + failed + " failed" : "") +
        (batches.length > 1 ? " · " + batches.length + " StealthWriter calls" : " · 1 StealthWriter call");
      if (splitFailed) {
        msg += " · could not split one batch (markers lost) — retry that selection";
      }
      showToast(msg);
    }).catch(function (err) {
      stopProgress();
      refreshCoins();
      var m = String(err && err.message);
      if (authRequired || m === "AUTH_REQUIRED" || m === "REGISTER_REQUIRED") {
        requireAuth("Create a free account to humanize your document.")
          .then(function () { runHumanize(); })
          .catch(function () {});
      } else if (insufficient || m === "INSUFFICIENT_COINS") {
        showToast(insufficientMsg || "Not enough credits. Top up to continue.");
      } else if (loginRequired) {
        showToast("StealthWriter login required — open the login once, then retry.");
      } else if (m === "NO_CHANGE") {
        showToast(noChangeMsg || "StealthWriter returned no change (daily limit may be reached).");
      } else {
        showToast("Humanize failed: " + (err && err.message ? err.message : "unknown error"));
      }
    });
  }

  /* ============================== AI TAB (UI only) ====================== */
  function bindAiTab() {
    $all("[data-ws-ai-action]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        showToast(btn.getAttribute("data-ws-ai-action") + " — Coming Soon");
      });
    });
    var apply = $("[data-ws-ai-apply]");
    if (apply) apply.addEventListener("click", function () { showToast("AI assistant — Coming Soon"); });
  }

  /* ====================== CITE TAB — CitationService ==================== */
  var citeResults = [];

  function mockCite(query) {
    // Normalized shape identical to the backend (frontend stays provider-agnostic).
    return [
      {
        title: "Attention Is All You Need",
        authors: ["Vaswani, A.", "Shazeer, N.", "Parmar, N."],
        year: "2017",
        journal: "Advances in Neural Information Processing Systems",
        doi: "10.48550/arXiv.1706.03762",
        url: "https://doi.org/10.48550/arXiv.1706.03762",
        intext: "(Vaswani et al., 2017)",
        label: "Vaswani et al., 2017",
        reference: "Vaswani, A., Shazeer, N. & Parmar, N. (2017). Attention Is All You Need. Advances in Neural Information Processing Systems. https://doi.org/10.48550/arXiv.1706.03762",
      },
    ].filter(function (r) { return !query || r.title.toLowerCase().indexOf(String(query).toLowerCase()) >= 0 || true; });
  }

  function chargeCitationUse(action, meta) {
    return fetch("/api/workspace/citations/use", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        action: action || "insert",
        doi: (meta && meta.doi) || "",
      }),
    }).then(function (res) {
      return res.json().then(function (p) { return { ok: res.ok, status: res.status, p: p }; });
    });
  }

  function renderCiteResults(results, isMock) {
    var out = $("[data-ws-cite-results]");
    citeResults = results || [];
    if (!out) return;
    if (!citeResults.length) { out.innerHTML = '<p class="ws-empty-note">No results — try another query.</p>'; return; }
    out.innerHTML = citeResults.map(function (r, i) {
      var authors = (r.authors || []).join(", ");
      var meta = [authors, r.year, r.journal].filter(Boolean).map(escapeHtml).join(" · ");
      return '<div class="ws-cite-item">' +
        "<h5>" + escapeHtml(r.title) + "</h5>" +
        "<p>" + meta + "</p>" +
        '<p class="ws-cite-ref">' + escapeHtml(r.reference || "") + "</p>" +
        '<div class="ws-cite-actions">' +
        '<button type="button" class="ws-action ws-action-outline" data-ws-cite-insert="' + i + '">↥ Insert (' + escapeHtml(r.label || "") + ")</button>" +
        '<button type="button" class="ws-action ws-action-ghost" data-ws-cite-ref="' + i + '">≣ Add reference</button>' +
        "</div></div>";
    }).join("") + (isMock ? '<p class="ws-empty-note">Showing sample results (search backend offline).</p>' : "");
    $all("[data-ws-cite-insert]", out).forEach(function (b) {
      b.addEventListener("click", function () {
        var r = citeResults[parseInt(b.getAttribute("data-ws-cite-insert"), 10)];
        if (!r) return;
        chargeCitationUse("insert", r).then(function (resp) {
          if (resp.p && (resp.p.error === "AUTH_REQUIRED" || resp.p.error === "REGISTER_REQUIRED")) {
            requireAuth("Create a free account to insert citations.")
              .then(function () { b.click(); })
              .catch(function () {});
            return;
          }
          if (resp.status === 402 || (resp.p && resp.p.error === "INSUFFICIENT_COINS")) {
            showToast((resp.p && resp.p.message) || "Not enough credits. This requires 2 credits.");
            return;
          }
          if (!resp.ok) {
            showToast((resp.p && resp.p.message) || (resp.p && resp.p.error) || "Could not charge citation.");
            return;
          }
          insertAtEditor(" " + (r.intext || "(" + (r.label || "") + ")") + " ", true);
          refreshCoins();
          showToast("Citation inserted (−2 credits).");
        }).catch(function () {
          showToast("Could not insert citation.");
        });
      });
    });
    $all("[data-ws-cite-ref]", out).forEach(function (b) {
      b.addEventListener("click", function () {
        var r = citeResults[parseInt(b.getAttribute("data-ws-cite-ref"), 10)];
        if (!r) return;
        chargeCitationUse("reference", r).then(function (resp) {
          if (resp.p && (resp.p.error === "AUTH_REQUIRED" || resp.p.error === "REGISTER_REQUIRED")) {
            requireAuth("Create a free account to add references.")
              .then(function () { b.click(); })
              .catch(function () {});
            return;
          }
          if (resp.status === 402 || (resp.p && resp.p.error === "INSUFFICIENT_COINS")) {
            showToast((resp.p && resp.p.message) || "Not enough credits. This requires 2 credits.");
            return;
          }
          if (!resp.ok) {
            showToast((resp.p && resp.p.message) || (resp.p && resp.p.error) || "Could not charge citation.");
            return;
          }
          addReference(r.reference || "");
          refreshCoins();
        }).catch(function () {
          showToast("Could not add reference.");
        });
      });
    });
  }

  function doCiteSearch() {
    var q = $("[data-ws-cite-query]"), out = $("[data-ws-cite-results]"), styleSel = $("[data-ws-cite-style]");
    var query = q ? q.value.trim() : "";
    if (!query) { showToast("Enter a search query first."); return; }
    var style = styleSel ? styleSel.value : "APA 7";
    if (out) out.innerHTML = '<p class="ws-empty-note">Searching…</p>';
    fetch("/api/workspace/citations/search", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query, style: style, limit: 6 }),
    })
      .then(function (res) { return res.json().then(function (p) { return { ok: res.ok, status: res.status, p: p }; }); })
      .then(function (r) {
        if (r.p && (r.p.error === "AUTH_REQUIRED" || r.p.error === "REGISTER_REQUIRED")) {
          if (out) out.innerHTML = '<p class="ws-empty-note">Create a free account to search citations.</p>';
          requireAuth("Create a free account to search citations.")
            .then(function () { doCiteSearch(); })
            .catch(function () {});
          return;
        }
        if (!r.ok) {
          if (out) out.innerHTML = '<p class="ws-empty-note">Search failed — try again.</p>';
          showToast((r.p && r.p.error) || "Citation search failed.");
          return;
        }
        if (r.ok && r.p.results && r.p.results.length) renderCiteResults(r.p.results, false);
        else renderCiteResults(mockCite(query), true);
      })
      .catch(function () { renderCiteResults(mockCite(query), true); });
  }

  // Called from the floating toolbar @Cite button: prefill + search selection.
  function citeSearchFromSelection() {
    var sel = window.getSelection();
    var text = sel && !sel.isCollapsed && surface.contains(sel.anchorNode) ? sel.toString().trim() : "";
    var q = $("[data-ws-cite-query]");
    if (text && q) { q.value = text.slice(0, 200); doCiteSearch(); }
  }

  function insertAtEditor(text, asText) {
    surface.focus();
    var sel = window.getSelection();
    if (lastEditorRange) {
      // Insert at the END of the previous selection instead of replacing it,
      // so the in-text citation is appended right after the marked passage.
      var r = lastEditorRange.cloneRange();
      r.collapse(false);
      sel.removeAllRanges();
      sel.addRange(r);
    }
    try { document.execCommand(asText ? "insertText" : "insertHTML", false, text); } catch (e) {}
    // Remember the new caret so repeated inserts chain instead of overwriting.
    if (sel.rangeCount) lastEditorRange = sel.getRangeAt(0).cloneRange();
    refreshCounts();
    markDirty();
  }

  function addReference(refText) {
    if (!refText) return;
    var refs = surface.querySelector("[data-ws-refs]");
    if (!refs) {
      var h = document.createElement("h2");
      h.textContent = "References";
      refs = document.createElement("div");
      refs.setAttribute("data-ws-refs", "");
      surface.appendChild(h);
      surface.appendChild(refs);
    }
    var p = document.createElement("p");
    p.className = "ws-reference";
    p.textContent = refText;
    refs.appendChild(p);
    refreshCounts();
    markDirty();
    showToast("Reference added to the document.");
  }

  function bindCiteTab() {
    var go = $("[data-ws-cite-search]"), q = $("[data-ws-cite-query]"), styleSel = $("[data-ws-cite-style]");
    if (go) go.addEventListener("click", doCiteSearch);
    if (q) q.addEventListener("keydown", function (e) { if (e.key === "Enter") doCiteSearch(); });
    if (styleSel) styleSel.addEventListener("change", function () { if (($("[data-ws-cite-query]") || {}).value) doCiteSearch(); });
    var scan = $("[data-ws-cite-scan]");
    if (scan) scan.addEventListener("click", function () {
      var r = Mock.scanCitations ? Mock.scanCitations() : { found: 0, issues: 0, style: "APA 7" };
      showToast("Found " + r.found + " citations · " + r.issues + " issue(s) · " + r.style);
    });
  }

  /* =========================== COMMENTS TAB (UI) ======================== */
  function bindComments() {
    var add = $("[data-ws-comment-add]"), input = $("[data-ws-comment-input]"), list = $("[data-ws-comments-list]");
    function render() {
      if (!list) return;
      if (!comments.length) { list.innerHTML = '<p class="ws-empty-note">No comments yet.</p>'; return; }
      list.innerHTML = comments.map(function (c) {
        return '<div class="ws-comment-item">' +
          (c.quote ? '<div class="ws-comment-quote">' + escapeHtml(c.quote) + "</div>" : "") +
          "<div>" + escapeHtml(c.text) + "</div>" +
          "<time>" + c.time + "</time></div>";
      }).join("");
    }
    if (add) add.addEventListener("click", function () {
      var text = input ? input.value.trim() : "";
      if (!text) { showToast("Write a comment first."); return; }
      var box = $("[data-ws-comment-quote]");
      var quote = box && !box.hidden ? (box.getAttribute("data-quote") || "") : "";
      comments.unshift({ text: text, quote: quote, time: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }) });
      if (input) input.value = "";
      var qb = $("[data-ws-comment-quote]");
      if (qb) { qb.hidden = true; qb.removeAttribute("data-quote"); }
      render();
    });
    render();
  }

  // Show the current selection as a quote above the comment box.
  function updateCommentQuote() {
    var box = $("[data-ws-comment-quote]");
    if (!box) return;
    var sel = window.getSelection();
    var text = sel && !sel.isCollapsed && surface.contains(sel.anchorNode) && surface.contains(sel.focusNode)
      ? sel.toString().trim()
      : "";
    if (text) {
      var trimmed = text.slice(0, 180);
      box.hidden = false;
      box.textContent = '"' + trimmed + (text.length > 180 ? "…" : "") + '"';
      box.setAttribute("data-quote", trimmed);
    } else if (!box.dataset.pinned) {
      box.hidden = true;
      box.removeAttribute("data-quote");
    }
  }

  /* ==================== FLOATING TOOLBAR + SELECTION SYNC ================ */
  function hideFloatbar() {
    if (!floatbar || floatbar.hidden) return;
    floatbar.classList.remove("is-visible");
    setTimeout(function () {
      if (floatbar && !floatbar.classList.contains("is-visible")) floatbar.hidden = true;
    }, 160);
  }

  function updateFloatbar() {
    if (!floatbar) return;
    var sel = window.getSelection();
    if (!sel || sel.rangeCount === 0 || sel.isCollapsed ||
        !surface.contains(sel.anchorNode) || !surface.contains(sel.focusNode)) {
      hideFloatbar();
      return;
    }
    var rect = sel.getRangeAt(0).getBoundingClientRect();
    if (!rect || (rect.width === 0 && rect.height === 0)) { hideFloatbar(); return; }
    floatbar.hidden = false;
    var fw = floatbar.offsetWidth, fh = floatbar.offsetHeight;
    var left = rect.left + rect.width / 2 - fw / 2;
    var top = rect.top - fh - 8;
    if (top < 8) top = rect.bottom + 8;
    left = Math.max(8, Math.min(left, window.innerWidth - fw - 8));
    floatbar.style.left = left + "px";
    floatbar.style.top = top + "px";
    requestAnimationFrame(function () { floatbar.classList.add("is-visible"); });
    ["bold", "italic", "underline"].forEach(function (c) {
      var b = $('[data-ws-fb="' + c + '"]', floatbar);
      if (!b) return;
      var on = false; try { on = document.queryCommandState(c); } catch (e) {}
      b.classList.toggle("is-active", on);
    });
  }

  function bindFloatbar() {
    if (!floatbar) return;
    floatbar.addEventListener("mousedown", function (e) { e.preventDefault(); });
    $all("[data-ws-fb]", floatbar).forEach(function (btn) {
      btn.addEventListener("click", function () {
        var act = btn.getAttribute("data-ws-fb");
        if (act === "ai") { activateTab("ai"); }
        else if (act === "humanize") { activateTab("humanize"); }
        else if (act === "cite") { activateTab("cite"); citeSearchFromSelection(); }
        else if (act === "bold") exec("bold");
        else if (act === "italic") exec("italic");
        else if (act === "underline") exec("underline");
        else if (act === "link") { var u = window.prompt("Link URL:", "https://"); if (u) exec("createLink", u); }
        updateFloatbar();
      });
    });
  }

  // Keep the editor caret so citations/references insert in the right place.
  function rememberEditorRange() {
    var sel = window.getSelection();
    if (sel && sel.rangeCount && surface.contains(sel.anchorNode)) {
      lastEditorRange = sel.getRangeAt(0).cloneRange();
    }
  }

  var selRaf = null;
  function scheduleSelectionSync() {
    if (selRaf) return;
    selRaf = requestAnimationFrame(function () {
      selRaf = null;
      rememberEditorRange();
      updateToolbarStates();
      updateFloatbar();
      updateCommentQuote();
    });
  }

  /* =============================== TABS ================================= */
  function activateTab(name) {
    $all("[data-ws-tab]").forEach(function (t) { t.classList.toggle("is-active", t.getAttribute("data-ws-tab") === name); });
    $all("[data-ws-panel]").forEach(function (p) { p.classList.toggle("is-active", p.getAttribute("data-ws-panel") === name); });
  }
  function bindTabs() {
    $all("[data-ws-tab]").forEach(function (t) {
      t.addEventListener("click", function () { activateTab(t.getAttribute("data-ws-tab")); });
    });
  }

  /* ============================ IMPORT / EXPORT ========================= */
  function loadMammoth() {
    if (window.mammoth) return Promise.resolve(window.mammoth);
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = "https://cdn.jsdelivr.net/npm/mammoth@1.9.0/mammoth.browser.min.js";
      s.onload = function () { resolve(window.mammoth); };
      s.onerror = function () { reject(new Error("could not load importer")); };
      document.head.appendChild(s);
    });
  }

  function importDocx(file) {
    if (!file) return;
    if (!/\.docx$/i.test(file.name)) { showToast("Please choose a .docx file."); return; }
    showToast("Importing " + file.name + "…");
    loadMammoth().then(function (mammoth) {
      return file.arrayBuffer().then(function (buf) {
        return mammoth.convertToHtml({ arrayBuffer: buf });
      });
    }).then(function (result) {
      var html = result.value || "<p></p>";
      // Strip Word/mammoth inline fonts so Inter + theme typography win.
      html = html
        .replace(/\sstyle="[^"]*"/gi, function (m) {
          return m
            .replace(/font-family:[^;"]+;?/gi, "")
            .replace(/font-size:[^;"]+;?/gi, "")
            .replace(/color:[^;"]+;?/gi, "")
            .replace(/background(-color)?:[^;"]+;?/gi, "")
            .replace(/line-height:[^;"]+;?/gi, "");
        })
        .replace(/\sstyle="\s*"/gi, "");
      openEditor({ title: file.name.replace(/\.docx$/i, ""), html: html });
      showToast("Imported.");
    }).catch(function () {
      showToast("Import needs an internet connection (Word parser).");
    });
  }

  function exportDoc() {
    var title = (titleInput ? titleInput.value : "document") || "document";
    var clone = surface.cloneNode(true);
    // Strip editor-only highlights for a clean submission file.
    $all(".ws-mark, .ws-ai-highlight, .ws-humanized, .ws-humanized-unchanged, .ws-humanized-failed", clone).forEach(function (el) {
      el.removeAttribute("class");
      el.removeAttribute("data-mark-id");
      el.removeAttribute("data-ai-part");
    });
    var html =
      '<!DOCTYPE html><html xmlns:o="urn:schemas-microsoft-com:office:office" ' +
      'xmlns:w="urn:schemas-microsoft-com:office:word" xmlns="http://www.w3.org/TR/REC-html40">' +
      '<head><meta charset="utf-8"><title>' + escapeHtml(title) + "</title></head><body>" +
      clone.innerHTML + "</body></html>";
    var blob = new Blob(["\ufeff", html], { type: "application/msword" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = title.replace(/[^\w\-]+/g, "_") + ".doc";
    a.click();
    URL.revokeObjectURL(a.href);
    showToast("Exported " + a.download);
  }

  /* =============================== TOUR ================================= */
  var steps = window.WSTourSteps || [];
  var tourEl = $("[data-ws-tour]");
  var tourIdx = 0;

  function positionTour(step) {
    var spot = $("[data-ws-tour-spot]");
    var card = $("[data-ws-tour-card]");
    if (!spot || !card) return;
    var target = step.target ? document.querySelector(step.target) : null;
    card.classList.toggle("is-warn", !!step.warn);

    if (!target || step.placement === "center") {
      spot.hidden = true;
      card.style.top = "50%";
      card.style.left = "50%";
      card.style.transform = "translate(-50%, -50%)";
      return;
    }
    card.style.transform = "none";
    var r = target.getBoundingClientRect();
    var pad = 6;
    spot.hidden = false;
    spot.style.top = (r.top - pad) + "px";
    spot.style.left = (r.left - pad) + "px";
    spot.style.width = (r.width + pad * 2) + "px";
    spot.style.height = (r.height + pad * 2) + "px";

    var cw = card.offsetWidth || 340, ch = card.offsetHeight || 200;
    var top, left;
    var place = step.placement || "bottom";
    if (place === "left") { left = r.left - cw - 16; top = r.top; }
    else if (place === "right") { left = r.right + 16; top = r.top; }
    else if (place === "bottom") { left = r.left; top = r.bottom + 14; }
    else { left = r.left; top = r.top - ch - 14; }
    // clamp to viewport
    left = Math.max(12, Math.min(left, window.innerWidth - cw - 12));
    top = Math.max(12, Math.min(top, window.innerHeight - ch - 12));
    card.style.left = left + "px";
    card.style.top = top + "px";
  }

  function renderTour() {
    var step = steps[tourIdx];
    if (!step) return endTour(true);
    if (step.tab) activateTab(step.tab);
    setText("[data-ws-tour-title]", step.title);
    setText("[data-ws-tour-body]", step.body);
    setText("[data-ws-tour-progress]", (tourIdx + 1) + " / " + steps.length);
    var back = $("[data-ws-tour-back]"), next = $("[data-ws-tour-next]");
    if (back) back.style.visibility = tourIdx === 0 ? "hidden" : "visible";
    if (next) next.textContent = step.last ? "Done" : "Next →";
    // let the tab switch paint before measuring
    requestAnimationFrame(function () { positionTour(step); });
  }

  function startTour() {
    if (!tourEl || !steps.length) return;
    if (editorView && editorView.hidden) openEditorSilently();
    tourIdx = 0;
    tourEl.hidden = false;
    renderTour();
  }
  function openEditorSilently() {
    if (landing) landing.hidden = true;
    if (editorView) editorView.hidden = false;
  }
  function endTour(complete) {
    if (tourEl) tourEl.hidden = true;
    if (complete) { try { localStorage.setItem(TOUR_KEY, "1"); } catch (e) {} }
  }

  function bindTour() {
    if (!tourEl) return;
    var next = $("[data-ws-tour-next]"), back = $("[data-ws-tour-back]"), close = $("[data-ws-tour-close]");
    if (next) next.addEventListener("click", function () {
      if (steps[tourIdx] && steps[tourIdx].last) return endTour(true);
      tourIdx = Math.min(steps.length - 1, tourIdx + 1); renderTour();
    });
    if (back) back.addEventListener("click", function () { tourIdx = Math.max(0, tourIdx - 1); renderTour(); });
    if (close) close.addEventListener("click", function () { endTour(true); });
    var bd = $("[data-ws-tour-backdrop]");
    if (bd) bd.addEventListener("click", function () { endTour(true); });
    window.addEventListener("resize", function () { if (tourEl && !tourEl.hidden) positionTour(steps[tourIdx]); });
    window.addEventListener("keydown", function (e) {
      if (tourEl.hidden) return;
      if (e.key === "Escape") endTour(true);
      if (e.key === "ArrowRight" && next) next.click();
      if (e.key === "ArrowLeft" && back) back.click();
    });
  }

  /* =============================== BINDINGS ============================= */
  function bind() {
    bindToolbar();
    bindTabs();
    bindAiTab();
    bindCiteTab();
    bindComments();
    bindFloatbar();
    bindTour();

    if (surface) {
      // Anonymous users can open/preview a document, but the first real edit
      // opens the registration wall (no navigation — the doc stays put).
      surface.addEventListener("beforeinput", function (e) {
        if (!isAuthed()) {
          e.preventDefault();
          requireAuth("Create a free account to edit your document.")
            .then(function () { surface.focus(); })
            .catch(function () {});
        }
      });
      surface.addEventListener("input", function () { refreshCounts(); markDirty(); refreshPending(); refreshAiHighlights(); });
    }
    if (titleInput) titleInput.addEventListener("input", function () {
      if (!isAuthed()) { requireAuth("Create a free account to edit your document.").catch(function () {}); return; }
      markDirty();
    });

    // Keep editor, floating toolbar and sidebar in sync with the selection.
    document.addEventListener("selectionchange", scheduleSelectionSync);
    if (surface) {
      surface.addEventListener("mouseup", scheduleSelectionSync);
      surface.addEventListener("keyup", scheduleSelectionSync);
    }
    var scroller = $(".ws-doc-scroll");
    if (scroller) scroller.addEventListener("scroll", function () { if (floatbar && !floatbar.hidden) updateFloatbar(); });
    window.addEventListener("resize", function () { if (floatbar && !floatbar.hidden) updateFloatbar(); });

    // Humanize actions
    on("[data-ws-mark]", markSelection);
    on("[data-ws-unmark]", unmarkSelection);
    on("[data-ws-unmark-all]", unmarkEverything);
    on("[data-ws-detect]", detectAI);
    on("[data-ws-mark-all-ai]", markAllAi);
    on("[data-ws-humanize-run]", runHumanize);
    on("[data-ws-hl-prev]", function () { gotoHighlight(-1); });
    on("[data-ws-hl-next]", function () { gotoHighlight(1); });
    var toggle = $("[data-ws-hl-toggle]");
    if (toggle) toggle.addEventListener("click", function () {
      toggle.classList.toggle("is-on");
      surface.classList.toggle("ws-hl-hidden", !toggle.classList.contains("is-on"));
    });

    // Top bar placeholders + real actions
    on("[data-ws-export]", exportDoc);
    on("[data-ws-back]", showLanding);
    on("[data-ws-history-btn]", function () { showToast("Version history — coming soon."); });
    on("[data-ws-share]", function () { showToast("Live collaboration — coming soon."); });
    on("[data-ws-topup]", function () { window.location.href = "/pricing"; });

    // Landing
    on("[data-ws-new-blank]", function () { openEditor({ title: "Untitled document", html: "<h1>Untitled document</h1><p></p>" }); });
    on("[data-ws-open-sample]", function () { openEditor({ title: Mock.SAMPLE_TITLE || "Sample document", html: Mock.SAMPLE_HTML || "<p></p>" }); });
    on("[data-ws-open-turnitin]", function () { showToast("Turnitin reports — coming soon."); });

    var importInput = $("[data-ws-import-input]");
    if (importInput) importInput.addEventListener("change", function () { importDocx(importInput.files && importInput.files[0]); });
    var dz = $("[data-ws-dropzone]");
    if (dz) {
      ["dragover", "dragenter"].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.add("is-drag"); }); });
      ["dragleave", "drop"].forEach(function (ev) { dz.addEventListener(ev, function (e) { e.preventDefault(); dz.classList.remove("is-drag"); }); });
      dz.addEventListener("drop", function (e) { if (e.dataTransfer && e.dataTransfer.files) importDocx(e.dataTransfer.files[0]); });
    }
  }
  function on(sel, fn) { var el = $(sel); if (el) el.addEventListener("click", fn); }

  /* =============================== INIT ================================= */
  function init() {
    bind();
    refreshCoins();
    var draft = Mock.loadDraft ? Mock.loadDraft() : null;
    if (draft && draft.html) {
      openEditor(draft);
    } else if (!localStorage.getItem(TOUR_KEY)) {
      // First-time visitor: open the sample doc and run the tour.
      openEditor({ title: Mock.SAMPLE_TITLE || "Welcome tour — sample document", html: Mock.SAMPLE_HTML || "<p></p>" });
    } else {
      showLanding();
    }
  }

  init();
})();
