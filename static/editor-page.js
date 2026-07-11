(function () {
  var DRAFT_KEY = "docmaxxing_workspace_draft";
  var editor = document.getElementById("editor_surface");
  var stats = document.getElementById("editor_stats");
  var status = document.getElementById("editor_save_status");

  if (!editor) {
    return;
  }

  function wordCount(text) {
    var t = String(text || "").trim();
    if (!t) {
      return 0;
    }
    return t.split(/\s+/).filter(Boolean).length;
  }

  function loadDraft() {
    try {
      var raw = sessionStorage.getItem(DRAFT_KEY) || localStorage.getItem(DRAFT_KEY);
      if (!raw) {
        return;
      }
      var data = JSON.parse(raw);
      if (data && data.text) {
        editor.textContent = data.text;
      }
    } catch (e) {
      /* ignore */
    }
  }

  function saveDraft() {
    try {
      var payload = JSON.stringify({ text: editor.innerText || "", updatedAt: Date.now() });
      sessionStorage.setItem(DRAFT_KEY, payload);
      localStorage.setItem(DRAFT_KEY, payload);
      if (status) {
        status.textContent = "All changes saved locally";
      }
    } catch (e) {
      /* ignore */
    }
  }

  function refreshStats() {
    if (stats) {
      stats.textContent = wordCount(editor.innerText).toLocaleString() + " words";
    }
  }

  loadDraft();
  refreshStats();

  var timer;
  editor.addEventListener("input", function () {
    refreshStats();
    if (status) {
      status.textContent = "Saving…";
    }
    clearTimeout(timer);
    timer = setTimeout(saveDraft, 400);
  });
})();
