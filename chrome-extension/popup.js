const statusEl = document.getElementById("status");
const signInBtn = document.getElementById("sign-in");
const renewBtn = document.getElementById("renew");
const signOutBtn = document.getElementById("sign-out");

function apiBase() {
  return "__VEIL_API_BASE__".startsWith("__") ? "http://127.0.0.1:5001" : "__VEIL_API_BASE__";
}

async function render() {
  const stored = await chrome.storage.local.get(["veil_token", "veil_email", "veil_balance"]);
  if (!stored.veil_token) {
    statusEl.textContent = "Sign in with your DocMaxxing account. Access lasts 30 days after you pay on the site.";
    signInBtn.hidden = false;
    renewBtn.hidden = true;
    signOutBtn.hidden = true;
    return;
  }
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
    const res = await fetch(apiBase().replace(/\/$/, "") + "/api/veil/me", {
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

signInBtn.addEventListener("click", () => {
  chrome.tabs.create({ url: apiBase().replace(/\/$/, "") + "/veil/connect" });
  window.close();
});

renewBtn.addEventListener("click", () => {
  chrome.tabs.create({ url: apiBase().replace(/\/$/, "") + "/veil#access" });
  window.close();
});

signOutBtn.addEventListener("click", async () => {
  const stored = await chrome.storage.local.get(["veil_token"]);
  if (stored.veil_token) {
    try {
      await fetch(apiBase().replace(/\/$/, "") + "/api/veil/revoke", {
        method: "POST",
        headers: { Authorization: "Bearer " + stored.veil_token },
      });
    } catch (_err) {
      /* local sign-out still happens */
    }
  }
  await chrome.storage.local.remove(["veil_token", "veil_email", "veil_balance"]);
  render();
});

render();
