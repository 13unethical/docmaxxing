(function () {
  "use strict";

  var root = document.querySelector("[data-assignment-page]");
  if (!root) return;

  var STORAGE_KEY = "asgWizardV1";

  var PIPELINE = [
    { key: "requirement", match: ["upload"] },
    { key: "price", match: ["price"] },
    { key: "research", match: ["research"] },
    { key: "blueprint", match: ["blueprint"] },
    { key: "writer", match: ["writer"] },
    { key: "humanizer", match: ["humanizer"] },
    { key: "review", match: ["review"] },
    { key: "detection", match: ["detection"] },
    { key: "delivery", match: ["delivery"] },
  ];

  var STAGE_ORDER = [
    "upload",
    "price",
    "research",
    "blueprint",
    "writer",
    "citations",
    "humanizer",
    "format",
    "review",
    "revision",
    "validation",
    "detection",
    "delivery",
  ];

  var STAGE_PROGRESS = {
    upload: 8,
    price: 8,
    requirement: 8,
    research: 16,
    blueprint: 24,
    writer: 40,
    citations: 48,
    humanizer: 60,
    format: 70,
    review: 78,
    revision: 84,
    validation: 90,
    detection: 96,
    delivery: 100,
  };

  var MAX_DETECTION_ATTEMPTS = 1;

  var FILE_KIND_LABELS = {
    brief: "Requirements",
    extra: "Additional file",
    file: "File",
  };

  var state = {
    stage: "upload",
    projectId: null,
    requirement: null,
    price: null,
    paymentConfirmed: false,
    research: null,
    blueprint: null,
    writerSession: null,
    draft: null,
    review: null,
    humanizerSession: null,
    detectionSession: null,
    detectionReport: null,
    deliveryPackage: null,
    humanizerPass: 1,
    reviewPass: 1,
    detectionAttempt: 1,
    reviewMeta: null,
    citationPack: null,
    formattedDocument: null,
    validationReport: null,
    /** Accumulated composer attachments (chat +). */
    pendingFiles: [],
    extraFiles: [],
    busy: false,
    autoRunning: false,
    retryAction: null,
    forceContinue: false,
    productionPeakPct: 0,
    composerMode: "brief", /* brief | revision */
  };

  function $(sel) { return root.querySelector(sel); }

  function isStaleProjectError(err) {
    var msg = String((err && err.message) || "").trim().toLowerCase();
    // Only treat an explicit missing-project response as an expired session.
    // Generic HTTP 404 (e.g. a missing stage route before server restart) must NOT wipe progress.
    return msg === "project not found" || msg.indexOf("project not found:") === 0;
  }

  function show(el, on) {
    if (!el) return;
    el.hidden = !on;
  }

  function set(sel, value) {
    var el = $(sel);
    if (!el) return;
    el.textContent = value === undefined || value === null || value === "" ? "—" : String(value);
  }

  function html(sel, value) {
    var el = $(sel);
    if (!el) return;
    el.innerHTML = value || "";
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function na(v) {
    return v === undefined || v === null || v === "" ? "—" : String(v);
  }

  function fmtMoney(v) {
    return v == null ? "—" : "$" + Number(v).toFixed(2);
  }

  function fmtPct(v) {
    return v == null ? "—" : Number(v).toFixed(1) + "%";
  }

  function pid() {
    return state.projectId;
  }

  function projectUrl(path) {
    return "/api/assignment/projects/" + encodeURIComponent(pid()) + path;
  }

  function clearSavedProject() {
    state.projectId = null;
    localStorage.removeItem(STORAGE_KEY);
  }

  function resetProjectState() {
    clearSavedProject();
    state.requirement = null;
    state.price = null;
    state.pricing = null;
    state.paymentConfirmed = false;
    state.research = null;
    state.blueprint = null;
    state.writerSession = null;
    state.draft = null;
    state.review = null;
    state.humanizerSession = null;
    state.detectionSession = null;
    state.detectionReport = null;
    state.deliveryPackage = null;
    state.citationPack = null;
    state.formattedDocument = null;
    state.validationReport = null;
    state.extraFiles = [];
    state.pendingFiles = [];
    state.composerMode = "brief";
    state.humanizerPass = 1;
    state.reviewPass = 1;
    state.detectionAttempt = 1;
    state.reviewMeta = null;
    state.autoRunning = false;
    state.retryAction = null;
    state.forceContinue = false;
    state.stage = "upload";
    state.productionPeakPct = 0;
  }

  function staleSessionMessage() {
    return "Previous session expired. Attach your files and send again.";
  }

  function responseMeansProjectMissing(res, payload) {
    if (res.status !== 404 || !/\/api\/assignment\/projects\//.test(res.url || "")) {
      return false;
    }
    return String((payload && payload.error) || "").trim().toLowerCase() === "project not found";
  }

  var LLM_REQUEST_TIMEOUT_MS = 600000;

  function isLongRunningStageUrl(url) {
    return /\/(research|blueprint|writer|citations|humanizer|format|validate-requirements|review|revision|ai-detection|delivery)\b/.test(url || "");
  }

  function apiLlm(url, options) {
    var opts = options || {};
    opts.timeoutMs = LLM_REQUEST_TIMEOUT_MS;
    return api(url, opts);
  }

  async function api(url, options) {
    var opts = options || {};
    var timeoutMs = opts.timeoutMs;
    var fetchOpts = Object.assign({}, opts);
    delete fetchOpts.timeoutMs;
    var controller;
    if (timeoutMs) {
      controller = new AbortController();
      fetchOpts.signal = controller.signal;
      setTimeout(function () { controller.abort(); }, timeoutMs);
    }
    var res;
    try {
      res = await fetch(url, fetchOpts);
    } catch (err) {
      if (err && err.name === "AbortError") {
        throw new Error("This AI step timed out. Please click Retry.");
      }
      throw new Error("Network error. Please check your connection and retry.");
    }
    var payload = await res.json().catch(function () { return {}; });
    if (!res.ok) {
      if (payload.error === "REGISTER_REQUIRED" || payload.error === "AUTH_REQUIRED") {
        var authErr = new Error(payload.message || "Create a free account to continue.");
        authErr.code = "REGISTER_REQUIRED";
        throw authErr;
      }
      if (responseMeansProjectMissing(res, payload)) {
        resetProjectState();
      }
      var msg = payload.error || "";
      if (res.status === 404 && !responseMeansProjectMissing(res, payload)) {
        throw new Error(
          msg ||
          ("This step is unavailable (HTTP 404). Restart the server if you just updated the app, then click Retry.")
        );
      }
      if (res.status === 504) {
        throw new Error(msg || "This AI step can take a few minutes. Please wait and click Retry.");
      }
      if (res.status >= 500) {
        throw new Error(
          msg ||
          (isLongRunningStageUrl(url)
            ? "This AI step failed on the server. Please click Retry."
            : ("Server error (" + res.status + "). Please click Retry."))
        );
      }
      throw new Error(msg || ("HTTP " + res.status));
    }
    return payload;
  }

  function saveWizard() {
    if (!state.projectId) {
      localStorage.removeItem(STORAGE_KEY);
      return;
    }
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      projectId: state.projectId,
      stage: state.stage,
      paymentConfirmed: state.paymentConfirmed,
    }));
  }

  function pipelineIndex(stage) {
    for (var i = 0; i < PIPELINE.length; i++) {
      if (PIPELINE[i].match.indexOf(stage) >= 0) return i;
    }
    return 0;
  }

  function writerSectionsComplete(session) {
    var sections = (session && session.sections) || [];
    if (!sections.length) return false;
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].status !== "completed") return false;
    }
    return true;
  }

  function writerDone() {
    var s = state.writerSession;
    if (!s) return false;
    if (s.status === "merged") return true;
    return s.status === "completed" && writerSectionsComplete(s);
  }

  function productionPercent(stage) {
    var key = stage === "requirement" ? "upload" : stage;
    var base = STAGE_PROGRESS[key] != null ? STAGE_PROGRESS[key] : 10;
    if ((stage || state.stage) === "writer" && state.writerSession) {
      var wp = Number(state.writerSession.progress) || 0;
      return Math.round(35 + (wp / 100) * 25);
    }
    if ((stage || state.stage) === "humanizer" && state.humanizerSession) {
      var hp = Number(state.humanizerSession.progress) || 0;
      return Math.round(60 + (hp / 100) * 20);
    }
    return base;
  }

  function threadEl() {
    return $("[data-asg-thread]");
  }

  function scrollThread() {
    var sc = $("[data-asg-chat-scroll]");
    if (sc) sc.scrollTop = sc.scrollHeight;
  }

  function hideEmptyState() {
    show($("[data-asg-empty]"), false);
  }

  function showEmptyStateIfNeeded() {
    var thread = threadEl();
    var empty = !thread || !thread.children.length;
    show($("[data-asg-empty]"), empty && !state.requirement && !state.deliveryPackage);
  }

  function appendBubble(role, htmlInner, attrs) {
    hideEmptyState();
    var thread = threadEl();
    if (!thread) return null;
    var div = document.createElement("div");
    div.className = "asg-bubble asg-bubble--" + role;
    if (attrs && attrs.id) div.id = attrs.id;
    if (attrs && attrs["data-kind"]) div.setAttribute("data-kind", attrs["data-kind"]);
    var cardKinds = { price: 1, production: 1, complete: 1 };
    if (attrs && attrs["data-kind"] && cardKinds[attrs["data-kind"]]) {
      div.classList.add("asg-bubble--card");
    }
    div.innerHTML = htmlInner;
    thread.appendChild(div);
    scrollThread();
    schedulePersistChat();
    return div;
  }

  function upsertBubble(kind, role, htmlInner) {
    var thread = threadEl();
    if (!thread) return null;
    var existing = thread.querySelector('[data-kind="' + kind + '"]');
    var cardKinds = { price: 1, production: 1, complete: 1 };
    if (existing) {
      existing.innerHTML = htmlInner;
      if (cardKinds[kind]) existing.classList.add("asg-bubble--card");
      scrollThread();
      schedulePersistChat();
      return existing;
    }
    var el = appendBubble(role, htmlInner, { "data-kind": kind });
    if (el && cardKinds[kind]) el.classList.add("asg-bubble--card");
    return el;
  }

  function removeBubble(kind) {
    var thread = threadEl();
    if (!thread) return;
    thread.querySelectorAll('[data-kind="' + kind + '"]').forEach(function (n) {
      n.remove();
    });
    schedulePersistChat();
  }

  function serializeChatTranscript() {
    var thread = threadEl();
    if (!thread) return [];
    var out = [];
    Array.prototype.forEach.call(thread.children, function (node) {
      if (!node || !node.classList || !node.classList.contains("asg-bubble")) return;
      var kind = node.getAttribute("data-kind") || "";
      if (kind === "status") return;
      var role = node.classList.contains("asg-bubble--user") ? "user" : "assistant";
      out.push({
        role: role,
        kind: kind,
        html: node.innerHTML,
      });
    });
    return out;
  }

  var _restoringChat = false;
  var _persistChatTimer = null;
  function schedulePersistChat() {
    if (!pid() || _restoringChat) return;
    if (_persistChatTimer) clearTimeout(_persistChatTimer);
    _persistChatTimer = setTimeout(function () {
      _persistChatTimer = null;
      persistChatTranscript();
    }, 450);
  }

  async function persistChatTranscript() {
    if (!pid() || _restoringChat) return;
    var messages = serializeChatTranscript();
    try {
      await fetch(projectUrl("/chat-transcript"), {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ messages: messages }),
      });
    } catch (err) {
      /* best-effort */
    }
  }

  function restoreChatTranscript(messages) {
    var thread = threadEl();
    if (!thread || !messages || !messages.length) return false;
    _restoringChat = true;
    clearThread();
    hideEmptyState();
    var cardKinds = { price: 1, production: 1, complete: 1 };
    messages.forEach(function (m) {
      if (!m || !m.html) return;
      if (m.kind === "status") return;
      if (m.kind === "production" && state.deliveryPackage) return;
      var role = m.role === "user" ? "user" : "assistant";
      var div = document.createElement("div");
      div.className = "asg-bubble asg-bubble--" + role;
      if (m.kind) div.setAttribute("data-kind", m.kind);
      if (m.kind && cardKinds[m.kind]) div.classList.add("asg-bubble--card");
      div.innerHTML = m.html;
      thread.appendChild(div);
    });
    if (state.deliveryPackage && state.deliveryPackage.id) {
      thread.querySelectorAll('[data-kind="production"]').forEach(function (n) {
        n.remove();
      });
      if (!thread.querySelector('[data-kind="complete"]')) {
        var completeHtml =
          '<div class="asg-complete-card">' +
          "<h3>Your assignment is ready</h3>" +
          "<p>Download the file, or describe changes below for a free revision.</p>" +
          '<button type="button" class="asg-btn asg-btn--primary" data-asg-thread-download>Download</button>' +
          "</div>";
        var cdiv = document.createElement("div");
        cdiv.className = "asg-bubble asg-bubble--assistant asg-bubble--card";
        cdiv.setAttribute("data-kind", "complete");
        cdiv.innerHTML = completeHtml;
        thread.appendChild(cdiv);
      }
    }
    scrollThread();
    showEmptyStateIfNeeded();
    _restoringChat = false;
    return thread.children.length > 0;
  }

  function reconstructChatFromState() {
    clearThread();
    hideEmptyState();
    var files = state._uploadedFileNames || [];
    if (files.length) {
      appendBubble(
        "user",
        '<ul class="asg-attach-list">' +
          files
            .map(function (n) {
              return "<li>" + esc(n) + "</li>";
            })
            .join("") +
          "</ul>"
      );
    }
    if (state.requirement && state.price != null) {
      renderSummary();
    }
    if (state.deliveryPackage && state.deliveryPackage.id) {
      removeBubble("production");
      showCompleteUI();
    } else if (state.paymentConfirmed && !state.deliveryPackage) {
      enterProductionLayout();
    }
    showEmptyStateIfNeeded();
  }

  async function restoreChatForOpenProject(serverTranscript) {
    var restored = restoreChatTranscript(serverTranscript);
    if (restored) {
      syncComposerMode();
      schedulePersistChat();
      return;
    }
    reconstructChatFromState();
    // Also pull revision messages into the thread for older projects.
    try {
      await loadRevisionChat();
    } catch (e) {}
    schedulePersistChat();
  }

  function clearThread() {
    var thread = threadEl();
    if (thread) thread.innerHTML = "";
    showEmptyStateIfNeeded();
  }

  function syncComposerMode() {
    var input = $("[data-asg-note]");
    var attach = $("[data-asg-attach]");
    if (state.deliveryPackage && state.composerMode !== "brief") {
      state.composerMode = "revision";
      if (input) {
        input.placeholder = "Describe changes for a free revision…";
        input.removeAttribute("disabled");
      }
      // Keep + visible — attaching files starts a new assignment.
      if (attach) {
        attach.hidden = false;
        attach.removeAttribute("hidden");
      }
      syncSendEnabled();
      return;
    }
    state.composerMode = "brief";
    if (input) input.placeholder = "Add a note (optional)…";
    if (attach) {
      attach.hidden = false;
      attach.removeAttribute("hidden");
    }
    syncSendEnabled();
  }

  function syncSendEnabled() {
    var send = $("[data-asg-send]");
    if (!send) return;
    if (state.composerMode === "revision") {
      var note = $("[data-asg-note]");
      send.disabled = state.busy || !(note && note.value.trim());
      return;
    }
    var noteEl = $("[data-asg-note]");
    var hasNote = !!(noteEl && noteEl.value.trim());
    send.disabled =
      state.busy || (!(state.pendingFiles && state.pendingFiles.length) && !hasNote);
  }

  function beginNewBriefSession() {
    resetProjectState();
    state.composerMode = "brief";
    state.pendingFiles = [];
    clearThread();
    clearError();
    show($("[data-asg-complete]"), false);
    show($("[data-asg-production]"), false);
    show($("[data-asg-wizard]"), false);
    show($("[data-asg-empty]"), true);
    renderChips();
    try {
      var url = new URL(window.location.href);
      url.searchParams.delete("project");
      url.searchParams.delete("new");
      window.history.replaceState({}, "", url.pathname + (url.search || ""));
    } catch (e) {}
    setStage("upload", { skipSave: true });
    syncComposerMode();
    syncSendEnabled();
    showEmptyStateIfNeeded();
    if (typeof window.DM_refreshAssignmentHistory === "function") {
      window.DM_refreshAssignmentHistory();
    }
    var note = $("[data-asg-note]");
    if (note) {
      note.value = "";
      note.focus();
    }
  }

  window.DM_startNewAssignment = beginNewBriefSession;

  /** Attach / drop files — if a finished project is open, start a new brief. */
  function addFilesFromUser(fileList) {
    if (!fileList || !fileList.length) return;
    if (state.deliveryPackage || state.composerMode === "revision") {
      beginNewBriefSession();
    }
    mergePendingFiles(fileList);
    renderChips();
    syncSendEnabled();
  }

  function fileTypeLabel(file) {
    var name = String((file && file.name) || "").toLowerCase();
    if (/\.(png|jpe?g|gif|webp|svg)$/.test(name)) return "Image";
    if (/\.pdf$/.test(name)) return "PDF";
    if (/\.zip$/.test(name)) return "Archive";
    if (/\.(docx?|rtf|txt)$/.test(name)) return "Document";
    return "File";
  }

  function truncateName(name, max) {
    max = max || 28;
    var s = String(name || "file");
    if (s.length <= max) return s;
    var dot = s.lastIndexOf(".");
    var ext = dot > 0 ? s.slice(dot) : "";
    var base = dot > 0 ? s.slice(0, dot) : s;
    var keep = Math.max(6, max - ext.length - 1);
    return base.slice(0, keep) + "…" + ext;
  }

  function renderChips() {
    var wrap = $("[data-asg-chips]");
    if (!wrap) return;
    if (!state.pendingFiles.length) {
      wrap.innerHTML = "";
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    wrap.removeAttribute("hidden");
    wrap.innerHTML = state.pendingFiles
      .map(function (f, i) {
        return (
          '<div class="asg-file-pill" title="' +
          esc(f.name) +
          '">' +
          '<span class="asg-file-pill-icon" aria-hidden="true">' +
          '<svg width="18" height="18" viewBox="0 0 24 24" fill="none">' +
          '<path d="M7 3.75h6.5L19 8.75V20a1.25 1.25 0 0 1-1.25 1.25H7.25A1.25 1.25 0 0 1 6 20V5A1.25 1.25 0 0 1 7.25 3.75Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>' +
          '<path d="M13.5 3.75V8.75H18.5" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round"/>' +
          "</svg></span>" +
          '<span class="asg-file-pill-meta">' +
          '<span class="asg-file-pill-name">' +
          esc(truncateName(f.name)) +
          "</span>" +
          '<span class="asg-file-pill-type">' +
          esc(fileTypeLabel(f)) +
          "</span></span>" +
          '<button type="button" class="asg-file-pill-remove" data-asg-chip-remove="' +
          i +
          '" aria-label="Remove file">×</button>' +
          "</div>"
        );
      })
      .join("");
    wrap.querySelectorAll("[data-asg-chip-remove]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var idx = parseInt(btn.getAttribute("data-asg-chip-remove"), 10);
        if (!isNaN(idx)) {
          state.pendingFiles.splice(idx, 1);
          renderChips();
          syncSendEnabled();
        }
      });
    });
  }

  function setDropOverlay(on) {
    var overlay = $("[data-asg-drop-overlay]");
    if (!overlay) return;
    if (on) {
      overlay.hidden = false;
      overlay.removeAttribute("hidden");
    } else {
      overlay.hidden = true;
    }
    root.classList.toggle("is-dragging-files", !!on);
  }

  function setupDragDrop() {
    var dragDepth = 0;

    function hasFiles(e) {
      var dt = e.dataTransfer;
      if (!dt) return false;
      try {
        var types = dt.types ? Array.prototype.slice.call(dt.types) : [];
        if (types.indexOf("Files") !== -1) return true;
        if (types.indexOf("application/x-moz-file") !== -1) return true;
      } catch (err) {}
      return !!(dt.files && dt.files.length);
    }

    function onDragEnter(e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.stopPropagation();
      dragDepth += 1;
      setDropOverlay(true);
    }

    function onDragOver(e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      setDropOverlay(true);
    }

    function onDragLeave(e) {
      e.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) setDropOverlay(false);
    }

    function onDrop(e) {
      e.preventDefault();
      e.stopPropagation();
      dragDepth = 0;
      setDropOverlay(false);
      var files = e.dataTransfer && e.dataTransfer.files;
      if (!files || !files.length) return;
      addFilesFromUser(files);
    }

    // Listen on the chat root and the main column so drops work over the whole page area.
    var targets = [root];
    var main = document.querySelector(".app-shell-main");
    if (main) targets.push(main);
    targets.forEach(function (el) {
      el.addEventListener("dragenter", onDragEnter);
      el.addEventListener("dragover", onDragOver);
      el.addEventListener("dragleave", onDragLeave);
      el.addEventListener("drop", onDrop);
    });
    window.addEventListener("dragend", function () {
      dragDepth = 0;
      setDropOverlay(false);
    });
  }

  function updateProductionProgress(stage) {
    if (state.deliveryPackage) {
      removeBubble("production");
      return;
    }
    var raw = productionPercent(stage || state.stage);
    var pct = Math.max(Number(state.productionPeakPct) || 0, Math.max(0, Math.min(100, raw)));
    state.productionPeakPct = pct;
    var fill = $("[data-asg-production-fill]");
    var label = $("[data-asg-production-pct]");
    if (fill) fill.style.width = pct + "%";
    if (label) label.textContent = pct + "%";
    upsertBubble(
      "production",
      "assistant",
      '<div class="asg-prod-card">' +
        "<h3>Generating your assignment</h3>" +
        '<div class="asg-production-bar" aria-hidden="true"><div class="asg-production-bar-fill" style="width:' +
        pct +
        '%"></div></div>' +
        '<p class="asg-production-pct">' +
        pct +
        "%</p>" +
        '<p class="asg-production-eta">Estimated time: 3–5 minutes</p>' +
        "</div>"
    );
  }

  function enterProductionLayout() {
    show($("[data-asg-production]"), true);
    show($("[data-asg-complete]"), false);
    removeBubble("complete");
    updateProductionProgress(state.stage);
    var form = $("[data-asg-composer-form]");
    if (form) {
      form.querySelectorAll("[data-asg-attach],[data-asg-send],[data-asg-note],[data-asg-files]").forEach(function (el) {
        el.disabled = true;
      });
    }
  }

  function showCompleteUI() {
    if (!state.deliveryPackage || !state.deliveryPackage.id) {
      return;
    }
    state.productionPeakPct = 100;
    show($("[data-asg-production]"), false);
    show($("[data-asg-complete]"), true);
    // Progress card must not linger next to the ready card.
    removeBubble("production");
    upsertBubble(
      "complete",
      "assistant",
      '<div class="asg-complete-card">' +
        "<h3>Your assignment is ready</h3>" +
        "<p>Download the file, or describe changes below for a free revision.</p>" +
        '<button type="button" class="asg-btn asg-btn--primary" data-asg-thread-download>Download</button>' +
        "</div>"
    );
    loadRevisionChat();
    syncComposerMode();
    var form = $("[data-asg-composer-form]");
    if (form) {
      form.querySelectorAll("[data-asg-send],[data-asg-note]").forEach(function (el) {
        el.disabled = false;
      });
    }
    syncSendEnabled();
    var note = $("[data-asg-note]");
    if (note) note.focus();
    if (typeof window.DM_refreshAssignmentHistory === "function") {
      window.DM_refreshAssignmentHistory();
    }
  }

  function exitProductionLayout() {
    show($("[data-asg-production]"), false);
    updateChrome();
  }

  function renderProgress() {
    if (state.paymentConfirmed && !state.deliveryPackage) {
      updateProductionProgress(state.stage);
    }
  }

  function setStatus(text) {
    if (state.autoRunning) return;
    var el = $("[data-asg-wizard-status]");
    if (el) el.textContent = text || "";
  }

  function showError(msg) {
    var el = $("[data-asg-page-error]") || $("[data-asg-wizard-error]");
    if (!el) return;
    if (msg) {
      el.textContent = msg;
      el.hidden = false;
    } else {
      el.textContent = "";
      el.hidden = true;
    }
  }

  function clearError() {
    showError("");
    state.retryAction = null;
  }

  function setBusy(on) {
    state.busy = on;
    var primary = $("[data-asg-wizard-primary]");
    var back = $("[data-asg-wizard-back]");
    var analyze = $("[data-asg-analyze]");
    var pay = $("[data-asg-continue]");
    if (primary) primary.disabled = on || primary.dataset.forceDisabled === "1";
    if (back) back.disabled = on;
    if (analyze) analyze.disabled = on || collectUploadFiles().length === 0;
    if (pay) pay.disabled = on || state.autoRunning || state.price == null || state.paymentConfirmed;
    syncSendEnabled();
  }

  function hideWizardActions(on) {
    var actions = root.querySelector(".asg-wizard-actions");
    if (actions) actions.hidden = on;
  }

  function fail(err, retryFn) {
    state.retryAction = retryFn || null;
    state.autoRunning = false;
    var message = "Something went wrong. Please try again.";
    if (err && err.message) {
      message = isStaleProjectError(err) ? staleSessionMessage() : err.message;
    }
    if (isStaleProjectError(err)) {
      resetProjectState();
      setStage("upload");
      showError("");
      set("[data-asg-analysis-status]", message);
      renderSummary();
      updateChrome();
      setBusy(false);
      return;
    }
    root.classList.remove("asg-page--production");
    show($("[data-asg-production]"), false);
    show($("[data-asg-wizard]"), false);
    showError(message);
    upsertBubble("error", "assistant", "<p>" + esc(message) + "</p>");
    var primary = $("[data-asg-wizard-primary]");
    if (primary) {
      primary.textContent = retryFn ? "Retry" : primary.dataset.defaultLabel || "Continue";
      primary.disabled = false;
      primary.dataset.forceDisabled = "0";
    }
    hideWizardActions(false);
    setBusy(false);
    var form = $("[data-asg-composer-form]");
    if (form) {
      form.querySelectorAll("[data-asg-attach],[data-asg-send],[data-asg-note],[data-asg-files]").forEach(function (el) {
        el.disabled = false;
      });
    }
    syncComposerMode();
  }

  async function handleProductionResult(result) {
    return !result || result.ok !== false;
  }

  function renderCard(inner) {
    var card = $("[data-asg-wizard-card]");
    if (!card) return;
    card.innerHTML = inner;
  }

  function syncPaymentFromServer(data) {
    state.paymentConfirmed = !!(data && data.project && data.project.artifacts && data.project.artifacts.payment_confirmed);
  }

  function formatMinutes(m) {
    m = Math.max(1, parseInt(m, 10) || 0);
    if (m < 60) return "~" + m + " min";
    var h = Math.floor(m / 60);
    var rem = m % 60;
    return rem ? "~" + h + "h " + rem + "m" : "~" + h + "h";
  }

  function titleCase(s) {
    if (!s) return "";
    return String(s).replace(/[_-]+/g, " ").replace(/\b\w/g, function (c) { return c.toUpperCase(); });
  }

  function difficultyLabel(n) {
    if (n <= 2) return "Very easy";
    if (n <= 4) return "Easy";
    if (n <= 6) return "Moderate";
    if (n <= 8) return "Hard";
    return "Very hard";
  }

  function difficultyText(n) {
    n = Math.max(1, Math.min(10, parseInt(n, 10) || 5));
    return n + "/10 · " + difficultyLabel(n);
  }

  function showRow(sel, on) {
    var el = $(sel);
    if (el) el.hidden = !on;
  }

  function renderPriceBreakdown(p) {
    var box = $("[data-asg-price-breakdown]");
    if (!box) return;
    if (!p || p.amount_usd == null) {
      box.hidden = true;
      box.innerHTML = "";
      return;
    }
    var rows = [];
    rows.push(["Base · " + (p.word_count || 0).toLocaleString() + " words", fmtMoney(p.base_usd)]);
    if (p.difficulty_multiplier && Math.abs(p.difficulty_multiplier - 1) > 0.001) {
      rows.push(["Difficulty " + (p.difficulty_stars || "") + "/10", "×" + p.difficulty_multiplier]);
    }
    box.innerHTML = rows
      .map(function (r) {
        return '<div class="asg-price-row"><span>' + r[0] + "</span><span>" + r[1] + "</span></div>";
      })
      .join("");
    box.hidden = false;
  }

  function renderSummary() {
    var req = state.requirement || {};
    var p = state.pricing || {};
    set("[data-asg-summary-words]", req.word_count);
    set("[data-asg-summary-deadline]", req.deadline);
    set("[data-asg-summary-type]", titleCase(req.assignment_type) || "—");

    var stars = p.difficulty_stars;
    if (stars != null) {
      set("[data-asg-summary-difficulty]", difficultyText(stars) + (p.difficulty_estimated ? " (est.)" : ""));
    } else {
      set("[data-asg-summary-difficulty]", "—");
    }

    showRow("[data-asg-summary-eta-row]", !!p.estimated_minutes);
    if (p.estimated_minutes) {
      set("[data-asg-summary-eta]", formatMinutes(p.estimated_minutes));
    }

    set("[data-asg-summary-total]", fmtMoney(state.price));
    renderPriceBreakdown(state.pricing);

    var coinsEl = $("[data-asg-summary-coins]");
    if (coinsEl) {
      if (p.amount_coins) {
        coinsEl.textContent = "≈ " + p.amount_coins.toLocaleString() + " coins";
        coinsEl.hidden = false;
      } else {
        coinsEl.hidden = true;
      }
    }

    updateSummaryPayButton();

    if (!state.requirement || state.price == null) return;
    if (state.paymentConfirmed || state.deliveryPackage) return;

    var rows = [];
    rows.push(["Words", na(req.word_count)]);
    rows.push(["Type", titleCase(req.assignment_type) || "—"]);
    if (stars != null) rows.push(["Complexity", difficultyText(stars)]);
    if (p.estimated_minutes) rows.push(["Est. time", formatMinutes(p.estimated_minutes)]);
    if (req.deadline) rows.push(["Deadline", na(req.deadline)]);

    var breakdown = "";
    if (p.amount_usd != null) {
      breakdown +=
        '<div class="asg-price-row"><span>Base · ' +
        (p.word_count || 0).toLocaleString() +
        " words</span><span>" +
        fmtMoney(p.base_usd) +
        "</span></div>";
      if (p.difficulty_multiplier && Math.abs(p.difficulty_multiplier - 1) > 0.001) {
        breakdown +=
          '<div class="asg-price-row"><span>Difficulty ' +
          (p.difficulty_stars || "") +
          "/10</span><span>×" +
          p.difficulty_multiplier +
          "</span></div>";
      }
    }

    var coinsLine = p.amount_coins
      ? '<p class="asg-price-coins">≈ ' + p.amount_coins.toLocaleString() + " coins</p>"
      : "";

    upsertBubble(
      "price",
      "assistant",
      '<div class="asg-price-card">' +
        "<h3>Project summary</h3>" +
        '<dl class="asg-price-dl">' +
        rows
          .map(function (r) {
            return "<div><dt>" + esc(r[0]) + "</dt><dd>" + esc(String(r[1])) + "</dd></div>";
          })
          .join("") +
        "</dl>" +
        (breakdown ? '<div class="asg-price-breakdown">' + breakdown + "</div>" : "") +
        '<p class="order-total"><span>Total</span><strong>' +
        fmtMoney(state.price) +
        "</strong></p>" +
        coinsLine +
        '<button type="button" class="assignment-pay-btn" data-asg-thread-pay>Start Writing</button>' +
        "</div>"
    );

    var payBtn = document.querySelector("[data-asg-thread-pay]");
    if (payBtn && !payBtn._bound) {
      payBtn._bound = true;
      payBtn.addEventListener("click", function () {
        if (!state.paymentConfirmed) {
          runAutoProduction().catch(function (err) {
            fail(err, runAutoProduction);
          });
        } else {
          continueAutoProduction().catch(function (err) {
            fail(err, continueAutoProduction);
          });
        }
      });
    }
  }

  function updateSummaryPayButton() {
    var btn = $("[data-asg-continue]");
    if (!btn) return;
    var ready = state.requirement && state.price != null;
    btn.hidden = !ready || state.autoRunning;
    if (!state.paymentConfirmed) {
      btn.textContent = "Start Writing";
    } else if (state.deliveryPackage) {
      btn.hidden = true;
    } else {
      btn.textContent = "Continue";
    }
    btn.disabled = state.busy || state.autoRunning || !ready;
  }

  function renderPriceStage() {
    /* Price lives only in Project Summary — no duplicate quote card. */
  }

  function renderResearchStage() { renderProgress(); }
  function renderBlueprintStage() { renderProgress(); }
  function renderWriterStage() { renderProgress(); }
  function renderReviewStage() { renderProgress(); }
  function renderHumanizerStage() { renderProgress(); }
  function renderDetectionStage() { renderProgress(); }

  function renderDeliveryStage() {
    renderProgress();
    if (state.deliveryPackage && state.deliveryPackage.id) {
      showCompleteUI();
    }
  }

  function updateChrome() {
    var hasReq = !!state.requirement;
    var isComplete = !!state.deliveryPackage;
    var inProduction = state.paymentConfirmed && !isComplete && state.autoRunning;

    if (isComplete) {
      showCompleteUI();
      return;
    }

    if (inProduction) {
      enterProductionLayout();
    } else {
      show($("[data-asg-wizard]"), false);
      show($("[data-asg-production]"), false);
      show($("[data-asg-complete]"), false);
    }

    if (hasReq) renderSummary();
    syncComposerMode();
    showEmptyStateIfNeeded();
  }

  function updateActions() {
    var primary = $("[data-asg-wizard-primary]");
    var back = $("[data-asg-wizard-back]");
    if (!primary || !back) return;

    if (state.autoRunning) {
      hideWizardActions(true);
      return;
    }

    hideWizardActions(state.stage === "upload");

    var labels = {
      price: "Start Writing",
      writer: "Write next section",
      delivery: "Download package",
    };

    primary.textContent = labels[state.stage] || "Continue";
    primary.dataset.defaultLabel = primary.textContent;
    back.hidden = true;

    if (state.stage === "price") {
      primary.hidden = false;
      primary.disabled = state.busy || state.price == null || !state.requirement;
    } else if (state.stage === "delivery") {
      primary.hidden = false;
      primary.disabled = state.busy;
    } else if (["research", "blueprint", "review", "humanizer", "detection"].indexOf(state.stage) >= 0) {
      primary.hidden = true;
    } else if (state.stage === "writer") {
      primary.hidden = writerDone();
      primary.disabled = state.busy;
    } else {
      primary.hidden = false;
      primary.disabled = state.busy;
    }
  }

  function setStage(stage, opts) {
    opts = opts || {};
    state.stage = stage;
    clearError();
    renderProgress();
    updateChrome();

    if (stage === "price") renderPriceStage();
    else if (stage === "research") renderResearchStage();
    else if (stage === "blueprint") renderBlueprintStage();
    else if (stage === "writer") renderWriterStage();
    else if (stage === "review") renderReviewStage();
    else if (stage === "humanizer") renderHumanizerStage();
    else if (stage === "detection") renderDetectionStage();
    else if (stage === "delivery") renderDeliveryStage();

    updateActions();
    if (!opts.skipSave) saveWizard();
  }

  function parseDeadline() {
    return null;
  }

  function fileKey(file) {
    return [file.name, file.size, file.lastModified || 0].join("::");
  }

  function mergePendingFiles(fileList) {
    if (!fileList || !fileList.length) return;
    var seen = {};
    state.pendingFiles.forEach(function (f) {
      seen[fileKey(f)] = true;
    });
    Array.prototype.forEach.call(fileList, function (f) {
      var key = fileKey(f);
      if (seen[key]) return;
      seen[key] = true;
      state.pendingFiles.push(f);
    });
  }

  function mergeExtraFiles(fileList) {
    mergePendingFiles(fileList);
  }

  function removeExtraFile(index) {
    if (index < 0 || index >= state.pendingFiles.length) return;
    state.pendingFiles.splice(index, 1);
    renderChips();
    syncSendEnabled();
  }

  function collectUploadFiles() {
    return (state.pendingFiles || []).map(function (f) {
      return { kind: "file", file: f };
    });
  }

  function getPriority() {
    var selected = root.querySelector('input[name="asg_priority"]:checked');
    return selected ? selected.value : "standard";
  }

  function renderFiles(entries) {
    renderChips();
  }

  async function hydrateFromServer() {
    if (!pid()) return;
    var data = await api(projectUrl(""));
    state.requirement = data.requirement || null;
    state.price = data.project && data.project.price != null ? data.project.price : state.price;
    if (data.project && data.project.artifacts && data.project.artifacts.pricing) {
      state.pricing = data.project.artifacts.pricing;
    }
    syncPaymentFromServer(data);
    state.research = data.research_plan || null;
    state.blueprint = data.blueprint || null;
    state.writerSession = data.writer_session || null;
    state.draft = data.draft || null;
    state.review = data.review_report || null;
    state.humanizerSession = data.humanizer_session || null;
    state.detectionSession = data.detection_session || null;
    state.detectionReport = data.detection_report || null;
    state.deliveryPackage = data.delivery_package || null;
    state.chatTranscript = Array.isArray(data.chat_transcript) ? data.chat_transcript : [];
    var uploadedNames = [];
    var fileLists = [data.files, data.uploaded_files];
    fileLists.forEach(function (list) {
      if (!Array.isArray(list)) return;
      list.forEach(function (f) {
        var name = (f && (f.original_filename || f.filename || f.name)) || "";
        if (name && uploadedNames.indexOf(name) < 0) uploadedNames.push(name);
      });
    });
    state._uploadedFileNames = uploadedNames;
    if (data.project && data.project.artifacts) {
      state.reviewPass = data.project.artifacts.review_pass_number || state.reviewPass;
      state.detectionAttempt = data.project.artifacts.detection_attempt_number || state.detectionAttempt;
      state.humanizerPass = data.project.artifacts.revision_attempts
        ? data.project.artifacts.revision_attempts + 1
        : state.humanizerPass;
      state.citationPack = data.project.artifacts.citation_pack || state.citationPack;
      state.formattedDocument = data.project.artifacts.formatted_document || state.formattedDocument;
      state.validationReport = data.project.artifacts.validation_report || state.validationReport;
    }
  }

  function inferStageFromArtifacts() {
    if (state.deliveryPackage) return "delivery";
    if (state.detectionReport || (state.detectionSession && state.detectionSession.status === "completed")) return "detection";
    if (state.validationReport && state.validationReport.passed) return "validation";
    if (state.review) return "review";
    if (state.formattedDocument) return "format";
    if (state.humanizerSession && humanizerDone()) return "humanizer";
    if (state.citationPack) return "citations";
    if (state.writerSession) return "writer";
    if (state.blueprint) return "blueprint";
    if (state.research) return "research";
    if (state.paymentConfirmed) return "research";
    if (state.price != null || state.requirement) return "price";
    return "upload";
  }

  async function uploadProject() {
    var form = new FormData();
    var files = collectUploadFiles();
    var noteEl = $("[data-asg-note]");
    var note = noteEl ? noteEl.value.trim() : "";
    // Prefer legacy field names so the server always stores an assignment_brief.
    files.forEach(function (entry, idx) {
      var f = entry.file;
      if (idx === 0) form.append("assignment_brief", f, f.name);
      else form.append("additional_files", f, f.name);
    });
    if (!files.length && !note) throw new Error("Attach at least one file or add a note.");
    if (note) form.append("note", note);
    form.append("priority", getPriority());
    var payload = await api("/api/assignment/projects/upload", { method: "POST", body: form });
    state.projectId = payload.project && payload.project.id;
    if (!state.projectId) {
      throw new Error("Upload did not return a project id. Please try again.");
    }
    state.requirement = payload.requirement || null;
    saveWizard();
    loadAssignmentHistory();
  }

  async function analyzeRequirements() {
    var payload = await api(projectUrl("/analyze-requirements"), { method: "POST" });
    state.requirement = payload.requirement || state.requirement;
  }

  async function calculatePrice() {
    var payload = await api(projectUrl("/pricing"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ priority: getPriority() }),
    });
    state.price = payload.project && payload.project.price != null ? payload.project.price : state.price;
    if (payload.project && payload.project.artifacts && payload.project.artifacts.pricing) {
      state.pricing = payload.project.artifacts.pricing;
    }
  }

  async function runPrePayment() {
    setBusy(true);
    clearError();
    var filesSnapshot = collectUploadFiles().map(function (e) {
      return e.file;
    });
    var noteEl = $("[data-asg-note]");
    var noteSnapshot = noteEl ? noteEl.value.trim() : "";
    if (!filesSnapshot.length && !noteSnapshot && !pid()) {
      setBusy(false);
      throw new Error("Attach at least one file or add a note.");
    }
    try {
      if (filesSnapshot.length > 0 || noteSnapshot) {
        var names = filesSnapshot.map(function (f) {
          return esc(f.name);
        });
        appendBubble(
          "user",
          (names.length
            ? '<ul class="asg-attach-list">' +
              names
                .map(function (n) {
                  return "<li>" + n + "</li>";
                })
                .join("") +
              "</ul>"
            : "") + (noteSnapshot ? "<p>" + esc(noteSnapshot) + "</p>" : "")
        );
        resetProjectState();
        state.pendingFiles = filesSnapshot.slice();
        if (noteEl) noteEl.value = noteSnapshot;
        upsertBubble("status", "assistant", "<p>Uploading and analyzing…</p>");
        await uploadProject();
        // Keep chips until price is ready; clear after success path below.
      }
      upsertBubble("status", "assistant", "<p>Analyzing your requirements…</p>");
      await analyzeRequirements();
      upsertBubble("status", "assistant", "<p>Calculating price…</p>");
      await calculatePrice();
      var statusBubble = document.querySelector('[data-kind="status"]');
      if (statusBubble) statusBubble.remove();
      state.pendingFiles = [];
      renderChips();
      if (noteEl) noteEl.value = "";
      setBusy(false);
      setStage("price");
    } catch (err) {
      // Restore attachments so the user can retry without re-picking files.
      state.pendingFiles = filesSnapshot.slice();
      renderChips();
      if (noteEl && noteSnapshot) noteEl.value = noteSnapshot;
      setBusy(false);
      throw err;
    }
  }

  async function ensurePaymentConfirmed() {
    var data = await api(projectUrl(""));
    syncPaymentFromServer(data);
    if (state.paymentConfirmed) return;
    var confirmed = await api(projectUrl("/confirm-payment"), { method: "POST" });
    syncPaymentFromServer(confirmed);
    if (!state.paymentConfirmed) {
      throw new Error("Payment could not be confirmed. Please try again.");
    }
    saveWizard();
    renderSummary();
  }

  async function confirmPayment() {
    await ensurePaymentConfirmed();
  }

  async function runResearch() {
    if (!state.research) {
      var created = await apiLlm(projectUrl("/research"), { method: "POST" });
      state.research = created.research_plan || null;
    }
    if (!state.research) {
      var data = await api(projectUrl(""));
      state.research = data.research_plan || null;
    }
    renderProgress();
  }

  async function runBlueprint() {
    if (!state.blueprint) {
      var created = await apiLlm(projectUrl("/blueprint"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ research_plan: state.research || null }),
      });
      state.blueprint = created.blueprint || null;
    }
    if (!state.blueprint) {
      var data = await api(projectUrl(""));
      state.blueprint = data.blueprint || null;
    }
    renderProgress();
  }

  function writerSessionBody() {
    return {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ writer_session: state.writerSession || null }),
    };
  }

  function humanizerSessionBody() {
    return {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ humanizer_session: state.humanizerSession || null }),
    };
  }

  function detectionSessionBody() {
    return {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ detection_session: state.detectionSession || null }),
    };
  }

  async function ensureWriterSession() {
    if (state.writerSession && !writerDone()) return state.writerSession;
    try {
      state.writerSession = await api(projectUrl("/writer"));
    } catch (err) {
      state.writerSession = await apiLlm(projectUrl("/writer/start"), { method: "POST" });
    }
    return state.writerSession;
  }

  async function advanceWriter() {
    await ensureWriterSession();
    try {
      state.writerSession = await apiLlm(projectUrl("/writer/advance"), {
        method: "POST",
        ...writerSessionBody(),
      });
    } catch (err) {
      if (String(err.message || "").toLowerCase().indexOf("not found") >= 0) {
        state.writerSession = null;
        await ensureWriterSession();
        state.writerSession = await apiLlm(projectUrl("/writer/advance"), {
          method: "POST",
          ...writerSessionBody(),
        });
      } else {
        throw err;
      }
    }
    renderProgress();
    if (writerSectionsComplete(state.writerSession)) {
      try {
        state.draft = await apiLlm(projectUrl("/writer/merge"), {
          method: "POST",
          ...writerSessionBody(),
        });
        state.writerSession.status = "merged";
      } catch (err) {
        var mergeMsg = String(err && err.message || "");
        if (/still in progress|sections remaining|before merge/i.test(mergeMsg)) {
          if (state.writerSession) state.writerSession.status = "active";
          return;
        }
        throw err;
      }
    } else if (state.writerSession.status === "completed") {
      // Inconsistent snapshot — keep advancing instead of merging early.
      state.writerSession.status = "active";
    }
  }

  function humanizerDone() {
    var s = state.humanizerSession;
    return s && (s.status === "completed" || s.status === "merged");
  }

  async function ensureDetection() {
    if (state.detectionSession &&
      (state.detectionSession.status === "active" ||
        state.detectionSession.status === "completed" ||
        state.detectionSession.status === "needs_manual_review")) {
      return state.detectionSession;
    }
    try {
      state.detectionSession = await api(projectUrl("/ai-detection"));
    } catch (err) {
      state.detectionSession = await apiLlm(projectUrl("/ai-detection/start"), { method: "POST" });
    }
    try {
      var data = await api(projectUrl(""));
      if (data.project && data.project.artifacts && data.project.artifacts.detection_attempt_number) {
        state.detectionAttempt = data.project.artifacts.detection_attempt_number;
      }
      if (data.detection_report) state.detectionReport = data.detection_report;
    } catch (err) {
      /* optional hydrate */
    }
    return state.detectionSession;
  }

  async function advanceDetection() {
    await ensureDetection();
    var attempts = 0;
    while (true) {
      attempts += 1;
      try {
        state.detectionSession = await apiLlm(projectUrl("/ai-detection/advance"), {
          method: "POST",
          ...detectionSessionBody(),
        });
        break;
      } catch (err) {
        var msg = String(err.message || "").toLowerCase();
        if (msg.indexOf("not found") >= 0) {
          state.detectionSession = null;
          await ensureDetection();
          state.detectionSession = await apiLlm(projectUrl("/ai-detection/advance"), {
            method: "POST",
            ...detectionSessionBody(),
          });
          break;
        }
        // Soft retry for transient ZeroGPT / network blips.
        if (attempts < 3 && (msg.indexOf("try again") >= 0 || msg.indexOf("zerogpt") >= 0 || msg.indexOf("timed out") >= 0 || msg.indexOf("502") >= 0 || msg.indexOf("detection step failed") >= 0)) {
          await new Promise(function (resolve) { setTimeout(resolve, 800 * attempts); });
          continue;
        }
        throw err;
      }
    }
    renderProgress();
  }

  async function resetDetection() {
    state.detectionReport = null;
    // Keep an existing in-progress session; only clear local pointer when starting fresh scan.
    state.detectionSession = null;
  }

  async function runDetectionScan() {
    setStage("detection");
    await resetDetection();
    await ensureDetection();
    var guard = 0;
    var maxSteps = Math.max(
      20,
      (((state.detectionSession && state.detectionSession.paragraphs) || []).length * 4) + 5
    );
    while (state.detectionSession &&
      state.detectionSession.status !== "completed" &&
      state.detectionSession.status !== "needs_manual_review") {
      guard += 1;
      if (guard > maxSteps) {
        throw new Error("Detection took too long. Please refresh and try again.");
      }
      await advanceDetection();
    }
    if (!state.detectionReport) {
      var payload = await apiLlm(projectUrl("/ai-detection/finalize"), {
        method: "POST",
        ...detectionSessionBody(),
      });
      state.detectionReport = payload.detection_report || payload;
    }
    renderProgress();
  }

  async function runDelivery() {
    setStatus("Packaging your assignment…");
    state.deliveryPackage = await api(projectUrl("/delivery"), { method: "POST" });
    setStage("delivery");
    setStatus("");
    loadAssignmentHistory();
  }

  async function downloadDelivery() {
    try {
      if (!state.deliveryPackage || !state.deliveryPackage.id) {
        setBusy(true);
        setStatus("Packaging your assignment…");
        await runDelivery();
      }
      var id = state.deliveryPackage && state.deliveryPackage.id;
      if (!id) {
        throw new Error("Delivery package is not ready yet. Please try again.");
      }
      // Prefer project-scoped download so a missing in-memory package can be rebuilt from disk.
      window.location.href = "/api/assignment/projects/" + encodeURIComponent(state.projectId) + "/download";
      loadRevisionChat();
    } catch (err) {
      fail(err, downloadDelivery);
    } finally {
      setBusy(false);
      setStatus("");
      updateActions();
      updateChrome();
    }
  }

  function renderRevisionChat(payload) {
    var messages = (payload && payload.messages) || [];
    var used = (payload && payload.rounds_used) || 0;
    var max = (payload && payload.max_rounds) || 5;
    var meta = $("[data-asg-revchat-meta]");
    if (meta) meta.textContent = used + " / " + max + " free revision rounds used";

    // Mirror into the main chat thread (skip duplicates by rewriting revision block).
    var thread = threadEl();
    if (thread) {
      thread.querySelectorAll('[data-kind="rev-msg"]').forEach(function (n) {
        n.remove();
      });
      messages.forEach(function (m) {
        var role = m.role === "assistant" ? "assistant" : "user";
        appendBubble(
          role,
          "<p>" + esc(m.content || "") + "</p>",
          { "data-kind": "rev-msg" }
        );
      });
      if (messages.length) {
        upsertBubble(
          "rev-meta",
          "assistant",
          "<p class=\"asg-rev-meta\">" + used + " / " + max + " free revision rounds used</p>"
        );
      }
    }

    var hiddenThread = $("[data-asg-revchat-thread]");
    if (hiddenThread) {
      hiddenThread.innerHTML = messages
        .map(function (m) {
          var role = m.role === "assistant" ? "assistant" : "user";
          return (
            '<div class="asg-revchat-msg asg-revchat-msg--' +
            role +
            '"><p>' +
            esc(m.content || "") +
            "</p></div>"
          );
        })
        .join("");
    }
  }

  async function loadRevisionChat() {
    if (!state.projectId) return;
    try {
      var payload = await api(projectUrl("/revision-chat"));
      renderRevisionChat(payload);
    } catch (err) {
      // Guest / not ready — ignore.
    }
  }

  async function sendRevisionChat(event) {
    if (event) event.preventDefault();
    var input = $("[data-asg-note]") || $("[data-asg-revchat-input]");
    var message = input && input.value ? input.value.trim() : "";
    if (!message) return;
    setBusy(true);
    setStatus("Applying your revisions…");
    try {
      var payload = await apiLlm(projectUrl("/revision-chat"), {
        method: "POST",
        body: JSON.stringify({ message: message }),
      });
      if (input) input.value = "";
      if (payload.delivery_package) state.deliveryPackage = payload.delivery_package;
      renderRevisionChat(payload);
      setStatus("Revision applied. Download the updated file.");
      loadAssignmentHistory();
      upsertBubble(
        "complete",
        "assistant",
        '<div class="asg-complete-card">' +
          "<h3>Revision applied</h3>" +
          "<p>Download the updated file, or request another change.</p>" +
          '<button type="button" class="asg-btn asg-btn--primary" data-asg-thread-download>Download</button>' +
          "</div>"
      );
      var dl = document.querySelector("[data-asg-thread-download]");
      if (dl) {
        dl._bound = false;
        dl.addEventListener("click", downloadDelivery);
        dl._bound = true;
      }
    } catch (err) {
      fail(err, function () {
        return sendRevisionChat();
      });
    } finally {
      setBusy(false);
      updateActions();
      updateChrome();
      syncSendEnabled();
    }
  }

  async function runReview() {
    var payload = await apiLlm(projectUrl("/review"), { method: "POST" });
    state.review = payload.review_report || null;
    state.reviewMeta = {
      pass_number: payload.pass_number || state.reviewPass,
      issues_found: payload.issues_found,
      issues_fixed: payload.issues_fixed,
    };
    if (payload.pass_number) state.reviewPass = payload.pass_number;
    renderProgress();
  }

  async function runRevision() {
    var payload = await apiLlm(projectUrl("/revision"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ review_report: state.review || null }),
    });
    state.reviewMeta = state.reviewMeta || {};
    var result = payload.revision_result || payload;
    state.reviewMeta.issues_fixed = (result && result.issues_addressed)
      ? result.issues_addressed.length
      : state.reviewMeta.issues_fixed;
    renderProgress();
    return result || null;
  }

  async function runCitations() {
    setStage("citations");
    var payload = await apiLlm(projectUrl("/citations/generate"), { method: "POST" });
    state.citationPack = payload.citation_pack || null;
    renderProgress();
    return state.citationPack;
  }

  async function runFormatting() {
    setStage("format");
    var payload = await apiLlm(projectUrl("/format"), { method: "POST" });
    state.formattedDocument = payload.formatted_document || null;
    renderProgress();
    return state.formattedDocument;
  }

  async function runValidation() {
    setStage("validation");
    var payload = await apiLlm(projectUrl("/validate-requirements"), { method: "POST" });
    state.validationReport = payload.validation_report || null;
    renderProgress();
    // Soft-continue: failed validation is stored for the summary, but does not stop delivery.
    if (state.validationReport && state.validationReport.passed === false) {
      var issues = (state.validationReport.blocking_issues || []).join("; ")
        || (state.validationReport.missing_requirements || []).join("; ")
        || "Requirement checks flagged issues";
      console.warn("Requirement validation soft-fail:", issues);
      // Never surface soft-fail text via throw/showError — pipeline continues.
    }
    return state.validationReport;
  }

  async function ensureHumanizer() {
    if (state.humanizerSession && state.humanizerSession.status !== "merged") return state.humanizerSession;
    try {
      state.humanizerSession = await api(projectUrl("/humanizer"));
    } catch (err) {
      state.humanizerSession = await apiLlm(projectUrl("/humanizer/start"), { method: "POST" });
    }
    return state.humanizerSession;
  }

  async function advanceHumanizer() {
    await ensureHumanizer();
    try {
      state.humanizerSession = await apiLlm(projectUrl("/humanizer/advance"), {
        method: "POST",
        ...humanizerSessionBody(),
      });
    } catch (err) {
      if (String(err.message || "").toLowerCase().indexOf("not found") >= 0) {
        state.humanizerSession = null;
        await ensureHumanizer();
        state.humanizerSession = await apiLlm(projectUrl("/humanizer/advance"), {
          method: "POST",
          ...humanizerSessionBody(),
        });
      } else {
        throw err;
      }
    }
    renderProgress();
  }

  async function mergeHumanizer() {
    if (state.humanizerSession && state.humanizerSession.status === "merged") return;
    await apiLlm(projectUrl("/humanizer/merge"), {
      method: "POST",
      ...humanizerSessionBody(),
    });
    var data = await api(projectUrl(""));
    state.humanizerSession = data.humanizer_session || state.humanizerSession;
  }

  async function runHumanizerFull() {
    setStage("humanizer");
    await ensureHumanizer();
    var guard = 0;
    var maxSteps = Math.max(20, ((state.humanizerSession && state.humanizerSession.total_paragraphs) || 1) * 5);
    while (!humanizerDone()) {
      guard += 1;
      if (guard > maxSteps) {
        throw new Error("Generation took too long. Please refresh and try again.");
      }
      await advanceHumanizer();
    }
    await mergeHumanizer();
  }

  async function runSilentImprovements() {
    try {
      await runRevision();
      state.review = null;
      setStage("review");
      await runReview();
    } catch (err) {
      /* Revision is best-effort before citations — never block the pipeline here. */
    }
  }

  async function runReviewLoop() {
    setStage("review");
    if (!state.review) await runReview();
    var score = state.review ? Number(state.review.overall_score) : 0;
    if (score >= 75) {
      await runRevision(); // no-op / no_issues path when passed
      return true;
    }
    if (score >= 60 && state.review && !state.review.passed) {
      await runSilentImprovements();
    } else if (state.review && !state.review.passed) {
      await runRevision();
    }
    return true;
  }

  function detectionScoreOk(report) {
    if (!report) return false;
    var threshold = (report.thresholds && report.thresholds.acceptable_max) || 15;
    return Number(report.overall_ai_score) <= threshold;
  }

  async function runDetectionLoop() {
    await runDetectionScan();
    return true;
  }

  async function runWriterFull() {
    setStage("writer");
    if (writerDone()) return;
    await ensureWriterSession();
    var guard = 0;
    var maxSteps = Math.max(20, ((state.writerSession && state.writerSession.sections) || []).length * 4 + 5);
    var lastCompleted = -1;
    var staleSteps = 0;
    while (state.writerSession && !writerDone()) {
      guard += 1;
      if (guard > maxSteps) {
        throw new Error("Writing took too long. Please refresh and try again.");
      }
      await advanceWriter();
      var completed = (state.writerSession.completed_section_ids || []).length;
      if (completed === lastCompleted) {
        staleSteps += 1;
        if (staleSteps >= 3) {
          throw new Error("Writing stalled. Please refresh and try again.");
        }
      } else {
        staleSteps = 0;
        lastCompleted = completed;
      }
    }
  }

  async function runProductionCore() {
    if (!state.research) {
      setStage("research");
      await runResearch();
    }
    if (!state.blueprint) {
      setStage("blueprint");
      await runBlueprint();
    }
    if (!writerDone()) {
      await runWriterFull();
    }
    if (!state.citationPack) {
      await runCitations();
    }
    if (!humanizerDone()) {
      state.humanizerPass = 1;
      await runHumanizerFull();
    } else if (state.humanizerSession && state.humanizerSession.status !== "merged") {
      await mergeHumanizer();
    }
    if (!state.formattedDocument) {
      await runFormatting();
    }
    if (!state.review || Number(state.review.overall_score) < 75) {
      state.reviewPass = state.reviewPass || 1;
      await runReviewLoop();
    } else if (!state.reviewMeta) {
      await runRevision();
    }
    if (!state.validationReport) {
      await runValidation();
    }
    if (!state.detectionReport) {
      await runDetectionLoop();
    }
    if (!state.deliveryPackage) {
      await runDelivery();
    }
    state.forceContinue = false;
    return { ok: true };
  }

  async function beginProduction() {
    state.productionPeakPct = 0;
    setStage("research");
    enterProductionLayout();
    updateProductionProgress("research");
  }

  async function continueAutoProduction() {
    if (state.autoRunning) return;
    state.autoRunning = true;
    clearError();
    hideWizardActions(true);
    setBusy(true);
    updateSummaryPayButton();
    try {
      await ensurePaymentConfirmed();
      beginProduction();
      var result = await runProductionCore();
      if (!(await handleProductionResult(result))) return;
    } catch (err) {
      if (String(err.message || "").toLowerCase().indexOf("payment") >= 0) {
        state.paymentConfirmed = false;
        saveWizard();
        state.autoRunning = false;
        setStage("price");
        renderSummary();
      }
      fail(err, continueAutoProduction);
      return;
    } finally {
      state.autoRunning = false;
      setBusy(false);
      updateActions();
      updateChrome();
    }
  }

  async function runAutoProduction() {
    if (state.autoRunning) return;
    state.autoRunning = true;
    clearError();
    hideWizardActions(true);
    setBusy(true);
    updateSummaryPayButton();
    try {
      await ensurePaymentConfirmed();
      beginProduction();
      state.humanizerPass = 1;
      state.reviewPass = 1;
      state.detectionAttempt = 1;
      state.forceContinue = false;
      var result = await runProductionCore();
      if (!(await handleProductionResult(result))) return;
    } catch (err) {
      if (String(err.message || "").toLowerCase().indexOf("payment") >= 0) {
        state.paymentConfirmed = false;
        saveWizard();
        state.autoRunning = false;
        setStage("price");
        renderSummary();
      }
      fail(err, runAutoProduction);
      return;
    } finally {
      state.autoRunning = false;
      setBusy(false);
      updateActions();
      updateChrome();
    }
  }

  async function handlePrimary() {
    if (state.retryAction) {
      var retry = state.retryAction;
      clearError();
      try {
        setBusy(true);
        await retry();
      } catch (err) {
        fail(err, retry);
      } finally {
        setBusy(false);
        updateActions();
      }
      return;
    }

    if (state.stage === "price") {
      await runAutoProduction();
      return;
    }
    if ((state.stage === "review" || state.stage === "humanizer" || state.stage === "detection") && !state.autoRunning) {
      await continueAutoProduction();
      return;
    }
    if (state.stage === "writer" && state.writerSession && !writerDone()) {
      try {
        setBusy(true);
        setStatus("Writing section…");
        await advanceWriter();
        setStatus("");
      } catch (err) {
        fail(err, handlePrimary);
      } finally {
        setBusy(false);
        updateActions();
      }
      return;
    }
    if (state.stage === "delivery") {
      downloadDelivery();
      return;
    }
  }

  async function resume() {
    var params = new URLSearchParams(window.location.search || "");
    if (params.get("new") === "1") {
      beginNewBriefSession();
      return;
    }
    var fromUrl = (params.get("project") || "").trim();
    var raw = localStorage.getItem(STORAGE_KEY);
    try {
      if (fromUrl) {
        state.projectId = fromUrl;
        saveWizard();
      } else if (raw) {
        var saved = JSON.parse(raw);
        state.projectId = saved.projectId || null;
      } else {
        setStage("upload");
        return;
      }
      if (!state.projectId) {
        setStage("upload");
        return;
      }
      await hydrateFromServer();
      await restoreChatForOpenProject(state.chatTranscript);
      if (state.deliveryPackage) {
        setStage("delivery", { skipSave: true });
        saveWizard();
        syncComposerMode();
        return;
      }
      var stage = "price";
      if (raw && !fromUrl) {
        try {
          var savedStage = JSON.parse(raw);
          if (savedStage.stage && STAGE_ORDER.indexOf(savedStage.stage) >= 0) stage = savedStage.stage;
        } catch (e) {}
      }
      if (!state.paymentConfirmed) {
        stage = "price";
      } else if (state.paymentConfirmed && !state.deliveryPackage) {
        stage = inferStageFromArtifacts();
        if (stage === "price" || stage === "upload") stage = "research";
        setStage(stage, { skipSave: true });
        saveWizard();
        syncComposerMode();
        return;
      }
      setStage(stage, { skipSave: true });
      saveWizard();
      syncComposerMode();
    } catch (err) {
      if (isStaleProjectError(err)) {
        resetProjectState();
        setStage("upload");
        clearError();
        set("[data-asg-analysis-status]", staleSessionMessage());
        renderSummary();
        updateChrome();
        return;
      }
      fail(err, resume);
    }
  }

  var resumePromise = null;

  function startResume() {
    if (!resumePromise) {
      resumePromise = resume().finally(function () {
        resumePromise = null;
      });
    }
    return resumePromise;
  }

  function wire() {
    var fileInput = $("[data-asg-files]");
    var attachBtn = $("[data-asg-attach]");
    var form = $("[data-asg-composer-form]");
    var note = $("[data-asg-note]");

    if (attachBtn && fileInput) {
      attachBtn.addEventListener("click", function () {
        fileInput.click();
      });
    }
    if (fileInput) {
      fileInput.addEventListener("change", function () {
        addFilesFromUser(fileInput.files);
        fileInput.value = "";
      });
    }
    if (note) {
      note.addEventListener("input", syncSendEnabled);
      note.addEventListener("keydown", function (e) {
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          if (form) form.requestSubmit();
        }
      });
    }
    if (form) {
      form.addEventListener("submit", function (e) {
        e.preventDefault();
        if (state.composerMode === "revision") {
          sendRevisionChat(e);
          return;
        }
        runPrePayment().catch(function (err) {
          if (err && err.code === "REGISTER_REQUIRED" && window.DMAuth) {
            setBusy(false);
            window.DMAuth.require({
              reason: err.message || "Create a free account to analyze and price your assignment.",
            })
              .then(function () {
                form.requestSubmit();
              })
              .catch(function () {});
            return;
          }
          fail(err, runPrePayment);
        });
      });
    }

    var pay = $("[data-asg-continue]");
    if (pay) {
      pay.addEventListener("click", function () {
        if (!state.paymentConfirmed) {
          runAutoProduction().catch(function (err) {
            fail(err, runAutoProduction);
          });
          return;
        }
        continueAutoProduction().catch(function (err) {
          fail(err, continueAutoProduction);
        });
      });
    }

    var primary = $("[data-asg-wizard-primary]");
    if (primary) primary.addEventListener("click", function () { handlePrimary(); });

    var completeDownload = $("[data-asg-complete-download]");
    if (completeDownload) completeDownload.addEventListener("click", downloadDelivery);
    var completeDownload2 = $("[data-asg-complete-download-secondary]");
    if (completeDownload2) completeDownload2.addEventListener("click", downloadDelivery);

    var revForm = $("[data-asg-revchat-form]");
    if (revForm) revForm.addEventListener("submit", sendRevisionChat);

    syncComposerMode();
    setupDragDrop();
    loadAssignmentHistory();
    startResume();

    root.addEventListener("click", function (e) {
      if (e.target.closest("[data-asg-thread-download]")) {
        e.preventDefault();
        downloadDelivery();
        return;
      }
      if (e.target.closest("[data-asg-thread-pay]")) {
        e.preventDefault();
        if (!state.paymentConfirmed) {
          runAutoProduction().catch(function (err) {
            fail(err, runAutoProduction);
          });
        } else {
          continueAutoProduction().catch(function (err) {
            fail(err, continueAutoProduction);
          });
        }
      }
    });
  }

  function escHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtHistoryDate(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      });
    } catch (e) {
      return iso;
    }
  }

  async function openHistoryProject(projectId) {
    if (!projectId) return;
    state.projectId = projectId;
    saveWizard();
    var url = new URL(window.location.href);
    url.searchParams.set("project", projectId);
    window.history.replaceState({}, "", url.toString());
    setBusy(true);
    setStatus("Opening assignment…");
    clearThread();
    try {
      await hydrateFromServer();
      await restoreChatForOpenProject(state.chatTranscript);
      if (state.deliveryPackage) {
        setStage("delivery", { skipSave: true });
        saveWizard();
      } else if (!state.paymentConfirmed) {
        setStage("price", { skipSave: true });
      } else {
        var stage = inferStageFromArtifacts();
        if (stage === "price" || stage === "upload") stage = "research";
        setStage(stage, { skipSave: true });
      }
      saveWizard();
      syncComposerMode();
      setStatus("");
    } catch (err) {
      fail(err, function () {
        return openHistoryProject(projectId);
      });
    } finally {
      setBusy(false);
      syncComposerMode();
    }
  }

  async function loadAssignmentHistory() {
    if (typeof window.DM_refreshAssignmentHistory === "function") {
      window.DM_refreshAssignmentHistory();
    }
  }

  wire();
})();
