(function () {
  "use strict";

  var COLLAPSE_KEY = "dm_sidebar_collapsed";

  function closeSidebar() {
    document.body.classList.remove("sidebar-open");
    var toggle = document.querySelector("[data-sidebar-toggle]");
    if (toggle) toggle.setAttribute("aria-expanded", "false");
    document.querySelectorAll("[data-sidebar-close]").forEach(function (el) {
      if (el.classList.contains("app-sidebar-backdrop")) el.hidden = true;
    });
  }

  function openSidebar() {
    document.body.classList.add("sidebar-open");
    var toggle = document.querySelector("[data-sidebar-toggle]");
    if (toggle) toggle.setAttribute("aria-expanded", "true");
    var backdrop = document.querySelector(".app-sidebar-backdrop");
    if (backdrop) backdrop.hidden = false;
  }

  function isDesktop() {
    return window.matchMedia && window.matchMedia("(min-width: 901px)").matches;
  }

  function setCollapsed(collapsed) {
    document.body.classList.toggle("sidebar-collapsed", !!collapsed);
    try {
      localStorage.setItem(COLLAPSE_KEY, collapsed ? "1" : "0");
    } catch (e) {}
    var btn = document.querySelector("[data-sidebar-collapse]");
    if (btn) {
      btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      btn.setAttribute("aria-label", collapsed ? "Expand sidebar" : "Collapse sidebar");
      btn.title = collapsed ? "Expand sidebar" : "Collapse sidebar";
    }
    var brand = document.querySelector("[data-sidebar-brand]");
    if (brand) {
      if (collapsed) {
        brand.setAttribute("aria-label", "Open sidebar");
        brand.setAttribute("title", "Open sidebar");
        brand.setAttribute("role", "button");
      } else {
        brand.setAttribute("aria-label", "DocMaxxing Home");
        brand.setAttribute("title", "DocMaxxing");
        brand.removeAttribute("role");
      }
    }
  }

  function restoreCollapsed() {
    if (!isDesktop()) {
      document.body.classList.remove("sidebar-collapsed");
      return;
    }
    var collapsed = false;
    try {
      collapsed = localStorage.getItem(COLLAPSE_KEY) === "1";
    } catch (e) {}
    setCollapsed(collapsed);
  }

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function historyRoot() {
    return document.querySelector("[data-tool-history]");
  }

  function currentTool() {
    var root = historyRoot();
    return root ? root.getAttribute("data-tool") : null;
  }

  function activeProjectId() {
    try {
      var params = new URLSearchParams(window.location.search);
      var fromQuery = params.get("project");
      if (fromQuery) return fromQuery;
      var raw = localStorage.getItem("asgWizardV1");
      if (!raw) return null;
      var parsed = JSON.parse(raw);
      return (parsed && parsed.projectId) || null;
    } catch (e) {
      return null;
    }
  }

  function activeLocalHistoryId() {
    try {
      return new URLSearchParams(window.location.search).get("h");
    } catch (e) {
      return null;
    }
  }

  function renderAssignmentHistory(items) {
    var list = document.querySelector("[data-tool-history-list]");
    if (!list) return;
    var auth = window.DM_AUTH && window.DM_AUTH.authenticated;
    if (!auth) {
      list.innerHTML =
        '<p class="app-sidebar-history-empty">Sign in to see history.</p>';
      return;
    }
    if (!items || !items.length) {
      list.innerHTML =
        '<p class="app-sidebar-history-empty">No assignments yet.</p>';
      return;
    }
    var current = activeProjectId();
    list.innerHTML = items
      .map(function (item) {
        var id = item.id || item.project_id || "";
        var title =
          item.title ||
          (item.requirement && item.requirement.title) ||
          "Assignment";
        var shortId = String(id).slice(0, 8);
        var active = current && String(current) === String(id) ? " is-active" : "";
        return (
          '<a class="app-sidebar-history-item' +
          active +
          '" href="/assignment?project=' +
          encodeURIComponent(id) +
          '" title="' +
          esc(title) +
          " · " +
          esc(shortId) +
          '">' +
          esc(title) +
          "</a>"
        );
      })
      .join("");
  }

  function renderLocalHistory(tool) {
    var list = document.querySelector("[data-tool-history-list]");
    if (!list || !window.DMToolHistory) return;
    var items = window.DMToolHistory.list(tool);
    if (!items.length) {
      list.innerHTML =
        '<p class="app-sidebar-history-empty">No history yet.</p>';
      return;
    }
    var current = activeLocalHistoryId();
    list.innerHTML = items
      .map(function (item) {
        var active = current && String(current) === String(item.id) ? " is-active" : "";
        var href = window.DMToolHistory.hrefFor(tool, item.id);
        return (
          '<a class="app-sidebar-history-item' +
          active +
          '" href="' +
          esc(href) +
          '" title="' +
          esc(item.title) +
          '">' +
          esc(item.title) +
          "</a>"
        );
      })
      .join("");
  }

  async function loadAssignmentHistory() {
    var list = document.querySelector("[data-tool-history-list]");
    if (!list) return;
    if (!(window.DM_AUTH && window.DM_AUTH.authenticated)) {
      renderAssignmentHistory([]);
      return;
    }
    try {
      var res = await fetch("/api/assignment/projects", {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!res.ok) throw new Error("Failed to load history");
      var data = await res.json();
      var items = Array.isArray(data) ? data : data.projects || data.items || [];
      renderAssignmentHistory(items);
    } catch (err) {
      list.innerHTML =
        '<p class="app-sidebar-history-empty">Could not load history.</p>';
    }
  }

  function refreshToolHistory() {
    var tool = currentTool();
    if (!tool) return;
    if (tool === "assignment") {
      loadAssignmentHistory();
      return;
    }
    renderLocalHistory(tool);
  }

  window.DM_refreshAssignmentHistory = function () {
    if (currentTool() === "assignment") loadAssignmentHistory();
  };
  window.DM_refreshToolHistory = refreshToolHistory;

  function startNewChat(tool) {
    closeSidebar();
    var t = tool || currentTool();
    if (t === "assignment") {
      if (typeof window.DM_startNewAssignment === "function") {
        window.DM_startNewAssignment();
        return;
      }
      window.location.href = "/assignment?new=1";
      return;
    }
    if (t === "humanizer") {
      window.location.href = "/humanizer";
      return;
    }
    if (t === "format") {
      window.location.href = "/";
      return;
    }
    if (t === "check") {
      window.location.href = "/check";
      return;
    }
  }

  document.addEventListener("click", function (e) {
    var brand = e.target.closest("[data-sidebar-brand]");
    if (brand && isDesktop() && document.body.classList.contains("sidebar-collapsed")) {
      e.preventDefault();
      setCollapsed(false);
      return;
    }
    var collapseBtn = e.target.closest("[data-sidebar-collapse]");
    if (collapseBtn) {
      e.preventDefault();
      if (!isDesktop()) return;
      setCollapsed(!document.body.classList.contains("sidebar-collapsed"));
      return;
    }
    var newChat = e.target.closest("[data-tool-new-chat], [data-asg-new-chat]");
    if (newChat) {
      e.preventDefault();
      startNewChat(newChat.getAttribute("data-tool") || currentTool());
      return;
    }
    var openBtn = e.target.closest("[data-sidebar-toggle]");
    if (openBtn) {
      if (document.body.classList.contains("sidebar-open")) closeSidebar();
      else openSidebar();
      return;
    }
    if (e.target.closest("[data-sidebar-close]")) {
      closeSidebar();
    }
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeSidebar();
  });

  window.addEventListener("resize", function () {
    restoreCollapsed();
  });

  function boot() {
    restoreCollapsed();
    refreshToolHistory();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
