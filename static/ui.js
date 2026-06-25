/**
 * Shared UI: toasts, copy-to-clipboard, loading helpers.
 */
(function (global) {
  var toastTimer = null;

  function ensureToastContainer() {
    var el = document.getElementById("app_toast_container");
    if (el) {
      return el;
    }
    el = document.createElement("div");
    el.id = "app_toast_container";
    el.className = "toast-container";
    el.setAttribute("aria-live", "polite");
    el.setAttribute("aria-atomic", "true");
    document.body.appendChild(el);
    return el;
  }

  function showToast(message, kind) {
    var container = ensureToastContainer();
    if (toastTimer) {
      clearTimeout(toastTimer);
    }
    container.innerHTML = "";
    var toast = document.createElement("div");
    toast.className = "toast toast-" + (kind || "info");
    toast.textContent = message;
    container.appendChild(toast);
    requestAnimationFrame(function () {
      toast.classList.add("is-visible");
    });
    toastTimer = setTimeout(function () {
      toast.classList.remove("is-visible");
      setTimeout(function () {
        if (toast.parentNode) {
          toast.parentNode.removeChild(toast);
        }
      }, 300);
    }, 3200);
  }

  function copyText(text, buttonEl) {
    var t = String(text || "").trim();
    if (!t) {
      showToast("Nothing to copy.", "error");
      return Promise.resolve(false);
    }
    function onSuccess() {
      showToast("Copied to clipboard", "success");
      if (buttonEl) {
        var orig = buttonEl.textContent;
        buttonEl.textContent = "Copied!";
        buttonEl.disabled = true;
        setTimeout(function () {
          buttonEl.textContent = orig;
          buttonEl.disabled = false;
        }, 1600);
      }
      return true;
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(t).then(onSuccess).catch(function () {
        showToast("Could not copy.", "error");
        return false;
      });
    }
    var ta = document.createElement("textarea");
    ta.value = t;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    document.body.appendChild(ta);
    ta.select();
    try {
      document.execCommand("copy");
      document.body.removeChild(ta);
      return Promise.resolve(onSuccess());
    } catch (e) {
      document.body.removeChild(ta);
      showToast("Could not copy.", "error");
      return Promise.resolve(false);
    }
  }

  function setButtonLoading(btn, loading, loadingText) {
    if (!btn) {
      return;
    }
    if (loading) {
      if (!btn.dataset.origText) {
        btn.dataset.origText = btn.textContent;
      }
      btn.textContent = loadingText || "Loading…";
      btn.disabled = true;
      btn.classList.add("is-loading");
    } else {
      btn.textContent = btn.dataset.origText || btn.textContent;
      btn.disabled = false;
      btn.classList.remove("is-loading");
    }
  }

  global.AppUI = {
    showToast: showToast,
    copyText: copyText,
    setButtonLoading: setButtonLoading,
  };
})(typeof window !== "undefined" ? window : this);
