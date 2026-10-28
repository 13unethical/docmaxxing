const statusEl = document.getElementById("status");
const openPanelBtn = document.getElementById("open-panel");
const signInBtn = document.getElementById("sign-in");
const renewBtn = document.getElementById("renew");
const signOutBtn = document.getElementById("sign-out");

function packedApiBase() {
  return "__VEIL_API_BASE__".startsWith("__") ? "" : "__VEIL_API_BASE__".replace(/\/$/, "");
}

async function apiBase() {
  const stored = await chrome.storage.local.get(["veil_api_base"]);
  return String(stored.veil_api_base || packedApiBase() || "https://docmaxxing.com").replace(/\/$/, "");
}

async function render() {
  const stored = await chrome.storage.local.get(["veil_token", "veil_email", "veil_balance"]);
  if (!stored.veil_token) {
    statusEl.textContent = "Sign in with your DocMaxxing account. Access lasts 30 days after you pay on the site.";
    openPanelBtn.hidden = true;
    signInBtn.hidden = false;
    renewBtn.hidden = true;
    signOutBtn.hidden = true;
    return;
  }
  openPanelBtn.hidden = false;
  signInBtn.hidden = true;
  signOutBtn.hidden = false;
  renewBtn.hidden = true;
  statusEl.innerHTML = "";
  const email = document.createElement("span");
  email.className = "email";
  email.textContent = stored.veil_email || "Signed in";
  statusEl.append(email);
  const line = document.createElement("span");
  line.textContent = " — loading balance…";
  statusEl.append(line);
  try {
    const res = await fetch((await apiBase()) + "/api/veil/me", {
      headers: { Authorization: "Bearer " + stored.veil_token },
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      await chrome.storage.local.remove(["veil_token", "veil_email", "veil_balance"]);
      render();
      return;
    }
    await chrome.storage.local.set({ veil_email: data.email, veil_balance: data.balance });
    if (data.pass_active) {
      line.textContent = " · active until " + (data.pass_expires_label || "this month");
      renewBtn.hidden = true;
    } else {
      line.textContent = " · access ended. Pay again on the site to continue.";
      renewBtn.hidden = false;
    }
  } catch (_err) {
    const balance = typeof stored.veil_balance === "number" ? stored.veil_balance + " credits" : "offline";
    line.textContent = " · " + balance;
  }
}

openPanelBtn.addEventListener("click", () => {
  chrome.runtime.sendMessage({ type: "TOGGLE_PANEL" }, () => {
    void chrome.runtime.lastError;
    window.close();
  });
});

signInBtn.addEventListener("click", async () => {
  chrome.tabs.create({ url: (await apiBase()) + "/veil/connect" });
  window.close();
});

renewBtn.addEventListener("click", async () => {
  chrome.tabs.create({ url: (await apiBase()) + "/veil#access" });
  window.close();
});

signOutBtn.addEventListener("click", async () => {
  const stored = await chrome.storage.local.get(["veil_token"]);
  if (stored.veil_token) {
    try {
      await fetch((await apiBase()) + "/api/veil/revoke", {
        method: "POST",
        headers: { Authorization: "Bearer " + stored.veil_token },
      });
    } catch (_err) {
      /* local sign-out still happens */
    }
  }
  await chrome.storage.local.remove(["veil_token", "veil_email", "veil_balance", "veil_api_base"]);
  render();
});

render();
