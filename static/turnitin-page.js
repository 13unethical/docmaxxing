/**
 * Turnitin page — PlagDetect integration (browser automation backend).
 */
(function () {
  "use strict";

  var CREDITS_PER_CHECK = 25;
  var TURNITIN_CHECK_URL = "/api/turnitin/check";
  var TURNITIN_REPORTS_URL = "/api/turnitin/reports";
  var POLL_MS = 2000;

  var root = document.querySelector("[data-turnitin-page]");
  if (!root) {
    return;
  }

  function readInitialCredits() {
    var el = document.querySelector("[data-tt-credits]");
    var n = el ? parseInt(el.textContent, 10) : 0;
    return isNaN(n) ? 0 : n;
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
    reportsBody: root.querySelector("[data-tt-reports-body]"),
    search: root.querySelector("[data-tt-search]"),
    empty: root.querySelector("[data-tt-empty]"),
  };

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

  function highlightsEligible(report) {
    if (report.status !== "completed") return false;
    if (report.hasHighlightsReport || report.aiHighlightsDisplay || report.aiHighlights != null) {
      return false;
    }
    return report.aiScoreDisplay === "*%";
  }

  function formatHighlightsCell(report) {
    var label = scoreDisplay(report, "aiHighlights", "aiHighlightsDisplay");
    if (label) {
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

  function statusBadge(status) {
    var labels = {
      queued: "Queued",
      running: "Running",
      completed: "Completed",
      failed: "Failed",
    };
    return (
      '<span class="tt-badge tt-badge--' +
      status +
      '">' +
      (labels[status] || status) +
      "</span>"
    );
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
    var els2 = document.querySelectorAll("[data-coin-balance]");
    Array.prototype.forEach.call(els2, function (el) {
      el.textContent = String(state.credits);
    });
    if (els.credits && !els.credits.hasAttribute("data-coin-balance")) {
      els.credits.textContent = String(state.credits);
    }
  }

  function renderTable() {
    if (!els.reportsBody) {
      return;
    }
    var rows = filteredReports();
    if (els.empty) {
      els.empty.hidden = rows.length > 0;
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
          statusBadge(report.status) +
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
      els.submitStatus.textContent = "";
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

  function submitCheck() {
    if (!state.selectedFiles.length) {
      return;
    }
    var files = state.selectedFiles.slice();
    var needed = files.length * CREDITS_PER_CHECK;
    if (state.credits < needed) {
      if (els.submitStatus) {
        els.submitStatus.textContent =
          "Not enough coins. Need " + needed + ", have " + state.credits + ".";
      }
      return;
    }

    var options = getOptions();
    if (els.submitBtn) {
      els.submitBtn.disabled = true;
    }
    if (els.submitStatus) {
      els.submitStatus.textContent =
        files.length === 1 ? "Submitting…" : "Submitting " + files.length + " files…";
    }

    var chain = Promise.resolve({ okCount: 0, failCount: 0, lastBalance: state.credits });
    files.forEach(function (file) {
      chain = chain.then(function (acc) {
        return submitOneFile(file, options).then(function (r) {
          if (
            (r.data && (r.data.error === "AUTH_REQUIRED" || r.data.error === "REGISTER_REQUIRED")) &&
            window.DMAuth
          ) {
            return window.DMAuth.require({
              reason: (r.data && r.data.message) || "Create a free account to run a Turnitin check.",
            }).then(function () {
              return submitOneFile(file, options);
            }).then(function (r2) {
              return handleSubmitResult(r2, acc);
            }).catch(function () {
              acc.failCount += 1;
              return acc;
            });
          }
          return handleSubmitResult(r, acc);
        });
      });
    });

    function handleSubmitResult(r, acc) {
      if (r.status === 402 || (r.data && r.data.error === "INSUFFICIENT_COINS")) {
        acc.failCount += 1;
        if (els.submitStatus) {
          els.submitStatus.textContent =
            (r.data && r.data.message) || "Not enough coins. Buy coins to continue.";
        }
        return acc;
      }
        if (!r.ok || !r.data || !r.data.success) {
          acc.failCount += 1;
          if (els.submitStatus) {
            els.submitStatus.textContent =
              (r.data && (r.data.error || r.data.message)) ||
              ("Submission failed (HTTP " + r.status + "). Please try again.");
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

    chain
      .then(function (acc) {
        if (els.submitBtn) els.submitBtn.disabled = false;
        state.credits = acc.lastBalance;
        if (typeof window.refreshCoinBalance === "function") {
          window.refreshCoinBalance();
        }
        renderCredits();
        if (els.fileInput) els.fileInput.value = "";
        setFiles([]);
        schedulePoll();
        if (els.submitStatus) {
          if (acc.okCount && !acc.failCount) {
            els.submitStatus.textContent =
              acc.okCount === 1
                ? "Queued. Checking on PlagDetect…"
                : acc.okCount + " files queued. Checking on PlagDetect…";
          } else if (acc.okCount && acc.failCount) {
            els.submitStatus.textContent =
              acc.okCount + " queued, " + acc.failCount + " failed.";
          } else if (acc.failCount) {
            els.submitStatus.textContent = "Submission failed. Please try again.";
          }
        }
      })
      .catch(function () {
        if (els.submitBtn) els.submitBtn.disabled = false;
        if (els.submitStatus) {
          els.submitStatus.textContent = "Network error. Please try again.";
        }
      });
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
          if (els.submitStatus) {
            els.submitStatus.textContent =
              (r.data && r.data.error) || "Could not request AI Highlights.";
          }
          return;
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
        if (els.submitStatus) {
          els.submitStatus.textContent = "Network error while requesting AI Highlights.";
        }
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
    if (
      report.status === "completed" &&
      (!report.hasSimilarityReport || !report.hasAiReport)
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
  loadReports();
})();
