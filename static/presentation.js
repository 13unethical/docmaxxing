(function () {
  "use strict";

  var page = document.querySelector(".pres-page");
  if (!page) return;

  var themes = [];
  try {
    themes = JSON.parse(document.getElementById("pres_themes_data").textContent || "[]");
  } catch (_e) {
    themes = [];
  }
  var themeById = {};
  themes.forEach(function (t) {
    themeById[t.id] = t;
  });

  var CATEGORY_LABELS = {
    academic: "Academic",
    work: "Work",
    finance: "Finance",
    promotion: "Promotion",
    consulting: "Consulting",
  };
  var THEME_STORAGE_KEY = "dm_pres_theme";
  var SAMPLES_URL = page.dataset.samples || "/static/presentation/samples/";
  var CONTENT_LAYOUTS = { bullets: 1, image: 1, cards: 1, timeline: 1, two_column: 1 };

  var topicEl = document.getElementById("pres_topic");
  var toneEl = document.getElementById("pres_tone");
  var imagesEl = document.getElementById("pres_images");
  var generateBtn = document.getElementById("pres_generate_btn");
  var downloadBtn = document.getElementById("pres_download_btn");
  var newBtn = document.getElementById("pres_new_btn");
  var statusEl = document.getElementById("pres_status");
  var resultEl = document.getElementById("pres_result");
  var loadingEl = document.getElementById("pres_loading");
  var slidesEl = document.getElementById("pres_slides");
  var chipThumb = document.getElementById("pres_theme_chip_thumb");
  var chipName = document.getElementById("pres_theme_chip_name");
  var chipBtn = document.getElementById("pres_theme_chip");
  var galleryEl = document.getElementById("pres_gallery");
  var gridEl = document.getElementById("pres_theme_grid");
  var tabs = Array.prototype.slice.call(document.querySelectorAll(".pres-tab"));
  var composerEl = document.getElementById("pres_composer");
  var filesEl = document.getElementById("pres_files");
  var fileInput = document.getElementById("pres_file_input");
  var attachBtn = document.getElementById("pres_attach_btn");
  var costEl = document.getElementById("pres_cost");

  var BASE_COST = Number(page.dataset.cost) || 0;
  var RESEARCH_COST = Number(page.dataset.researchCost) || 0;
  var RESEARCH_MAX_CHARS = Number(page.dataset.researchMaxChars) || 1500;
  var MAX_FILES = Number(page.dataset.maxFiles) || 3;

  var deck = null;
  var busy = false;
  var files = [];
  var fileSeq = 0;
  var selectedTheme = pickInitialTheme();

  function pickInitialTheme() {
    var saved = null;
    try {
      saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    } catch (_e) {
      saved = null;
    }
    if (saved && themeById[saved]) return saved;
    var fallback = page.dataset.defaultTheme;
    return themeById[fallback] ? fallback : themes.length ? themes[0].id : "";
  }

  /* ---------- helpers ---------- */

  function setStatus(text, kind) {
    statusEl.textContent = text || "";
    statusEl.className = "req-status pres-status" + (kind ? " " + kind : "");
  }

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  function applyThemeVars(node, theme) {
    if (!node || !theme) return;
    var vars = {
      "--t-bg": theme.bg,
      "--t-ink": theme.ink,
      "--t-muted": theme.muted,
      "--t-accent": theme.accent,
      "--t-col": theme.col_heading,
      "--t-pale": theme.pale,
      "--t-cover-bg": theme.cover_bg,
      "--t-cover-ink": theme.cover_ink,
      "--t-cover-muted": theme.cover_muted,
      "--t-cover-accent": theme.cover_accent,
    };
    Object.keys(vars).forEach(function (key) {
      node.style.setProperty(key, "#" + vars[key]);
    });
    node.style.setProperty("--t-hfont", theme.web_heading_font);
    node.style.setProperty("--t-bfont", theme.web_body_font);
    node.style.setProperty("--t-case", theme.heading_upper ? "uppercase" : "none");
    node.style.setProperty("--t-hweight", theme.heading_bold === false ? "400" : "700");
    node.classList.toggle("is-plain-cover", theme.cover_bg.toUpperCase() === theme.bg.toUpperCase());
    node.dataset.design = theme.design || "classic";
  }

  /* Mirrors accent_split() in services/presentation_themes.py. */
  function accentSplit(text, mode) {
    var words = String(text || "").split(/\s+/).filter(Boolean);
    if ((mode !== "lead" && mode !== "tail") || words.length < 2) return [[String(text || ""), false]];
    var k = Math.min(3, Math.max(1, Math.floor(words.length / 3)));
    if (mode === "lead") return [[words.slice(0, k).join(" ") + " ", true], [words.slice(k).join(" "), false]];
    return [[words.slice(0, -k).join(" ") + " ", false], [words.slice(-k).join(" "), true]];
  }

  function fillTitle(node, text, theme) {
    var len = String(text || "").length;
    node.style.setProperty("--ts", len <= 30 ? "1" : len <= 45 ? "0.88" : len <= 60 ? "0.78" : "0.68");
    node.textContent = "";
    accentSplit(text, theme && theme.title_accent).forEach(function (part) {
      node.appendChild(part[1] ? el("span", "pres-hl", part[0]) : document.createTextNode(part[0]));
    });
    return node;
  }

  function deckTheme() {
    return themeById[(deck && deck.theme) || selectedTheme] || themeById[selectedTheme];
  }

  /* ---------- theme selection + gallery ---------- */

  function selectTheme(id, opts) {
    if (!themeById[id]) return;
    selectedTheme = id;
    try {
      window.localStorage.setItem(THEME_STORAGE_KEY, id);
    } catch (_e) {
      /* storage unavailable */
    }
    var theme = themeById[id];
    applyThemeVars(chipThumb, theme);
    chipName.textContent = theme.name;
    gridEl.querySelectorAll(".pres-theme-card").forEach(function (card) {
      var on = card.dataset.theme === id;
      card.classList.toggle("is-selected", on);
      card.setAttribute("aria-pressed", on ? "true" : "false");
    });
    if (deck) {
      deck.theme = id;
      renderDeck();
    }
    if (opts && opts.reveal) {
      var target = deck ? resultEl : page;
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      if (!deck) topicEl.focus({ preventScroll: true });
      if (deck) setStatus("Style changed to " + theme.name + ". Download to get the restyled .pptx.", "success");
    }
  }

  function themeCard(theme) {
    var card = el("button", "pres-theme-card");
    card.type = "button";
    card.dataset.theme = theme.id;
    card.dataset.category = theme.category;
    card.setAttribute("aria-label", "Use style " + theme.name);
    applyThemeVars(card, theme);

    var slide = el("div", "pres-slide pres-slide--cover");
    slide.appendChild(el("div", "pres-deco"));
    slide.appendChild(fillTitle(el("div", "pres-slide-title"), theme.sample_title, theme));
    slide.appendChild(el("div", "pres-slide-sub", (CATEGORY_LABELS[theme.category] || "Slides") + " · 16:9"));
    slide.appendChild(el("div", "pres-slide-byline", "DocMaxxing Slides"));
    if (theme.sample_image) {
      var img = el("img", "pres-slide-photo");
      img.src = SAMPLES_URL + theme.sample_image + ".jpg";
      img.alt = "";
      img.loading = "lazy";
      slide.classList.add("has-photo");
      slide.appendChild(img);
    }
    var use = el("span", "pres-use-btn", "Use this style");
    slide.appendChild(use);
    card.appendChild(slide);

    var name = el("span", "pres-theme-name");
    name.appendChild(el("span", "", theme.name));
    var check = el("span", "pres-theme-check");
    check.innerHTML =
      '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>';
    name.appendChild(check);
    card.appendChild(name);

    card.addEventListener("click", function () {
      selectTheme(theme.id, { reveal: true });
    });
    return card;
  }

  function renderGallery() {
    gridEl.innerHTML = "";
    themes.forEach(function (theme) {
      gridEl.appendChild(themeCard(theme));
    });
  }

  function filterGallery(category) {
    tabs.forEach(function (tab) {
      var on = tab.dataset.category === category;
      tab.classList.toggle("is-active", on);
      tab.setAttribute("aria-selected", on ? "true" : "false");
    });
    gridEl.querySelectorAll(".pres-theme-card").forEach(function (card) {
      card.classList.toggle("hidden", category !== "all" && card.dataset.category !== category);
    });
  }

  tabs.forEach(function (tab) {
    tab.addEventListener("click", function () {
      filterGallery(tab.dataset.category);
    });
  });

  chipBtn.addEventListener("click", function () {
    galleryEl.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  /* ---------- deck editing ---------- */

  function getPath(path) {
    return path.split(".").reduce(function (obj, key) {
      return obj == null ? undefined : obj[key];
    }, deck);
  }

  function setPath(path, value) {
    var keys = path.split(".");
    var last = keys.pop();
    var target = keys.reduce(function (obj, key) {
      return obj[key];
    }, deck);
    target[last] = value;
  }

  function editable(tag, className, path) {
    var node = el(tag, className, getPath(path) || "");
    node.contentEditable = "true";
    node.spellcheck = true;
    node.dataset.path = path;
    return node;
  }

  function bulletList(path, items) {
    var ul = el("ul");
    (items || []).forEach(function (_item, i) {
      ul.appendChild(editable("li", "", path + "." + i));
    });
    return ul;
  }

  function pad2(n) {
    return String(n).padStart(2, "0");
  }

  function slideFrame(kind, label, number, total) {
    var wrap = el("div", "pres-slide-wrap");
    var meta = el("div", "pres-slide-meta");
    meta.appendChild(el("span", "", label));
    meta.appendChild(el("span", "", number + " / " + total));
    wrap.appendChild(meta);
    var slide = el("div", "pres-slide pres-slide--" + kind);
    slide.appendChild(el("div", "pres-deco"));
    if (CONTENT_LAYOUTS[kind]) {
      slide.classList.add("is-content");
      slide.appendChild(el("div", "pres-run", deck.title || ""));
      var num = el("div", "pres-num");
      num.appendChild(el("b", "", pad2(number)));
      num.appendChild(el("span", "pres-num-total", " / " + pad2(total)));
      slide.appendChild(num);
    }
    wrap.appendChild(slide);
    return { wrap: wrap, slide: slide };
  }

  function editableTitle(path) {
    return fillTitle(editable("div", "pres-slide-title", path), getPath(path), deckTheme());
  }

  var LAYOUT_LABELS = {
    bullets: "Content",
    image: "Photo",
    cards: "Key points",
    timeline: "Timeline",
    two_column: "Comparison",
    section: "Section",
    closing: "Conclusion",
  };

  function addPhoto(frame, image) {
    if (!image || !image.url) return;
    var img = el("img", "pres-slide-photo");
    img.src = image.url;
    img.alt = "";
    img.loading = "lazy";
    if (image.credit) img.title = image.credit;
    frame.slide.classList.add("has-photo");
    frame.slide.appendChild(img);
    if (image.credit) frame.wrap.appendChild(el("div", "pres-credit", image.credit));
  }

  function itemBlocks(container, base, items, prefix) {
    items.forEach(function (_item, j) {
      var path = base + ".items." + j;
      var block = el("div", prefix);
      block.appendChild(el("div", prefix + "-num", prefix === "pres-card" ? String(j + 1).padStart(2, "0") : String(j + 1)));
      var body = el("div", prefix + "-body");
      body.appendChild(editable("div", prefix + "-heading", path + ".heading"));
      body.appendChild(editable("div", prefix + "-text", path + ".text"));
      block.appendChild(body);
      container.appendChild(block);
    });
  }

  function renderSlide(data, index, total) {
    var base = "slides." + index;
    var layout = data.layout === "image" && !(data.image && data.image.url) ? "bullets" : data.layout;
    var design = deckTheme().design || "classic";
    var kind = layout === "section" && design !== "classic" ? "cover" : layout;
    var frame = slideFrame(kind, LAYOUT_LABELS[layout] || "Slide", index + 2, total);
    var slide = frame.slide;
    slide.appendChild(editableTitle(base + ".title"));

    if (layout === "cards" || layout === "timeline") {
      var items = data.items || [];
      var box = el("div", layout === "cards" ? "pres-cards" : "pres-timeline");
      var cols = layout === "cards" && items.length === 4 ? 2 : items.length;
      box.style.setProperty("--cols", String(cols));
      if (layout === "cards" && cols < items.length) box.classList.add("is-grid");
      itemBlocks(box, base, items, layout === "cards" ? "pres-card" : "pres-step");
      slide.appendChild(box);
    } else if (layout === "two_column") {
      var cols = el("div", "pres-cols");
      ["left", "right"].forEach(function (side) {
        var col = el("div", "pres-col");
        col.appendChild(editable("div", "pres-col-heading", base + "." + side + ".heading"));
        col.appendChild(bulletList(base + "." + side + ".bullets", data[side].bullets));
        cols.appendChild(col);
      });
      slide.appendChild(cols);
    } else if (layout === "section") {
      if (data.subtitle) slide.appendChild(editable("div", "pres-slide-sub", base + ".subtitle"));
    } else if (data.bullets && data.bullets.length) {
      slide.appendChild(bulletList(base + ".bullets", data.bullets));
    } else if (data.subtitle) {
      slide.appendChild(editable("div", "pres-slide-sub", base + ".subtitle"));
    }
    if (layout === "image" || layout === "section") addPhoto(frame, data.image);

    if (data.notes) {
      var notes = el("details", "pres-notes");
      notes.appendChild(el("summary", "", "Speaker notes"));
      notes.appendChild(editable("p", "", base + ".notes"));
      frame.wrap.appendChild(notes);
    }
    return frame.wrap;
  }

  function renderDeck() {
    slidesEl.innerHTML = "";
    if (!deck) return;
    applyThemeVars(slidesEl, deckTheme());
    var total = deck.slides.length + 1;
    var cover = slideFrame("cover", "Title", 1, total);
    cover.slide.appendChild(editableTitle("title"));
    if (deck.subtitle) cover.slide.appendChild(editable("div", "pres-slide-sub", "subtitle"));
    if (deck.presenter) cover.slide.appendChild(editable("div", "pres-slide-byline", "presenter"));
    addPhoto(cover, deck.cover_image);
    slidesEl.appendChild(cover.wrap);
    deck.slides.forEach(function (data, i) {
      slidesEl.appendChild(renderSlide(data, i, total));
    });
  }

  slidesEl.addEventListener("input", function (e) {
    var target = e.target.closest("[data-path]");
    if (!target || !deck) return;
    setPath(target.dataset.path, target.textContent.replace(/\s+/g, " ").trim());
  });

  slidesEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && e.target.closest("[data-path]")) {
      e.preventDefault();
      e.target.blur();
    }
  });

  /* ---------- composer ---------- */

  function autoGrow() {
    topicEl.style.height = "auto";
    topicEl.style.height = Math.min(topicEl.scrollHeight, 220) + "px";
  }

  topicEl.addEventListener("input", function () {
    autoGrow();
    updateCost();
  });
  topicEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      e.preventDefault();
      generate();
    }
  });

  /* ---------- research + attachments ---------- */

  /* Mirrors needs_research() in services/presentation_generator.py. */
  function researchOn() {
    return !files.length && topicEl.value.trim().length <= RESEARCH_MAX_CHARS;
  }

  function updateCost() {
    var total = BASE_COST + (researchOn() ? RESEARCH_COST : 0);
    costEl.textContent = total + " credits";
    costEl.title = researchOn()
      ? "Includes " + RESEARCH_COST + " credits for web research. Paste or attach your own material to skip it."
      : "";
  }

  function formatChars(n) {
    var words = Math.round(n / 6);
    return words >= 1000 ? (words / 1000).toFixed(1).replace(/\.0$/, "") + "k words" : words + " words";
  }

  function renderFiles() {
    updateCost();
    filesEl.innerHTML = "";
    filesEl.classList.toggle("hidden", files.length === 0);
    files.forEach(function (file) {
      var item = el("li", "pres-file" + (file.loading ? " is-loading" : ""));
      var name = el("span", "pres-file-name", file.name);
      name.title = file.name;
      item.appendChild(name);
      var meta = file.loading ? "reading…" : formatChars(file.chars) + (file.truncated ? " (trimmed)" : "");
      item.appendChild(el("span", "pres-file-meta", meta));
      var remove = el("button", "pres-file-remove", "×");
      remove.type = "button";
      remove.title = "Remove " + file.name;
      remove.setAttribute("aria-label", "Remove " + file.name);
      remove.addEventListener("click", function () {
        files = files.filter(function (f) {
          return f.id !== file.id;
        });
        renderFiles();
      });
      item.appendChild(remove);
      filesEl.appendChild(item);
    });
  }

  async function uploadFile(file) {
    var entry = { id: ++fileSeq, name: file.name, loading: true, text: "", chars: 0 };
    files.push(entry);
    renderFiles();
    var fd = new FormData();
    fd.append("file", file);
    try {
      var res = await fetch("/api/presentation/extract", { method: "POST", body: fd });
      var data = {};
      try {
        data = await res.json();
      } catch (_e) {
        data = {};
      }
      if (!res.ok || !data.success) throw new Error(errorMessage(res, data));
      entry.text = data.text || "";
      entry.chars = data.chars || entry.text.length;
      entry.truncated = !!data.truncated;
      entry.loading = false;
      setStatus("");
    } catch (err) {
      files = files.filter(function (f) {
        return f.id !== entry.id;
      });
      setStatus(file.name + ": " + (err.message || "could not read the file."), "error");
    }
    renderFiles();
  }

  function addFiles(list) {
    var incoming = Array.prototype.slice.call(list || []);
    if (!incoming.length) return;
    var room = MAX_FILES - files.length;
    if (room <= 0) {
      setStatus("You can attach up to " + MAX_FILES + " files.", "error");
      return;
    }
    if (incoming.length > room) setStatus("Only the first " + room + " file(s) were attached.", "error");
    incoming.slice(0, room).forEach(uploadFile);
  }

  attachBtn.addEventListener("click", function () {
    fileInput.click();
  });

  fileInput.addEventListener("change", function () {
    addFiles(fileInput.files);
    fileInput.value = "";
  });

  ["dragenter", "dragover"].forEach(function (type) {
    composerEl.addEventListener(type, function (e) {
      if (!e.dataTransfer || Array.prototype.indexOf.call(e.dataTransfer.types || [], "Files") < 0) return;
      e.preventDefault();
      composerEl.classList.add("is-dragover");
    });
  });
  ["dragleave", "drop"].forEach(function (type) {
    composerEl.addEventListener(type, function () {
      composerEl.classList.remove("is-dragover");
    });
  });
  composerEl.addEventListener("drop", function (e) {
    if (!e.dataTransfer || !e.dataTransfer.files.length) return;
    e.preventDefault();
    addFiles(e.dataTransfer.files);
  });

  function setLoading(on) {
    busy = on;
    generateBtn.disabled = on;
    generateBtn.classList.toggle("is-busy", on);
    loadingEl.classList.toggle("hidden", !on);
    if (on) {
      resultEl.classList.remove("hidden");
      slidesEl.innerHTML = "";
      downloadBtn.disabled = true;
    } else if (!deck) {
      resultEl.classList.add("hidden");
    }
  }

  function updateBalance(balance) {
    if (typeof balance !== "number") return;
    document.querySelectorAll("[data-coin-balance]").forEach(function (node) {
      node.textContent = balance.toLocaleString("en-US");
    });
  }

  function errorMessage(res, data) {
    var code = data && data.error;
    if (res.status === 401 || code === "AUTH_REQUIRED") return "Please sign in to generate presentations.";
    if (code === "EMAIL_NOT_VERIFIED") return "Please verify your email first.";
    if (res.status === 402 || code === "INSUFFICIENT_COINS") {
      return (data && data.message) || "Not enough credits. Top up to continue.";
    }
    return (data && (data.message || data.error)) || "Something went wrong. Please try again.";
  }

  async function generate() {
    if (busy) return;
    var topic = topicEl.value.trim();
    var pending = files.some(function (f) {
      return f.loading;
    });
    if (pending) {
      setStatus("Still reading your file — one moment.", "error");
      return;
    }
    var attached = files.map(function (f) {
      return { name: f.name, text: f.text };
    });
    if (!topic && !attached.length) {
      setStatus("Describe what the presentation is about, or attach your brief.", "error");
      topicEl.focus();
      return;
    }
    var research = researchOn();
    deck = null;
    setLoading(true);
    setStatus(
      research
        ? "Researching the web, then writing your slides… this usually takes 1–3 minutes."
        : imagesEl.value === "on"
          ? "Writing your slides and picking photos… this usually takes 30–90 seconds."
          : "Writing your slides… this usually takes 20–60 seconds."
    );
    resultEl.scrollIntoView({ behavior: "smooth", block: "start" });
    try {
      var res = await fetch("/api/presentation/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          topic: topic,
          tone: toneEl.value,
          theme: selectedTheme,
          images: imagesEl.value === "on",
          files: attached,
        }),
      });
      var data = {};
      try {
        data = await res.json();
      } catch (_e) {
        data = {};
      }
      if (!res.ok || !data.success) {
        setStatus(errorMessage(res, data), "error");
        return;
      }
      deck = data.deck;
      updateBalance(data.balance);
      var done = "Done — " + (deck.slides.length + 1) + " slides. Edit any text, then download the .pptx.";
      if (data.research === "failed") {
        done += " Web research was unavailable, so its " + RESEARCH_COST + " credits were refunded.";
      }
      setStatus(done, "success");
      renderDeck();
      downloadBtn.disabled = false;
    } catch (_err) {
      setStatus("Network error. Check your connection and try again.", "error");
    } finally {
      setLoading(false);
    }
  }

  async function download() {
    if (!deck) return;
    downloadBtn.disabled = true;
    var label = downloadBtn.querySelector("span");
    var original = label.textContent;
    label.textContent = "Preparing…";
    try {
      var res = await fetch("/api/presentation/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ deck: deck }),
      });
      if (!res.ok) {
        var data = {};
        try {
          data = await res.json();
        } catch (_e) {
          data = {};
        }
        setStatus(errorMessage(res, data), "error");
        return;
      }
      var blob = await res.blob();
      var name = "presentation.pptx";
      var disposition = res.headers.get("Content-Disposition") || "";
      var match = disposition.match(/filename\*=UTF-8''([^;]+)/i) || disposition.match(/filename="?([^";]+)"?/i);
      if (match) name = decodeURIComponent(match[1]);
      var url = URL.createObjectURL(blob);
      var a = document.createElement("a");
      a.href = url;
      a.download = name;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () {
        URL.revokeObjectURL(url);
      }, 2000);
    } catch (_err) {
      setStatus("Download failed. Please try again.", "error");
    } finally {
      label.textContent = original;
      downloadBtn.disabled = false;
    }
  }

  function newDeck() {
    deck = null;
    slidesEl.innerHTML = "";
    resultEl.classList.add("hidden");
    downloadBtn.disabled = true;
    topicEl.value = "";
    files = [];
    renderFiles();
    autoGrow();
    setStatus("");
    page.scrollIntoView({ behavior: "smooth", block: "start" });
    topicEl.focus({ preventScroll: true });
  }

  generateBtn.addEventListener("click", generate);
  downloadBtn.addEventListener("click", download);
  newBtn.addEventListener("click", newDeck);

  renderGallery();
  selectTheme(selectedTheme);
  updateCost();
})();
