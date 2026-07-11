/**
 * Workspace shell — tab switching, coin mock, draft from Format page.
 */
(function () {
  var DRAFT_KEY = "docmaxxing_workspace_draft";
  var COINS_KEY = "docmaxxing_workspace_coins";
  var WELCOME_COINS = 50;

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function $$(sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  }

  function wordStats(text) {
    var t = String(text || "").trim();
    if (!t) {
      return { words: 0, chars: 0 };
    }
    var words = t.split(/\s+/).filter(Boolean).length;
    return { words: words, chars: t.length };
  }

  function loadCoins() {
    try {
      var raw = localStorage.getItem(COINS_KEY);
      if (raw == null) {
        localStorage.setItem(COINS_KEY, String(WELCOME_COINS));
        return WELCOME_COINS;
      }
      var n = parseInt(raw, 10);
      return isNaN(n) ? WELCOME_COINS : n;
    } catch (e) {
      return WELCOME_COINS;
    }
  }

  function loadDraft() {
    try {
      var raw = sessionStorage.getItem(DRAFT_KEY) || localStorage.getItem(DRAFT_KEY);
      if (!raw) {
        return null;
      }
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function saveDraftFromEditor(editor, titleEl, statusEl) {
    var text = editor.innerText || "";
    var payload = {
      text: text,
      title: (titleEl && titleEl.textContent) || "Untitled draft",
      updatedAt: Date.now(),
    };
    try {
      sessionStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
      localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
    } catch (e) {
      /* quota */
    }
    if (statusEl) {
      statusEl.textContent = "Draft saved locally";
    }
  }

  function initTabs(root) {
    var tabs = $$("[data-ws-tab]", root);
    var panels = $$("[data-ws-panel]", root);
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var id = tab.getAttribute("data-ws-tab");
        tabs.forEach(function (t) {
          var on = t === tab;
          t.classList.toggle("is-active", on);
          t.setAttribute("aria-selected", on ? "true" : "false");
        });
        panels.forEach(function (panel) {
          var on = panel.getAttribute("data-ws-panel") === id;
          panel.classList.toggle("is-active", on);
          if (on) {
            panel.removeAttribute("hidden");
          } else {
            panel.setAttribute("hidden", "");
          }
        });
      });
    });
  }

  function init() {
    var root = $("[data-workspace]");
    if (!root) {
      return;
    }

    var editor = $("#workspace_editor", root);
    var statsEl = $("#workspace_stats", root);
    var coinsEl = $("#workspace_coin_count", root);
    var titleEl = $("#workspace_doc_title", root);
    var statusEl = $("#workspace_save_status", root);

    if (coinsEl) {
      coinsEl.textContent = String(loadCoins());
    }

    var draft = loadDraft();
    if (draft && draft.text && editor) {
      editor.textContent = draft.text;
      if (titleEl && draft.title) {
        titleEl.textContent = draft.title;
      }
      if (statusEl) {
        statusEl.textContent = "Loaded from Format · saved locally";
      }
    }

    function refreshStats() {
      if (!editor || !statsEl) {
        return;
      }
      var s = wordStats(editor.innerText || "");
      statsEl.textContent = s.words.toLocaleString() + " words · " + s.chars.toLocaleString() + " chars";
    }

    refreshStats();
    initTabs(root);

    if (editor) {
      var saveTimer = null;
      editor.addEventListener("input", function () {
        refreshStats();
        if (statusEl) {
          statusEl.textContent = "Saving…";
        }
        clearTimeout(saveTimer);
        saveTimer = setTimeout(function () {
          saveDraftFromEditor(editor, titleEl, statusEl);
        }, 400);
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.WorkspaceDraft = {
    DRAFT_KEY: DRAFT_KEY,
    saveFromText: function (text, title) {
      var payload = {
        text: String(text || ""),
        title: title || "Formatted draft",
        updatedAt: Date.now(),
      };
      try {
        sessionStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
        localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
      } catch (e) {
        /* ignore */
      }
    },
  };
})();
