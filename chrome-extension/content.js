try {
  (() => {
    const host = document.createElement("div");
    Object.assign(host.style, {
      position: "fixed",
      top: "0",
      left: "0",
      width: "100%",
      height: "100%",
      pointerEvents: "none",
      zIndex: "2147483647",
    });

    const shadow = host.attachShadow({ mode: "closed" });

    const style = document.createElement("style");
    style.textContent = `
    :host { all: initial; }
    .panel {
      pointer-events: auto;
      position: fixed;
      top: 20px;
      right: 20px;
      width: 220px;
      max-width: calc(100vw - 32px);
      display: none;
      flex-direction: column;
      max-height: 85vh;
      box-sizing: border-box;
      padding: 6px;
      padding-top: 14px;
      border-radius: 10px;
      background: #111;
      color: #f5f5f5;
      font: 13px/1.4 system-ui, sans-serif;
      box-shadow: 0 8px 32px rgba(0, 0, 0, 0.45);
      transition: none;
    }
    .drag-handle {
      height: 20px;
      width: 100%;
      cursor: grab;
      background: transparent;
      position: absolute;
      top: 0;
      left: 0;
      z-index: 10;
    }
    .image-preview-container {
      display: none;
      flex-direction: row;
      flex-wrap: nowrap;
      gap: 8px;
      overflow-x: auto;
      overflow-y: hidden;
      margin: 0 0 8px;
      padding-bottom: 4px;
    }
    .thumb {
      position: relative;
      flex: 0 0 auto;
      width: 64px;
      height: 64px;
      border-radius: 6px;
      overflow: hidden;
      background: #1c1c1c;
      border: 1px solid #333;
    }
    .thumb img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
      pointer-events: none;
    }
    .thumb-remove {
      position: absolute;
      top: 2px;
      right: 2px;
      width: 16px;
      height: 16px;
      border: 0;
      border-radius: 50%;
      background: #000;
      color: #fff;
      font: 11px/16px system-ui, sans-serif;
      cursor: pointer;
      padding: 0;
    }
    textarea {
      display: block;
      width: 100%;
      min-height: 32px;
      box-sizing: border-box;
      resize: vertical;
      margin: 0 0 6px;
      padding: 4px;
      border: 1px solid #333;
      border-radius: 6px;
      background: #1c1c1c;
      color: inherit;
      font: inherit;
      font-size: 11px;
      outline: none;
    }
    .row {
      display: flex;
      justify-content: flex-end;
      align-items: center;
    }
    .row label {
      margin-right: auto;
      cursor: pointer;
      font-size: 10px;
      color: #ccc;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    button.screenshot {
      width: 28px;
      height: 28px;
      padding: 0;
      border: 0;
      border-radius: 8px;
      background: #333;
      color: #fff;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-right: 4px;
      transition: background 0.2s;
    }
    button.screenshot:hover { background: #444; }
    button.screenshot svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; }
    button.send {
      width: 28px;
      height: 28px;
      padding: 0;
      border: 0;
      border-radius: 8px;
      background: #2f6fed;
      color: #fff;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      margin-right: 4px;
    }
    button.send:disabled { opacity: 0.55; cursor: default; }
    button.send svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2; }
    .chat-history {
      flex: 1;
      min-height: 40px;
      max-height: 120px;
      overflow-y: auto;
      display: flex;
      flex-direction: column;
      gap: 4px;
      margin-bottom: 6px;
    }
    .msg {
      padding: 4px 8px;
      border-radius: 8px;
      max-width: 90%;
      word-break: break-word;
      white-space: pre-wrap;
      font-size: 11px;
    }
    .msg.user {
      background: #2f6fed;
      align-self: flex-end;
    }
    .msg.ai {
      background: #333;
      align-self: flex-start;
    }
    .crop-overlay {
      pointer-events: auto;
      position: fixed;
      inset: 0;
      z-index: 999999;
      cursor: crosshair;
      background-color: #000;
      background-repeat: no-repeat;
      background-position: 0 0;
      background-size: 100% 100%;
    }
    .crop-rect {
      position: absolute;
      box-sizing: border-box;
      border: 1px solid #2f6fed;
      background: rgba(47, 111, 237, 0.2);
      pointer-events: none;
    }
  `;

    const panel = document.createElement("div");
    panel.className = "panel";

    const preview = document.createElement("div");
    preview.className = "image-preview-container";

    const textarea = document.createElement("textarea");
    textarea.placeholder = "Вставьте вопрос...";

    const row = document.createElement("div");
    row.className = "row";

    const screenshotBtn = document.createElement("button");
    screenshotBtn.type = "button";
    screenshotBtn.className = "screenshot";
    screenshotBtn.setAttribute("aria-label", "Сделать скриншот");
    screenshotBtn.innerHTML =
      '<svg viewBox="0 0 24 24"><path d="M6 2v14a2 2 0 0 0 2 2h14"/><path d="M18 22V8a2 2 0 0 0-2-2H2"/></svg>';

    const extendedLabel = document.createElement("label");
    Object.assign(extendedLabel.style, { marginRight: "auto", cursor: "pointer" });
    const extendedToggle = document.createElement("input");
    extendedToggle.type = "checkbox";
    extendedToggle.id = "extended-toggle";
    extendedLabel.append(extendedToggle, document.createTextNode(" Развернутый"));

    const sendBtn = document.createElement("button");
    sendBtn.type = "button";
    sendBtn.className = "send";
    sendBtn.setAttribute("aria-label", "Отправить");
    sendBtn.innerHTML =
      '<svg viewBox="0 0 24 24"><path d="M22 2L11 13"/><path d="M22 2L15 22l-4-9-9-4 20-7z"/></svg>';

    const chatHistory = document.createElement("div");
    chatHistory.className = "chat-history";

    const dragHandle = document.createElement("div");
    dragHandle.className = "drag-handle";

    row.append(extendedLabel, screenshotBtn, sendBtn);
    panel.append(chatHistory, preview, textarea, row);
    panel.appendChild(dragHandle);
    shadow.append(style, panel);

    function mountHost() {
      if (document.documentElement && !host.isConnected) {
        document.documentElement.appendChild(host);
      }
    }
    mountHost();
    if (!host.isConnected) {
      document.addEventListener("DOMContentLoaded", mountHost, { once: true });
    }

    const images = [];
    let pending = false;
    let capturing = false;

    function appendMsg(role, text, imgs = []) {
      const msg = document.createElement("div");
      msg.className = "msg " + role;
      if (text) {
        const span = document.createElement("span");
        span.textContent = text;
        msg.appendChild(span);
      }
      if (imgs && imgs.length) {
        imgs.forEach((src) => {
          const img = document.createElement("img");
          img.src = src;
          img.style.maxWidth = "50px";
          img.style.maxHeight = "50px";
          img.style.objectFit = "cover";
          img.style.borderRadius = "4px";
          img.style.display = "block";
          msg.appendChild(img);
        });
      }
      chatHistory.appendChild(msg);
      chatHistory.scrollTop = chatHistory.scrollHeight;
      return msg;
    }

    function setPanelDisplay(value) {
      panel.style.display = value;
    }

    function toggleAssistantPanelImpl() {
      const opening = panel.style.display !== "flex";
      if (opening) {
        const selected = String(
          (window.getSelection && window.getSelection().toString()) || ""
        ).trim();
        if (selected) textarea.value = selected;
      }
      setPanelDisplay(opening ? "flex" : "none");
      if (opening) textarea.focus();
    }

    function isolate(el) {
      [
        "keydown",
        "keyup",
        "keypress",
        "click",
        "mousedown",
        "mouseup",
        "mousemove",
        "wheel",
        "pointerdown",
        "pointerup",
        "pointermove",
      ].forEach((type) => {
        el.addEventListener(type, (e) => {
          e.stopPropagation();
          e.stopImmediatePropagation();
        });
      });
    }

    isolate(panel);

    let isDragging = false;
    let currentX;
    let currentY;
    let initialX;
    let initialY;
    let xOffset = 0;
    let yOffset = 0;

    dragHandle.addEventListener("mousedown", (e) => {
      e.preventDefault();
      e.stopPropagation();
      isDragging = true;
      dragHandle.style.cursor = "grabbing";
      initialX = e.clientX - xOffset;
      initialY = e.clientY - yOffset;
    });

    window.addEventListener(
      "mousemove",
      (e) => {
        if (isDragging !== true) return;
        e.preventDefault();
        currentX = e.clientX - initialX;
        currentY = e.clientY - initialY;
        xOffset = currentX;
        yOffset = currentY;
        panel.style.transform = "translate3d(" + currentX + "px, " + currentY + "px, 0)";
      },
      true
    );

    window.addEventListener(
      "mouseup",
      () => {
        if (!isDragging) return;
        isDragging = false;
        dragHandle.style.cursor = "grab";
      },
      true
    );

    function renderThumbs() {
      preview.innerHTML = "";
      preview.style.display = images.length ? "flex" : "none";
      images.forEach((src, index) => {
        const thumb = document.createElement("div");
        thumb.className = "thumb";
        const img = document.createElement("img");
        img.src = src;
        img.alt = "";
        const remove = document.createElement("button");
        remove.type = "button";
        remove.className = "thumb-remove";
        remove.textContent = "×";
        remove.addEventListener("click", (e) => {
          e.preventDefault();
          e.stopPropagation();
          images.splice(index, 1);
          renderThumbs();
        });
        thumb.append(img, remove);
        preview.appendChild(thumb);
      });
    }

    function cropDataUrl(dataUrl, box) {
      return new Promise((resolve, reject) => {
        const img = new Image();
        img.onload = () => {
          const vw = window.innerWidth || 1;
          const vh = window.innerHeight || 1;
          const sx = Math.round((box.x / vw) * img.naturalWidth);
          const sy = Math.round((box.y / vh) * img.naturalHeight);
          const sw = Math.max(1, Math.round((box.w / vw) * img.naturalWidth));
          const sh = Math.max(1, Math.round((box.h / vh) * img.naturalHeight));
          const canvas = document.createElement("canvas");
          canvas.width = sw;
          canvas.height = sh;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
          resolve(canvas.toDataURL("image/png"));
        };
        img.onerror = () => reject(new Error("Не удалось загрузить скриншот"));
        img.src = dataUrl;
      });
    }

    function startCrop(dataUrl) {
      const overlay = document.createElement("div");
      overlay.className = "crop-overlay";
      overlay.style.backgroundImage = `url("${dataUrl}")`;

      const rect = document.createElement("div");
      rect.className = "crop-rect";
      overlay.appendChild(rect);
      shadow.appendChild(overlay);
      host.style.pointerEvents = "auto";

      let startX = 0;
      let startY = 0;
      let dragging = false;

      function boxFrom(e) {
        const x1 = Math.max(0, Math.min(startX, e.clientX));
        const y1 = Math.max(0, Math.min(startY, e.clientY));
        const x2 = Math.min(window.innerWidth, Math.max(startX, e.clientX));
        const y2 = Math.min(window.innerHeight, Math.max(startY, e.clientY));
        return { x: x1, y: y1, w: x2 - x1, h: y2 - y1 };
      }

      function paint(box) {
        rect.style.left = box.x + "px";
        rect.style.top = box.y + "px";
        rect.style.width = box.w + "px";
        rect.style.height = box.h + "px";
      }

      function cleanup() {
        overlay.remove();
        host.style.pointerEvents = "none";
        capturing = false;
      }

      overlay.addEventListener("mousedown", (e) => {
        e.preventDefault();
        e.stopPropagation();
        dragging = true;
        startX = e.clientX;
        startY = e.clientY;
        paint(boxFrom(e));
      });

      overlay.addEventListener("mousemove", (e) => {
        if (!dragging) return;
        e.preventDefault();
        e.stopPropagation();
        paint(boxFrom(e));
      });

      overlay.addEventListener("mouseup", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (!dragging) {
          cleanup();
          return;
        }
        dragging = false;
        const box = boxFrom(e);
        if (box.w < 4 || box.h < 4) {
          cleanup();
          return;
        }
        cropDataUrl(dataUrl, box)
          .then((cropped) => {
            images.push(cropped);
            renderThumbs();
            setPanelDisplay("flex");
          })
          .catch((err) => {
            appendMsg("ai", err.message || "Ошибка обрезки");
            setPanelDisplay("flex");
          })
          .finally(cleanup);
      });

      overlay.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          cleanup();
        }
      });
    }

    function takeScreenshot() {
      if (capturing || pending) return;
      capturing = true;
      const wasOpen = panel.style.display === "flex";
      setPanelDisplay("none");

      requestAnimationFrame(() => {
        chrome.runtime.sendMessage({ type: "TAKE_SCREENSHOT" }, (res) => {
          if (chrome.runtime.lastError || !res || !res.ok) {
            capturing = false;
            if (wasOpen) setPanelDisplay("flex");
            appendMsg(
              "ai",
              (res && res.error) ||
                (chrome.runtime.lastError && chrome.runtime.lastError.message) ||
                "Не удалось сделать скриншот"
            );
            setPanelDisplay("flex");
            return;
          }
          startCrop(res.dataUrl);
        });
      });
    }

    async function ask() {
      const text = textarea.value.trim();
      const extended = !!extendedToggle.checked;
      if ((!text && !images.length) || pending) return;

      const payloadImages = images.slice();
      appendMsg("user", text, payloadImages);
      textarea.value = "";
      images.length = 0;
      renderThumbs();
      pending = true;
      sendBtn.disabled = true;

      chrome.runtime.sendMessage(
        { type: "ASK_AI", payload: { text, images: payloadImages, extended } },
        (res) => {
          pending = false;
          sendBtn.disabled = false;
          if (chrome.runtime.lastError) {
            appendMsg("ai", chrome.runtime.lastError.message);
            return;
          }
          if (!res || !res.ok) {
            appendMsg("ai", (res && res.error) || "Ошибка запроса");
            return;
          }
          appendMsg("ai", res.answer || "");
        }
      );
    }

    chrome.runtime.onMessage.addListener((message) => {
      if (message && message.action === "toggle_panel") {
        toggleAssistantPanelImpl();
      }
    });

    window.addEventListener(
      "keydown",
      (e) => {
        if (e.altKey && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
          if (e.code === "KeyQ" || e.key.toLowerCase() === "q") {
            e.preventDefault();
            e.stopImmediatePropagation();
            toggleAssistantPanelImpl();
          } else if (e.code === "KeyS" || e.key.toLowerCase() === "s") {
            e.preventDefault();
            e.stopImmediatePropagation();
            takeScreenshot();
          }
        }
      },
      true
    );

    screenshotBtn.addEventListener("mousedown", (e) => e.stopPropagation());
    screenshotBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      takeScreenshot();
    });
    sendBtn.addEventListener("click", ask);
    textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        ask();
      }
    });
  })();
} catch (err) {
  console.error("Veil failed to start:", err);
}
