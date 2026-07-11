(function () {
  var MAX_WORDS = 5000;

  function $(sel, ctx) {
    return (ctx || document).querySelector(sel);
  }

  function countWords(text) {
    var raw = String(text || "").replace(/\u00a0/g, " ").trim();
    return raw ? raw.split(/\s+/).filter(Boolean).length : 0;
  }

  function plainText(el) {
    return (el && (el.innerText || el.textContent) ? (el.innerText || el.textContent) : "").trim();
  }

  function downloadText(filename, text) {
    var blob = new Blob([text || ""], { type: "text/plain;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = filename;
    a.click();
    URL.revokeObjectURL(a.href);
  }

  var root = $("[data-humanizer-page]");
  if (!root) return;

  var editorIn = $("[data-hz-input]", root);
  var editorOut = $("[data-hz-output]", root);
  var countIn = $("[data-hz-wordcount]", root);
  var countOut = $("[data-hz-out-words]", root);
  var runBtn = $("[data-hz-run]", root);
  var copyBtn = $("[data-hz-copy]", root);
  var dlDocxBtn = $("[data-hz-dl-docx]", root);
  var dlTxtBtn = $("[data-hz-dl-txt]", root);
  var fileInput = $("[data-hz-file]", root);
  var fileNameEl = $("[data-hz-filename]", root);
  var pasteBtn = $("[data-hz-paste-focus]", root);
  var fontSelect = $("[data-hz-font]", root);
  var outputReady = false;

  function setOutputEnabled(enabled) {
    outputReady = !!enabled;
    [copyBtn, dlDocxBtn, dlTxtBtn].forEach(function (btn) {
      if (btn) btn.disabled = !enabled;
    });
  }

  function refreshInputCount() {
    if (!countIn || !editorIn) return;
    var words = countWords(plainText(editorIn));
    countIn.textContent = "Words: " + words.toLocaleString() + " / " + MAX_WORDS;
  }

  function refreshOutputCount() {
    if (!countOut || !editorOut) return;
    countOut.textContent = String(countWords(plainText(editorOut)).toLocaleString());
  }

  function setLoading(isLoading) {
    if (!runBtn) return;
    runBtn.disabled = !!isLoading;
    runBtn.textContent = isLoading ? "Processing… this may take a few minutes for long texts" : "Humanize Text";
  }

  function parseApiResponse(res) {
    return res.text().then(function (body) {
      var payload = {};
      if (body) {
        try {
          payload = JSON.parse(body);
        } catch (parseErr) {
          if (!res.ok) {
            throw new Error(
              res.status === 404
                ? "Humanizer API not found. Restart the Flask server (python3 app.py) and try again."
                : "Server returned an invalid response (HTTP " + res.status + ")."
            );
          }
          throw parseErr;
        }
      }
      if (!res.ok) throw new Error(payload.error || ("HTTP " + res.status));
      return payload;
    });
  }

  function runHumanize() {
    if (!editorIn || !editorOut || !runBtn) return;
    var source = plainText(editorIn);
    if (!source) {
      editorIn.focus();
      return;
    }
    var words = countWords(source);
    if (words > MAX_WORDS) {
      editorOut.textContent = "Maximum " + MAX_WORDS.toLocaleString() + " words per request.";
      return;
    }

    setLoading(true);
    setOutputEnabled(false);
    editorOut.innerHTML = "";

    fetch("/api/humanizer/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: source }),
    })
      .then(parseApiResponse)
      .then(function (payload) {
        editorOut.textContent = payload.text || "";
        refreshOutputCount();
        setOutputEnabled(true);
      })
      .catch(function (err) {
        editorOut.textContent = err && err.message ? err.message : String(err);
      })
      .finally(function () {
        setLoading(false);
      });
  }

  if (editorIn) {
    editorIn.addEventListener("input", refreshInputCount);
    refreshInputCount();
  }

  if (pasteBtn && editorIn) {
    pasteBtn.addEventListener("click", function () {
      editorIn.focus();
    });
  }

  if (fontSelect && editorIn) {
    fontSelect.addEventListener("change", function () {
      editorIn.style.fontFamily = fontSelect.value + ", sans-serif";
      editorIn.focus();
    });
  }

  root.querySelectorAll("[data-hz-format]").forEach(function (btn) {
    btn.addEventListener("click", function () {
      var command = btn.getAttribute("data-hz-format");
      if (!command) return;
      editorIn.focus();
      document.execCommand(command, false, null);
      refreshInputCount();
    });
  });

  if (fileInput) {
    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file || !fileNameEl) return;
      fileNameEl.hidden = false;
      fileNameEl.textContent = file.name;
    });
  }

  if (runBtn) {
    runBtn.addEventListener("click", runHumanize);
  }

  if (copyBtn && editorOut) {
    copyBtn.addEventListener("click", function () {
      if (!outputReady) return;
      navigator.clipboard.writeText(plainText(editorOut));
    });
  }

  if (dlTxtBtn && editorOut) {
    dlTxtBtn.addEventListener("click", function () {
      if (!outputReady) return;
      downloadText("humanized.txt", plainText(editorOut));
    });
  }

  if (dlDocxBtn && editorOut) {
    dlDocxBtn.addEventListener("click", function () {
      if (!outputReady) return;
      // Placeholder until DOCX generation endpoint exists.
      downloadText("humanized.docx.txt", plainText(editorOut));
    });
  }

  setOutputEnabled(false);
  refreshOutputCount();
})();
