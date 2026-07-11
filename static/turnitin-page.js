/**
 * Turnitin page — frontend only.
 * Replace DEMO_REPORTS + local state with API responses when backend is ready.
 */
(function () {
  "use strict";

  var CREDITS_PER_CHECK = 25;

  /** Demo seed data — replace with GET /api/turnitin/reports */
  var DEMO_REPORTS = [
    {
      id: "103806",
      filename: "Final_Essay.docx",
      similarity: 12,
      aiScore: 19,
      status: "completed",
      createdAt: "2026-06-23T19:33:00",
      pages: 14,
      wordCount: 2840,
      processingTime: "2m 14s",
      hasReport: true,
    },
    {
      id: "103791",
      filename: "Literature_Review.pdf",
      similarity: 5,
      aiScore: 8,
      status: "completed",
      createdAt: "2026-06-20T11:02:00",
      pages: 22,
      wordCount: 5120,
      processingTime: "1m 48s",
      hasReport: true,
    },
    {
      id: "103784",
      filename: "Draft_v3.docx",
      similarity: null,
      aiScore: null,
      status: "running",
      createdAt: "2026-06-19T16:45:00",
      pages: null,
      wordCount: null,
      processingTime: null,
      hasReport: false,
    },
    {
      id: "103770",
      filename: "Case_Study.doc",
      similarity: null,
      aiScore: null,
      status: "queued",
      createdAt: "2026-06-18T09:15:00",
      pages: null,
      wordCount: null,
      processingTime: null,
      hasReport: false,
    },
    {
      id: "103755",
      filename: "corrupted_upload.txt",
      similarity: null,
      aiScore: null,
      status: "failed",
      createdAt: "2026-06-15T14:20:00",
      pages: null,
      wordCount: null,
      processingTime: null,
      hasReport: false,
      errorMessage: "File could not be processed",
    },
  ];

  var root = document.querySelector("[data-turnitin-page]");
  if (!root) {
    return;
  }

  var state = {
    reports: DEMO_REPORTS.slice(),
    credits: 120,
    selectedFile: null,
    activeReportId: null,
    searchQuery: "",
    nextId: 103807,
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
    drawer: root.querySelector("[data-tt-drawer]"),
    drawerBackdrop: root.querySelector("[data-tt-drawer-backdrop]"),
    drawerBody: root.querySelector("[data-tt-drawer-body]"),
    drawerClose: root.querySelector("[data-tt-drawer-close]"),
    drawerDlPdf: root.querySelector("[data-tt-drawer-dl-pdf]"),
    drawerOpen: root.querySelector("[data-tt-drawer-open]"),
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

  function formatScore(value, type) {
    if (value === null || value === undefined) {
      return '<span class="tt-score tt-score--pending">—</span>';
    }
    var cls = type === "ai" ? "tt-score--ai" : "tt-score--similarity";
    return '<span class="tt-score ' + cls + '">' + value + "%</span>";
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

  function findReport(id) {
    return state.reports.find(function (r) {
      return r.id === id;
    });
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
    if (els.credits) {
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
        var canView = report.status === "completed" && report.hasReport;
        var canDownload = canView;
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
          "<td>" +
          formatScore(report.similarity, "similarity") +
          "</td>" +
          "<td>" +
          formatScore(report.aiScore, "ai") +
          "</td>" +
          "<td>" +
          statusBadge(report.status) +
          "</td>" +
          '<td class="tt-cell-date">' +
          formatDate(report.createdAt) +
          "</td>" +
          '<td><div class="tt-actions">' +
          '<button type="button" class="tt-action-btn" data-tt-view="' +
          report.id +
          '" title="View Report"' +
          (canView ? "" : " disabled") +
          '><svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7-10-7-10-7z" stroke="currentColor" stroke-width="1.6"/><circle cx="12" cy="12" r="3" stroke="currentColor" stroke-width="1.6"/></svg></button>' +
          '<button type="button" class="tt-action-btn" data-tt-download="' +
          report.id +
          '" title="Download PDF"' +
          (canDownload ? "" : " disabled") +
          '><svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M12 4v10m0 0l-3.5-3.5M12 14l3.5-3.5M5 20h14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg></button>' +
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

  function setFile(file) {
    state.selectedFile = file || null;
    if (els.filename) {
      if (file) {
        els.filename.hidden = false;
        els.filename.textContent = file.name;
      } else {
        els.filename.hidden = true;
        els.filename.textContent = "";
      }
    }
    if (els.submitStatus && !file) {
      els.submitStatus.textContent = "";
    }
  }

  function openDrawer(reportId) {
    var report = findReport(reportId);
    if (!report || !els.drawer || !els.drawerBody) {
      return;
    }
    state.activeReportId = reportId;
    var canOpen = report.status === "completed" && report.hasReport;

    els.drawerBody.innerHTML =
      '<dl class="tt-drawer-meta">' +
      metaRow("Filename", report.filename) +
      metaRow("Submission date", formatDate(report.createdAt)) +
      metaRow(
        "Similarity Score",
        report.similarity !== null ? report.similarity + "%" : "—"
      ) +
      metaRow("AI Score", report.aiScore !== null ? report.aiScore + "%" : "—") +
      metaRow("Pages", report.pages !== null ? String(report.pages) : "—") +
      metaRow(
        "Word Count",
        report.wordCount !== null ? report.wordCount.toLocaleString() : "—"
      ) +
      metaRow(
        "Processing time",
        report.processingTime || "—"
      ) +
      (report.errorMessage
        ? metaRow("Error", report.errorMessage)
        : "") +
      "</dl>";

    if (els.drawerDlPdf) {
      els.drawerDlPdf.disabled = !canOpen;
    }
    if (els.drawerOpen) {
      els.drawerOpen.disabled = !canOpen;
    }

    els.drawer.hidden = false;
    if (els.drawerBackdrop) {
      els.drawerBackdrop.hidden = false;
      requestAnimationFrame(function () {
        els.drawerBackdrop.classList.add("is-visible");
        els.drawer.classList.add("is-open");
      });
    }
    document.body.style.overflow = "hidden";
  }

  function metaRow(label, value) {
    return (
      "<div><dt>" +
      escapeHtml(label) +
      "</dt><dd>" +
      escapeHtml(value) +
      "</dd></div>"
    );
  }

  function closeDrawer() {
    if (!els.drawer) {
      return;
    }
    els.drawer.classList.remove("is-open");
    if (els.drawerBackdrop) {
      els.drawerBackdrop.classList.remove("is-visible");
    }
    setTimeout(function () {
      if (els.drawer) {
        els.drawer.hidden = true;
      }
      if (els.drawerBackdrop) {
        els.drawerBackdrop.hidden = true;
      }
      state.activeReportId = null;
      document.body.style.overflow = "";
    }, 220);
  }

  function submitCheck() {
    if (!state.selectedFile) {
      return;
    }
    if (state.credits < CREDITS_PER_CHECK) {
      if (els.submitStatus) {
        els.submitStatus.textContent = "Not enough credits. Buy credits to continue.";
      }
      return;
    }

    var options = getOptions();

    var id = String(state.nextId++);
    var report = {
      id: id,
      filename: state.selectedFile.name,
      similarity: null,
      aiScore: null,
      status: "queued",
      createdAt: new Date().toISOString(),
      pages: null,
      wordCount: null,
      processingTime: null,
      hasReport: false,
      options: options,
    };

    state.reports.unshift(report);
    state.credits -= CREDITS_PER_CHECK;

    if (els.submitStatus) {
      els.submitStatus.textContent =
        "Submission #" + id + " queued. Results will appear when processing completes.";
    }

    if (els.fileInput) {
      els.fileInput.value = "";
    }
    setFile(null);
    renderCredits();
    renderTable();

    // Demo status progression — remove when API provides webhooks/polling.
    setTimeout(function () {
      updateReportStatus(id, "running");
    }, 1500);
    setTimeout(function () {
      updateReportStatus(id, "completed", {
        similarity: null,
        aiScore: null,
        pages: null,
        wordCount: null,
        processingTime: null,
        hasReport: false,
      });
      if (els.submitStatus) {
        els.submitStatus.textContent =
          "Submission #" + id + " completed. Awaiting report from Turnitin API.";
      }
    }, 5000);
  }

  function updateReportStatus(id, status, patch) {
    var report = findReport(id);
    if (!report) {
      return;
    }
    report.status = status;
    if (patch) {
      Object.keys(patch).forEach(function (key) {
        report[key] = patch[key];
      });
    }
    renderTable();
    if (state.activeReportId === id) {
      openDrawer(id);
    }
  }

  function deleteReport(id) {
    state.reports = state.reports.filter(function (r) {
      return r.id !== id;
    });
    if (state.activeReportId === id) {
      closeDrawer();
    }
    renderTable();
  }

  // —— Events ——

  if (els.submitBtn && els.fileInput) {
    els.submitBtn.addEventListener("click", function () {
      els.fileInput.click();
    });

    els.fileInput.addEventListener("change", function () {
      var file = els.fileInput.files && els.fileInput.files[0];
      if (!file) {
        return;
      }
      setFile(file);
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
      var viewBtn = e.target.closest("[data-tt-view]");
      var dlBtn = e.target.closest("[data-tt-download]");
      var delBtn = e.target.closest("[data-tt-delete]");

      if (viewBtn) {
        openDrawer(viewBtn.getAttribute("data-tt-view"));
      } else if (dlBtn) {
        var id = dlBtn.getAttribute("data-tt-download");
        if (els.submitStatus) {
          els.submitStatus.textContent = "PDF download for #" + id + " connects to API.";
        }
      } else if (delBtn) {
        deleteReport(delBtn.getAttribute("data-tt-delete"));
      }
    });
  }

  if (els.drawerClose) {
    els.drawerClose.addEventListener("click", closeDrawer);
  }
  if (els.drawerBackdrop) {
    els.drawerBackdrop.addEventListener("click", closeDrawer);
  }
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && state.activeReportId) {
      closeDrawer();
    }
  });

  if (els.drawerDlPdf) {
    els.drawerDlPdf.addEventListener("click", function () {
      if (state.activeReportId && els.submitStatus) {
        els.submitStatus.textContent =
          "PDF download for #" + state.activeReportId + " connects to API.";
      }
    });
  }
  if (els.drawerOpen) {
    els.drawerOpen.addEventListener("click", function () {
      if (state.activeReportId && els.submitStatus) {
        els.submitStatus.textContent =
          "Open report for #" + state.activeReportId + " connects to API.";
      }
    });
  }

  renderCredits();
  renderTable();
})();
