/**
 * Guest preview — show tool pages without redirect; open auth modal on interaction.
 */
(function (global) {
  "use strict";

  var DM = global.DM_AUTH || { authenticated: false };

  function authed() {
    return !!(DM.authenticated || (global.DMAuth && global.DMAuth.authed && global.DMAuth.authed()));
  }

  function gateFrom(el) {
    var root = el && el.closest ? el.closest("[data-guest-tool], [data-require-auth]") : null;
    return {
      title:
        (el && el.getAttribute("data-auth-title")) ||
        (root && root.getAttribute("data-auth-title")) ||
        "Create your free account",
      reason:
        (el && el.getAttribute("data-auth-reason")) ||
        (root && root.getAttribute("data-auth-reason")) ||
        "Sign up to run this tool and keep your work.",
    };
  }

  function promptAuth(el) {
    if (!global.DMAuth || typeof global.DMAuth.require !== "function") {
      global.location.href = "/register?next=" + encodeURIComponent(global.location.pathname);
      return Promise.reject(new Error("AUTH_REQUIRED"));
    }
    var g = gateFrom(el);
    return global.DMAuth.require({ title: g.title, reason: g.reason });
  }

  function isInteractive(target) {
    if (!target || !target.closest) return false;
    if (target.closest(".dm-auth-layer, .app-sidebar, .app-topbar, [data-guest-allow]")) {
      return false;
    }
    return !!target.closest(
      "button, a[href], input, select, textarea, summary, [data-require-auth], [role='button']"
    );
  }

  function bindGuestTools() {
    if (authed()) return;
    document.body.classList.add("dm-guest-preview");

    document.querySelectorAll("[data-guest-tool]").forEach(function (root) {
      root.classList.add("is-guest-locked");
    });

    document.addEventListener(
      "click",
      function (e) {
        if (authed()) return;
        var authTarget = e.target.closest("[data-require-auth]");
        if (authTarget) {
          e.preventDefault();
          e.stopPropagation();
          promptAuth(authTarget);
          return;
        }
        var toolRoot = e.target.closest("[data-guest-tool]");
        if (!toolRoot || !isInteractive(e.target)) return;
        e.preventDefault();
        e.stopPropagation();
        promptAuth(toolRoot);
      },
      true
    );

    document.addEventListener(
      "submit",
      function (e) {
        if (authed()) return;
        var form = e.target;
        if (!form || !form.closest) return;
        if (!form.closest("[data-guest-tool], [data-require-auth]")) return;
        e.preventDefault();
        promptAuth(form);
      },
      true
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindGuestTools);
  } else {
    bindGuestTools();
  }

  global.DMGuestPreview = {
    authed: authed,
    promptAuth: promptAuth,
  };
})(typeof window !== "undefined" ? window : this);
