/**
 * Floating support helpdesk: web ↔ Telegram two-way chat.
 * Polls GET /api/chat/messages every 5s while the panel is open.
 */
(function () {
  var layer = document.getElementById("support_chat_layer");
  var toggle = document.getElementById("support_chat_toggle");
  var messageEl = document.getElementById("support_chat_message");
  var sendBtn = document.getElementById("support_chat_send");
  var statusEl = document.getElementById("support_chat_status");
  var threadEl = document.getElementById("support_chat_thread");

  if (!layer || !toggle || !messageEl || !sendBtn) {
    return;
  }

  var OPEN_CLASS = "is-open";
  var POLL_MS = 5000;
  var pollTimer = null;
  var knownIds = {};
  var lastId = 0;
  var authenticated =
    !!(window.DM_AUTH && window.DM_AUTH.authenticated);

  function esc(text) {
    return String(text == null ? "" : text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setStatus(text, kind) {
    if (!statusEl) {
      return;
    }
    statusEl.textContent = text || "";
    statusEl.className =
      "support-chat-status" + (kind ? " support-chat-status--" + kind : "");
  }

  function isOpen() {
    return layer.classList.contains(OPEN_CLASS);
  }

  function scrollThreadToBottom() {
    if (!threadEl) return;
    threadEl.scrollTop = threadEl.scrollHeight;
  }

  function appendMessage(msg, opts) {
    if (!threadEl || !msg || msg.id == null) return;
    var id = String(msg.id);
    if (knownIds[id]) return;
    knownIds[id] = true;
    if (Number(msg.id) > lastId) lastId = Number(msg.id);

    var sender = msg.sender === "admin" ? "admin" : "user";
    var label = sender === "admin" ? "Support" : "You";
    var bubble = document.createElement("div");
    bubble.className = "support-chat-bubble support-chat-bubble--" + sender;
    bubble.setAttribute("data-msg-id", id);
    bubble.innerHTML =
      '<span class="support-chat-bubble-label">' +
      esc(label) +
      "</span>" +
      '<p class="support-chat-bubble-text">' +
      esc(msg.message).replace(/\n/g, "<br>") +
      "</p>";
    threadEl.appendChild(bubble);
    if (!opts || opts.scroll !== false) {
      scrollThreadToBottom();
    }
  }

  function renderEmptyHint() {
    if (!threadEl || threadEl.children.length) return;
    var hint = document.createElement("p");
    hint.className = "support-chat-empty";
    hint.setAttribute("data-support-empty", "1");
    if (!authenticated) {
      hint.textContent = "Sign in to chat with support.";
    } else {
      hint.textContent = "Send a message — we reply here from Telegram.";
    }
    threadEl.appendChild(hint);
  }

  function clearEmptyHint() {
    if (!threadEl) return;
    var empty = threadEl.querySelector("[data-support-empty]");
    if (empty) empty.remove();
  }

  async function fetchMessages(opts) {
    if (!authenticated || !threadEl) return;
    var incremental = !!(opts && opts.incremental);
    var url = "/api/chat/messages";
    if (incremental && lastId > 0) {
      url += "?after_id=" + encodeURIComponent(String(lastId));
    }
    try {
      var res = await fetch(url, {
        method: "GET",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (res.status === 401) {
        authenticated = false;
        setStatus("Please sign in to use support chat.", "error");
        return;
      }
      if (!res.ok) return;
      var data = await res.json();
      var list = (data && data.messages) || [];
      if (!list.length) {
        if (!incremental) renderEmptyHint();
        return;
      }
      clearEmptyHint();
      list.forEach(function (msg) {
        appendMessage(msg, { scroll: true });
      });
    } catch (err) {
      /* polling stays quiet on transient network errors */
    }
  }

  function startPolling() {
    stopPolling();
    if (!authenticated) return;
    pollTimer = setInterval(function () {
      if (isOpen()) fetchMessages({ incremental: true });
    }, POLL_MS);
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  function openPanel() {
    layer.classList.add(OPEN_CLASS);
    layer.setAttribute("aria-hidden", "false");
    toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("support-chat-open");
    setStatus("");
    if (authenticated) {
      fetchMessages({ incremental: false }).then(function () {
        startPolling();
      });
    } else {
      renderEmptyHint();
      setStatus("Sign in to send and receive replies.", "error");
    }
    messageEl.focus();
  }

  function closePanel() {
    layer.classList.remove(OPEN_CLASS);
    layer.setAttribute("aria-hidden", "true");
    toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("support-chat-open");
    stopPolling();
    toggle.focus();
  }

  toggle.addEventListener("click", function () {
    if (isOpen()) {
      closePanel();
    } else {
      openPanel();
    }
  });

  layer.querySelectorAll("[data-support-close]").forEach(function (el) {
    el.addEventListener("click", function () {
      closePanel();
    });
  });

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape" && isOpen()) {
      closePanel();
    }
  });

  sendBtn.addEventListener("click", async function () {
    var userMessage = (messageEl.value || "").trim();
    setStatus("");
    if (!userMessage) {
      setStatus("Please enter a message.", "error");
      return;
    }
    if (!authenticated) {
      setStatus("Please sign in to use support chat.", "error");
      return;
    }
    sendBtn.disabled = true;
    setStatus("Sending…", "pending");
    try {
      var res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: JSON.stringify({ message: userMessage }),
      });
      var data = {};
      try {
        data = await res.json();
      } catch (e2) {
        setStatus("Could not read server response.", "error");
        return;
      }
      if (res.status === 401) {
        authenticated = false;
        setStatus("Please sign in to use support chat.", "error");
        return;
      }
      if (!res.ok) {
        setStatus(data.error || "Something went wrong.", "error");
        // Still show locally saved message if server persisted it.
        if (data.message) {
          clearEmptyHint();
          appendMessage(data.message);
        }
        return;
      }
      messageEl.value = "";
      clearEmptyHint();
      if (data.message) {
        appendMessage(data.message);
      } else {
        appendMessage({
          id: "local-" + Date.now(),
          sender: "user",
          message: userMessage,
        });
      }
      setStatus("Message sent", "success");
    } catch (err) {
      setStatus("Could not send — check your connection or try again.", "error");
    } finally {
      sendBtn.disabled = false;
    }
  });
})();
