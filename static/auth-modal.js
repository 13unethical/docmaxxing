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

  function buildSidebarCreditsHtml(balance) {
    var bal = typeof global.formatCoinBalance === "function"
      ? global.formatCoinBalance(typeof balance === "number" ? balance : 0)
      : (typeof balance === "number" ? balance.toLocaleString("en-US") : "0");
    return (
      '<a href="/pricing" class="app-sidebar-credits" data-tour="coins" title="Top up credits">' +
      '<span class="app-sidebar-credits-main">' +
      '<svg class="app-sidebar-credits-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
      '<circle cx="12" cy="12" r="8.25" stroke="currentColor" stroke-width="1.6" />' +
      '<path d="M12 8.5v7M9.75 10.25h3.5a1.5 1.5 0 0 1 0 3h-2.5a1.5 1.5 0 0 0 0 3h3.5" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" />' +
      "</svg>" +
      '<span class="app-sidebar-credits-balance">' +
      '<span class="app-sidebar-credits-amount" data-coin-balance>' +
      bal +
      '</span><span class="app-sidebar-credits-label">credits</span></span></span>' +
      '<span class="app-sidebar-credits-action">Top up</span></a>'
    );
  }

  function buildLoggedInHeader(user, balance) {
    var account = q(".app-topbar-account") || q(".nav-account");
    if (account) account.innerHTML = "";
    var email = (user && user.email) || "";
    var name = (user && (user.name || email.split("@")[0])) || "Account";
    var initial = (name.charAt(0) || "U").toUpperCase();

    var footer = q(".app-sidebar-footer");
    if (footer) {
      footer.innerHTML =
        '<div class="app-sidebar-account-stack">' +
        buildSidebarCreditsHtml(balance) +
        '<div class="nav-user-menu app-sidebar-user" data-user-menu>' +
        '<button type="button" class="nav-user-trigger app-sidebar-user-trigger" data-user-menu-toggle aria-label="' +
        escapeHtml(name) +
        '" aria-expanded="false" aria-haspopup="true">' +
        '<span class="nav-user-avatar" aria-hidden="true">' +
        escapeHtml(initial) +
        "</span>" +
        '<span class="app-sidebar-user-meta app-sidebar-label"><span class="app-sidebar-user-name">' +
        escapeHtml(name) +
        '</span><span class="app-sidebar-user-sub">Account</span></span>' +
        '<svg class="nav-user-chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<path d="M7 10l5 5 5-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>' +
        "</svg></button>" +
        '<div class="nav-user-dropdown app-sidebar-dropdown" data-user-menu-panel hidden>' +
        '<div class="nav-user-dropdown-head">' +
        '<span class="nav-user-avatar nav-user-avatar--lg" aria-hidden="true">' +
        escapeHtml(initial) +
        "</span>" +
        '<div class="nav-user-dropdown-meta"><span class="nav-user-dropdown-name">' +
        escapeHtml(name) +
        '</span><span class="nav-user-dropdown-email">' +
        escapeHtml(email) +
        "</span></div></div>" +
        '<div class="nav-theme-switch" role="group" aria-label="Color theme">' +
        '<button type="button" class="nav-theme-option" data-theme-set="light" aria-pressed="true" aria-label="Light mode">' +
        '<svg class="theme-toggle-icon theme-toggle-icon--sun" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<circle cx="12" cy="12" r="3.75" stroke="currentColor" stroke-width="1.6" />' +
        '<path d="M12 2.75v2.1M12 19.15v2.1M2.75 12h2.1M19.15 12h2.1M5.22 5.22l1.48 1.48M17.3 17.3l1.48 1.48M5.22 18.78l1.48-1.48M17.3 6.7l1.48-1.48" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/>' +
        "</svg></button>" +
        '<button type="button" class="nav-theme-option" data-theme-set="dark" aria-pressed="false" aria-label="Dark mode">' +
        '<svg class="theme-toggle-icon theme-toggle-icon--moon" viewBox="0 0 24 24" fill="none" aria-hidden="true">' +
        '<path d="M20.5 14.2A8.2 8.2 0 1 1 9.8 3.5 6.7 6.7 0 0 0 20.5 14.2Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>' +
        "</svg></button></div>" +
        '<div class="nav-user-dropdown-links">' +
        '<a href="/account" class="nav-user-dropdown-link">Account</a>' +
        '<a href="/pricing" class="nav-user-dropdown-link">Billing</a>' +
        '<form method="post" action="/logout" class="nav-user-dropdown-form">' +
        '<button type="submit" class="nav-user-dropdown-link nav-user-dropdown-link--btn">Log out</button></form>' +
        "</div></div></div></div>";
    }
    if (typeof global.DMThemeApply === "function") {
      global.DMThemeApply();
    }
    if (typeof global.DM_refreshAssignmentHistory === "function") {
      global.DM_refreshAssignmentHistory();
    }
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
    if (kind === "register") {
      if ((body.password || "") !== (body.password_confirm || "")) {
        showError("Passwords do not match.");
        return;
      }
    }
    var btn = q(".dm-auth-submit", form);
    var label = btn ? btn.textContent : "";
    if (btn) { btn.disabled = true; btn.textContent = "Please wait…"; }
    showError("");
    if (kind === "register") {
      try {
        var params = new URLSearchParams(window.location.search);
        var ref = params.get("ref") || params.get("referral_code") || "";
        if (ref) body.referral_code = ref;
        else if (!body.referral_code) {
          var stored = sessionStorage.getItem("dm_pending_ref");
          if (stored) body.referral_code = stored;
        }
      } catch (e) {}
      return (window.DMDeviceFingerprint
        ? window.DMDeviceFingerprint()
        : Promise.resolve("")
      ).then(function (fp) {
        if (fp) body.device_fingerprint = fp;
        return postAuth(url, body, btn, label);
      });
    }
    return postAuth(url, body, btn, label);
  }

  function postAuth(url, body, btn, label) {
    return fetch(url, {
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
          var needsVerify = r.data.email_verification_required
            || (r.data.user && r.data.user.is_verified === false);
          if (needsVerify) {
            window.location.href = "/verify-email/code";
            return;
          }
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

  try {
    var params = new URLSearchParams(window.location.search);
    var ref = params.get("ref") || params.get("referral_code");
    if (ref) sessionStorage.setItem("dm_pending_ref", ref);
  } catch (e) {}
})(typeof window !== "undefined" ? window : this);
