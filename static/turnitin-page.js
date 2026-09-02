/**
 * Turnitin page — PlagDetect integration (browser automation backend).
 */
(function () {
  "use strict";

  var CREDITS_PER_CHECK = (function () {
    var btn = document.querySelector("[data-tt-submit]");
    var raw = btn && btn.getAttribute("data-tt-cost");
    var n = raw ? parseInt(raw, 10) : 300;
    return isNaN(n) || n < 1 ? 300 : n;
  })();
  var TURNITIN_CHECK_URL = "/api/turnitin/check";
  var TURNITIN_REPORTS_URL = "/api/turnitin/reports";
  var POLL_MS = 2000;

  var root = document.querySelector("[data-turnitin-page]");
  if (!root) {
    return;
  }

  function readInitialCredits() {
    var el =
      document.querySelector("[data-tt-credits]") ||
      document.querySelector("[data-coin-balance]");
    if (!el) return null;
    var n = parseInt(String(el.textContent || "").replace(/[^\d-]/g, ""), 10);
    return isNaN(n) ? null : n;
  }

  var state = {
    reports: [],
    credits: readInitialCredits(),
    selectedFiles: [],
    searchQuery: "",
    pollTimer: null,
    highlightsPending: {},
  };

  var els = {
    credits: root.querySelector("[data-tt-credits]"),
    fileInput: root.querySelector("[data-tt-file]"),
    filename: root.querySelector("[data-tt-filename]"),
    submitBtn: root.querySelector("[data-tt-submit]"),
    submitStatus: root.querySelector("[data-tt-submit-status]"),
    feedback: root.querySelector("[data-tt-feedback]"),
    reportsBody: root.querySelector("[data-tt-reports-body]"),
    search: root.querySelector("[data-tt-search]"),
    empty: root.querySelector("[data-tt-empty]"),
    emptyZero: root.querySelector(".tt-empty-zero"),
    optionsRow: root.querySelector("[data-tour='tt-options']"),
    submitToolbar: root.querySelector(".tt-submit-toolbar"),
    table: root.querySelector(".tt-table"),
    footnote: root.querySelector(".tt-ai-footnote"),
  };

  function setStatusText(text) {
    if (els.submitStatus) els.submitStatus.textContent = text || "";
  }

  function clearFeedback() {
    if (!els.feedback) return;
    els.feedback.hidden = true;
    els.feedback.innerHTML = "";
  }

  function showCreditsNeeded(required, balance) {
    setStatusText("");
    if (!els.feedback || !window.dmStates) {
      setStatusText(
        "Not enough credits. Need " + required + ", have " + balance + "."
      );
      return;
    }
    els.feedback.hidden = false;
    els.feedback.innerHTML = window.dmStates.creditsWarn({
      required: required,
      balance: balance,
      topupHref: "/pricing",
    });
  }

  function humanizeServiceError(code, message) {
    var c = String(code || "");
    if (c === "STALE_PAGE") {
      return {
        body: "The checker session closed before your file was sent. Your credits weren’t charged. Try again.",
        detail: c,
      };
    }
    if (c === "LOGIN_REQUIRED") {
      return {
        body: "The checking service isn’t signed in right now. Your credits weren’t charged. Try again in a moment.",
        detail: c,
      };
    }
    var msg = String(message || "");
    if (/INSUFFICIENT|not enough/i.test(msg) || c === "INSUFFICIENT_COINS") {
      return null;
    }
    if (/Target page, context or browser has been closed/i.test(msg)) {
      return {
        body: "The checker session closed before your file was sent. Your credits weren’t charged. Try again.",
        detail: c || "STALE_PAGE",
      };
    }
    return {
      body: msg && !/^[A-Z][A-Z0-9_]+$/.test(msg)
        ? msg
        : "We couldn’t finish this check. Your credits weren’t charged if the upload never started. Try again.",
      detail: c && c !== msg ? c : (/^[A-Z][A-Z0-9_]+$/.test(msg) ? msg : ""),
    };
  }

  function showSubmitError(body, detail, onRetry) {
    setStatusText("");
    if (!els.feedback || !window.dmStates) {
      setStatusText(body);
      return;
    }
    els.feedback.hidden = false;
    els.feedback.innerHTML = window.dmStates.error({
      title: "Check didn’t finish",
      body: body,
      detail: detail || "",
      retryAttrs: "data-tt-feedback-retry",
    });
    var btn = els.feedback.querySelector("[data-tt-feedback-retry]");
    if (btn) {
      btn.addEventListener("click", function () {
        clearFeedback();
        if (typeof onRetry === "function") onRetry();
        else if (els.fileInput) els.fileInput.click();
      });
    }
  }

  function formatDate(iso) {
    try {
      return new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch (e) {
      return iso;
    }
  }

  function scoreDisplay(report, numericKey, displayKey) {
    if (report[displayKey]) {
      return report[displayKey];
    }
    var value = report[numericKey];
    if (value === null || value === undefined) {
      return null;
    }
    return value + "%";
  }

  function formatScoreCell(report, numericKey, displayKey, type, kind) {
    if (type === "ai" && report.aiUnavailable) {
      return (
        '<div class="tt-score-cell" title="' +
        escapeAttr(String(report.aiUnavailable)) +
        '">' +
        '<span class="tt-score tt-score--muted">' +
        escapeHtml(String(report.aiUnavailable)) +
        "</span></div>"
      );
    }
    var label = scoreDisplay(report, numericKey, displayKey);
    if (!label) {
      return '<div class="tt-score-cell"><span class="tt-score tt-score--pending">—</span></div>';
    }
    var cls =
      type === "ai"
        ? "tt-score--ai"
        : type === "highlights"
          ? "tt-score--highlights"
          : "tt-score--similarity";
    var hasFile =
      kind === "similarity"
        ? !!report.hasSimilarityReport
        : kind === "ai"
          ? !!report.hasAiReport
          : !!report.hasHighlightsReport;
    var html =
      '<div class="tt-score-cell">' +
      '<span class="tt-score ' + cls + '">' + escapeHtml(label) + "</span>";
    if (report.status === "completed" && hasFile) {
      html +=
        '<button type="button" class="tt-score-download' +
        (type === "highlights" ? " tt-score-download--blue" : "") +
        '" data-tt-download="' +
        escapeAttr(report.id) +
        '" data-tt-kind="' +
        kind +
        '">' +
        '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5M5 20h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>' +
        "</svg>Download</button>";
    }
    html += "</div>";
    return html;
  }

  function isOfficialTurnitin(report) {
    return report && report.provider === "turnitin";
  }

  function highlightsEligible(report) {
    if (report.status !== "completed") return false;
    if (report.hasHighlightsReport) return false;
    if (isOfficialTurnitin(report)) {
      return !report.aiUnavailable;
    }
    if (report.aiHighlightsDisplay || report.aiHighlights != null) {
      return false;
    }
    if (report.aiScoreDisplay === "*%") return true;
    var n = Number(report.aiScore);
    return Number.isFinite(n) && n > 0;
  }

  function formatHighlightsCell(report) {
    if (report.hasHighlightsReport) {
      return formatScoreCell(report, "aiHighlights", "aiHighlightsDisplay", "highlights", "highlights");
    }

    var hs = report.highlightsStatus;
    if (hs === "queued" || hs === "running" || state.highlightsPending[report.id]) {
      return (
        '<div class="tt-score-cell">' +
        '<span class="tt-badge tt-badge--running tt-badge--compact">Processing</span>' +
        "</div>"
      );
    }

    if (highlightsEligible(report) || (report.status === "completed" && report.aiScoreDisplay === "*%" && hs === "failed")) {
      return (
        '<div class="tt-score-cell tt-score-cell--action">' +
        '<button type="button" class="tt-get-highlights" data-tt-get-highlights="' +
        escapeAttr(report.id) +
        '">' +
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<path d="M7 3h7l5 5v13H7V3z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>' +
        '<path d="M14 3v5h5" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>' +
        "</svg>" +
        (hs === "failed" ? "Retry Highlights" : "Get Highlights") +
        '<span class="tt-get-highlights-badge">FREE</span>' +
        "</button></div>"
      );
    }

    return '<div class="tt-score-cell"><span class="tt-score tt-score--pending">—</span></div>';
  }

  function statusBadge(status, errorMessage) {
    var labels = {
      queued: "Queued",
      running: "Running",
      completed: "Completed",
      failed: "Failed",
    };
    var html =
      '<span class="tt-badge tt-badge--' +
      status +
      '"' +
      (errorMessage ? ' title="' + escapeAttr(errorMessage) + '"' : "") +
      ">" +
      (labels[status] || status) +
      "</span>";
    if (status === "failed" && errorMessage) {
      html +=
        '<p class="tt-error-hint">' + escapeHtml(String(errorMessage)) + "</p>";
    }
    return html;
  }

  function getOptions() {
    var opts = {};
    root.querySelectorAll("[data-tt-opt]").forEach(function (input) {
      opts[input.getAttribute("data-tt-opt")] = input.checked;
    });
    return opts;
  }

  function filteredReports() {
    var q = state.searchQuery.trim().toLowerCase();
    if (!q) {
      return state.reports;
    }
    return state.reports.filter(function (r) {
      return r.id.toLowerCase().includes(q) || r.filename.toLowerCase().includes(q);
    });
  }

  function renderCredits() {
    if (typeof state.credits !== "number" || isNaN(state.credits)) {
      return;
    }
    var els2 = document.querySelectorAll("[data-coin-balance]");
    var formatted = typeof window.formatCoinBalance === "function"
      ? window.formatCoinBalance(state.credits)
      : state.credits.toLocaleString("en-US");
    Array.prototype.forEach.call(els2, function (el) {
      el.textContent = formatted;
    });
    if (els.credits && !els.credits.hasAttribute("data-coin-balance")) {
      els.credits.textContent = formatted;
    }
  }

  function syncCreditsFromServer() {
    if (typeof window.refreshCoinBalance === "function") {
      return window.refreshCoinBalance().then(function (d) {
        if (d && typeof d.balance === "number") {
          state.credits = d.balance;
          renderCredits();
        }
        return d;
      });
    }
    return fetch("/api/economy/balance", { headers: { Accept: "application/json" } })
      .then(function (r) {
        return r.json();
      })
      .then(function (d) {
        if (d && typeof d.balance === "number") {
          state.credits = d.balance;
          renderCredits();
        }
        return d;
      })
      .catch(function () {});
  }

  function renderTable() {
    if (!els.reportsBody) {
      return;
    }
    var hasReports = state.reports.length > 0;
    var rows = filteredReports();
    var searchMiss = hasReports && rows.length === 0;

    if (els.emptyZero) {
      els.emptyZero.hidden = hasReports;
    }
    if (els.submitToolbar) {
      els.submitToolbar.hidden = !hasReports;
    }
    if (els.optionsRow) {
      els.optionsRow.hidden = !hasReports;
    }
    if (els.submitBtn) {
      els.submitBtn.hidden = !hasReports;
    }
    if (els.search) {
      var searchWrap = els.search.closest(".tt-search-wrap");
      if (searchWrap) {
        searchWrap.hidden = !hasReports;
      }
    }
    if (els.table) {
      els.table.hidden = !hasReports;
    }
    if (els.empty) {
      els.empty.hidden = !searchMiss;
    }
    if (els.footnote) {
      els.footnote.hidden = !hasReports;
    }
    var stillPending = state.reports.some(function (report) {
      if (report.status === "queued" || report.status === "running") return true;
      var hs = report.highlightsStatus;
      if (hs === "queued" || hs === "running" || !!state.highlightsPending[report.id]) return true;
      if (report.status === "completed") {
        if (isOfficialTurnitin(report)) return false;
        if (!report.hasSimilarityReport) return true;
        if (!report.hasAiReport && !report.aiUnavailable) return true;
      }
      return false;
    });
    if (!stillPending && els.submitStatus) {
      var st = els.submitStatus.textContent || "";
      if (/Queued\. Checking/i.test(st) || /files queued\. Checking/i.test(st)) {
        setStatusText("");
      }
    }

    els.reportsBody.innerHTML = rows
      .map(function (report) {
        return (
          "<tr data-tt-row=\"" +
          report.id +
          "\">" +
          '<td class="tt-cell-id">#' +
          report.id +
          "</td>" +
          '<td class="tt-cell-filename" title="' +
          escapeAttr(report.filename) +
          '">' +
          escapeHtml(report.filename) +
          "</td>" +
          '<td class="tt-cell-score">' +
          formatScoreCell(report, "similarity", "similarityDisplay", "similarity", "similarity") +
          "</td>" +
          '<td class="tt-cell-score">' +
          formatScoreCell(report, "aiScore", "aiScoreDisplay", "ai", "ai") +
          "</td>" +
          '<td class="tt-cell-score">' +
          formatHighlightsCell(report) +
          "</td>" +
          "<td>" +
          statusBadge(report.status, report.errorMessage) +
          "</td>" +
          '<td class="tt-cell-date">' +
          formatDate(report.createdAt) +
          "</td>" +
          '<td><div class="tt-actions">' +
          '<button type="button" class="tt-action-btn tt-action-btn--danger" data-tt-delete="' +
          report.id +
          '" title="Delete"><svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 7h16M9 7V5h6v2M7 7l1 14h8l1-14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
          "</div></td></tr>"
        );
      })
      .join("");
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function escapeAttr(str) {
    return escapeHtml(str);
  }

  function setFiles(files) {
    state.selectedFiles = files && files.length ? Array.prototype.slice.call(files) : [];
    if (els.filename) {
      if (state.selectedFiles.length === 1) {
        els.filename.hidden = false;
        els.filename.textContent = state.selectedFiles[0].name;
      } else if (state.selectedFiles.length > 1) {
        els.filename.hidden = false;
        els.filename.textContent = state.selectedFiles.length + " files selected";
      } else {
        els.filename.hidden = true;
        els.filename.textContent = "";
      }
    }
    if (els.submitStatus && !state.selectedFiles.length) {
      setStatusText("");
    }
  }

  function reportUrl(id, kind) {
    return "/api/turnitin/submissions/" + encodeURIComponent(id) + "/report/" + kind;
  }

  function downloadReport(id, kind) {
    if (!id) {
      return;
    }
    window.location.href = reportUrl(id, kind || "similarity");
  }

  function mergeReport(existing, incoming) {
    if (!existing) {
      return incoming;
    }
    Object.keys(incoming).forEach(function (k) {
      existing[k] = incoming[k];
    });
    return existing;
  }

  function upsertReport(report) {
    var prev = state.reports.find(function (r) {
      return r.id === report.id;
    });
    var idx = state.reports.findIndex(function (r) {
      return r.id === report.id;
    });
    if (idx >= 0) {
      state.reports[idx] = mergeReport(state.reports[idx], report);
    } else {
      state.reports.unshift(report);
    }
    if (
      report.highlightsStatus === "completed" ||
      report.highlightsStatus === "failed" ||
      report.aiHighlightsDisplay
    ) {
      delete state.highlightsPending[report.id];
    }
    renderTable();
    if (
      report.status === "queued" ||
      report.status === "running" ||
      report.status === "processing"
    ) {
      if (prev && prev.status === "failed") {
        clearFeedback();
        setStatusText("Retrying your check automatically…");
      }
    }
    if (report.status === "failed" && (!prev || prev.status !== "failed")) {
      var meta = report.meta || {};
      var human = humanizeServiceError(
        meta.error_code || meta.error || "",
        report.errorMessage || ""
      );
      if (human) {
        setStatusText(human.body + " Credits were refunded if the check did not finish.");
        showSubmitError(human.body, human.detail, function () {
          if (els.fileInput) els.fileInput.click();
        });
      }
    }
  }

  function submitOneFile(file, options) {
    var fd = new FormData();
    fd.append("file", file);
    Object.keys(options).forEach(function (k) {
      fd.append(k, options[k] ? "1" : "0");
    });
    return fetch(TURNITIN_CHECK_URL, { method: "POST", body: fd }).then(function (res) {
      return res
        .json()
        .catch(function () { return {}; })
        .then(function (data) { return { status: res.status, ok: res.ok, data: data, file: file }; });
    });
  }

  function handleSubmitResult(r, acc) {
    if (r.status === 402 || (r.data && r.data.error === "INSUFFICIENT_COINS")) {
      acc.failCount += 1;
      var amounts = window.dmStates
        ? window.dmStates.parseCreditAmounts(
            r.data && r.data.message,
            CREDITS_PER_CHECK,
            typeof state.credits === "number" ? state.credits : "—"
          )
        : {
            required: CREDITS_PER_CHECK,
            balance: typeof state.credits === "number" ? state.credits : "—",
          };
      if (r.data && typeof r.data.required === "number") amounts.required = r.data.required;
      if (r.data && typeof r.data.balance === "number") amounts.balance = r.data.balance;
      showCreditsNeeded(amounts.required, amounts.balance);
      return acc;
    }
    if (!r.ok || !r.data || !r.data.success) {
      acc.failCount += 1;
      var code = r.data && r.data.error;
      var metaCode =
        r.data && r.data.meta && (r.data.meta.error_code || r.data.meta.error);
      var rawMsg = (r.data && (r.data.message || r.data.error_message)) || "";
      var human = humanizeServiceError(metaCode || code, rawMsg || code);
      if (human) {
        acc.lastError = human;
      } else {
        acc.lastError = {
          body: "Submission failed. Please try again.",
          detail: code || ("HTTP " + r.status),
        };
      }
      return acc;
    }
    if (typeof r.data.balance === "number") {
      acc.lastBalance = r.data.balance;
      state.credits = r.data.balance;
    }
    upsertReport({
      id: r.data.submission_id,
      filename: r.file.name,
      similarity: null,
      aiScore: null,
      aiHighlights: null,
      status: r.data.status || "queued",
      createdAt: new Date().toISOString(),
      hasReport: false,
    });
    acc.okCount += 1;
    return acc;
  }

  function finishSubmitBatch(acc) {
    if (els.submitBtn) els.submitBtn.disabled = false;
    if (typeof acc.lastBalance === "number") {
      state.credits = acc.lastBalance;
    }
    if (typeof window.refreshCoinBalance === "function") {
      window.refreshCoinBalance();
    }
    renderCredits();
    if (els.fileInput) els.fileInput.value = "";
    setFiles([]);
    schedulePoll();
    if (acc.okCount && !acc.failCount) {
      clearFeedback();
      setStatusText(
        acc.okCount === 1
          ? "Queued. Checking on PlagDetect…"
          : acc.okCount + " files queued. Checking on PlagDetect…"
      );
    } else if (acc.okCount && acc.failCount) {
      clearFeedback();
      setStatusText(acc.okCount + " queued, " + acc.failCount + " failed.");
    } else if (acc.failCount) {
      if (acc.lastError) {
        showSubmitError(acc.lastError.body, acc.lastError.detail);
      } else if (!els.feedback || els.feedback.hidden) {
        showSubmitError(
          "We couldn’t submit your file. Your credits weren’t charged. Try again.",
          ""
        );
      }
    }
    return acc;
  }

  function submitCheck() {
    if (!state.selectedFiles.length) {
      showSubmitError("Choose a DOC, DOCX, PDF, or TXT file to check.", "", function () {
        if (els.fileInput) els.fileInput.click();
      });
      return;
    }
    var files = state.selectedFiles.slice();
    var needed = files.length * CREDITS_PER_CHECK;

    function runWithCredits() {
      if (typeof state.credits !== "number" || state.credits < needed) {
        showCreditsNeeded(
          needed,
          typeof state.credits === "number" ? state.credits : "—"
        );
        return;
      }
      clearFeedback();
      if (els.submitBtn) {
        els.submitBtn.disabled = true;
      }
      setStatusText(
        files.length === 1
          ? "Uploading…"
          : "Uploading " + files.length + " files…"
      );
      var options = getOptions();
      var chain = Promise.resolve({ okCount: 0, failCount: 0, lastBalance: state.credits, lastError: null });
      files.forEach(function (file) {
        chain = chain.then(function (acc) {
          return submitOneFile(file, options).then(function (r) {
            if (
              r.data &&
              (r.data.error === "AUTH_REQUIRED" || r.data.error === "REGISTER_REQUIRED") &&
              window.DMAuth
            ) {
              return window.DMAuth.require({
                reason:
                  (r.data && r.data.message) ||
                  "Create a free account to run a Turnitin check.",
              })
                .then(function () {
                  return submitOneFile(file, options);
                })
                .then(function (r2) {
                  return handleSubmitResult(r2, acc);
                })
                .catch(function () {
                  acc.failCount += 1;
                  showSubmitError(
                    "Sign in to run a Turnitin check. Nothing was charged.",
                    "AUTH_REQUIRED"
                  );
                  return acc;
                });
            }
            return handleSubmitResult(r, acc);
          });
        });
      });
      chain
        .then(finishSubmitBatch)
        .catch(function () {
          if (els.submitBtn) els.submitBtn.disabled = false;
          showSubmitError(
            "Network error. Check your connection and try again. Your credits weren’t charged if the upload didn’t start.",
            ""
          );
        });
    }

    if (typeof state.credits !== "number") {
      syncCreditsFromServer().then(runWithCredits);
    } else {
      runWithCredits();
    }
  }

  function needsPolling() {
    return state.reports.some(isReportPending);
  }

  function schedulePoll() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
    if (!needsPolling()) {
      return;
    }
    state.pollTimer = setInterval(pollActive, POLL_MS);
  }

  function pollOne(id) {
    return fetch("/api/turnitin/submissions/" + encodeURIComponent(id), {
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (r) {
        if (r.ok && r.data && r.data.report) {
          upsertReport(r.data.report);
        }
      });
  }

  function pollActive() {
    var pending = state.reports.filter(isReportPending);
    if (!pending.length) {
      schedulePoll();
      return;
    }
    Promise.all(pending.map(function (r) { return pollOne(r.id); })).then(schedulePoll);
  }

  function loadReports() {
    return fetch(TURNITIN_REPORTS_URL, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (data) {
          return { ok: res.ok, status: res.status, data: data };
        });
      })
      .then(function (r) {
        if (r.status === 401 && window.DMAuth) {
          return;
        }
        if (r.ok && r.data && r.data.reports) {
          state.reports = r.data.reports.slice();
          renderTable();
          schedulePoll();
        }
      })
      .catch(function () {});
  }

  function requestHighlights(id) {
    if (!id || state.highlightsPending[id]) {
      return;
    }
    state.highlightsPending[id] = true;
    renderTable();
    if (typeof setStatusText === "function") {
      setStatusText("Requesting AI Highlights… this can take a minute.");
    }

    fetch("/api/turnitin/submissions/" + encodeURIComponent(id) + "/highlights", {
      method: "POST",
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () { return {}; })
          .then(function (data) { return { ok: res.ok, status: res.status, data: data }; });
      })
      .then(function (r) {
        if (!r.ok || !r.data || !r.data.success) {
          delete state.highlightsPending[id];
          renderTable();
          var msg = (r.data && (r.data.error || r.data.message)) || "";
          var human = humanizeServiceError(msg, msg);
          showSubmitError(
            (human && human.body) ||
              "Couldn’t start AI Highlights. Nothing extra was charged.",
            (human && human.detail) || msg || ("HTTP " + r.status)
          );
          if (typeof setStatusText === "function") setStatusText("");
          return;
        }
        if (r.data.viewer_url) {
          try {
            window.open(r.data.viewer_url, "_blank", "noopener");
          } catch (err) {}
        }
        if (r.data.report) {
          upsertReport(r.data.report);
        } else {
          upsertReport({ id: id, highlightsStatus: r.data.highlights_status || "queued" });
        }
        schedulePoll();
      })
      .catch(function () {
        delete state.highlightsPending[id];
        renderTable();
        showSubmitError(
          "Network error while requesting AI Highlights. Try again.",
          ""
        );
      });
  }

  function deleteReport(id) {
    fetch("/api/turnitin/submissions/" + encodeURIComponent(id), { method: "DELETE" })
      .then(function (res) { return res.json().catch(function () { return {}; }); })
      .then(function () {
        state.reports = state.reports.filter(function (r) {
          return r.id !== id;
        });
        delete state.highlightsPending[id];
        renderTable();
        schedulePoll();
      });
  }

  function isReportPending(report) {
    if (report.status === "queued" || report.status === "running") {
      return true;
    }
    var hs = report.highlightsStatus;
    if (hs === "queued" || hs === "running" || !!state.highlightsPending[report.id]) {
      return true;
    }
    // Keep polling until PDFs are attached after scores complete.
    if (report.status === "completed" && isOfficialTurnitin(report)) {
      return false;
    }
    if (
      report.status === "completed" &&
      (!report.hasSimilarityReport || (!report.hasAiReport && !report.aiUnavailable))
    ) {
      return true;
    }
    return false;
  }

  if (els.submitBtn && els.fileInput) {
    els.submitBtn.addEventListener("click", function () {
      els.fileInput.click();
    });

    els.fileInput.addEventListener("change", function () {
      var list = els.fileInput.files;
      if (!list || !list.length) {
        return;
      }
      setFiles(list);
      submitCheck();
    });
  }

  var emptyCta = root.querySelector("[data-tt-empty-cta]") || root.querySelector(".tt-empty-cta");
  if (emptyCta && els.fileInput) {
    emptyCta.addEventListener("click", function () {
      els.fileInput.click();
    });
  }

  (function setupDragDrop() {
    var overlay = root.querySelector("[data-tt-drop-overlay]");
    var dragDepth = 0;

    function setDropOverlay(on) {
      if (overlay) {
        if (on) {
          overlay.hidden = false;
          overlay.removeAttribute("hidden");
        } else {
          overlay.hidden = true;
        }
      }
      root.classList.toggle("is-dragging-files", !!on);
    }

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
      setFiles(files);
      submitCheck();
    }

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
  })();

  if (els.search) {
    els.search.addEventListener("input", function () {
      state.searchQuery = els.search.value;
      renderTable();
    });
  }

  if (els.reportsBody) {
    els.reportsBody.addEventListener("click", function (e) {
      var dlBtn = e.target.closest("[data-tt-download]");
      var delBtn = e.target.closest("[data-tt-delete]");
      var hlBtn = e.target.closest("[data-tt-get-highlights]");

      if (dlBtn) {
        downloadReport(dlBtn.getAttribute("data-tt-download"), dlBtn.getAttribute("data-tt-kind") || "similarity");
      } else if (hlBtn) {
        requestHighlights(hlBtn.getAttribute("data-tt-get-highlights"));
      } else if (delBtn) {
        deleteReport(delBtn.getAttribute("data-tt-delete"));
      }
    });
  }

  renderCredits();
  syncCreditsFromServer();
  loadReports();
})();
