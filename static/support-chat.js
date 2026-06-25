/**
 * Floating support widget: opens panel, POST /api/feedback with message.
 */
(function () {
  var layer = document.getElementById("support_chat_layer");
  var toggle = document.getElementById("support_chat_toggle");
  var messageEl = document.getElementById("support_chat_message");
  var sendBtn = document.getElementById("support_chat_send");
  var statusEl = document.getElementById("support_chat_status");

  if (!layer || !toggle || !messageEl || !sendBtn) {
    return;
  }

  var OPEN_CLASS = "is-open";

  function setStatus(text, kind) {
    if (!statusEl) {
      return;
    }
    statusEl.textContent = text || "";
    statusEl.className = "support-chat-status" + (kind ? " support-chat-status--" + kind : "");
  }

  function isOpen() {
    return layer.classList.contains(OPEN_CLASS);
  }

  function openPanel() {
    layer.classList.add(OPEN_CLASS);
    layer.setAttribute("aria-hidden", "false");
    toggle.setAttribute("aria-expanded", "true");
    document.body.classList.add("support-chat-open");
    setStatus("");
    messageEl.focus();
  }

  function closePanel() {
    layer.classList.remove(OPEN_CLASS);
    layer.setAttribute("aria-hidden", "true");
    toggle.setAttribute("aria-expanded", "false");
    document.body.classList.remove("support-chat-open");
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
    sendBtn.disabled = true;
    setStatus("Sending…", "pending");
    try {
      var res = await fetch("/api/feedback", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ message: userMessage }),
      });
      var data = {};
      try {
        data = await res.json();
      } catch (e2) {
        setStatus("Could not read server response.", "error");
        return;
      }
      if (!res.ok) {
        setStatus(data.error || "Something went wrong.", "error");
        return;
      }
      messageEl.value = "";
      setStatus("Message sent", "success");
    } catch (err) {
      setStatus("Could not send — check your connection or try again.", "error");
    } finally {
      sendBtn.disabled = false;
    }
  });
})();
