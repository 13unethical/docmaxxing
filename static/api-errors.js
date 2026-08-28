/**
 * Map API error codes to user-facing copy. Internal codes stay in logs only.
 */
(function (global) {
  "use strict";

  var AUTH_CODES = {
    AUTH_REQUIRED: true,
    REGISTER_REQUIRED: true,
    EMAIL_NOT_VERIFIED: true,
  };

  var MESSAGES = {
    AUTH_REQUIRED: "Create a free account to continue.",
    REGISTER_REQUIRED: "Create a free account to continue.",
    EMAIL_NOT_VERIFIED: "Please verify your email to continue.",
    INSUFFICIENT_COINS: "Not enough credits for this step.",
  };

  function isInternalCode(value) {
    return /^[A-Z][A-Z0-9_]+$/.test(String(value || ""));
  }

  function isAuthCode(code) {
    return !!AUTH_CODES[String(code || "")];
  }

  function isGuest() {
    return !(global.DM_AUTH && global.DM_AUTH.authenticated);
  }

  function userMessage(payload, fallback) {
    payload = payload || {};
    var code = String(payload.error || payload.code || "");
    var message = String(payload.message || "");
    if (message && !isInternalCode(message)) return message;
    if (MESSAGES[code]) return MESSAGES[code];
    if (message && isInternalCode(message) && MESSAGES[message]) return MESSAGES[message];
    return fallback || "Something went wrong. Please try again.";
  }

  function promptAuth(opts) {
    if (!global.DMAuth || typeof global.DMAuth.require !== "function") {
      global.location.href =
        "/register?next=" + encodeURIComponent(global.location.pathname + global.location.search);
      return Promise.reject(new Error("AUTH_REQUIRED"));
    }
    return global.DMAuth.require(opts || {});
  }

  global.DMApiErrors = {
    isInternalCode: isInternalCode,
    isAuthCode: isAuthCode,
    isGuest: isGuest,
    userMessage: userMessage,
    promptAuth: promptAuth,
  };
})(typeof window !== "undefined" ? window : this);
