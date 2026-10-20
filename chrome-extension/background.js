// Replaced with the site origin when the zip is built. Unpacked from the repo, it talks to local Flask.
const VEIL_API_BASE = "__VEIL_API_BASE__".startsWith("__")
  ? "http://127.0.0.1:5001"
  : "__VEIL_API_BASE__";

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryable(err) {
  const msg = String((err && err.message) || err || "");
  return /503|429|timeout|timed out|failed to fetch|network/i.test(msg);
}

async function askApiOnce(text, images, extended) {
  const stored = await chrome.storage.local.get(["veil_token"]);
  const token = String(stored.veil_token || "").trim();
  if (!token) {
    throw new Error("SIGN_IN");
  }
  const res = await fetch(VEIL_API_BASE.replace(/\/$/, "") + "/api/veil/ask", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: "Bearer " + token,
    },
    body: JSON.stringify({ text, images, extended }),
  });
  const data = await res.json().catch(() => ({}));
  if (res.status === 401) {
    await chrome.storage.local.remove(["veil_token", "veil_email"]);
    throw new Error("SIGN_IN");
  }
  if (!res.ok) {
    throw new Error(data.message || "Could not get an answer. Try again.");
  }
  if (typeof data.balance === "number") {
    await chrome.storage.local.set({ veil_balance: data.balance });
  }
  return String(data.answer ?? "");
}

async function askApi(text, images, extended) {
  let lastErr;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      return await askApiOnce(text, images, extended);
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

chrome.runtime.onMessageExternal.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "VEIL_AUTH" || !message.token) {
    return false;
  }
  chrome.storage.local
    .set({
      veil_token: String(message.token),
      veil_email: String(message.email || ""),
      veil_balance: typeof message.balance === "number" ? message.balance : null,
    })
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

  if (message.type !== "ASK_AI") {
    return false;
  }

  const payload = message.payload || {};
  const text = String(payload.text || "").trim();
  const images = Array.isArray(payload.images) ? payload.images.filter(Boolean) : [];
  const extended = !!payload.extended;
  if (!text && !images.length) {
    sendResponse({ ok: false, error: "Type a question or attach an image." });
    return false;
  }

  askApi(text, images, extended)
    .then((answer) => sendResponse({ ok: true, answer }))
    .catch((err) => sendResponse({ ok: false, error: String(err && err.message ? err.message : err) }));
  return true;
});
