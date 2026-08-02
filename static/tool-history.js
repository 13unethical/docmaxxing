(function (global) {
  "use strict";

  var KEY = "dm_tool_history_v1";
  var MAX = 40;
  var TOOLS = ["humanizer", "format", "check", "workspace"];

  function emptyStore() {
    return { humanizer: [], format: [], check: [], workspace: [] };
  }

  function readAll() {
    try {
      var raw = localStorage.getItem(KEY);
      if (!raw) return emptyStore();
      var parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== "object") return emptyStore();
      var out = emptyStore();
      TOOLS.forEach(function (tool) {
        out[tool] = Array.isArray(parsed[tool]) ? parsed[tool] : [];
      });
      return out;
    } catch (e) {
      return emptyStore();
    }
  }

  function writeAll(data) {
    try {
      localStorage.setItem(KEY, JSON.stringify(data || emptyStore()));
    } catch (e) {
      /* quota / private mode */
    }
  }

  function uid() {
    return (
      Date.now().toString(36) +
      Math.random().toString(36).slice(2, 8)
    );
  }

  function titleFromText(text, fallback) {
    var t = String(text || "")
      .replace(/\s+/g, " ")
      .trim();
    if (!t) return fallback || "Untitled";
    return t.length > 48 ? t.slice(0, 45) + "…" : t;
  }

  function list(tool) {
    var store = readAll();
    return (store[tool] || []).slice();
  }

  function get(tool, id) {
    if (!id) return null;
    var items = list(tool);
    for (var i = 0; i < items.length; i++) {
      if (String(items[i].id) === String(id)) return items[i];
    }
    return null;
  }

  function push(tool, entry) {
    if (TOOLS.indexOf(tool) === -1) return null;
    var store = readAll();
    var items = store[tool] || [];
    var id = (entry && entry.id) || uid();
    var next = {
      id: id,
      title: (entry && entry.title) || "Untitled",
      updatedAt: Date.now(),
      payload: (entry && entry.payload) || {},
    };
    items = items.filter(function (item) {
      return String(item.id) !== String(id);
    });
    items.unshift(next);
    if (items.length > MAX) items = items.slice(0, MAX);
    store[tool] = items;
    writeAll(store);
    return id;
  }

  function remove(tool, id) {
    var store = readAll();
    store[tool] = (store[tool] || []).filter(function (item) {
      return String(item.id) !== String(id);
    });
    writeAll(store);
  }

  function historyParam() {
    try {
      return new URLSearchParams(global.location.search).get("h");
    } catch (e) {
      return null;
    }
  }

  function pathForTool(tool) {
    if (tool === "humanizer") return "/humanizer";
    if (tool === "format") return "/";
    if (tool === "check") return "/check";
    if (tool === "workspace") return "/workspace";
    return "/";
  }

  function hrefFor(tool, id) {
    return pathForTool(tool) + "?h=" + encodeURIComponent(id);
  }

  global.DMToolHistory = {
    KEY: KEY,
    MAX: MAX,
    TOOLS: TOOLS,
    list: list,
    get: get,
    push: push,
    remove: remove,
    titleFromText: titleFromText,
    historyParam: historyParam,
    pathForTool: pathForTool,
    hrefFor: hrefFor,
  };
})(window);
