// Replaced with the site origin when the zip is built. Unpacked from the repo, it talks to local Flask first.
const PACKED_API_BASE = "__VEIL_API_BASE__";
const LOCAL_API_BASE = "http://127.0.0.1:5001";
const PROD_API_BASE = "https://docmaxxing.com";

function packedApiBase() {
  return PACKED_API_BASE.startsWith("__") ? "" : PACKED_API_BASE.replace(/\/$/, "");
}

function originOf(sender) {
  const raw = String((sender && (sender.origin || sender.url)) || "");
  try {
    return new URL(raw).origin;
  } catch (_err) {
    return "";
  }
}

async function apiBases() {
  const stored = await chrome.storage.local.get(["veil_api_base"]);
  const saved = String(stored.veil_api_base || "").replace(/\/$/, "");
  const ordered = [];
  function add(url) {
    const clean = String(url || "").replace(/\/$/, "");
    if (!clean || ordered.indexOf(clean) >= 0) return;
    ordered.push(clean);
  }
  add(saved);
  add(packedApiBase());
  add(LOCAL_API_BASE);
  add(PROD_API_BASE);
  return ordered;
}

function isNetworkError(err) {
  const msg = String((err && err.message) || err || "");
  return /failed to fetch|networkerror|load failed|network request failed|err_connection|connection refused|could not connect/i.test(msg);
}

async function apiFetch(path, options) {
  const bases = await apiBases();
  let lastErr;
  let sawUnauthorized = false;
  for (let i = 0; i < bases.length; i++) {
    const base = bases[i];
    try {
      const res = await fetch(base + path, options);
      if (res.status === 401) {
        sawUnauthorized = true;
        lastErr = new Error("SIGN_IN");
        continue;
      }
      if (res.status === 404 && i < bases.length - 1) {
        lastErr = new Error("Not found");
        continue;
      }
      await chrome.storage.local.set({ veil_api_base: base });
      return res;
    } catch (err) {
      lastErr = err;
    }
  }
  if (sawUnauthorized) {
    await chrome.storage.local.remove(["veil_token", "veil_email", "docmaxxing_key"]);
    throw new Error("SIGN_IN");
  }
  if (isNetworkError(lastErr)) {
    throw new Error("Server offline. Start Flask on :5001, or sign in on docmaxxing.com.");
  }
  throw lastErr || new Error("Could not reach the server.");
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryable(err) {
  const msg = String((err && err.message) || err || "");
  return /503|502|429|timeout|timed out|failed to fetch|network|try again|busy/i.test(msg);
}

async function askApiOnce(text, images, extended, model) {
  const stored = await chrome.storage.local.get(["veil_token"]);
  const token = String(stored.veil_token || "").trim();
  if (!token) {
    throw new Error("SIGN_IN");
  }
  const res = await apiFetch("/api/veil/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify({ text, images, extended, model }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.message || "Could not get an answer. Try again.");
  }
  if (typeof data.balance === "number") {
    await chrome.storage.local.set({ veil_balance: data.balance });
  }
  return String(data.answer ?? "");
}

async function askApi(text, images, extended, model) {
  let lastErr;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      return await askApiOnce(text, images, extended, model);
    } catch (err) {
      lastErr = err;
      if (String(err && err.message) === "SIGN_IN" || !isRetryable(err) || attempt === 3) break;
      await sleep(800 * attempt);
    }
  }
  const msg = String((lastErr && lastErr.message) || lastErr || "");
  if (msg === "SIGN_IN") {
    throw new Error("Sign in from the Veil icon first.");
  }
  throw new Error(msg || "Could not get an answer. Try again.");
}

let humanizeBusy = false;

async function humanizeApi(text, key) {
  const stored = await chrome.storage.local.get(["veil_token", "docmaxxing_key"]);
  const token = String(key || stored.docmaxxing_key || stored.veil_token || "").trim();
  if (!token) {
    throw new Error("SIGN_IN");
  }
  const res = await apiFetch("/api/extension/humanize", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify({ text, key: token }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.message || data.error || "Could not humanize. Try again.");
  }
  const humanized = String(data.humanized_text || "").trim();
  if (!humanized) {
    throw new Error("Humanizer returned empty text. Try again.");
  }
  const srcWords = String(text || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean).length;
  const outWords = humanized.split(/\s+/).filter(Boolean).length;
  if (
    /^(gemini|chatgpt|gpt-?4o?|claude|sonnet|haiku|copy|cut|paste|undo|redo|humanize|rehumanize)$/i.test(
      humanized
    ) ||
    (srcWords >= 20 && outWords < 5)
  ) {
    throw new Error("Humanizer returned unusable text. Try again.");
  }
  if (typeof data.balance === "number") {
    await chrome.storage.local.set({ veil_balance: data.balance });
  }
  return humanized;
}

function captureVisiblePng() {
  return new Promise((resolve, reject) => {
    chrome.tabs.captureVisibleTab({ format: "png" }, (dataUrl) => {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      if (!dataUrl) {
        reject(new Error("Empty screenshot"));
        return;
      }
      resolve(dataUrl);
    });
  });
}

async function hudToTab(tabId, payload) {
  if (!tabId || !payload) return;
  try {
    await chrome.tabs.sendMessage(tabId, { action: "hz_hud", payload });
    return;
  } catch (_err) {
    /* content script may not be listening yet */
  }
  try {
    await chrome.scripting.executeScript({
      target: { tabId, allFrames: false },
      func: (data) => {
        if (typeof window.__veilHzHud === "function") window.__veilHzHud(data);
      },
      args: [payload],
    });
  } catch (_err2) {
    /* page may not allow injection */
  }
}

async function pingTab(tabId, message) {
  if (!tabId) return;
  const inject = () =>
    chrome.scripting.executeScript({
      target: { tabId, allFrames: true },
      files: ["content.js"],
    });
  const sendAll = async () => {
    if (message && message.action === "quick_humanize") {
      await chrome.scripting.executeScript({
        target: { tabId, allFrames: true },
        func: () => {
          if (typeof window.__veilQuickHumanize === "function") {
            window.__veilQuickHumanize();
            return true;
          }
          return false;
        },
      });
      return;
    }
    await chrome.tabs.sendMessage(tabId, message);
  };
  try {
    await sendAll();
  } catch (_err) {
    await inject();
    await sendAll();
  }
}

async function togglePanelOnTab(tabId) {
  await pingTab(tabId, { action: "toggle_panel" });
}

chrome.commands.onCommand.addListener((command) => {
  if (command !== "quick-humanize") return;
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    if (tab && tab.id) pingTab(tab.id, { action: "quick_humanize" });
  });
});

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message && message.type === "TOGGLE_PANEL") {
    const tabId = sender.tab && sender.tab.id;
    const run = async () => {
      if (tabId) {
        await togglePanelOnTab(tabId);
        return;
      }
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab && tab.id) await togglePanelOnTab(tab.id);
    };
    run()
      .then(() => sendResponse({ ok: true }))
      .catch((err) =>
        sendResponse({ ok: false, error: String(err && err.message ? err.message : err) })
      );
    return true;
  }
  return false;
});

chrome.runtime.onMessageExternal.addListener((message, sender, sendResponse) => {
  if (!message || message.type !== "VEIL_AUTH" || !message.token) {
    return false;
  }
  const origin = originOf(sender);
  const patch = {
    veil_token: String(message.token),
    veil_email: String(message.email || ""),
    veil_balance: typeof message.balance === "number" ? message.balance : null,
  };
  if (origin) patch.veil_api_base = origin;
  chrome.storage.local
    .set(patch)
    .then(() => sendResponse({ ok: true }))
    .catch(() => sendResponse({ ok: false }));
  return true;
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || !message.type) {
    return false;
  }

  if (message.type === "TAKE_SCREENSHOT") {
    captureVisiblePng()
      .then((dataUrl) => sendResponse({ ok: true, dataUrl }))
      .catch((err) => sendResponse({ ok: false, error: String(err && err.message ? err.message : err) }));
    return true;
  }

  if (message.type === "HUMANIZE_HUD") {
    const tabId = _sender.tab && _sender.tab.id;
    hudToTab(tabId, message.payload || {});
    sendResponse({ ok: true });
    return false;
  }

  if (message.type === "HUMANIZE_APPLY") {
    const tabId = _sender.tab && _sender.tab.id;
    const payload = message.payload || {};
    const original = String(payload.original || "");
    const next = String(payload.next || "");
    if (!tabId || !original || !next) {
      sendResponse({ ok: false });
      return false;
    }
    chrome.scripting
      .executeScript({
        target: { tabId, allFrames: true },
        func: (orig, text) => {
          if (typeof window.__veilApplyHumanize === "function") {
            return !!window.__veilApplyHumanize(orig, text);
          }
          return false;
        },
        args: [original, next],
      })
      .then((rows) => sendResponse({ ok: !!(rows && rows.some((row) => row && row.result)) }))
      .catch(() => sendResponse({ ok: false }));
    return true;
  }

  if (message.type === "HUMANIZE_TEXT") {
    const tabId = _sender.tab && _sender.tab.id;
    const payload = message.payload || {};
    const text = String(payload.text || "").trim();
    const key = String(payload.key || "").trim();
    if (!text) {
      hudToTab(tabId, { phase: "error", text: "Highlight text first." });
      sendResponse({ ok: false, error: "Highlight text first." });
      return false;
    }
    if (humanizeBusy) {
      sendResponse({ ok: false, error: "Already humanizing" });
      return false;
    }
    humanizeBusy = true;
    hudToTab(tabId, { phase: "loading" });
    humanizeApi(text, key)
      .then((humanized) => {
        sendResponse({ ok: true, humanized_text: humanized });
      })
      .catch((err) => {
        const msg = String((err && err.message) || err || "");
        const error = msg === "SIGN_IN" ? "Sign in from the Veil icon first." : msg;
        hudToTab(tabId, { phase: "error", text: error });
        sendResponse({ ok: false, error });
      })
      .finally(() => {
        humanizeBusy = false;
      });
    return true;
  }

  if (message.type !== "ASK_AI") {
    return false;
  }

  const payload = message.payload || {};
  const text = String(payload.text || "").trim();
  const images = Array.isArray(payload.images) ? payload.images.filter(Boolean) : [];
  const extended = !!payload.extended;
  const model = payload.model === "deep" ? "deep" : "fast";
  if (!text && !images.length) {
    sendResponse({ ok: false, error: "Type a question or attach an image." });
    return false;
  }

  askApi(text, images, extended, model)
    .then((answer) => sendResponse({ ok: true, answer }))
    .catch((err) => sendResponse({ ok: false, error: String(err && err.message ? err.message : err) }));
  return true;
});
