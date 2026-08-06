/**
 * Soft device fingerprint for welcome-bonus anti-abuse (not a hard ban).
 * Stable-ish per browser profile; stored in localStorage.
 */
(function (global) {
  "use strict";

  function toHex(buffer) {
    return Array.prototype.map
      .call(new Uint8Array(buffer), function (b) {
        return ("0" + b.toString(16)).slice(-2);
      })
      .join("");
  }

  function canvasSignal() {
    try {
      var c = document.createElement("canvas");
      c.width = 120;
      c.height = 40;
      var ctx = c.getContext("2d");
      if (!ctx) return "nocanvas";
      ctx.textBaseline = "top";
      ctx.font = "14px Arial";
      ctx.fillStyle = "#f60";
      ctx.fillRect(10, 2, 80, 20);
      ctx.fillStyle = "#069";
      ctx.fillText("DocMaxxing", 2, 8);
      return c.toDataURL().slice(-64);
    } catch (e) {
      return "canvas-err";
    }
  }

  function rawParts() {
    var nav = global.navigator || {};
    return [
      nav.userAgent || "",
      nav.language || "",
      String(global.screen && screen.width) + "x" + String(global.screen && screen.height),
      String(global.devicePixelRatio || 1),
      Intl.DateTimeFormat().resolvedOptions().timeZone || "",
      canvasSignal(),
    ].join("|");
  }

  function hashString(text) {
    if (global.crypto && crypto.subtle && global.TextEncoder) {
      return crypto.subtle
        .digest("SHA-256", new TextEncoder().encode(text))
        .then(function (buf) {
          return toHex(buf).slice(0, 64);
        })
        .catch(function () {
          return fallbackHash(text);
        });
    }
    return Promise.resolve(fallbackHash(text));
  }

  function fallbackHash(text) {
    var h = 2166136261;
    for (var i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    var out = (h >>> 0).toString(16);
    while (out.length < 16) out = "0" + out;
    return (out + out + out + out).slice(0, 32);
  }

  global.DMDeviceFingerprint = function () {
    try {
      var cached = localStorage.getItem("dm_device_fp");
      if (cached && /^[a-f0-9]{16,128}$/i.test(cached)) {
        return Promise.resolve(cached.toLowerCase());
      }
    } catch (e) {}
    return hashString(rawParts()).then(function (id) {
      try {
        localStorage.setItem("dm_device_fp", id);
      } catch (e2) {}
      return id;
    });
  };
})(window);
