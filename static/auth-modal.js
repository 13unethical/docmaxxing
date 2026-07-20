/**
 * Registration wall — a shared, page-agnostic auth modal.
 *
 * Pages call window.DMAuth.require({ reason }) which returns a Promise that
 * resolves when the user is authenticated (immediately if already signed in,
 * otherwise after they register/sign in through the modal). No navigation
 * happens, so the caller can simply retry the pending action on resolve.
 */
(function (global) {
  "use strict";

  var DM = (global.DM_AUTH = global.DM_AUTH || { authenticated: false });

  var layer, backdrop, modal, reasonEl, errorEl, titleEl;
  var pending = null; // { resolve, reject }
  var lastFocus = null;

  function authed() {
    return !!DM.authenticated;
  }

  function q(sel, ctx) {
    return (ctx || document).querySelector(sel);
  }
  function qa(sel, ctx) {
    return Array.prototype.slice.call((ctx || document).querySelectorAll(sel));
  }

  function ensureEls() {
    if (layer) return layer;
    layer = q("[data-auth-layer]");
    if (!layer) return null;
    backdrop = q("[data-auth-backdrop]", layer);
    modal = q(".dm-auth-modal", layer);
    reasonEl = q("[data-auth-reason]", layer);
    errorEl = q("[data-auth-error]", layer);
    titleEl = q("[data-auth-title]", layer);
    wire();
    return layer;
  }

  function showError(msg) {
    if (!errorEl) return;
    if (msg) {
      errorEl.textContent = msg;
      errorEl.hidden = false;
    } else {
      errorEl.textContent = "";
      errorEl.hidden = true;
    }
  }

  function switchTab(name) {
    qa("[data-auth-tab]", layer).forEach(function (t) {
      t.classList.toggle("is-active", t.getAttribute("data-auth-tab") === name);
    });
    qa("[data-auth-form]", layer).forEach(function (f) {
      f.hidden = f.getAttribute("data-auth-form") !== name;
    });
    showError("");
  }

  function openModal(reason) {
    if (!ensureEls()) return;
    if (reason && reasonEl) reasonEl.textContent = reason;
    showError("");
    switchTab("register");
    lastFocus = document.activeElement;
    layer.hidden = false;
    layer.setAttribute("aria-hidden", "false");
    requestAnimationFrame(function () {
      layer.classList.add("is-open");
      var first = q('[data-auth-form="register"] input', layer);
      if (first) first.focus();
    });
    document.body.style.overflow = "hidden";
  }

  function closeModal(reject) {
    if (!layer) return;
    layer.classList.remove("is-open");
    layer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
    setTimeout(function () {
      if (layer) layer.hidden = true;
    }, 200);
    if (lastFocus && lastFocus.focus) {
      try { lastFocus.focus(); } catch (e) {}
    }
    if (reject && pending) {
      var p = pending;
      pending = null;
      p.reject(new Error("AUTH_CANCELLED"));
    }
  }

  function buildLoggedInHeader(user, balance) {
    var account = q(".nav-account");
    if (!account) return;
    var email = (user && user.email) || "";
    var name = (user && (user.name || email.split("@")[0])) || "Account";
    var initial = (name.charAt(0) || "U").toUpperCase();
    account.innerHTML =
      '<a href="/pricing" class="coin-pill" title="Your coin balance">' +
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="8.25" stroke="currentColor" stroke-width="1.6" />' +
      '<path d="M12 8.5v7M9.75 10.25h3.5a1.5 1.5 0 0 1 0 3h-2.5a1.5 1.5 0 0 0 0 3h3.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />' +
      "</svg><span data-coin-balance>" +
      (typeof balance === "number" ? balance : 0) +
      "</span></a>" +
      '<div class="nav-user-menu" data-user-menu>' +
      '<button type="button" class="nav-user-trigger" data-user-menu-toggle aria-expanded="false" aria-haspopup="true">' +
      '<span class="nav-user-avatar" aria-hidden="true">' +
      escapeHtml(initial) +
      "</span>" +
      '<span class="nav-user-meta"><span class="nav-user-name">' +
      escapeHtml(name) +
      '</span><span class="nav-user-email">' +
      escapeHtml(email) +
      "</span></span>" +
      '<svg class="nav-user-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
      '<path d="M7 10l5 5 5-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>' +
      "</svg></button>" +
      '<div class="nav-user-dropdown" data-user-menu-panel hidden>' +
      '<div class="nav-user-dropdown-head">' +
      '<span class="nav-user-avatar nav-user-avatar--lg" aria-hidden="true">' +
      escapeHtml(initial) +
      "</span>" +
      '<div class="nav-user-dropdown-meta"><span class="nav-user-dropdown-name">' +
      escapeHtml(name) +
      '</span><span class="nav-user-dropdown-email">' +
      escapeHtml(email) +
      "</span></div></div>" +
      '<div class="nav-user-dropdown-links">' +
      '<a href="/account" class="nav-user-dropdown-link">' +
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
      '<circle cx="12" cy="8" r="3.25" stroke="currentColor" stroke-width="1.6"/>' +
      '<path d="M5.5 19c1.6-3 4-4.5 6.5-4.5S16.9 16 18.5 19" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
      "</svg>Account</a>" +
      '<a href="/pricing" class="nav-user-dropdown-link">' +
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
      '<rect x="3.5" y="6.5" width="17" height="11" rx="2" stroke="currentColor" stroke-width="1.6"/>' +
      '<path d="M3.5 10.5h17" stroke="currentColor" stroke-width="1.6"/>' +
      "</svg>Billing</a>" +
      '<form method="post" action="/logout" class="nav-user-dropdown-form">' +
      '<button type="submit" class="nav-user-dropdown-link nav-user-dropdown-link--btn">' +
      '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
      '<path d="M10 5H7a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h3" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
      '<path d="M14 16l4-4-4-4M18 12H10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>' +
      "</svg>Log out</button></form>" +
      "</div></div></div>";
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function onAuthSuccess(data) {
    DM.authenticated = true;
    DM.user = data.user || null;
    buildLoggedInHeader(data.user, data.balance);
    if (typeof global.refreshCoinBalance === "function") {
      global.refreshCoinBalance();
    }
    var p = pending;
    pending = null;
    closeModal(false);
    if (p) p.resolve(data);
  }

  function submitForm(kind, form) {
    var url = kind === "login" ? "/api/auth/login" : "/api/auth/register";
    var body = {};
    qa("input", form).forEach(function (inp) {
      if (inp.name) body[inp.name] = inp.value;
    });
    var btn = q(".dm-auth-submit", form);
    var label = btn ? btn.textContent : "";
    if (btn) { btn.disabled = true; btn.textContent = "Please wait…"; }
    showError("");

    fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        return res.json().catch(function () { return {}; }).then(function (d) {
          return { ok: res.ok, data: d };
        });
      })
      .then(function (r) {
        if (btn) { btn.disabled = false; btn.textContent = label; }
        if (r.ok && r.data && r.data.success) {
          onAuthSuccess(r.data);
        } else {
          showError((r.data && r.data.error) || "Something went wrong. Please try again.");
        }
      })
      .catch(function () {
        if (btn) { btn.disabled = false; btn.textContent = label; }
        showError("Network error. Please try again.");
      });
  }

  var wired = false;
  function wire() {
    if (wired || !layer) return;
    wired = true;
    qa("[data-auth-close]", layer).forEach(function (el) {
      el.addEventListener("click", function () { closeModal(true); });
    });
    qa("[data-auth-tab]", layer).forEach(function (t) {
      t.addEventListener("click", function () { switchTab(t.getAttribute("data-auth-tab")); });
    });
    qa("[data-auth-form]", layer).forEach(function (f) {
      f.addEventListener("submit", function (e) {
        e.preventDefault();
        submitForm(f.getAttribute("data-auth-form"), f);
      });
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && layer && !layer.hidden) closeModal(true);
    });
  }

  function require(opts) {
    opts = opts || {};
    if (authed()) return Promise.resolve({ already: true });
    return new Promise(function (resolve, reject) {
      // Only one pending gate at a time; reject the previous.
      if (pending) pending.reject(new Error("AUTH_SUPERSEDED"));
      pending = { resolve: resolve, reject: reject };
      openModal(opts.reason || "Create a free account to continue.");
    });
  }

  global.DMAuth = {
    authed: authed,
    require: require,
    open: function (reason) { openModal(reason); },
    close: function () { closeModal(true); },
  };
})(typeof window !== "undefined" ? window : this);
