try {
  (() => {
    const IS_TOP = window === window.top;

    function isHumanizeHotkey(e) {
      if (!e || e.metaKey || e.repeat) return false;
      const isH = e.code === "KeyH" || String(e.key || "").toLowerCase() === "h";
      if (!isH) return false;
      if (e.ctrlKey && !e.altKey) return true;
      if (e.altKey && !e.ctrlKey && !e.shiftKey) return true;
      return false;
    }

    function installHumanizeHud() {
      if (window.__veilHzHud) return window.__veilHzHud;
      document.querySelectorAll("[data-veil-hz-root]").forEach((node) => node.remove());
      const root = document.createElement("div");
      root.setAttribute("data-veil-hz-root", "1");
      Object.assign(root.style, {
        position: "fixed",
        right: "16px",
        bottom: "16px",
        zIndex: "2147483647",
        pointerEvents: "none",
      });
      const shadow = root.attachShadow({ mode: "closed" });
      const style = document.createElement("style");
      style.textContent = `
        :host { all: initial; }
        .card {
          pointer-events: auto;
          display: none;
          align-items: center;
          gap: 8px;
          box-sizing: border-box;
          padding: 10px 12px;
          border-radius: 12px;
          background: #fff;
          color: #111;
          font: 13px/1.4 system-ui, sans-serif;
          box-shadow: 0 12px 40px rgba(0,0,0,.28);
          border: 1px solid #e6e6e6;
        }
        .card.show { display: flex; }
        .spin {
          width: 14px; height: 14px; border: 2px solid #d9e4fb; border-top-color: #2f6fed;
          border-radius: 50%; animation: hz .6s linear infinite; flex: 0 0 auto;
        }
        @keyframes hz { to { transform: rotate(360deg); } }
        .status { font-weight: 650; }
        .card.err .status { color: #b42318; font-weight: 500; }
      `;
      const card = document.createElement("div");
      card.className = "card";
      const spin = document.createElement("div");
      spin.className = "spin";
      const status = document.createElement("div");
      status.className = "status";
      status.textContent = "Working…";
      card.append(spin, status);
      shadow.append(style, card);
      function mount() {
        if (!document.documentElement) return;
        document.documentElement.appendChild(root);
      }
      mount();
      if (!root.isConnected) document.addEventListener("DOMContentLoaded", mount, { once: true });

      let hideTimer = 0;
      function hide() {
        if (hideTimer) window.clearTimeout(hideTimer);
        hideTimer = 0;
        card.classList.remove("show", "err");
      }

      function render(payload) {
        if (!payload) return;
        const phase = String(payload.phase || "");
        if (hideTimer) window.clearTimeout(hideTimer);
        if (phase === "loading") {
          mount();
          card.classList.remove("err");
          card.classList.add("show");
          spin.style.display = "block";
          status.textContent = "Working…";
          return;
        }
        if (phase === "error") {
          mount();
          card.classList.add("show", "err");
          spin.style.display = "none";
          status.textContent = String(payload.text || "Humanize failed");
          hideTimer = window.setTimeout(hide, 6000);
          return;
        }
        hide();
      }

      window.__veilHzHud = render;
      window.addEventListener("message", (event) => {
        const data = event && event.data;
        if (!data || data.source !== "veil-hz") return;
        render(data);
      });
      chrome.runtime.onMessage.addListener((message) => {
        if (message && message.action === "hz_hud") render(message.payload || message);
      });
      return render;
    }

    function installHumanize() {
      let busy = false;
      let loaderTimer = 0;
      let keepSelTimer = 0;

      function hideLoader() {
        if (loaderTimer) window.clearTimeout(loaderTimer);
        notifyHud({ phase: "done" });
      }

      function notifyHud(payload) {
        try {
          chrome.runtime.sendMessage({ type: "HUMANIZE_HUD", payload });
        } catch (_err) {
          /* worker may be asleep */
        }
        try {
          if (!IS_TOP) window.top.postMessage(Object.assign({ source: "veil-hz" }, payload), "*");
        } catch (_err2) {
          /* cross-origin top may still accept it */
        }
        if (IS_TOP && typeof window.__veilHzHud === "function") {
          window.__veilHzHud(payload);
        }
      }

      function showLoader(_target) {
        notifyHud({ phase: "loading" });
      }

      function showLoaderNote(target, text, isError) {
        hideLoader();
        notifyHud({
          phase: isError ? "error" : "result",
          text: text,
        });
      }

      function isTextField(el) {
        if (!el || el.nodeType !== 1) return false;
        const tag = String(el.tagName || "").toUpperCase();
        if (tag === "TEXTAREA") return true;
        if (tag !== "INPUT") return false;
        const type = String(el.type || "text").toLowerCase();
        return (
          !type ||
          type === "text" ||
          type === "search" ||
          type === "email" ||
          type === "url" ||
          type === "tel" ||
          type === "password" ||
          type === "number"
        );
      }

      function closestEditable(node) {
        let el = node;
        if (el && el.nodeType === 3) el = el.parentElement;
        while (el && el.nodeType === 1) {
          if (el.isContentEditable) return el;
          el = el.parentElement;
        }
        return null;
      }

      function isVeilNode(node) {
        let el = node && node.nodeType === 1 ? node : node && node.parentElement;
        while (el) {
          if (el.getAttribute && el.getAttribute("data-veil-root")) return true;
          el = el.parentElement;
        }
        return false;
      }

      function setNativeValue(el, value) {
        const proto =
          String(el.tagName || "").toUpperCase() === "TEXTAREA"
            ? HTMLTextAreaElement.prototype
            : HTMLInputElement.prototype;
        const desc = Object.getOwnPropertyDescriptor(proto, "value");
        if (desc && desc.set) desc.set.call(el, value);
        else el.value = value;
      }

      function fireInput(el) {
        if (!el) return;
        el.dispatchEvent(new Event("input", { bubbles: true }));
        el.dispatchEvent(new Event("change", { bubbles: true }));
        try {
          el.dispatchEvent(
            new InputEvent("input", {
              bubbles: true,
              composed: true,
              inputType: "insertReplacementText",
            })
          );
        } catch (_err) {
          /* older engines */
        }
      }

      function readFieldSelection(el) {
        if (!isTextField(el)) return null;
        const start = el.selectionStart;
        const end = el.selectionEnd;
        if (typeof start !== "number" || typeof end !== "number" || end <= start) return null;
        const raw = String(el.value).slice(start, end);
        const text = raw.trim();
        if (!text) return null;
        return { kind: "input", el, start, end, raw, text };
      }

      function captureHighlightSync() {
        const field = readFieldSelection(document.activeElement);
        if (field) return field;
        const sel = window.getSelection && window.getSelection();
        const raw = String((sel && sel.toString()) || "");
        const text = raw.trim();
        if (!text) return null;
        const range = sel.rangeCount ? sel.getRangeAt(0).cloneRange() : null;
        const editable = range ? closestEditable(range.commonAncestorContainer) : null;
        return {
          kind: editable ? "contenteditable" : "generic",
          el: editable || document.activeElement,
          range,
          raw,
          text,
        };
      }

      async function captureHighlight() {
        const sync = captureHighlightSync();
        if (sync) return sync;
        let copied = false;
        try {
          copied = !!document.execCommand("copy");
        } catch (_err) {
          copied = false;
        }
        if (!copied) return null;
        try {
          const text = String((await navigator.clipboard.readText()) || "").trim();
          if (!text || looksLikeUiJunk(text)) return null;
          return { kind: "editor", el: document.activeElement || document.body, raw: text, text };
        } catch (_err) {
          return null;
        }
      }

      function replaceInput(el, start, end, original, next) {
        if (!el || el.isConnected === false) return false;
        const value = String(el.value);
        let from = typeof start === "number" ? start : -1;
        let to = typeof end === "number" ? end : -1;
        const slice = from >= 0 && to >= from ? value.slice(from, to) : "";
        if (slice !== original && slice.trim() !== String(original || "").trim()) {
          const exact = original ? value.indexOf(original) : -1;
          const trimmed = original && original.trim() ? value.indexOf(original.trim()) : -1;
          if (exact >= 0) {
            from = exact;
            to = exact + original.length;
          } else if (trimmed >= 0) {
            from = trimmed;
            to = trimmed + original.trim().length;
          } else {
            return false;
          }
        }
        if (from < 0 || to < from) return false;
        try {
          el.focus();
        } catch (_err) {
          /* hidden inputs */
        }
        if (typeof el.setRangeText === "function") {
          el.setRangeText(next, from, to, "end");
        }
        setNativeValue(el, value.slice(0, from) + next + value.slice(to));
        try {
          el.selectionStart = from;
          el.selectionEnd = from + next.length;
        } catch (_err) {
          /* some inputs reject selection updates */
        }
        fireInput(el);
        return true;
      }

      function textEq(a, b) {
        const left = String(a || "");
        const right = String(b || "");
        return left === right || left.trim() === right.trim();
      }

      function looksLikeUiJunk(text) {
        const value = String(text || "").trim();
        if (!value) return true;
        if (value.length > 80) return false;
        return /^(gemini|chatgpt|gpt-?4o?|claude|sonnet|haiku|copy|cut|paste|undo|redo|humanize|rehumanize|stealthwriter|legacy\s*5\.?1|ghost\s*5\.?2)$/i.test(
          value
        );
      }

      function isPlausibleRewrite(original, next) {
        const src = String(original || "").trim();
        const out = String(next || "").trim();
        if (!out || looksLikeUiJunk(out)) return false;
        const srcWords = src.split(/\s+/).filter(Boolean).length;
        const outWords = out.split(/\s+/).filter(Boolean).length;
        if (srcWords >= 20 && outWords < 5) return false;
        if (src.length >= 80 && out.length < Math.max(24, Math.floor(src.length * 0.2))) return false;
        return true;
      }

      function selectedPlain() {
        try {
          const el = document.activeElement;
          if (isTextField(el) && typeof el.selectionStart === "number" && el.selectionEnd > el.selectionStart) {
            return String(el.value).slice(el.selectionStart, el.selectionEnd);
          }
        } catch (_err) {
          /* ignore */
        }
        try {
          return String((window.getSelection && window.getSelection().toString()) || "");
        } catch (_err2) {
          return "";
        }
      }

      function restoreSelection(original, range) {
        if (range) {
          try {
            const doc = range.startContainer.ownerDocument || document;
            const sel = doc.getSelection ? doc.getSelection() : window.getSelection();
            if (sel) {
              sel.removeAllRanges();
              sel.addRange(range);
            }
            if (textEq(selectedPlain(), original)) return true;
          } catch (_err) {
            /* stale range */
          }
        }
        if (textEq(selectedPlain(), original)) return true;
        return false;
      }

      function execInsert(doc, next) {
        const target = doc || document;
        try {
          if (target.execCommand("insertText", false, next)) return true;
        } catch (_err) {
          /* insertText is not always allowed */
        }
        return false;
      }

      function execPaste(doc) {
        const target = doc || document;
        try {
          return !!target.execCommand("paste");
        } catch (_err) {
          return false;
        }
      }

      function focusDocsEventTarget() {
        const iframe = document.querySelector("iframe.docs-texteventtarget-iframe");
        if (!iframe) return null;
        try {
          const doc = iframe.contentDocument || (iframe.contentWindow && iframe.contentWindow.document);
          if (!doc) return null;
          const el = doc.querySelector("[contenteditable='true']") || doc.body;
          if (el && el.focus) el.focus();
          return doc;
        } catch (_err) {
          return null;
        }
      }

      function focusEditor() {
        const docs = focusDocsEventTarget();
        if (docs) return docs;
        const active = document.activeElement;
        if (active && (isTextField(active) || active.isContentEditable)) return document;
        const nodes = document.querySelectorAll("[contenteditable='true'], [role='textbox']");
        for (let i = 0; i < nodes.length; i++) {
          const el = nodes[i];
          if (isVeilNode(el)) continue;
          try {
            el.focus();
            return document;
          } catch (_err) {
            /* keep looking */
          }
        }
        return document;
      }

      function dispatchPaste(el, text) {
        if (!el) return;
        try {
          const dt = new DataTransfer();
          dt.setData("text/plain", text);
          const ev = new ClipboardEvent("paste", { bubbles: true, cancelable: true, composed: true });
          Object.defineProperty(ev, "clipboardData", { value: dt });
          el.dispatchEvent(ev);
        } catch (_err) {
          try {
            el.dispatchEvent(
              new InputEvent("beforeinput", {
                inputType: "insertText",
                data: text,
                bubbles: true,
                cancelable: true,
                composed: true,
              })
            );
          } catch (_err2) {
            /* ignore */
          }
        }
      }

      async function writeClipboard(text) {
        try {
          if (navigator.clipboard && navigator.clipboard.writeText) {
            await navigator.clipboard.writeText(text);
            return true;
          }
        } catch (_err) {
          return false;
        }
        return false;
      }

      function selectionIsOriginal(original) {
        return !!(original && textEq(selectedPlain(), original));
      }

      function nativeReplaceSelected(original, next) {
        if (!selectionIsOriginal(original) || !isPlausibleRewrite(original, next)) return false;
        const docs = focusDocsEventTarget();
        if (docs) {
          execInsert(docs, next);
          if (textEq(selectedPlain(), next)) return true;
          dispatchPaste(docs.activeElement || docs.body, next);
          if (textEq(selectedPlain(), next)) return true;
        }
        focusEditor();
        restoreSelection(original, null);
        if (!selectionIsOriginal(original)) return false;
        execInsert(document, next);
        if (textEq(selectedPlain(), next)) return true;
        dispatchPaste(document.activeElement, next);
        return textEq(selectedPlain(), next);
      }

      function applyHumanized(original, next, range, _allowFind) {
        if (!original || !next || !isPlausibleRewrite(original, next)) return false;
        if (document.activeElement && isTextField(document.activeElement)) {
          const el = document.activeElement;
          if (replaceInput(el, el.selectionStart, el.selectionEnd, original, next)) return true;
        }
        restoreSelection(original, range || null);
        if (!selectionIsOriginal(original)) return false;
        return nativeReplaceSelected(original, next);
      }

      function stopKeepSelection() {
        if (keepSelTimer) window.clearInterval(keepSelTimer);
        keepSelTimer = 0;
      }

      function startKeepSelection(target) {
        stopKeepSelection();
        const original = target && (target.raw || target.text);
        if (!original) return;
        keepSelTimer = window.setInterval(() => {
          if (textEq(selectedPlain(), original)) return;
          if (target.range) restoreSelection(original, target.range);
        }, 1200);
      }

      async function clipboardHas(text) {
        try {
          if (!navigator.clipboard || !navigator.clipboard.readText) return false;
          return textEq(await navigator.clipboard.readText(), text);
        } catch (_err) {
          return false;
        }
      }

      async function replaceSelection(target, next) {
        if (!target || !next) return false;
        const original = target.raw || target.text;
        if (!isPlausibleRewrite(original, next)) return false;
        if (target.kind === "input" && target.el) {
          if (replaceInput(target.el, target.start, target.end, original, next)) return true;
        }
        if (applyHumanized(original, next, target.range, true)) return true;
        try {
          const res = await new Promise((resolve) => {
            chrome.runtime.sendMessage(
              { type: "HUMANIZE_APPLY", payload: { original, next } },
              (msg) => {
                if (chrome.runtime.lastError) {
                  resolve({ ok: false });
                  return;
                }
                resolve(msg || { ok: false });
              }
            );
          });
          if (res && res.ok) return true;
        } catch (_err) {
          /* other frames may not be reachable */
        }
        const wrote = await writeClipboard(next);
        restoreSelection(original, target.range);
        if (selectionIsOriginal(original)) {
          dispatchPaste(document.activeElement, next);
          if (textEq(selectedPlain(), next)) return true;
          if (wrote && (await clipboardHas(next))) {
            execPaste(document);
            if (textEq(selectedPlain(), next)) return true;
          }
        }
        return false;
      }

      function storageGet(keys) {
        return new Promise((resolve) => {
          try {
            chrome.storage.local.get(keys, (stored) => {
              if (chrome.runtime.lastError) {
                resolve({});
                return;
              }
              resolve(stored || {});
            });
          } catch (_err) {
            resolve({});
          }
        });
      }

      async function quickHumanize(fromKey) {
        if (busy) return;
        const target = await captureHighlight();
        if (!target || !target.text) {
          if (fromKey) showLoaderNote(null, "Highlight text first", true);
          return;
        }
        const stored = await storageGet(["docmaxxing_key", "veil_token"]);
        const key = String((stored && (stored.docmaxxing_key || stored.veil_token)) || "").trim();
        if (!key) {
          showLoaderNote(target, "Sign in from the Veil icon first.", true);
          return;
        }
        busy = true;
        showLoader(target);
        startKeepSelection(target);
        chrome.runtime.sendMessage(
          { type: "HUMANIZE_TEXT", payload: { text: target.text, key } },
          async (res) => {
            const stop = () => {
              stopKeepSelection();
              busy = false;
            };
            if (chrome.runtime.lastError) {
              stop();
              showLoaderNote(target, chrome.runtime.lastError.message || "Humanize failed", true);
              return;
            }
            if (res && res.error === "Already humanizing") {
              stop();
              return;
            }
            if (!res || !res.ok) {
              stop();
              showLoaderNote(target, (res && res.error) || "Humanize failed", true);
              return;
            }
            const humanized = String(res.humanized_text || "").trim();
            if (!humanized || !isPlausibleRewrite(target.text, humanized)) {
              stop();
              showLoaderNote(target, "Humanizer returned unusable text. Try again.", true);
              return;
            }
            let replaced = false;
            try {
              replaced = await replaceSelection(target, humanized);
            } catch (_err) {
              replaced = false;
            }
            stop();
            hideLoader();
            if (!replaced) await writeClipboard(humanized);
          }
        );
      }

      window.__veilApplyHumanize = function (original, next) {
        try {
          return applyHumanized(original, next, null, false);
        } catch (_err) {
          return false;
        }
      };
      window.__veilQuickHumanize = function () {
        quickHumanize(false);
      };

      chrome.runtime.onMessage.addListener((message) => {
        if (message && message.action === "quick_humanize") quickHumanize(false);
        if (message && message.action === "apply_humanize") {
          const original = String((message.original || "")).trim();
          const next = String((message.next || "")).trim();
          return applyHumanized(original, next, null, false);
        }
      });

      window.addEventListener(
        "keydown",
        (e) => {
          if (!isHumanizeHotkey(e)) return;
          e.preventDefault();
          e.stopImmediatePropagation();
          quickHumanize(true);
        },
        true
      );
    }

    if (!IS_TOP) {
      installHumanize();
      return;
    }

    installHumanizeHud();
    document.querySelectorAll("[data-veil-root]").forEach((el) => el.remove());
    const host = document.createElement("div");
    host.setAttribute("data-veil-root", "1");
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
      margin: 0 0 6px;
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
    select.model {
      display: block;
      width: 100%;
      box-sizing: border-box;
      height: 26px;
      margin: 0 0 6px;
      padding: 0 6px;
      border: 1px solid #333;
      border-radius: 6px;
      background: #1c1c1c;
      color: #ccc;
      font: inherit;
      font-size: 11px;
      cursor: pointer;
      outline: none;
    }
    .msg.ai.thinking { color: #999; font-style: italic; }
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

    const modelSelect = document.createElement("select");
    modelSelect.className = "model";
    modelSelect.setAttribute("aria-label", "Модель");
    modelSelect.title = "Haiku — быстрые тесты. Sonnet — универ и многошаговые задачи.";
    [
      ["fast", "Haiku"],
      ["deep", "Sonnet"],
    ].forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      modelSelect.appendChild(option);
    });
    try {
      chrome.storage.local.get(["veil_model"], (stored) => {
        if (chrome.runtime.lastError) return;
        if (stored && stored.veil_model === "deep") modelSelect.value = "deep";
      });
    } catch (_err) {
      /* storage can be missing while the worker is restarting */
    }
    modelSelect.addEventListener("change", () => {
      chrome.storage.local.set({ veil_model: modelSelect.value });
    });

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
    panel.append(chatHistory, preview, textarea, modelSelect, row);
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

    function appendMsg(role, text, imgs) {
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

    installHumanize();

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

    function compressDataUrl(dataUrl) {
      return new Promise((resolve) => {
        const img = new Image();
        img.onload = () => {
          const maxW = 1280;
          const scale = Math.min(1, maxW / (img.naturalWidth || maxW));
          const canvas = document.createElement("canvas");
          canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
          canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
          const ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
          resolve(canvas.toDataURL("image/jpeg", 0.72));
        };
        img.onerror = () => resolve(dataUrl);
        img.src = dataUrl;
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
          .then(compressDataUrl)
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
      const model = modelSelect.value === "deep" ? "deep" : "fast";
      if ((!text && !images.length) || pending) return;

      const payloadImages = images.slice();
      appendMsg("user", text, payloadImages);
      textarea.value = "";
      images.length = 0;
      renderThumbs();
      pending = true;
      sendBtn.disabled = true;
      const thinking = appendMsg("ai", "Думаю…");
      thinking.classList.add("thinking");

      chrome.runtime.sendMessage(
        { type: "ASK_AI", payload: { text, images: payloadImages, extended, model } },
        (res) => {
          pending = false;
          sendBtn.disabled = false;
          thinking.remove();
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
        const key = String(e.key || "").toLowerCase();
        const isQ = e.code === "KeyQ" || key === "q";
        const isS = e.code === "KeyS" || key === "s";
        const noMetaShift = !e.metaKey && !e.shiftKey;
        const altOnly = e.altKey && !e.ctrlKey && noMetaShift;
        const ctrlOnly = e.ctrlKey && !e.altKey && noMetaShift;
        if (!altOnly && !ctrlOnly) return;
        if (isQ) {
          e.preventDefault();
          e.stopImmediatePropagation();
          toggleAssistantPanelImpl();
        } else if (isS) {
          e.preventDefault();
          e.stopImmediatePropagation();
          takeScreenshot();
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
