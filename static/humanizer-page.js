(function () {
  var MAX_WORDS = 5000;

  function $(sel, ctx) {
    return (ctx || document).querySelector(sel);
  }
  function $all(sel, ctx) {
    return Array.prototype.slice.call((ctx || document).querySelectorAll(sel));
  }

  function countWords(text) {
    var raw = String(text || "").replace(/\u00a0/g, " ").trim();
    return raw ? raw.split(/\s+/).filter(Boolean).length : 0;
  }

  function plainText(el) {
    return (el && (el.innerText || el.textContent) ? el.innerText || el.textContent : "").trim();
  }

  var root = $("[data-humanizer-page]");
  if (!root) return;

  var editorIn = $("[data-hz-input]", root);
  var editorOut = $("[data-hz-output]", root);
  var countIn = $("[data-hz-wordcount]", root);
  var countOut = $("[data-hz-out-words]", root);
  var runBtn = $("[data-hz-run]", root);
  var runLabel = $("[data-hz-run-label]", root);
  var runIcon = $("[data-hz-run-icon]", root);
  var runSpinner = $("[data-hz-run-spinner]", root);
  var copyBtn = $("[data-hz-copy]", root);
  var copyLabel = $("[data-hz-copy-label]", root);
  var copyIcon = $("[data-hz-copy-icon]", root);
  var clearBtn = $("[data-hz-clear]", root);
  var fileInput = $("[data-hz-file]", root);
  var pasteBtn = $("[data-hz-paste-focus]", root);
  var fontSelect = $("[data-hz-font]", root);
  var segment = $("[data-hz-segment]", root);
  var sourceBtns = $all("[data-hz-source]", root);
  var stageEl = $("[data-hz-stage]", root);
  var loadingEl = $("[data-hz-loading]", root);
  var resultEl = $("[data-hz-result]", root);
  var errorPanel = $("[data-hz-error]", root);
  var errorMsg = $("[data-hz-error-msg]", root);

  var outputReady = false;
  var origCopyIcon = copyIcon ? copyIcon.innerHTML : "";
  var CHECK_ICON = '<polyline points="20 6 9 17 4 12"></polyline>';
  var copyTimer = null;
  var currentStage = "idle";

  /* -------------------------------------------------------------- stages */
  function setStage(stage) {
    currentStage = stage;
    if (stageEl) stageEl.setAttribute("data-stage", stage);

    if (loadingEl) loadingEl.hidden = stage !== "loading";
    if (resultEl) resultEl.hidden = stage !== "result";
    if (errorPanel) errorPanel.hidden = stage !== "error";

    var loading = stage === "loading";
    if (runBtn) {
      runBtn.disabled = loading;
      runBtn.classList.toggle("is-loading", loading);
    }
    if (runLabel) runLabel.textContent = loading ? "Humanizing..." : "Humanize";
    if (runIcon) runIcon.hidden = loading;
    if (runSpinner) runSpinner.hidden = !loading;

    if (stage !== "result") {
      setOutputEnabled(false);
    }

    var scrollTarget =
      stage === "loading" ? loadingEl : stage === "result" ? resultEl : stage === "error" ? errorPanel : null;
    if (scrollTarget && typeof scrollTarget.scrollIntoView === "function") {
      setTimeout(function () {
        scrollTarget.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 40);
    }
  }

  function setOutputEnabled(enabled) {
    outputReady = !!enabled;
    if (copyBtn) copyBtn.disabled = !enabled;
    $all("[data-hz-format]", root).forEach(function (btn) {
      btn.disabled = !enabled;
    });
    if (fontSelect) fontSelect.disabled = !enabled;
    if (editorOut) editorOut.setAttribute("contenteditable", enabled ? "true" : "false");
  }

  function revealOutput() {
    if (!editorOut) return;
    editorOut.classList.remove("hz-reveal");
    void editorOut.offsetWidth;
    editorOut.classList.add("hz-reveal");
  }

  function showError(message) {
    if (errorMsg) errorMsg.textContent = message || "Something went wrong.";
    setStage("error");
  }

  /* ----------------------------------------------------------- word counts */
  function refreshInputCount() {
    if (!countIn || !editorIn) return;
    var words = countWords(plainText(editorIn));
    countIn.textContent = words.toLocaleString() + " / " + MAX_WORDS.toLocaleString() + " words";
    if (clearBtn) clearBtn.hidden = words === 0;
  }

  function refreshOutputCount() {
    if (!countOut || !editorOut) return;
    countOut.textContent = countWords(plainText(editorOut)).toLocaleString();
  }

  /* --------------------------------------------------------- API response */
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
      if (!res.ok) {
        var err = new Error(payload.message || payload.error || "HTTP " + res.status);
        err.code = payload.error;
        err.status = res.status;
        throw err;
      }
      return payload;
    });
  }

  /* ------------------------------------------------------------- humanize */
  function runHumanize() {
    if (!editorIn || !editorOut || !runBtn) return;
    if (currentStage === "loading") return;

    var source = plainText(editorIn);
    if (!source) {
      editorIn.focus();
      return;
    }
    var words = countWords(source);
    if (words > MAX_WORDS) {
      showError("Maximum " + MAX_WORDS.toLocaleString() + " words per request.");
      return;
    }

    setOutputEnabled(false);
    editorOut.classList.remove("hz-reveal");
    editorOut.textContent = "";
    refreshOutputCount();
    setStage("loading");

    fetch("/api/browser/providers/stealthwriter/humanize", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ text: source }),
    })
      .then(parseApiResponse)
      .then(function (payload) {
        editorOut.textContent = payload.humanized_text || payload.text || "";
        if (typeof payload.balance === "number" && window.refreshCoinBalance) {
          window.refreshCoinBalance();
        }
        refreshOutputCount();
        setStage("result");
        setOutputEnabled(true);
        revealOutput();
      })
      .catch(function (err) {
        var code = err && err.code;
        if (code === "LOGIN_REQUIRED") {
          showError(
            (err && err.message) ||
              "StealthWriter is not logged in on the server. Export storageState on Mac and upload browser_profiles/sessions/stealthwriter.json to the VPS."
          );
          return;
        }
        if (code === "NO_CHANGE") {
          showError((err && err.message) || "StealthWriter did not rewrite the text (daily limit or same output).");
          return;
        }
        if ((code === "REGISTER_REQUIRED" || code === "AUTH_REQUIRED") && window.DMAuth) {
          setStage("idle");
          window.DMAuth.require({
            reason: (err && err.message) || "Create a free account to keep humanizing.",
          })
            .then(function () {
              runHumanize();
            })
            .catch(function () {});
          return;
        }
        if (code === "INSUFFICIENT_COINS") {
          showError((err && err.message ? err.message : "Not enough coins.") + " Add coins on the Pricing page.");
          return;
        }
        showError(err && err.message ? err.message : String(err));
      });
  }

  /* --------------------------------------------------- segmented control */
  function setSource(src) {
    var isUpload = src === "upload";
    if (segment) segment.classList.toggle("is-upload", isUpload);
    sourceBtns.forEach(function (b) {
      var active = b.getAttribute("data-hz-source") === src;
      b.classList.toggle("is-active", active);
      b.setAttribute("aria-selected", active ? "true" : "false");
    });
    if (!isUpload && editorIn) {
      editorIn.focus();
    }
  }

  sourceBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var src = btn.getAttribute("data-hz-source");
      setSource(src);
      // Same pattern as home Upload DOC: open native file chooser immediately.
      if (src === "upload" && fileInput) {
        fileInput.click();
      }
    });
  });

  /* -------------------------------------------------------------- upload */
  function applyUploadedText(text) {
    if (!editorIn) return;
    editorIn.textContent = text || "";
    refreshInputCount();
    setSource("paste");
    editorIn.focus();
  }

  function readPlainTextFile(file) {
    return new Promise(function (resolve, reject) {
      var reader = new FileReader();
      reader.onload = function () {
        resolve(String(reader.result || ""));
      };
      reader.onerror = function () {
        reject(new Error("Could not read the file."));
      };
      reader.readAsText(file, "UTF-8");
    });
  }

  function extractUploadedText(file) {
    var lower = (file.name || "").toLowerCase();
    if (/\.txt$/i.test(lower) || (file.type || "").indexOf("text/") === 0) {
      return readPlainTextFile(file).then(function (text) {
        return { ok: true, text: text };
      });
    }
    if (window.FC && typeof window.FC.extractDocumentText === "function") {
      return window.FC.extractDocumentText(file).then(function (result) {
        return result || { ok: false, error: "Could not read the uploaded file." };
      });
    }
    var fd = new FormData();
    fd.append("file", file);
    return fetch("/api/extract-document", { method: "POST", body: fd })
      .then(function (res) {
        return res.json().then(function (data) {
          if (!res.ok) {
            return { ok: false, error: (data && data.error) || "Could not read the uploaded file." };
          }
          return { ok: true, text: (data && data.text) || "" };
        });
      })
      .catch(function () {
        return { ok: false, error: "Network error while reading the uploaded file." };
      });
  }

  if (fileInput) {
    fileInput.addEventListener("change", function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) return;

      extractUploadedText(file)
        .then(function (result) {
          if (!result || !result.ok) {
            showError((result && result.error) || "Could not read the uploaded file.");
            return;
          }
          var text = String(result.text || "").trim();
          if (!text) {
            showError("No readable text found in that file.");
            return;
          }
          applyUploadedText(text);
        })
        .catch(function (err) {
          showError(err && err.message ? err.message : "Could not read the uploaded file.");
        })
        .finally(function () {
          fileInput.value = "";
        });
    });
  }

  /* -------------------------------------------------------------- inputs */
  if (editorIn) {
    editorIn.addEventListener("input", refreshInputCount);
    refreshInputCount();
  }

  if (clearBtn && editorIn) {
    clearBtn.addEventListener("click", function () {
      editorIn.innerHTML = "";
      refreshInputCount();
      editorIn.focus();
    });
  }

  if (pasteBtn && editorIn) {
    pasteBtn.addEventListener("click", function () {
      editorIn.focus();
    });
  }

  if (fontSelect && editorOut) {
    fontSelect.addEventListener("change", function () {
      if (!outputReady) return;
      editorOut.style.fontFamily = fontSelect.value + ", sans-serif";
      editorOut.focus();
    });
  }

  $all("[data-hz-format]", root).forEach(function (btn) {
    btn.addEventListener("click", function () {
      var command = btn.getAttribute("data-hz-format");
      if (!command || !editorOut || !outputReady) return;
      editorOut.focus();
      document.execCommand(command, false, null);
      refreshOutputCount();
    });
  });

  if (editorOut) {
    editorOut.addEventListener("input", refreshOutputCount);
  }

  if (runBtn) {
    runBtn.addEventListener("click", runHumanize);
  }

  /* ---------------------------------------------------------------- copy */
  if (copyBtn && editorOut) {
    copyBtn.addEventListener("click", function () {
      if (!outputReady) return;
      var text = plainText(editorOut);
      var reset = function () {
        clearTimeout(copyTimer);
        copyBtn.classList.add("is-copied");
        if (copyLabel) copyLabel.textContent = "Copied";
        if (copyIcon) copyIcon.innerHTML = CHECK_ICON;
        copyTimer = setTimeout(function () {
          copyBtn.classList.remove("is-copied");
          if (copyLabel) copyLabel.textContent = "Copy";
          if (copyIcon) copyIcon.innerHTML = origCopyIcon;
        }, 2000);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(reset, reset);
      } else {
        reset();
      }
    });
  }

  /* --------------------------------------------------------------- init */
  setStage("idle");
  setOutputEnabled(false);
  refreshOutputCount();
})();
