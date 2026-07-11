/**
 * Assignment Workspace — realtime status + timeline monitor.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-workspace]");
  if (!root) return;

  var PROJECT_KEY = "docmaxxing_workspace_project_id";
  var POLL_MS = 4000;

  var STAGES = [
    { key: "UPLOADED", label: "Uploaded Files" },
    { key: "REQUIREMENTS_READY", label: "Requirements" },
    { key: "RESEARCH_READY", label: "Research" },
    { key: "BLUEPRINT_READY", label: "Blueprint" },
    { key: "WRITING", label: "Draft" },
    { key: "FINAL_REVIEW", label: "Review" },
    { key: "EXPORTING", label: "Export" },
  ];

  var state = {
    projectId: null,
    projectName: "Assignment Project",
    status: null,
    timeline: [],
    projectData: null,
    pollTimer: null,
    startedAt: null,
  };

  function $(sel) {
    return root.querySelector(sel);
  }

  function safeText(value, fallback) {
    if (value === null || value === undefined || value === "") return fallback || "-";
    return String(value);
  }

  function stageName(raw) {
    if (!raw) return "Waiting";
    return String(raw).replace(/_/g, " ").toLowerCase().replace(/\b\w/g, function (m) {
      return m.toUpperCase();
    });
  }

  function formatTime(value) {
    if (!value) return "--:--";
    var d = new Date(value);
    if (Number.isNaN(d.getTime())) return "--:--";
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  function formatDuration(ms) {
    if (!ms || ms <= 0) return "0s";
    var s = Math.floor(ms / 1000);
    if (s < 60) return s + "s";
    var m = Math.floor(s / 60);
    var rem = s % 60;
    return m + "m " + rem + "s";
  }

  function parseProjectId() {
    var params = new URLSearchParams(window.location.search);
    var fromQuery = params.get("project_id");
    if (fromQuery) return fromQuery.trim();
    try {
      return (localStorage.getItem(PROJECT_KEY) || "").trim();
    } catch (e) {
      return "";
    }
  }

  function saveProjectId(projectId) {
    state.projectId = projectId;
    try {
      localStorage.setItem(PROJECT_KEY, projectId);
    } catch (e) {
      /* ignore localStorage failures */
    }
  }

  function updateHeader() {
    var nameEl = $("[data-ws-project-name]");
    if (nameEl) nameEl.textContent = state.projectName + (state.projectId ? " · " + state.projectId : "");
  }

  function renderLeftSidebar() {
    var list = $("[data-ws-stage-list]");
    if (!list) return;

    var completed = (state.status && state.status.completed_steps) || [];
    var current = state.status && state.status.current_stage;
    list.innerHTML = STAGES.map(function (item) {
      var isDone = completed.indexOf(item.key) >= 0;
      var isCurrent = current === item.key;
      var mark = isDone ? "✓" : isCurrent ? "●" : "○";
      var cls = isDone ? "is-completed" : isCurrent ? "is-current" : "is-pending";
      return '<li class="ws-stage-item ' + cls + '">' + mark + " " + item.label + "</li>";
    }).join("");
  }

  function renderCenter() {
    var status = state.status || {};
    var currentStage = status.current_stage;
    var timeline = state.timeline || [];
    var last = timeline.length ? timeline[timeline.length - 1] : null;

    var stageEl = $("[data-ws-current-stage]");
    if (stageEl) stageEl.textContent = stageName(currentStage);

    var fill = $("[data-ws-progress-fill]");
    var label = $("[data-ws-progress-label]");
    var p = Math.max(0, Math.min(100, Number(status.progress || 0)));
    if (fill) fill.style.width = p + "%";
    if (label) label.textContent = p + "%";

    var taskEl = $("[data-ws-current-task]");
    if (taskEl) {
      taskEl.textContent = last ? (last.status === "running" ? "Running " : "Completed ") + stageName(last.stage) : "-";
    }
    var modelEl = $("[data-ws-current-model]");
    if (modelEl) modelEl.textContent = safeText(last && last.model_used, "-");

    var remainEl = $("[data-ws-est-remaining]");
    if (remainEl) remainEl.textContent = safeText(status.estimated_remaining_time, "-");
  }

  function renderRightSummary() {
    var requirement = state.projectData && state.projectData.requirement;
    var latest = state.timeline.length ? state.timeline[state.timeline.length - 1] : null;

    var typeEl = $("[data-ws-assignment-type]");
    if (typeEl) typeEl.textContent = safeText(requirement && requirement.assignment_type, "-");
    var wcEl = $("[data-ws-word-count]");
    if (wcEl) wcEl.textContent = safeText(requirement && requirement.word_count, "-");
    var citeEl = $("[data-ws-citation-style]");
    if (citeEl) citeEl.textContent = safeText(requirement && requirement.citation_style, "-");
    var deadlineEl = $("[data-ws-deadline]");
    if (deadlineEl) deadlineEl.textContent = safeText(requirement && requirement.deadline, "-");
    var aiEl = $("[data-ws-current-ai-model]");
    if (aiEl) aiEl.textContent = safeText(latest && latest.model_used, "-");

    var creditsEl = $("[data-ws-credits-used]");
    if (creditsEl) {
      var used = state.timeline.filter(function (x) {
        return x.success;
      }).length;
      creditsEl.textContent = String(used);
    }

    var elapsedEl = $("[data-ws-time-elapsed]");
    if (elapsedEl) {
      var started = state.startedAt ? new Date(state.startedAt).getTime() : NaN;
      if (!Number.isNaN(started)) {
        elapsedEl.textContent = formatDuration(Date.now() - started);
      } else {
        elapsedEl.textContent = "-";
      }
    }
  }

  function feedDescription(entry) {
    if (entry.error) return entry.error;
    if (entry.status === "running") return stageName(entry.stage) + " in progress";
    if (entry.success) return stageName(entry.stage) + " completed";
    if (entry.status === "failed") return stageName(entry.stage) + " failed";
    return stageName(entry.stage) + " updated";
  }

  function renderFeed() {
    var list = $("[data-ws-activity-feed]");
    var stamp = $("[data-ws-feed-updated]");
    if (!list) return;
    if (!state.timeline.length) {
      list.innerHTML = '<li class="ws-feed-empty">No events yet.</li>';
    } else {
      list.innerHTML = state.timeline
        .slice()
        .reverse()
        .map(function (entry) {
          var icon = entry.success ? "✓" : entry.status === "running" ? "●" : entry.status === "failed" ? "!" : "•";
          var t = formatTime(entry.finished_at || entry.started_at);
          return (
            '<li class="ws-feed-item">' +
            '<span class="ws-feed-time">' + t + "</span>" +
            '<span class="ws-feed-icon">' + icon + "</span>" +
            '<span class="ws-feed-text">' + feedDescription(entry) + "</span>" +
            "</li>"
          );
        })
        .join("");
    }
    if (stamp) stamp.textContent = "Updated " + new Date().toLocaleTimeString();
  }

  function renderAll() {
    updateHeader();
    renderLeftSidebar();
    renderCenter();
    renderRightSummary();
    renderFeed();
  }

  function fetchJSON(url) {
    return fetch(url, { headers: { Accept: "application/json" } }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.json();
    });
  }

  function loadProjectMeta(projectId) {
    return fetchJSON("/api/debug/project/" + encodeURIComponent(projectId))
      .then(function (data) {
        state.projectData = data;
        state.projectName = (data.requirement && data.requirement.title) || state.projectName;
      })
      .catch(function () {
        state.projectData = null;
      });
  }

  function syncProject(projectId) {
    return Promise.all([
      fetchJSON("/api/project/" + encodeURIComponent(projectId) + "/status"),
      fetchJSON("/api/project/" + encodeURIComponent(projectId) + "/timeline"),
      loadProjectMeta(projectId),
    ]).then(function (results) {
      var statusPayload = results[0];
      var timelinePayload = results[1];
      state.status = statusPayload || {};
      state.timeline = (timelinePayload && timelinePayload.timeline) || [];
      state.startedAt = state.timeline.length ? state.timeline[0].started_at || state.timeline[0].finished_at : null;
      renderAll();
    });
  }

  function startPolling() {
    if (!state.projectId) return;
    if (state.pollTimer) clearInterval(state.pollTimer);
    state.pollTimer = setInterval(function () {
      syncProject(state.projectId).catch(function () {
        /* keep polling */
      });
    }, POLL_MS);
  }

  function bindProjectInput() {
    var input = $("[data-ws-project-id-input]");
    var btn = $("[data-ws-project-load]");
    if (!input || !btn) return;

    btn.addEventListener("click", function () {
      var value = (input.value || "").trim();
      if (!value) return;
      saveProjectId(value);
      var params = new URLSearchParams(window.location.search);
      params.set("project_id", value);
      window.history.replaceState({}, "", window.location.pathname + "?" + params.toString());
      syncProject(value).catch(function () {
        renderAll();
      });
      startPolling();
    });
  }

  function init() {
    bindProjectInput();
    var input = $("[data-ws-project-id-input]");
    var initialId = parseProjectId();
    if (input && initialId) input.value = initialId;
    if (!initialId) {
      renderAll();
      return;
    }
    saveProjectId(initialId);
    syncProject(initialId).catch(function () {
      renderAll();
    });
    startPolling();
  }

  init();
})();
