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
    busy: false,
    autoRunning: false,
    retryAction: null,
    forceContinue: false,
    productionPeakPct: 0,
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
    return "Previous session expired. Upload your requirements and click Analyze & get price.";
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

  function updateProductionProgress(stage) {
    var raw = productionPercent(stage || state.stage);
    var pct = Math.max(Number(state.productionPeakPct) || 0, Math.max(0, Math.min(100, raw)));
    state.productionPeakPct = pct;
    var fill = $("[data-asg-production-fill]");
    var label = $("[data-asg-production-pct]");
    if (fill) fill.style.width = pct + "%";
    if (label) label.textContent = pct + "%";
  }

  function enterProductionLayout() {
    show($("[data-asg-upload-card]"), true);
    show($("[data-asg-summary-card]"), true);
    show($("[data-asg-wizard]"), false);
    show($("[data-asg-complete]"), false);
    show($("[data-asg-production]"), true);
    updateProductionProgress(state.stage);
  }

  function showCompleteUI() {
    // Never claim "ready" until a real delivery package exists.
    if (!state.deliveryPackage || !state.deliveryPackage.id) {
      return;
    }
    show($("[data-asg-upload-card]"), true);
    show($("[data-asg-summary-card]"), true);
    show($("[data-asg-wizard]"), false);
    show($("[data-asg-production]"), false);
    show($("[data-asg-complete]"), true);
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
    show($("[data-asg-upload-card]"), true);
    show($("[data-asg-summary-card]"), true);
    show($("[data-asg-wizard]"), false);
    showError(message);
    var primary = $("[data-asg-wizard-primary]");
    if (primary) {
      primary.textContent = retryFn ? "Retry" : primary.dataset.defaultLabel || "Continue";
      primary.disabled = false;
      primary.dataset.forceDisabled = "0";
    }
    hideWizardActions(false);
    setBusy(false);
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
      show($("[data-asg-upload-card]"), true);
      show($("[data-asg-summary-card]"), true);
      show($("[data-asg-wizard]"), false);
      show($("[data-asg-production]"), false);
      show($("[data-asg-complete]"), false);
    }

    var analyze = $("[data-asg-analyze]");
    if (analyze) {
      analyze.textContent = hasReq ? "Update & re-price" : "Analyze & get price";
      analyze.disabled = state.busy || collectUploadFiles().length === 0;
    }
    if (hasReq) renderSummary();
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
    var d = $("[data-asg-deadline-date]");
    var t = $("[data-asg-deadline-time]");
    if (!d || !d.value) return null;
    return d.value + "T" + (t && t.value ? t.value : "12:00") + ":00";
  }

  function collectUploadFiles() {
    var files = [];
    var brief = $("[data-asg-brief]");
    var extra = $("[data-asg-extra]");
    if (brief && brief.files && brief.files[0]) files.push({ kind: "brief", file: brief.files[0] });
    if (extra && extra.files) {
      Array.prototype.forEach.call(extra.files, function (f) { files.push({ kind: "extra", file: f }); });
    }
    return files;
  }

  function getPriority() {
    var selected = root.querySelector('input[name="asg_priority"]:checked');
    return selected ? selected.value : "standard";
  }

  function renderFiles(entries) {
    var section = $("[data-asg-files-section]");
    var list = $("[data-asg-files]");
    if (!list) return;
    list.innerHTML = "";
    if (!entries.length) {
      show(section, false);
      return;
    }
    show(section, true);
    entries.forEach(function (entry) {
      var li = document.createElement("li");
      var kind = entry.kind || "extra";
      var label = FILE_KIND_LABELS[kind] || kind;
      var file = entry.file;
      li.innerHTML = "<strong>" + esc(label) + "</strong> · " + esc(file.name) +
        " <span class=\"assignment-file-size\">(" + Math.max(1, Math.round((file.size || 0) / 1024)) + " KB)</span>";
      list.appendChild(li);
    });
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
    var note = noteEl ? noteEl.value : "";
    files.forEach(function (entry) {
      if (entry.kind === "brief") form.append("assignment_brief", entry.file, entry.file.name);
      else form.append("additional_files", entry.file, entry.file.name);
    });
    if (!files.length) throw new Error("Please upload at least your requirements.");
    if (note) form.append("note", note);
    var deadline = parseDeadline();
    if (deadline) form.append("deadline", deadline);
    form.append("priority", getPriority());
    var payload = await api("/api/assignment/projects/upload", { method: "POST", body: form });
    state.projectId = payload.project && payload.project.id;
    if (!state.projectId) {
      throw new Error("Upload did not return a project id. Please try again.");
    }
    state.requirement = payload.requirement || null;
    saveWizard();
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
    var files = collectUploadFiles();
    if (files.length > 0) {
      resetProjectState();
      set("[data-asg-analysis-status]", "Uploading files…");
      await uploadProject();
    } else if (!pid()) {
      throw new Error("Please upload at least your requirements.");
    }
    set("[data-asg-analysis-status]", "Analyzing your requirements…");
    await analyzeRequirements();
    set("[data-asg-analysis-status]", "Calculating price…");
    await calculatePrice();
    set("[data-asg-analysis-status]", "Analysis complete.");
    setBusy(false);
    setStage("price");
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
    } catch (err) {
      fail(err, downloadDelivery);
    } finally {
      setBusy(false);
      setStatus("");
      updateActions();
      updateChrome();
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
    var raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      setStage("upload");
      return;
    }
    try {
      var saved = JSON.parse(raw);
      state.projectId = saved.projectId || null;
      if (!state.projectId) {
        setStage("upload");
        return;
      }
      await hydrateFromServer();
      if (state.deliveryPackage) {
        setStage("delivery", { skipSave: true });
        saveWizard();
        return;
      }
      var stage = saved.stage && STAGE_ORDER.indexOf(saved.stage) >= 0 ? saved.stage : inferStageFromArtifacts();
      if (!state.paymentConfirmed) {
        stage = "price";
      } else if (state.paymentConfirmed && !state.deliveryPackage) {
        stage = inferStageFromArtifacts();
        if (stage === "price" || stage === "upload") stage = "research";
        setStage(stage, { skipSave: true });
        saveWizard();
        updateChrome();
        return;
      }
      setStage(stage, { skipSave: true });
      saveWizard();
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
    var inputs = [$("[data-asg-brief]"), $("[data-asg-extra]")].filter(Boolean);
    inputs.forEach(function (input) {
      input.addEventListener("change", function () {
        renderFiles(collectUploadFiles());
        var analyze = $("[data-asg-analyze]");
        if (analyze) analyze.disabled = collectUploadFiles().length === 0;
      });
    });

    var analyze = $("[data-asg-analyze]");
    if (analyze) {
      analyze.addEventListener("click", function () {
        runPrePayment().catch(function (err) {
          if (err && err.code === "REGISTER_REQUIRED" && window.DMAuth) {
            setBusy(false);
            set("[data-asg-analysis-status]", "");
            window.DMAuth.require({
              reason: err.message || "Create a free account to analyze and price your assignment.",
            }).then(function () {
              analyze.click();
            }).catch(function () {});
            return;
          }
          var status = isStaleProjectError(err)
            ? staleSessionMessage()
            : (err.message || "Failed");
          set("[data-asg-analysis-status]", status);
          if (isStaleProjectError(err)) {
            resetProjectState();
            setStage("upload");
            clearError();
          } else if (state.requirement) {
            renderSummary();
            updateChrome();
            fail(err, runPrePayment);
            return;
          } else {
            fail(err, runPrePayment);
            return;
          }
          renderSummary();
          updateChrome();
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

    startResume();
  }

  wire();
})();
