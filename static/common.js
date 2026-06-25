/**
 * Shared keys, formatter settings, template apply, storage (localStorage + sessionStorage).
 */
(function (global) {
  var SETTINGS_SNAPSHOT_KEY = "formatter_settings_snapshot";
  var TEMPLATE_META_KEY = "formatter_active_template";
  var REF_STYLE_KEY = "academic_formatter_citation_style";

  function readStorage(key) {
    try {
      return localStorage.getItem(key) || sessionStorage.getItem(key);
    } catch (e) {
      try {
        return sessionStorage.getItem(key);
      } catch (e2) {
        return null;
      }
    }
  }

  function writeStorage(key, value) {
    try {
      localStorage.setItem(key, value);
    } catch (e) {
      /* quota */
    }
    try {
      sessionStorage.setItem(key, value);
    } catch (e2) {
      /* quota */
    }
  }

  function snapshotToExpected(d) {
    var pos = d.page_number_position || "none";
    return {
      font_family: d.font_family,
      font_size: typeof d.font_size === "number" ? d.font_size : parseInt(d.font_size, 10),
      line_spacing: typeof d.line_spacing === "number" ? d.line_spacing : parseFloat(d.line_spacing),
      alignment: d.alignment || "left",
      first_line_indent: !!d.first_line_indent,
      require_page_numbers: pos !== "none",
      page_number_position: pos,
      check_intro_conclusion: true,
      expect_references_section: true,
    };
  }

  function getFormatterConfigFromDom() {
    var $ = function (id) {
      return document.getElementById(id);
    };
    return {
      font_family: ($("font_family") && $("font_family").value) || "Times New Roman",
      font_size: ($("font_size") && $("font_size").value) || "12",
      line_spacing: ($("line_spacing") && $("line_spacing").value) || "1.5",
      alignment: ($("alignment") && $("alignment").value) || "left",
      margin_preset: ($("margin_preset") && $("margin_preset").value) || "normal",
      page_number_position: ($("page_number_position") && $("page_number_position").value) || "none",
      first_line_indent: $("first_line_indent") ? !!$("first_line_indent").checked : false,
      space_before_pt: ($("space_before_pt") && $("space_before_pt").value) || "0",
      space_after_pt: ($("space_after_pt") && $("space_after_pt").value) || "0",
      auto_headings: $("auto_headings") ? !!$("auto_headings").checked : true,
      heading_all_caps: $("heading_all_caps") ? !!$("heading_all_caps").checked : false,
      auto_justify_refs: $("auto_justify_refs") ? !!$("auto_justify_refs").checked : true,
      clean_extra_spaces: $("clean_extra_spaces") ? !!$("clean_extra_spaces").checked : false,
      clean_extra_linebreaks: $("clean_extra_linebreaks") ? !!$("clean_extra_linebreaks").checked : false,
    };
  }

  function normalizeFormatterConfig(cfg) {
    var base = getFormatterConfigFromDom();
    if (!cfg) {
      return base;
    }
    return Object.assign({}, base, cfg);
  }

  function saveFormatterSettingsSnapshot(cfg) {
    writeStorage(SETTINGS_SNAPSHOT_KEY, JSON.stringify(normalizeFormatterConfig(cfg)));
  }

  function applyFormatterConfig(cfg) {
    if (!cfg) {
      return;
    }
    var $ = function (id) {
      return document.getElementById(id);
    };
    var map = {
      font_family: "font_family",
      font_size: "font_size",
      line_spacing: "line_spacing",
      alignment: "alignment",
      margin_preset: "margin_preset",
      page_number_position: "page_number_position",
      space_before_pt: "space_before_pt",
      space_after_pt: "space_after_pt",
    };
    Object.keys(map).forEach(function (k) {
      if (cfg[k] != null && $(map[k])) {
        var el = $(map[k]);
        if ([].some.call(el.options || [], function (o) {
          return o.value === String(cfg[k]);
        })) {
          el.value = String(cfg[k]);
        }
      }
    });
    var checks = [
      "first_line_indent",
      "auto_headings",
      "heading_all_caps",
      "auto_justify_refs",
      "clean_extra_spaces",
      "clean_extra_linebreaks",
      "include_cover_page",
    ];
    checks.forEach(function (id) {
      if (Object.prototype.hasOwnProperty.call(cfg, id) && $(id)) {
        $(id).checked = !!cfg[id];
      }
    });
    [
      "cover_assignment_title",
      "cover_student_name",
      "cover_student_id",
      "cover_university",
      "cover_module",
      "cover_lecturer",
      "cover_submission_date",
    ].forEach(function (id) {
      if (cfg[id] != null && $(id)) {
        $(id).value = String(cfg[id]);
      }
    });
    if ($("font_family")) {
      saveFormatterSettingsFromDom();
    } else {
      saveFormatterSettingsSnapshot(cfg);
    }
  }

  function saveFormatterSettingsFromDom() {
    var o = getFormatterConfigFromDom();
    writeStorage(SETTINGS_SNAPSHOT_KEY, JSON.stringify(o));
  }

  function loadStoredFormatterSettings() {
    try {
      var raw = readStorage(SETTINGS_SNAPSHOT_KEY);
      if (!raw) {
        return null;
      }
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function saveFormatterSettingsFromHome() {
    saveFormatterSettingsFromDom();
  }

  function bindHomeSettingsAutosave() {
    var ids = [
      "font_family",
      "font_size",
      "line_spacing",
      "alignment",
      "margin_preset",
      "page_number_position",
      "space_before_pt",
      "space_after_pt",
      "first_line_indent",
      "auto_headings",
      "heading_all_caps",
      "auto_justify_refs",
      "clean_extra_spaces",
      "clean_extra_linebreaks",
      "include_cover_page",
      "cover_assignment_title",
      "cover_student_name",
      "cover_student_id",
      "cover_university",
      "cover_module",
      "cover_lecturer",
      "cover_submission_date",
    ];
    ids.forEach(function (id) {
      var el = document.getElementById(id);
      if (!el) {
        return;
      }
      el.addEventListener("change", saveFormatterSettingsFromDom);
      if (el.type === "checkbox") {
        el.addEventListener("click", saveFormatterSettingsFromDom);
      }
    });
  }

  function applyTemplate(template, options) {
    if (!template || !template.settings) {
      return;
    }
    var opts = options || {};
    applyFormatterConfig(template.settings);
    if (template.citationStyle) {
      writeStorage(REF_STYLE_KEY, template.citationStyle);
    }
    writeStorage(
      TEMPLATE_META_KEY,
      JSON.stringify({ id: template.id, name: template.name, appliedAt: Date.now() })
    );
    if (global.AppUI && opts.toast !== false) {
      global.AppUI.showToast('Template "' + template.name + '" applied', "success");
    }
  }

  function getActiveTemplateMeta() {
    try {
      var raw = readStorage(TEMPLATE_META_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  var REF_STORAGE_KEY = "academic_formatter_saved_references";

  function loadSavedReferencesForFormat() {
    try {
      var raw = readStorage(REF_STORAGE_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      return Array.isArray(arr) ? arr.map(String).filter(Boolean) : [];
    } catch (e) {
      return [];
    }
  }

  function citationStyleForFormat() {
    try {
      var v = readStorage(REF_STYLE_KEY);
      if (v && ["APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver"].indexOf(v) !== -1) {
        return v;
      }
    } catch (e) {
      /* ignore */
    }
    return "APA";
  }

  function appendCheckboxToFormData(fd, key, elId) {
    var el = document.getElementById(elId);
    fd.append(key, el && el.checked ? "on" : "off");
  }

  function appendCoverPageToFormData(fd) {
    var coverIds = [
      "cover_assignment_title",
      "cover_student_name",
      "cover_student_id",
      "cover_university",
      "cover_module",
      "cover_lecturer",
      "cover_submission_date",
    ];
    coverIds.forEach(function (id) {
      var el = document.getElementById(id);
      if (el) {
        fd.append(id, el.value || "");
      }
    });
    appendCheckboxToFormData(fd, "include_cover_page", "include_cover_page");
  }

  function isSupportedDocumentFile(file) {
    if (!file) {
      return false;
    }
    var name = (file.name || "").toLowerCase();
    if (name.endsWith(".docx") || name.endsWith(".pdf")) {
      return true;
    }
    var type = (file.type || "").toLowerCase();
    return (
      type === "application/pdf" ||
      type === "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    );
  }

  function unsupportedDocumentMessage() {
    return "Upload a .docx or .pdf file, or clear the file and paste text instead.";
  }

  async function extractDocumentText(file, statusEl) {
    if (!file) {
      return { ok: false, error: "No file selected." };
    }
    if (!isSupportedDocumentFile(file)) {
      return { ok: false, error: unsupportedDocumentMessage() };
    }
    if (statusEl) {
      statusEl.textContent = "Reading uploaded file…";
      statusEl.className = (statusEl.className || "").replace(/\s*(error|success|warn)\b/g, "");
    }
    try {
      var fd = new FormData();
      fd.append("file", file);
      var res = await fetch("/api/extract-document", { method: "POST", body: fd });
      var data = {};
      try {
        data = await res.json();
      } catch (e) {
        return { ok: false, error: "Invalid response from server." };
      }
      if (!res.ok) {
        return { ok: false, error: data.error || "Could not read the uploaded file." };
      }
      return { ok: true, text: data.text || "" };
    } catch (err) {
      return { ok: false, error: "Network error while reading the uploaded file." };
    }
  }

  function bindDocumentUploadExtract(fileInputId, pastedInputId, options) {
    var opts = options || {};
    var fileInput = document.getElementById(fileInputId);
    var pastedInput = document.getElementById(pastedInputId);
    if (!fileInput || !pastedInput) {
      return;
    }
    fileInput.addEventListener("change", async function () {
      var file = fileInput.files && fileInput.files[0];
      if (!file) {
        return;
      }
      if (!isSupportedDocumentFile(file)) {
        if (opts.statusEl) {
          opts.statusEl.textContent = unsupportedDocumentMessage();
          opts.statusEl.className = (opts.statusEl.className || "").replace(/\s*(error|success|warn)\b/g, "") + " error";
        }
        fileInput.value = "";
        return;
      }
      var result = await extractDocumentText(file, opts.statusEl);
      if (!result.ok) {
        if (opts.statusEl) {
          opts.statusEl.textContent = result.error;
          opts.statusEl.className = (opts.statusEl.className || "").replace(/\s*(error|success|warn)\b/g, "") + " error";
        }
        fileInput.value = "";
        return;
      }
      pastedInput.value = result.text;
      if (opts.statusEl) {
        opts.statusEl.textContent = "";
        opts.statusEl.className = (opts.statusEl.className || "").replace(/\s*(error|success|warn)\b/g, "");
      }
      if (typeof opts.onExtracted === "function") {
        opts.onExtracted(result.text);
      }
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
    URL.revokeObjectURL(url);
  }

  function formatDocument(options) {
    var opts = options || {};
    var fileInput = document.getElementById(opts.fileInputId || "file");
    var pastedInput = document.getElementById(opts.pastedInputId || "pasted_text");
    var formatBtn = opts.formatBtn || document.getElementById("format_btn");
    var statusEl = opts.statusEl || document.getElementById("format_status");

    function setFormatStatus(message, kind) {
      if (!statusEl) {
        return;
      }
      statusEl.textContent = message || "";
      statusEl.className = "format-status status" + (kind ? " " + kind : "");
    }

    return (async function () {
      var file = fileInput && fileInput.files && fileInput.files[0];
      var pasted = pastedInput ? pastedInput.value.trim() : "";

      setFormatStatus("");

      if (file && !isSupportedDocumentFile(file)) {
        setFormatStatus(unsupportedDocumentMessage(), "error");
        return { ok: false };
      }

      if (!file && !pasted) {
        setFormatStatus("Upload a .docx or .pdf file, or paste some text first.", "error");
        return { ok: false };
      }

      var fd = new FormData();
      if (file) {
        fd.append("file", file);
      }
      if (pasted) {
        fd.append("pasted_text", pastedInput.value);
      }

      var cfg = getFormatterConfigFromDom();
      fd.append("font_family", cfg.font_family);
      fd.append("font_size", cfg.font_size);
      fd.append("line_spacing", cfg.line_spacing);
      fd.append("alignment", cfg.alignment);
      fd.append("margin_preset", cfg.margin_preset);
      fd.append("page_number_position", cfg.page_number_position);
      fd.append("space_before_pt", cfg.space_before_pt);
      fd.append("space_after_pt", cfg.space_after_pt);

      appendCheckboxToFormData(fd, "first_line_indent", "first_line_indent");
      appendCheckboxToFormData(fd, "auto_headings", "auto_headings");
      appendCheckboxToFormData(fd, "heading_all_caps", "heading_all_caps");
      appendCheckboxToFormData(fd, "auto_justify_refs", "auto_justify_refs");
      appendCheckboxToFormData(fd, "clean_extra_spaces", "clean_extra_spaces");
      appendCheckboxToFormData(fd, "clean_extra_linebreaks", "clean_extra_linebreaks");
      appendCoverPageToFormData(fd);

      loadSavedReferencesForFormat().forEach(function (citation) {
        fd.append("references", citation);
      });
      fd.append("citation_style", citationStyleForFormat());
      saveFormatterSettingsFromDom();

      if (formatBtn) {
        formatBtn.disabled = true;
      }
      setFormatStatus("Formatting…");

      try {
        var res = await fetch("/api/format", { method: "POST", body: fd });
        var ct = res.headers.get("content-type") || "";

        if (!res.ok) {
          if (ct.includes("application/json")) {
            var data = await res.json();
            setFormatStatus(data.error || "Something went wrong.", "error");
          } else {
            setFormatStatus("Server error (" + res.status + ").", "error");
          }
          return { ok: false };
        }

        if (!ct.includes("wordprocessingml") && !ct.includes("octet-stream")) {
          setFormatStatus("Unexpected response from server.", "error");
          return { ok: false };
        }

        var blob = await res.blob();
        var filename = "formatted_document.docx";
        var cd = res.headers.get("content-disposition");
        var match = cd && cd.match(/filename\*?=(?:UTF-8''|")?([^\";]+)/i);
        if (match && match[1]) {
          filename = decodeURIComponent(match[1].replace(/"/g, ""));
        }

        triggerDownload(blob, filename);
        setFormatStatus("Your document is ready", "success");
        if (global.AppUI) {
          global.AppUI.showToast("Document downloaded", "success");
        }
        if (typeof opts.onSuccess === "function") {
          opts.onSuccess({ filename: filename });
        }
        return { ok: true, filename: filename };
      } catch (err) {
        setFormatStatus("Network error — is the Flask server running on port 5000?", "error");
        return { ok: false };
      } finally {
        if (formatBtn) {
          formatBtn.disabled = false;
        }
      }
    })();
  }

  global.FormatterCommon = {
    SETTINGS_SNAPSHOT_KEY: SETTINGS_SNAPSHOT_KEY,
    TEMPLATE_META_KEY: TEMPLATE_META_KEY,
    REF_STYLE_KEY: REF_STYLE_KEY,
    readStorage: readStorage,
    writeStorage: writeStorage,
    saveFormatterSettingsFromHome: saveFormatterSettingsFromHome,
    saveFormatterSettingsFromDom: saveFormatterSettingsFromDom,
    bindHomeSettingsAutosave: bindHomeSettingsAutosave,
    getFormatterConfigFromDom: getFormatterConfigFromDom,
    applyFormatterConfig: applyFormatterConfig,
    loadStoredFormatterSettings: loadStoredFormatterSettings,
    applyTemplate: applyTemplate,
    getActiveTemplateMeta: getActiveTemplateMeta,
    saveFormatterSettingsSnapshot: saveFormatterSettingsSnapshot,
    formatDocument: formatDocument,
    isSupportedDocumentFile: isSupportedDocumentFile,
    extractDocumentText: extractDocumentText,
    bindDocumentUploadExtract: bindDocumentUploadExtract,
    loadSavedReferencesForFormat: loadSavedReferencesForFormat,
    citationStyleForFormat: citationStyleForFormat,
  };
})(typeof window !== "undefined" ? window : this);
