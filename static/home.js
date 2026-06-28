/**
 * Home: presets, parse requirements, format + download (references from sessionStorage).
 */
(function () {
  var FC = window.FormatterCommon;
  if (!FC) {
    return;
  }

  var $ = function (id) {
    return document.getElementById(id);
  };

  var PRESETS = {
    harvard: {
      font_family: "Times New Roman",
      font_size: "12",
      line_spacing: "1.5",
      alignment: "justify",
      margin_preset: "normal",
      page_number_position: "none",
      first_line_indent: false,
      space_before_pt: "0",
      space_after_pt: "12",
      auto_headings: true,
      heading_all_caps: false,
      auto_justify_refs: true,
      clean_extra_spaces: false,
      clean_extra_linebreaks: false,
    },
    apa: {
      font_family: "Times New Roman",
      font_size: "12",
      line_spacing: "2.0",
      alignment: "left",
      margin_preset: "normal",
      page_number_position: "top_right",
      first_line_indent: false,
      space_before_pt: "0",
      space_after_pt: "0",
      auto_headings: true,
      heading_all_caps: false,
      auto_justify_refs: true,
      clean_extra_spaces: false,
      clean_extra_linebreaks: false,
    },
    mla: {
      font_family: "Times New Roman",
      font_size: "12",
      line_spacing: "2.0",
      alignment: "left",
      margin_preset: "normal",
      page_number_position: "top_right",
      first_line_indent: false,
      space_before_pt: "0",
      space_after_pt: "0",
      auto_headings: true,
      heading_all_caps: false,
      auto_justify_refs: true,
      clean_extra_spaces: false,
      clean_extra_linebreaks: false,
    },
  };
  var REF_STYLE_KEY = "academic_formatter_citation_style";

  function applyPreset(name) {
    var cfg = PRESETS[name];
    presetChipButtons().forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-preset") === name);
    });
    if (!cfg) {
      return;
    }
    FC.applyFormatterConfig(cfg);
  }

  function presetChipButtons() {
    return document.querySelectorAll(".text-settings-card .preset-chip");
  }

  function setPresetChipActiveOnly(name) {
    presetChipButtons().forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-preset") === name);
    });
  }

  function applyParsedForm(form) {
    if (!form) {
      return;
    }
    FC.applyFormatterConfig(form);
    FC.saveFormatterSettingsFromHome();
  }

  function presetKeyFromCitation(requirements) {
    var cite = requirements && requirements.citation_style;
    if (!cite || typeof cite !== "string") {
      return "harvard";
    }
    var u = cite.trim().toUpperCase();
    if (u === "APA") {
      return "apa";
    }
    if (u === "MLA") {
      return "mla";
    }
    if (u === "HARVARD") {
      return "harvard";
    }
    return "harvard";
  }

  function persistCitationStyleFromRequirements(requirements) {
    var cite = requirements && requirements.citation_style;
    if (!cite || typeof cite !== "string") {
      return;
    }
    var v = cite.trim();
    if (["APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver"].indexOf(v) === -1) {
      return;
    }
    FC.writeStorage(REF_STYLE_KEY, v);
  }

  presetChipButtons().forEach(function (btn) {
    btn.addEventListener("click", function () {
      var key = btn.getAttribute("data-preset");
      if (key === "custom") {
        presetChipButtons().forEach(function (b) {
          b.classList.remove("is-active");
        });
        btn.classList.add("is-active");
        FC.saveFormatterSettingsFromHome();
        return;
      }
      applyPreset(key);
    });
  });

  FC.bindHomeSettingsAutosave();

  var stored = FC.loadStoredFormatterSettings();
  if (stored) {
    FC.applyFormatterConfig(stored);
  } else {
    applyPreset("harvard");
  }

  function refreshHomePreview() {
    var DP = window.DocPreview;
    var section = $("home_preview_section");
    if (!DP || !section) {
      return;
    }
    var text = ($("pasted_text") && $("pasted_text").value.trim()) || DP.SAMPLE;
    var cfg = FC.getFormatterConfigFromDom();
    var style = null;
    try {
      style = FC.readStorage(FC.REF_STYLE_KEY);
    } catch (e) {
      style = null;
    }
    if (style) {
      cfg.citationStyle = style;
    }
    DP.renderPreviewPair(section, text, cfg);
  }

  var previewBtn = $("preview_changes_btn");
  var previewSection = $("home_preview_section");
  if (previewBtn && previewSection) {
    previewBtn.addEventListener("click", function () {
      previewSection.classList.remove("hidden");
      refreshHomePreview();
      previewSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
      if (window.AppUI) {
        window.AppUI.showToast("Preview updated", "info");
      }
    });
  }

  if (previewSection && !previewSection.classList.contains("hidden")) {
    refreshHomePreview();
  }

  ["font_family", "font_size", "line_spacing", "alignment", "first_line_indent", "auto_headings", "requirement_headings", "heading_size_pt"].forEach(
    function (id) {
      var el = $(id);
      if (el && previewSection && !previewSection.classList.contains("hidden")) {
        el.addEventListener("change", refreshHomePreview);
      }
    }
  );

  var pastedInputEarly = $("pasted_text");
  if (pastedInputEarly) {
    pastedInputEarly.addEventListener("input", function () {
      if (previewSection && !previewSection.classList.contains("hidden")) {
        refreshHomePreview();
      }
    });
  }

  if (FC && FC.bindDocumentUploadExtract) {
    FC.bindDocumentUploadExtract("file", "pasted_text", {
      statusEl: $("format_status"),
      onExtracted: function () {
        if (previewSection && !previewSection.classList.contains("hidden")) {
          refreshHomePreview();
        }
      },
    });
  }

  var requirementsText = $("requirements_text");
  var requirementsAttach = $("requirements_attach");
  var requirementsAttachBtn = $("requirements_attach_btn");
  var analyzeBtn = $("analyze_requirements_btn");
  var requirementsStatus = $("requirements_status");

  function setReqStatus(message, kind) {
    if (!requirementsStatus) {
      return;
    }
    requirementsStatus.textContent = message || "";
    requirementsStatus.className = "req-chat-status req-status" + (kind ? " " + kind : "");
  }

  function autosizeReqTextarea() {
    var el = requirementsText;
    if (!el || el.tagName !== "TEXTAREA") {
      return;
    }
    el.style.height = "auto";
    var maxPx = Math.min(window.innerHeight * 0.45, 288);
    el.style.height = Math.min(el.scrollHeight, maxPx) + "px";
    var composer = el.closest(".req-chat-composer");
    if (composer) {
      composer.classList.toggle("is-expanded", el.scrollHeight > 48);
    }
  }

  if (requirementsText) {
    requirementsText.addEventListener("input", autosizeReqTextarea);
    autosizeReqTextarea();
    requirementsText.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (analyzeBtn && !analyzeBtn.disabled) {
          analyzeBtn.click();
        }
      }
    });
  }

  function isSupportedBriefFile(file) {
    if (!file) {
      return false;
    }
    var lower = (file.name || "").toLowerCase();
    if (/\.(pdf|docx|txt|jpe?g|png)$/i.test(lower)) {
      return true;
    }
    var mime = (file.type || "").toLowerCase();
    return (
      mime === "application/pdf" ||
      mime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
      mime.indexOf("text/") === 0 ||
      mime === "image/jpeg" ||
      mime === "image/jpg" ||
      mime === "image/png"
    );
  }

  function readTextFileAsUtf8(file) {
    return new Promise(function (resolve, reject) {
      var r = new FileReader();
      r.onload = function () {
        resolve(String(r.result || ""));
      };
      r.onerror = function () {
        reject(new Error("read failed"));
      };
      r.readAsText(file, "UTF-8");
    });
  }

  if (requirementsAttachBtn && requirementsAttach) {
    requirementsAttachBtn.addEventListener("click", function () {
      requirementsAttach.click();
    });
  }

  if (requirementsAttach) {
    requirementsAttach.addEventListener("change", async function () {
      var file = requirementsAttach.files && requirementsAttach.files[0];
      if (!file) {
        return;
      }

      setReqStatus("");
      if (!isSupportedBriefFile(file)) {
        setReqStatus("Supported formats: PDF, DOCX, TXT, JPG, PNG.", "error");
        requirementsAttach.value = "";
        return;
      }

      requirementsAttachBtn.disabled = true;

      try {
        var lower = (file.name || "").toLowerCase();
        var mime = (file.type || "").toLowerCase();
        var isPlainText =
          /\.txt$/i.test(lower) || (mime.indexOf("text/") === 0 && mime !== "text/html");

        if (isPlainText) {
          setReqStatus("Loading file…");
          var plain = (await readTextFileAsUtf8(file)).trim();
          if (!plain) {
            setReqStatus("File is empty.", "error");
            return;
          }
          if (requirementsText) {
            requirementsText.value = plain;
            autosizeReqTextarea();
          }
          setReqStatus("Brief loaded — press send to apply settings.", "success");
          return;
        }

        setReqStatus("Extracting text from brief…");
        var fd = new FormData();
        fd.append("file", file);
        var res = await fetch("/api/extract-brief-text", { method: "POST", body: fd });
        var data = {};
        try {
          data = await res.json();
        } catch (e2) {
          setReqStatus("Invalid response from server.", "error");
          return;
        }
        if (!res.ok) {
          setReqStatus(data.error || "Could not extract text from brief.", "error");
          return;
        }
        var extracted = (data.text || "").trim();
        if (!extracted) {
          setReqStatus("No text could be extracted from this file.", "error");
          return;
        }
        if (requirementsText) {
          requirementsText.value = data.text || "";
          autosizeReqTextarea();
        }
        setReqStatus("Brief loaded — press send to apply settings.", "success");
      } catch (err) {
        setReqStatus("Could not read file.", "error");
      } finally {
        requirementsAttachBtn.disabled = false;
        requirementsAttach.value = "";
      }
    });
  }

  if (analyzeBtn) {
    analyzeBtn.addEventListener("click", async function () {
      var t = (requirementsText && requirementsText.value.trim()) || "";
      setReqStatus("");
      if (!t) {
        setReqStatus("Type instructions, attach an image or .txt, then send.", "error");
        return;
      }
      analyzeBtn.disabled = true;
      setReqStatus("Applying settings…");
      try {
        var res = await fetch("/parse-requirements", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ text: t }),
        });
        var data = {};
        try {
          data = await res.json();
        } catch (e2) {
          setReqStatus("Invalid response from server.", "error");
          return;
        }
        if (!res.ok) {
          setReqStatus(data.error || "Request failed.", "error");
          return;
        }
        var basePreset = presetKeyFromCitation(data.requirements || {});
        applyPreset(basePreset);
        applyParsedForm(data.form);
        persistCitationStyleFromRequirements(data.requirements || {});
        setPresetChipActiveOnly(basePreset);
        setReqStatus("Formatting settings applied successfully", "success");
      } catch (err) {
        setReqStatus("Network or server error.", "error");
      } finally {
        analyzeBtn.disabled = false;
      }
    });
  }

  var formatBtn = $("format_btn");
  var formatStatusEl = $("format_status");

  formatBtn.addEventListener("click", function () {
    FC.formatDocument({
      fileInputId: "file",
      pastedInputId: "pasted_text",
      formatBtn: formatBtn,
      statusEl: formatStatusEl,
    });
  });
})();
