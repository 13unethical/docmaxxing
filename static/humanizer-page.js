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

  function escapeHtml(str) {
    return String(str || "").replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
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
  var copyLabel = $("[data-hz-copy-label]", root);
  var copyIcon = $("[data-hz-copy-icon]", root);
  var dlToggle = $("[data-hz-dl-toggle]", root);
  var dropdown = $("[data-hz-dropdown]", root);
  var dlMenu = $("[data-hz-dl-menu]", root);
  var dlDocxBtn = $("[data-hz-dl-docx]", root);
  var dlTxtBtn = $("[data-hz-dl-txt]", root);
  var fileInput = $("[data-hz-file]", root);
  var fileNameEl = $("[data-hz-filename]", root);
  var pasteBtn = $("[data-hz-paste-focus]", root);
  var fontSelect = $("[data-hz-font]", root);
  var segment = $("[data-hz-segment]", root);
  var sourceBtns = $all("[data-hz-source]", root);
  var uploadZone = $("[data-hz-upload]", root);
  var emptyEl = $("[data-hz-empty]", root);
  var progress = $("[data-hz-progress]", root);
  var progressBar = $("[data-hz-progress-bar]", root);
  var steps = $all("[data-hz-progress-steps] li", root);

  var outputReady = false;
  var origCopyIcon = copyIcon ? copyIcon.innerHTML : "";
  var CHECK_ICON = '<polyline points="20 6 9 17 4 12"></polyline>';
  var copyTimer = null;

  /* --------------------------------------------------------- output state */
  function setOutputEnabled(enabled) {
    outputReady = !!enabled;
    [copyBtn, dlToggle].forEach(function (btn) {
      if (btn) btn.disabled = !enabled;
    });
    if (!enabled) closeMenu();
  }

  function updateEmptyState(loading) {
    if (!emptyEl) return;
    var hasContent = plainText(editorOut).length > 0;
    emptyEl.classList.toggle("is-hidden", !!loading || hasContent);
  }

  function revealOutput() {
    if (!editorOut) return;
    editorOut.classList.remove("hz-reveal");
    void editorOut.offsetWidth; // reflow to restart animation
    editorOut.classList.add("hz-reveal");
  }

  function showError(message) {
    if (!editorOut) return;
    editorOut.innerHTML = '<p class="hz-error">' + escapeHtml(message) + "</p>";
    refreshOutputCount();
    updateEmptyState();
  }

  /* ----------------------------------------------------------- word counts */
  function refreshInputCount() {
    if (!countIn || !editorIn) return;
    var words = countWords(plainText(editorIn));
    countIn.textContent = words.toLocaleString() + " / " + MAX_WORDS.toLocaleString() + " words";
  }

  function refreshOutputCount() {
    if (!countOut || !editorOut) return;
    countOut.textContent = countWords(plainText(editorOut)).toLocaleString();
  }

  /* ------------------------------------------------------------- progress */
  var progressTimers = [];
  var creepTimer = null;

  function clearProgressTimers() {
    progressTimers.forEach(clearTimeout);
    progressTimers = [];
    if (creepTimer) {
      clearInterval(creepTimer);
      creepTimer = null;
    }
  }

  function setStep(idx) {
    steps.forEach(function (li, i) {
      li.classList.toggle("is-active", i === idx);
      if (i < idx) li.classList.add("is-done");
      else li.classList.remove("is-done");
    });
  }

  function setBar(pct) {
    if (progressBar) progressBar.style.width = pct + "%";
  }

  function startProgress() {
    if (runBtn) runBtn.hidden = true;
    if (progress) progress.hidden = false;
    clearProgressTimers();
    steps.forEach(function (li) {
      li.classList.remove("is-done", "is-active");
    });
    setBar(6);
    setStep(0);
    progressTimers.push(
      setTimeout(function () {
        setStep(1);
        setBar(30);
      }, 700)
    );
    progressTimers.push(
      setTimeout(function () {
        setStep(2);
        setBar(58);
      }, 1700)
    );
    progressTimers.push(
      setTimeout(function () {
        var pct = 58;
        creepTimer = setInterval(function () {
          pct = Math.min(90, pct + 1.5);
          setBar(pct);
        }, 900);
      }, 2000)
    );
  }

  function hideProgress() {
    if (progress) progress.hidden = true;
    if (runBtn) {
      runBtn.hidden = false;
      runBtn.disabled = false;
    }
  }

  function finishProgress(success, done) {
    clearProgressTimers();
    if (success) {
      setStep(3);
      steps.forEach(function (li, i) {
        if (i < 3) li.classList.add("is-done");
      });
      setBar(100);
      progressTimers.push(
        setTimeout(function () {
          hideProgress();
          if (done) done();
        }, 450)
      );
    } else {
      hideProgress();
      if (done) done();
    }
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
    editorOut.innerHTML = "";
    updateEmptyState(true);
    startProgress();

    fetch("/api/browser/providers/stealthwriter/humanize", {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "same-origin",
      body: JSON.stringify({ text: source }),
    })
      .then(parseApiResponse)
      .then(function (payload) {
        finishProgress(true, function () {
          editorOut.textContent = payload.humanized_text || payload.text || "";
          if (typeof payload.balance === "number" && window.refreshCoinBalance) {
            window.refreshCoinBalance();
          }
          refreshOutputCount();
          setOutputEnabled(true);
          updateEmptyState();
          revealOutput();
        });
      })
      .catch(function (err) {
        var code = err && err.code;
        if (code === "LOGIN_REQUIRED") {
          finishProgress(false, function () {
            showError(
              (err && err.message) ||
                "StealthWriter is not logged in on the server. Export storageState on Mac and upload browser_profiles/sessions/stealthwriter.json to the VPS."
            );
          });
          return;
        }
        if (code === "NO_CHANGE") {
          finishProgress(false, function () {
            showError((err && err.message) || "StealthWriter did not rewrite the text (daily limit or same output).");
          });
          return;
        }
        if ((code === "REGISTER_REQUIRED" || code === "AUTH_REQUIRED") && window.DMAuth) {
          finishProgress(false, function () { updateEmptyState(); });
          window.DMAuth.require({
            reason: (err && err.message) || "Create a free account to keep humanizing.",
          }).then(function () {
            runHumanize();
          }).catch(function () {});
          return;
        }
        if (code === "INSUFFICIENT_COINS") {
          finishProgress(false, function () {
            showError((err && err.message ? err.message : "Not enough coins.") + " Add coins on the Pricing page.");
          });
          return;
        }
        finishProgress(false, function () {
          showError(err && err.message ? err.message : String(err));
        });
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
    if (uploadZone) uploadZone.hidden = !isUpload;
    if (!isUpload && editorIn) editorIn.focus();
  }

  sourceBtns.forEach(function (btn) {
    btn.addEventListener("click", function () {
      setSource(btn.getAttribute("data-hz-source"));
    });
  });

  /* ------------------------------------------------------------ dropdown */
  function openMenu() {
    if (dlMenu) dlMenu.hidden = false;
    if (dropdown) dropdown.classList.add("is-open");
    if (dlToggle) dlToggle.setAttribute("aria-expanded", "true");
  }
  function closeMenu() {
    if (dlMenu) dlMenu.hidden = true;
    if (dropdown) dropdown.classList.remove("is-open");
    if (dlToggle) dlToggle.setAttribute("aria-expanded", "false");
  }

  if (dlToggle) {
    dlToggle.addEventListener("click", function (e) {
      e.stopPropagation();
      if (dlToggle.disabled) return;
      if (dlMenu && dlMenu.hidden) openMenu();
      else closeMenu();
    });
  }
  document.addEventListener("click", function (e) {
    if (dropdown && !dropdown.contains(e.target)) closeMenu();
  });
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") closeMenu();
  });

  /* -------------------------------------------------------------- inputs */
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

  $all("[data-hz-format]", root).forEach(function (btn) {
    btn.addEventListener("click", function () {
      var command = btn.getAttribute("data-hz-format");
      if (!command || !editorIn) return;
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

  /* ------------------------------------------------------------ download */
  if (dlTxtBtn && editorOut) {
    dlTxtBtn.addEventListener("click", function () {
      if (!outputReady) return;
      downloadText("humanized.txt", plainText(editorOut));
      closeMenu();
    });
  }

  if (dlDocxBtn && editorOut) {
    dlDocxBtn.addEventListener("click", function () {
      if (!outputReady) return;
      // Placeholder until a DOCX generation endpoint exists (unchanged behavior).
      downloadText("humanized.docx.txt", plainText(editorOut));
      closeMenu();
    });
  }

  /* --------------------------------------------------------------- init */
  setOutputEnabled(false);
  refreshOutputCount();
  updateEmptyState();
})();
