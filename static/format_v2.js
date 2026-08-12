/**
 * Formatter V2 UI — independent of home.js / V1.
 * Only fields the user (or brief parse) actually changed are sent as overrides.
 */
(function () {
  "use strict";

  var MARGIN_PRESETS = {
    normal: { top_in: 1, bottom_in: 1, left_in: 1, right_in: 1 },
    narrow: { top_in: 0.5, bottom_in: 0.5, left_in: 0.5, right_in: 0.5 },
    wide: { top_in: 1.5, bottom_in: 1.5, left_in: 1.5, right_in: 1.5 },
  };

  var SPACING_LABELS = {
    "1": "одинарный интервал",
    "1.0": "одинарный интервал",
    "1.15": "интервал 1,15",
    "1.5": "полуторный интервал",
    "2": "двойной интервал",
    "2.0": "двойной интервал",
  };

  var STYLE_HINTS = {
    harvard: "Cite Them Right",
    apa7: "",
    mla9: "",
    chicago17: "",
    ieee: "",
  };

  var STYLE_CHIP_LABELS = {
    harvard: "Harvard",
    apa7: "APA 7",
    mla9: "MLA 9",
    chicago17: "Chicago 17",
    ieee: "IEEE",
  };

  var MARGIN_LABELS = {
    normal: 'поля 1"',
    narrow: 'поля 0,5"',
    wide: 'поля 1,5"',
    custom: "поля из профиля",
  };

  var state = {
    style: "harvard",
    displayName: "Harvard (Cite Them Right)",
    /** @type {Record<string, true>} */
    touched: {},
    /** @type {Record<string, string>} */
    evidence: {},
    defaults: null,
    customMargins: null,
    applying: false,
    hasFormatted: false,
    activeOverrides: {},
    overrideUndoStack: [],
    chatHistory: [],
    latestDownloadUrl: "",
    latestDownloadName: "formatted_document.docx",
  };

  var CHAT_FETCH_TIMEOUT_MS = 30000;
  var CHAT_PENDING_DEFAULT = "Применяю правку…";

  function fetchWithTimeout(url, options, timeoutMs) {
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, timeoutMs);
    var opts = Object.assign({}, options || {}, { signal: controller.signal });
    return fetch(url, opts).finally(function () {
      clearTimeout(timer);
    });
  }

  function $(id) {
    return document.getElementById(id);
  }

  function syncStyleChipSelection(style) {
    document.querySelectorAll("[data-v2-style]").forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-v2-style") === style);
    });
  }

  function markTouched(field) {
    if (state.applying || !field) return;
    state.touched[field] = true;
    updatePreview();
    updateProfileSummary();
  }

  function clearEvidence() {
    state.evidence = {};
    document.querySelectorAll("[data-evidence-for]").forEach(function (el) {
      el.hidden = true;
      el.removeAttribute("title");
    });
  }

  function setEvidence(map) {
    clearEvidence();
    state.evidence = map || {};
    Object.keys(state.evidence).forEach(function (key) {
      var quote = state.evidence[key];
      if (!quote) return;
      document.querySelectorAll('[data-evidence-for="' + key + '"]').forEach(function (el) {
        el.hidden = false;
        el.title = quote;
      });
    });
  }

  function setStatus(el, message, kind) {
    if (!el) return;
    el.textContent = message || "";
    el.className = "req-chat-status req-status" + (kind ? " " + kind : "");
  }

  function setFormatStatus(message, kind) {
    var el = $("v2_format_status");
    if (!el) return;
    el.textContent = message || "";
    el.className = "format-status status" + (kind ? " " + kind : "");
  }

  function normalizeLineSpacingOption(value) {
    if (value == null || value === "") return "";
    var n = Number(value);
    if (!isFinite(n)) return String(value);
    if (Math.abs(n - 1) < 0.001) return "1.0";
    if (Math.abs(n - 1.15) < 0.001) return "1.15";
    if (Math.abs(n - 1.5) < 0.001) return "1.5";
    if (Math.abs(n - 2) < 0.001) return "2.0";
    return String(n);
  }

  function resolvedLineSpacing() {
    var el = $("v2_line_spacing");
    if (el && el.value) return Number(el.value);
    if (state.defaults && state.defaults.line_spacing != null) {
      return Number(state.defaults.line_spacing);
    }
    return 1.5;
  }

  function spacingLabel(value) {
    var key = normalizeLineSpacingOption(value);
    return SPACING_LABELS[key] || ("интервал " + key);
  }

  function marginLabel(preset) {
    return MARGIN_LABELS[preset] || MARGIN_LABELS.normal;
  }

  function currentFormValues() {
    return {
      font_family: $("v2_font_family").value,
      font_size_pt: Number($("v2_font_size").value),
      line_spacing: resolvedLineSpacing(),
      alignment: $("v2_alignment").value,
      first_line_indent: $("v2_first_line_indent").checked,
      margin_preset: $("v2_margin_preset").value,
      page_size: $("v2_page_size").value,
      page_number_position: $("v2_page_number_position").value,
      cover_enabled: $("v2_cover_enabled").checked,
    };
  }

  function updateStyleHint() {
    var hint = $("v2_style_hint");
    if (!hint) return;
    hint.textContent = STYLE_HINTS[state.style] || "";
  }

  function updateProfileSummary() {
    var el = $("v2_profile_summary");
    if (!el) return;
    var v = currentFormValues();
    var preset = v.margin_preset || "normal";
    el.textContent =
      (STYLE_CHIP_LABELS[state.style] || state.displayName || state.style) +
      " · " +
      v.font_family +
      " " +
      v.font_size_pt +
      ", " +
      spacingLabel(v.line_spacing) +
      ", " +
      marginLabel(preset);
  }

  function updatePreview() {
    var page = $("v2_page_preview");
    var inner = $("v2_page_preview_inner");
    var cover = $("v2_preview_cover");
    var pagenum = $("v2_preview_pagenum");
    var summary = $("v2_preview_summary");
    if (!page || !inner) return;

    var v = currentFormValues();
    var preset = v.margin_preset || "normal";
    var margins = preset === "custom" && state.customMargins
      ? state.customMargins
      : MARGIN_PRESETS[preset] || MARGIN_PRESETS.normal;

    var marginPct = {
      top: Math.min(18, margins.top_in * 8),
      right: Math.min(16, margins.right_in * 8),
      bottom: Math.min(18, margins.bottom_in * 8),
      left: Math.min(16, margins.left_in * 8),
    };

    inner.style.top = marginPct.top + "%";
    inner.style.right = marginPct.right + "%";
    inner.style.bottom = marginPct.bottom + "%";
    inner.style.left = marginPct.left + "%";

    var lineGap = Math.max(3, Math.round(v.line_spacing * 4));
    inner.style.setProperty("--v2-line-gap", lineGap + "px");

    if (cover) {
      cover.hidden = !v.cover_enabled;
    }

    var existingLines = inner.querySelectorAll(".v2-page-preview__line");
    existingLines.forEach(function (line) {
      line.remove();
    });

    var widths = [100, 96, 100, 88, 100, 72];
    if (v.alignment === "center") {
      widths = widths.map(function () {
        return 70;
      });
    } else if (v.alignment === "right") {
      widths = [85, 80, 88, 75, 82, 60];
    } else if (v.alignment === "justify") {
      widths = [100, 100, 100, 100, 100, 100];
    }

    var heading = document.createElement("div");
    heading.className = "v2-page-preview__line v2-page-preview__line--heading";
    if (v.alignment === "center") {
      heading.style.marginLeft = "auto";
      heading.style.marginRight = "auto";
    } else if (v.alignment === "right") {
      heading.style.marginLeft = "auto";
    }
    inner.appendChild(heading);

    widths.forEach(function (width, idx) {
      var line = document.createElement("div");
      line.className = "v2-page-preview__line";
      if (v.first_line_indent && idx > 0) {
        line.classList.add("v2-page-preview__line--indent");
      }
      line.style.width = width + "%";
      if (v.alignment === "center") {
        line.style.marginLeft = "auto";
        line.style.marginRight = "auto";
      } else if (v.alignment === "right") {
        line.style.marginLeft = "auto";
      }
      inner.appendChild(line);
    });

    if (pagenum) {
      var pos = v.page_number_position || "none";
      pagenum.hidden = pos === "none";
      pagenum.textContent = "1";
      pagenum.style.top = "";
      pagenum.style.bottom = "";
      pagenum.style.left = "";
      pagenum.style.right = "";
      pagenum.style.transform = "";
      if (pos.indexOf("top_") === 0) pagenum.style.top = "4%";
      if (pos.indexOf("bottom_") === 0) pagenum.style.bottom = "4%";
      if (pos.indexOf("_left") !== -1) pagenum.style.left = marginPct.left + "%";
      if (pos.indexOf("_right") !== -1) pagenum.style.right = marginPct.right + "%";
      if (pos.indexOf("_center") !== -1) {
        pagenum.style.left = "50%";
        pagenum.style.transform = "translateX(-50%)";
      }
    }

    if (summary) {
      summary.textContent =
        state.displayName +
        " · " +
        v.font_family +
        " " +
        v.font_size_pt +
        " · " +
        spacingLabel(v.line_spacing);
    }
  }

  function parseAbbrEntries(text) {
    var entries = {};
    String(text || "")
      .split(/\n+/)
      .forEach(function (line) {
        var trimmed = line.trim();
        if (!trimmed) return;
        var parts = trimmed.split(/\s*[—–\-]\s*|\s*:\s*/);
        if (parts.length < 2) return;
        var key = parts[0].trim();
        var meaning = parts.slice(1).join(" — ").trim();
        if (key && meaning) entries[key] = meaning;
      });
    return entries;
  }

  function formatAbbrEntries(entries) {
    if (!entries || typeof entries !== "object") return "";
    return Object.keys(entries)
      .map(function (k) {
        return k + " — " + entries[k];
      })
      .join("\n");
  }

  function applyFormDefaults(form) {
    if (!form) return;
    state.applying = true;
    state.defaults = form;
    state.customMargins = form.margins || null;

    $("v2_font_family").value = form.font_family || "Times New Roman";
    $("v2_font_size").value = String(form.font_size_pt != null ? form.font_size_pt : 12);
    $("v2_line_spacing").value = normalizeLineSpacingOption(
      form.line_spacing != null ? form.line_spacing : 1.5
    );
    $("v2_alignment").value = form.alignment || "left";
    $("v2_first_line_indent").checked = !!form.first_line_indent;
    $("v2_margin_preset").value = form.margin_preset || "normal";
    $("v2_page_size").value = form.page_size || "a4";
    $("v2_page_number_position").value = form.page_number_position || "none";
    $("v2_heading_size_pt").value = "";

    var cite = form.citations || {};
    $("v2_citation_style_override").value = cite.style_override || "";

    var cover = form.cover_page || {};
    $("v2_cover_enabled").checked = !!cover.enabled;
    $("v2_cover_title").value =
      cover.title && cover.title !== "Assignment" ? cover.title : "";
    $("v2_cover_student").value = cover.student_name || "";
    $("v2_cover_lecturer").value = cover.lecturer || "";
    $("v2_cover_course").value = cover.course || "";
    $("v2_cover_date").value = cover.submission_date || "";

    var toc = form.table_of_contents || {};
    $("v2_toc_enabled").checked = !!toc.enabled;
    $("v2_toc_max_depth").value = String(toc.max_depth || 3);
    $("v2_toc_field_based").checked = !!toc.field_based;

    var abbr = form.abbreviations || {};
    $("v2_abbr_enabled").checked = !!abbr.enabled;
    $("v2_abbr_entries").value = formatAbbrEntries(abbr.entries || {});

    var apps = form.appendices || {};
    $("v2_appendices_enabled").checked = !!apps.enabled;
    $("v2_appendices_lettered").checked = apps.lettered !== false;

    var caps = form.captions || {};
    $("v2_captions_enabled").checked = caps.enabled !== false;
    $("v2_table_position").value = caps.table_position || "above";
    $("v2_figure_position").value = caps.figure_position || "below";

    var refs = form.references || {};
    $("v2_refs_enabled").checked = refs.enabled !== false;
    $("v2_refs_heading").value = refs.heading_text || "References";
    $("v2_refs_new_page").checked = refs.on_new_page !== false;
    $("v2_refs_numbered").checked = !!refs.numbered;

    state.applying = false;
    updateStyleHint();
    updateProfileSummary();
    updatePreview();
    syncDependentFields();
  }

  function buildOverrides() {
    var out = {};
    if (state.touched.style) out.style = state.style;

    if (state.touched.font_family) out.font_family = $("v2_font_family").value;
    if (state.touched.font_size_pt) out.font_size_pt = Number($("v2_font_size").value);
    if (state.touched.line_spacing) out.line_spacing = Number($("v2_line_spacing").value);
    if (state.touched.alignment) out.alignment = $("v2_alignment").value;
    if (state.touched.first_line_indent) out.first_line_indent = $("v2_first_line_indent").checked;

    if (state.touched.margins) {
      var preset = $("v2_margin_preset").value;
      if (preset === "custom" && state.customMargins) {
        out.margins = state.customMargins;
      } else if (MARGIN_PRESETS[preset]) {
        out.margins = MARGIN_PRESETS[preset];
      }
    }
    if (state.touched.page_size) out.page_size = $("v2_page_size").value;
    if (state.touched.page_numbering) {
      out.page_numbering = { position: $("v2_page_number_position").value };
    }
    if (state.touched.heading_size_pt) {
      var headingVal = $("v2_heading_size_pt").value;
      if (headingVal) out.heading_size_pt = Number(headingVal);
    }
    if (state.touched.citations) {
      var citeOverride = $("v2_citation_style_override").value;
      if (citeOverride) {
        out.citations = { style_override: citeOverride };
      }
    }

    if (state.touched.cover_page) {
      var enabled = $("v2_cover_enabled").checked;
      var title = ($("v2_cover_title").value || "").trim() || (enabled ? "Assignment" : "");
      out.cover_page = {
        enabled: enabled,
        title: title,
        student_name: ($("v2_cover_student").value || "").trim(),
        lecturer: ($("v2_cover_lecturer").value || "").trim(),
        course: ($("v2_cover_course").value || "").trim(),
        submission_date: $("v2_cover_date").value || null,
      };
    }

    if (state.touched.table_of_contents) {
      out.table_of_contents = {
        enabled: $("v2_toc_enabled").checked,
        max_depth: Number($("v2_toc_max_depth").value) || 3,
        field_based: $("v2_toc_field_based").checked,
      };
    }

    if (state.touched.abbreviations) {
      out.abbreviations = {
        enabled: $("v2_abbr_enabled").checked,
        entries: parseAbbrEntries($("v2_abbr_entries").value),
      };
    }

    if (state.touched.appendices) {
      out.appendices = {
        enabled: $("v2_appendices_enabled").checked,
        lettered: $("v2_appendices_lettered").checked,
      };
    }

    if (state.touched.captions) {
      out.captions = {
        enabled: $("v2_captions_enabled").checked,
        table_position: $("v2_table_position").value,
        figure_position: $("v2_figure_position").value,
      };
    }

    if (state.touched.references) {
      out.references = {
        enabled: $("v2_refs_enabled").checked,
        heading_text: ($("v2_refs_heading").value || "").trim() || "References",
        on_new_page: $("v2_refs_new_page").checked,
        numbered: $("v2_refs_numbered").checked,
      };
    }

    return out;
  }

  window.__formatV2BuildOverrides = buildOverrides;
  window.__formatV2State = state;
  window.__formatV2LoadProfile = loadProfile;

  function applyOverridesFromParse(overrides) {
    if (!overrides || typeof overrides !== "object") return;
    state.applying = true;

    if (overrides.style) {
      state.style = overrides.style;
      state.touched.style = true;
      $("v2_format_style").value = overrides.style;
      syncStyleChipSelection(overrides.style);
    }

    function setSelect(id, value, field) {
      if (value == null) return;
      var el = $(id);
      if (!el) return;
      if (id === "v2_line_spacing") {
        el.value = normalizeLineSpacingOption(value);
      } else {
        el.value = String(value);
      }
      state.touched[field] = true;
    }

    setSelect("v2_font_family", overrides.font_family, "font_family");
    setSelect("v2_font_size", overrides.font_size_pt, "font_size_pt");
    setSelect("v2_line_spacing", overrides.line_spacing, "line_spacing");
    setSelect("v2_alignment", overrides.alignment, "alignment");

    if (overrides.first_line_indent != null) {
      $("v2_first_line_indent").checked = !!overrides.first_line_indent;
      state.touched.first_line_indent = true;
    }

    if (overrides.margins) {
      var m = overrides.margins;
      var matched = null;
      Object.keys(MARGIN_PRESETS).forEach(function (name) {
        var p = MARGIN_PRESETS[name];
        if (
          p.top_in === m.top_in &&
          p.bottom_in === m.bottom_in &&
          p.left_in === m.left_in &&
          p.right_in === m.right_in
        ) {
          matched = name;
        }
      });
      if (matched) {
        $("v2_margin_preset").value = matched;
      } else {
        state.customMargins = m;
        $("v2_margin_preset").value = "custom";
      }
      state.touched.margins = true;
    }

    setSelect("v2_page_size", overrides.page_size, "page_size");

    if (overrides.page_numbering && overrides.page_numbering.position) {
      $("v2_page_number_position").value = overrides.page_numbering.position;
      state.touched.page_numbering = true;
    }

    if (overrides.heading_size_pt != null) {
      $("v2_heading_size_pt").value = String(overrides.heading_size_pt);
      state.touched.heading_size_pt = true;
    }

    if (overrides.citations && overrides.citations.style_override) {
      $("v2_citation_style_override").value = overrides.citations.style_override;
      state.touched.citations = true;
    }

    if (overrides.cover_page) {
      var c = overrides.cover_page;
      $("v2_cover_enabled").checked = !!c.enabled;
      if (c.title != null) $("v2_cover_title").value = c.title;
      if (c.student_name != null) $("v2_cover_student").value = c.student_name;
      if (c.lecturer != null) $("v2_cover_lecturer").value = c.lecturer;
      if (c.course != null) $("v2_cover_course").value = c.course;
      if (c.submission_date) $("v2_cover_date").value = String(c.submission_date).slice(0, 10);
      state.touched.cover_page = true;
    }

    if (overrides.table_of_contents) {
      var t = overrides.table_of_contents;
      if (t.enabled != null) $("v2_toc_enabled").checked = !!t.enabled;
      if (t.max_depth != null) $("v2_toc_max_depth").value = String(t.max_depth);
      if (t.field_based != null) $("v2_toc_field_based").checked = !!t.field_based;
      state.touched.table_of_contents = true;
    }

    if (overrides.appendices) {
      var a = overrides.appendices;
      if (a.enabled != null) $("v2_appendices_enabled").checked = !!a.enabled;
      if (a.lettered != null) $("v2_appendices_lettered").checked = !!a.lettered;
      state.touched.appendices = true;
    }

    if (overrides.captions) {
      var cap = overrides.captions;
      if (cap.enabled != null) $("v2_captions_enabled").checked = !!cap.enabled;
      if (cap.table_position) $("v2_table_position").value = cap.table_position;
      if (cap.figure_position) $("v2_figure_position").value = cap.figure_position;
      state.touched.captions = true;
    }

    if (overrides.references) {
      var r = overrides.references;
      if (r.enabled != null) $("v2_refs_enabled").checked = !!r.enabled;
      if (r.heading_text != null) $("v2_refs_heading").value = r.heading_text;
      if (r.on_new_page != null) $("v2_refs_new_page").checked = !!r.on_new_page;
      if (r.numbered != null) $("v2_refs_numbered").checked = !!r.numbered;
      state.touched.references = true;
    }

    if (overrides.abbreviations) {
      var ab = overrides.abbreviations;
      if (ab.enabled != null) $("v2_abbr_enabled").checked = !!ab.enabled;
      if (ab.entries) $("v2_abbr_entries").value = formatAbbrEntries(ab.entries);
      state.touched.abbreviations = true;
    }

    state.applying = false;
    updateStyleHint();
    updateProfileSummary();
    updatePreview();
    syncDependentFields();
  }

  async function loadProfile(style) {
    var res = await fetch("/api/format-v2/profile/" + encodeURIComponent(style));
    if (!res.ok) {
      var err = await res.json().catch(function () {
        return {};
      });
      throw new Error(err.error || "Could not load style profile.");
    }
    return res.json();
  }

  async function onStyleChange(style) {
    state.style = style;
    $("v2_format_style").value = style;
    syncStyleChipSelection(style);
    state.touched = {};
    clearEvidence();
    var data = await loadProfile(style);
    state.displayName = data.display_name || style;
    applyFormDefaults(data.form);
  }

  function syncDependentFields() {
    var toggles = {
      toc: !!($("v2_toc_enabled") && $("v2_toc_enabled").checked),
      abbr: !!($("v2_abbr_enabled") && $("v2_abbr_enabled").checked),
      appendices: !!($("v2_appendices_enabled") && $("v2_appendices_enabled").checked),
    };
    document.querySelectorAll("[data-v2-depends-on]").forEach(function (el) {
      var key = el.getAttribute("data-v2-depends-on");
      var enabled = !!toggles[key];
      el.classList.toggle("is-disabled", !enabled);
      el.querySelectorAll("input, select, textarea, button").forEach(function (control) {
        control.disabled = !enabled;
      });
    });
  }

  function bindDependentFields() {
    document.querySelectorAll("[data-v2-toggle]").forEach(function (el) {
      el.addEventListener("change", syncDependentFields);
    });
    syncDependentFields();
  }

  function buildDocumentFormData(overrides, options) {
    var fd = new FormData();
    var fileInput = $("v2_file");
    var pastedEl = $("v2_pasted_text");
    var pasted = pastedEl ? (pastedEl.value || "").trim() : "";
    var file = fileInput && fileInput.files && fileInput.files[0];
    if (file) fd.append("file", file);
    if (pasted && pastedEl) fd.append("pasted_text", pastedEl.value);
    fd.append("format_style", state.style);
    var payload = overrides != null ? overrides : buildOverrides();
    var alwaysInclude = options && options.alwaysIncludeOverrides;
    if (alwaysInclude || (payload && Object.keys(payload).length)) {
      fd.append("overrides", JSON.stringify(payload || {}));
    }
    return fd;
  }

  function showChatPanel(show) {
    var panel = $("v2_chat_panel");
    if (panel) panel.hidden = !show;
    showChatHistorySection(show);
    if (show) renderChatHistory();
  }

  function showChatHistorySection(show) {
    var wrap = $("v2_chat_history_wrap");
    if (wrap) wrap.hidden = !show;
  }

  function renderChatSummary(text) {
    var el = $("v2_chat_summary");
    if (!el) return;
    el.textContent = text || "";
    el.classList.remove("v2-chat-summary--error");
  }

  function renderChatError(text) {
    var el = $("v2_chat_summary");
    if (!el) return;
    el.textContent = text || "";
    el.classList.add("v2-chat-summary--error");
  }

  function renderChatRejected(items) {
    var list = $("v2_chat_rejected");
    if (!list) return;
    list.innerHTML = "";
    (items || []).forEach(function (item) {
      var li = document.createElement("li");
      if (typeof item === "string") {
        li.textContent = item;
      } else {
        li.textContent = (item.request || "") + " — " + (item.reason || "");
      }
      list.appendChild(li);
    });
  }

  function updateUndoButton() {
    var btn = $("v2_chat_undo");
    if (btn) btn.disabled = state.overrideUndoStack.length === 0;
  }

  function setChatPending(isPending, message) {
    var el = $("v2_chat_pending");
    var send = $("v2_chat_send");
    var msg = $("v2_chat_message");
    if (el) {
      el.hidden = !isPending;
      el.textContent = message || CHAT_PENDING_DEFAULT;
    }
    if (send) send.disabled = !!isPending;
    if (msg) msg.disabled = !!isPending;
  }

  function renderChatHistory() {
    var list = $("v2_chat_history");
    var empty = $("v2_chat_history_empty");
    if (!list) return;
    list.innerHTML = "";
    if (!state.chatHistory.length) {
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    state.chatHistory.forEach(function (line) {
      var li = document.createElement("li");
      li.textContent = line;
      list.appendChild(li);
    });
  }

  function appendChatHistoryEntry(line) {
    var text = (line || "").trim();
    if (!text) return;
    state.chatHistory.push(text);
    renderChatHistory();
  }

  function rememberDownload(blob, filename) {
    if (state.latestDownloadUrl) {
      URL.revokeObjectURL(state.latestDownloadUrl);
    }
    state.latestDownloadUrl = URL.createObjectURL(blob);
    state.latestDownloadName = filename || "formatted_document.docx";
    var link = $("v2_download_latest");
    if (!link) return;
    link.href = state.latestDownloadUrl;
    link.download = state.latestDownloadName;
    link.hidden = false;
  }

  async function handleFormatJsonResponse(res, options) {
    options = options || {};
    var ct = res.headers.get("content-type") || "";
    if (!res.ok) {
      if (ct.indexOf("application/json") !== -1) {
        var err = await res.json();
        throw new Error(err.error || "Что-то пошло не так.");
      }
      throw new Error("Ошибка сервера (" + res.status + ").");
    }

    var data = await res.json();
    renderNotices(data.notices || []);
    if (data.overrides && typeof data.overrides === "object") {
      state.activeOverrides = data.overrides;
    }

    var summary = data.summary || "";
    var rejected = data.rejected || [];
    var documentId = data.document_id;
    if (!documentId) {
      throw new Error("Сервер не вернул идентификатор документа.");
    }

    var docRes = await fetchWithTimeout(
      "/api/format-v2/download/" + encodeURIComponent(documentId),
      { method: "GET" },
      CHAT_FETCH_TIMEOUT_MS
    );
    if (!docRes.ok) {
      if ((docRes.headers.get("content-type") || "").indexOf("application/json") !== -1) {
        var dlErr = await docRes.json();
        throw new Error(dlErr.error || "Не удалось скачать документ.");
      }
      throw new Error("Не удалось скачать документ (" + docRes.status + ").");
    }

    var blob = await docRes.blob();
    var filename = "formatted_document.docx";
    rememberDownload(blob, filename);
    if (!options.skipAutoDownload) {
      triggerDownload(blob, filename);
    }
    return { response: res, summary: summary, rejected: rejected, documentId: documentId };
  }

  async function handleFormatResponse(res) {
    return handleFormatJsonResponse(res, { skipAutoDownload: false });
  }

  async function sendChatEdit() {
    var input = $("v2_chat_message");
    var message = (input && input.value || "").trim();
    if (!message) return;

    if (!state.hasFormatted) {
      renderChatError("Сначала отформатируйте документ.");
      setFormatStatus("Сначала отформатируйте документ.", "error");
      return;
    }

    setChatPending(true, "Применяю правку…");
    renderChatSummary("");
    renderChatRejected([]);

    state.overrideUndoStack.push(JSON.parse(JSON.stringify(state.activeOverrides)));
    updateUndoButton();

    try {
      var fd = buildDocumentFormData(state.activeOverrides, { alwaysIncludeOverrides: true });
      fd.append("message", message);

      var res = await fetchWithTimeout(
        "/api/format-v2/chat",
        { method: "POST", body: fd },
        CHAT_FETCH_TIMEOUT_MS
      );
      var handled = await handleFormatJsonResponse(res, { skipAutoDownload: true });
      var summary = handled.summary || "";
      var rejected = handled.rejected || [];
      var applied = !!summary;

      if (applied) {
        renderChatSummary(summary);
        appendChatHistoryEntry(summary);
        if (window.AppUI) window.AppUI.showToast("Документ обновлён", "success");
      } else if (rejected.length) {
        state.overrideUndoStack.pop();
        updateUndoButton();
        renderChatError("Правка не применена");
        renderChatRejected(rejected);
      } else {
        state.overrideUndoStack.pop();
        updateUndoButton();
        renderChatError("Не удалось применить правку: сервер не вернул изменений.");
      }

      if (input) input.value = "";
    } catch (e) {
      state.overrideUndoStack.pop();
      updateUndoButton();
      var errMsg = e.name === "AbortError"
        ? "Превышено время ожидания (30 с). Проверьте соединение и попробуйте снова."
        : (e.message || "Не удалось применить правку.");
      renderChatError(errMsg);
    } finally {
      setChatPending(false);
    }
  }

  async function undoChatEdit() {
    if (!state.overrideUndoStack.length) return;
    state.activeOverrides = state.overrideUndoStack.pop();
    if (state.chatHistory.length) state.chatHistory.pop();
    renderChatHistory();
    updateUndoButton();
    renderChatSummary("");
    renderChatRejected([]);

    var btn = $("v2_chat_undo");
    if (btn) btn.disabled = true;
    setChatPending(true, "Откатываю правку…");

    try {
      var res = await fetchWithTimeout(
        "/api/format-v2",
        {
          method: "POST",
          body: buildDocumentFormData(state.activeOverrides, { alwaysIncludeOverrides: true }),
        },
        CHAT_FETCH_TIMEOUT_MS
      );
      await handleFormatJsonResponse(res, { skipAutoDownload: true });
    } catch (e) {
      var undoErr = e.name === "AbortError"
        ? "Превышено время ожидания (30 с)."
        : (e.message || "Не удалось откатить.");
      renderChatError(undoErr);
    } finally {
      setChatPending(false);
      if (btn) btn.disabled = state.overrideUndoStack.length === 0;
    }
  }

  function renderNotices(notices) {
    var panel = $("v2_notices");
    var list = $("v2_notices_list");
    if (!panel || !list) return;
    list.innerHTML = "";
    if (!notices || !notices.length) {
      panel.hidden = true;
      return;
    }
    panel.hidden = false;
    notices.forEach(function (n) {
      var severity = n.severity === "info" ? "info" : "deviation";
      var row = document.createElement("div");
      row.className = "v2-notice v2-notice--" + severity;
      var icon = document.createElement("span");
      icon.className = "v2-notice-icon";
      icon.setAttribute("aria-hidden", "true");
      icon.textContent = severity === "deviation" ? "⚠" : "ℹ";
      var text = document.createElement("span");
      text.textContent = n.message || "";
      row.appendChild(icon);
      row.appendChild(text);
      list.appendChild(row);
    });
  }

  function triggerDownload(blob, filename) {
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () {
      URL.revokeObjectURL(url);
    }, 1500);
  }

  function bindFieldTouches() {
    document.querySelectorAll("[data-v2-field]").forEach(function (el) {
      var field = el.getAttribute("data-v2-field");
      var evt = el.tagName === "SELECT" || el.type === "checkbox" || el.type === "date" ? "change" : "input";
      el.addEventListener(evt, function () {
        markTouched(field);
      });
    });
    var coverEnabled = $("v2_cover_enabled");
    if (coverEnabled) {
      coverEnabled.addEventListener("change", function () {
        updatePreview();
      });
    }
  }

  function bindStyleChips() {
    document.querySelectorAll("[data-v2-style]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        var style = btn.getAttribute("data-v2-style");
        onStyleChange(style).catch(function (err) {
          setFormatStatus(err.message || "Profile load failed.", "error");
        });
      });
    });
  }

  function bindDocSegment() {
    var card = document.querySelector("[data-v2-doc-card]");
    if (!card) return;
    var segment = card.querySelector("[data-v2-doc-segment]");
    var sourceBtns = card.querySelectorAll("[data-v2-doc-source]");
    var pastePanel = card.querySelector('[data-v2-doc-panel="paste"]');
    var dropPlaceholder = $("v2_drop_placeholder");
    var fileInput = $("v2_file");

    function setDocSource(src) {
      var isPaste = src === "paste";
      if (segment) segment.classList.toggle("is-upload", isPaste);
      sourceBtns.forEach(function (btn) {
        var active = btn.getAttribute("data-v2-doc-source") === src;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (dropPlaceholder) dropPlaceholder.hidden = isPaste;
      if (pastePanel) pastePanel.hidden = !isPaste;
      if (isPaste) {
        var pasted = $("v2_pasted_text");
        if (pasted) pasted.focus();
      }
    }

    sourceBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var src = btn.getAttribute("data-v2-doc-source");
        setDocSource(src);
        if (src === "drop" && fileInput) fileInput.click();
      });
    });

    if (dropPlaceholder) {
      dropPlaceholder.addEventListener("click", function () {
        if (fileInput) fileInput.click();
      });
      dropPlaceholder.addEventListener("keydown", function (e) {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          if (fileInput) fileInput.click();
        }
      });
    }

    if (fileInput) {
      fileInput.addEventListener("change", function () {
        var file = fileInput.files && fileInput.files[0];
        var nameEl = $("v2_file_name");
        if (nameEl) nameEl.textContent = file ? file.name : "";
      });
    }
  }

  function setupDragDrop() {
    var layout = document.querySelector("[data-format-v2]");
    var zone = document.querySelector("[data-v2-drop-zone]");
    if (!layout || !zone) return;

    var dragDepth = 0;

    function hasFiles(e) {
      var dt = e.dataTransfer;
      if (!dt) return false;
      try {
        var types = dt.types ? Array.prototype.slice.call(dt.types) : [];
        if (types.indexOf("Files") !== -1) return true;
      } catch (err) {}
      return !!(dt.files && dt.files.length);
    }

    function showOverlay(on) {
      var overlay = zone.querySelector("[data-v2-zone-overlay]");
      if (overlay) overlay.hidden = !on;
      zone.classList.toggle("is-drop-active", !!on);
      layout.classList.toggle("is-dragging-files", !!on);
    }

    function onDragEnter(e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      dragDepth += 1;
      showOverlay(true);
    }

    function onDragOver(e) {
      if (!hasFiles(e)) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = "copy";
      showOverlay(true);
    }

    function onDragLeave(e) {
      e.preventDefault();
      dragDepth = Math.max(0, dragDepth - 1);
      if (dragDepth === 0) showOverlay(false);
    }

    function onDrop(e) {
      e.preventDefault();
      e.stopPropagation();
      dragDepth = 0;
      showOverlay(false);
      var files = e.dataTransfer && e.dataTransfer.files;
      if (!files || !files.length) return;
      var fileInput = $("v2_file");
      if (!fileInput) return;
      try {
        var dt = new DataTransfer();
        dt.items.add(files[0]);
        fileInput.files = dt.files;
      } catch (err) {
        return;
      }
      var nameEl = $("v2_file_name");
      if (nameEl) nameEl.textContent = files[0].name;
    }

    [layout, zone].forEach(function (el) {
      el.addEventListener("dragenter", onDragEnter);
      el.addEventListener("dragover", onDragOver);
      el.addEventListener("dragleave", onDragLeave);
      el.addEventListener("drop", onDrop);
    });
  }

  async function parseBrief() {
    var status = $("v2_requirements_status");
    var brief = ($("v2_requirements_text").value || "").trim();
    if (!brief) {
      setStatus(status, "Сначала вставьте требования.", "error");
      return;
    }
    var btn = $("v2_parse_btn");
    if (btn) btn.disabled = true;
    setStatus(status, "Разбираем…");
    try {
      var fd = new FormData();
      fd.append("requirements_text", brief);
      fd.append("format_style", state.style);
      var res = await fetch("/api/extract-requirements-v2", { method: "POST", body: fd });
      var data = await res.json();
      if (!res.ok) throw new Error(data.error || "Parse failed.");
      applyOverridesFromParse(data.overrides || {});
      setEvidence(data.evidence_by_field || {});
      if (data.style && data.style !== state.style) {
        state.style = data.style;
        $("v2_format_style").value = data.style;
        syncStyleChipSelection(data.style);
        var profile = await loadProfile(data.style);
        state.displayName = profile.display_name || data.style;
        var savedTouched = Object.assign({}, state.touched);
        var savedOverrides = buildOverrides();
        applyFormDefaults(profile.form);
        state.touched = savedTouched;
        applyOverridesFromParse(savedOverrides);
        setEvidence(data.evidence_by_field || {});
      }
      var warn = (data.warnings && data.warnings[0]) || "";
      setStatus(
        status,
        warn || "Настройки заполнены — проверьте перед форматированием.",
        warn ? "warn" : "success"
      );
    } catch (err) {
      setStatus(status, err.message || "Не удалось разобрать.", "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function formatDocument() {
    var btn = $("v2_format_btn");
    var fileInput = $("v2_file");
    var pastedEl = $("v2_pasted_text");
    var pasted = pastedEl ? (pastedEl.value || "").trim() : "";
    var file = fileInput && fileInput.files && fileInput.files[0];

    setFormatStatus("");

    if (!file && !pasted) {
      setFormatStatus("Загрузите DOCX/PDF или вставьте текст.", "error");
      return;
    }

    var overrides = buildOverrides();
    var fd = buildDocumentFormData(overrides);

    if (btn) btn.disabled = true;
    setFormatStatus("Форматируем…");

    try {
      var res = await fetch("/api/format-v2", { method: "POST", body: fd });
      await handleFormatResponse(res);
      state.hasFormatted = true;
      state.overrideUndoStack = [];
      state.chatHistory = [];
      updateUndoButton();
      renderChatHistory();
      renderChatSummary("");
      renderChatRejected([]);
      showChatPanel(true);
      setFormatStatus("Документ готов", "success");
      if (window.AppUI) window.AppUI.showToast("Документ скачан", "success");
    } catch (e) {
      setFormatStatus(e.message || "Сетевая ошибка — сервер запущен?", "error");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function init() {
    try {
      if (!$("v2_format_btn")) return;
      bindFieldTouches();
      bindStyleChips();
      bindDocSegment();
      setupDragDrop();
      bindDependentFields();
      $("v2_parse_btn").addEventListener("click", function () {
        parseBrief();
      });
      $("v2_format_btn").addEventListener("click", function () {
        formatDocument();
      });
      var chatSend = $("v2_chat_send");
      if (chatSend) {
        chatSend.addEventListener("click", function () {
          sendChatEdit();
        });
      }
      var chatInput = $("v2_chat_message");
      if (chatInput) {
        chatInput.addEventListener("keydown", function (e) {
          if (e.key === "Enter") {
            e.preventDefault();
            sendChatEdit();
          }
        });
      }
      var chatUndo = $("v2_chat_undo");
      if (chatUndo) {
        chatUndo.addEventListener("click", function () {
          undoChatEdit();
        });
      }
      onStyleChange(state.style).catch(function (err) {
        setFormatStatus(err.message || "Не удалось загрузить профиль.", "error");
      });
    } catch (err) {
      console.error("[format-v2] init failed:", err);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
