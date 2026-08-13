/**
 * Shared empty / credits-warn / error state builders for JS pages.
 * Matches macros in templates/macros/ui.html and .dm-* in components.css.
 */
(function (global) {
  "use strict";

  function esc(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function defaultEmptyIcon() {
    return (
      '<svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z"/>' +
      '<path d="M14 3v5h5"/>' +
      '<circle cx="11.5" cy="14.5" r="2.5"/>' +
      '<path d="M13.3 16.3 15.5 18.5"/>' +
      "</svg>"
    );
  }

  /**
   * @param {object} opts
   * @param {string} opts.title
   * @param {string} [opts.lede]
   * @param {string} [opts.hint]
   * @param {string} [opts.actionLabel]
   * @param {string} [opts.actionHref]
   * @param {string} [opts.actionAttrs] raw attribute string (trusted)
   * @param {string} [opts.cost] e.g. "300 credits"
   * @param {string} [opts.iconHtml]
   * @param {string} [opts.classes]
   * @param {string} [opts.attrs]
   */
  function emptyState(opts) {
    opts = opts || {};
    var action = "";
    if (opts.actionLabel) {
      var cost = opts.cost
        ? '<span class="dm-empty__cost">' + esc(opts.cost) + "</span>"
        : "";
      var inner =
        "<span>" + esc(opts.actionLabel) + "</span>" + cost;
      if (opts.actionHref) {
        action =
          '<div class="dm-empty__action"><a href="' +
          esc(opts.actionHref) +
          '" class="dm-btn dm-btn--accent"' +
          (opts.actionAttrs ? " " + opts.actionAttrs : "") +
          ">" +
          inner +
          "</a></div>";
      } else {
        action =
          '<div class="dm-empty__action"><button type="button" class="dm-btn dm-btn--accent"' +
          (opts.actionAttrs ? " " + opts.actionAttrs : "") +
          ">" +
          inner +
          "</button></div>";
      }
    }
    return (
      '<div class="dm-empty' +
      (opts.classes ? " " + esc(opts.classes) : "") +
      '"' +
      (opts.attrs ? " " + opts.attrs : "") +
      ">" +
      '<div class="dm-empty__icon" aria-hidden="true">' +
      (opts.iconHtml || defaultEmptyIcon()) +
      "</div>" +
      '<h2 class="dm-empty__title">' +
      esc(opts.title || "") +
      "</h2>" +
      (opts.lede ? '<p class="dm-empty__lede">' + esc(opts.lede) + "</p>" : "") +
      action +
      (opts.hint ? '<p class="dm-empty__hint">' + esc(opts.hint) + "</p>" : "") +
      "</div>"
    );
  }

  /**
   * @param {object} opts
   * @param {number|string} opts.required
   * @param {number|string} opts.balance
   * @param {string} [opts.topupHref]
   * @param {string} [opts.topupLabel]
   * @param {string} [opts.classes]
   * @param {string} [opts.attrs]
   */
  function creditsWarn(opts) {
    opts = opts || {};
    var href = opts.topupHref || "/pricing";
    var label = opts.topupLabel || "Top up";
    return (
      '<div class="dm-credits-warn' +
      (opts.classes ? " " + esc(opts.classes) : "") +
      '" role="status"' +
      (opts.attrs ? " " + opts.attrs : "") +
      ">" +
      '<h3 class="dm-credits-warn__title">Not enough credits</h3>' +
      '<p class="dm-credits-warn__body">' +
      'This needs <span class="dm-num" data-dm-credits-required>' +
      esc(opts.required) +
      "</span> credits, you have <span class=\"dm-num\" data-dm-credits-balance>" +
      esc(opts.balance) +
      "</span>.</p>" +
      '<div class="dm-credits-warn__actions">' +
      '<a href="' +
      esc(href) +
      '" class="dm-btn dm-btn--accent dm-btn--sm">' +
      esc(label) +
      "</a></div></div>"
    );
  }

  /**
   * @param {object} opts
   * @param {string} [opts.title]
   * @param {string} [opts.body]
   * @param {string} [opts.detail] technical code, shown small
   * @param {string} [opts.retryLabel]
   * @param {string} [opts.retryAttrs]
   * @param {boolean} [opts.hideRetry]
   * @param {string} [opts.classes]
   * @param {string} [opts.attrs]
   */
  function stateError(opts) {
    opts = opts || {};
    var retry = "";
    if (!opts.hideRetry) {
      retry =
        '<div class="dm-state-error__actions">' +
        '<button type="button" class="dm-btn dm-btn--outline-danger dm-btn--sm"' +
        (opts.retryAttrs ? " " + opts.retryAttrs : "") +
        ">" +
        esc(opts.retryLabel || "Retry") +
        "</button></div>";
    }
    return (
      '<div class="dm-state-error' +
      (opts.classes ? " " + esc(opts.classes) : "") +
      '" role="alert"' +
      (opts.attrs ? " " + opts.attrs : "") +
      ">" +
      '<h3 class="dm-state-error__title">' +
      esc(opts.title || "Something went wrong") +
      "</h3>" +
      (opts.body ? '<p class="dm-state-error__body">' + esc(opts.body) + "</p>" : "") +
      (opts.detail
        ? '<p class="dm-state-error__detail">' + esc(opts.detail) + "</p>"
        : "") +
      retry +
      "</div>"
    );
  }

  /** Parse required/balance from API credit messages when possible. */
  function parseCreditAmounts(message, fallbackRequired, fallbackBalance) {
    var text = String(message || "");
    var m =
      text.match(/requires?\s+(\d+)[^\d]+have\s+(\d+)/i) ||
      text.match(/Need\s+(\d+)[^\d]+have\s+(\d+)/i) ||
      text.match(/costs?\s+(\d+)[^\d]+have\s+(\d+)/i) ||
      text.match(/need\s+(\d+)[^\d]+have\s+(\d+)/i);
    return {
      required: m ? Number(m[1]) : fallbackRequired,
      balance: m ? Number(m[2]) : fallbackBalance,
    };
  }

  function isCreditError(code, message) {
    if (code === "INSUFFICIENT_COINS") return true;
    var t = String(message || "").toLowerCase();
    return t.indexOf("not enough credit") !== -1 || t.indexOf("not enough coin") !== -1 || t.indexOf("insufficient credit") !== -1;
  }

  global.dmStates = {
    empty: emptyState,
    creditsWarn: creditsWarn,
    error: stateError,
    parseCreditAmounts: parseCreditAmounts,
    isCreditError: isCreditError,
    esc: esc,
  };
})(typeof window !== "undefined" ? window : this);
