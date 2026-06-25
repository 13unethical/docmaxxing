/**
 * Templates page: upload/paste → select type → apply preset → preview → download.
 */
(function () {
  var FC = window.FormatterCommon;
  var AT = window.AssignmentTemplates;
  var DP = window.DocPreview;
  var UI = window.AppUI;

  if (!FC || !AT) {
    return;
  }

  var $ = function (id) {
    return document.getElementById(id);
  };

  var fileInput = $("tpl_file");
  var pastedInput = $("tpl_pasted_text");
  var templateSelect = $("template_select");
  var applyBtn = $("apply_template_btn");
  var formatBtn = $("tpl_format_btn");
  var formatStatus = $("tpl_format_status");
  var previewSection = $("template_preview_section");
  var previewHint = $("template_preview_hint");
  var settingsSection = $("templates_settings_section");
  var detailsEl = $("template_details");
  var detailsBody = $("template_details_body");
  var activeBadge = $("templates_active_badge");

  var appliedTemplate = null;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function populateTemplateSelect() {
    if (!templateSelect) {
      return;
    }
    AT.list.forEach(function (tpl) {
      var opt = document.createElement("option");
      opt.value = tpl.id;
      opt.textContent = tpl.name;
      templateSelect.appendChild(opt);
    });
  }

  function selectedTemplate() {
    if (!templateSelect || !templateSelect.value) {
      return null;
    }
    return AT.getById(templateSelect.value);
  }

  function hasDocumentInput() {
    var file = fileInput && fileInput.files && fileInput.files[0];
    var pasted = pastedInput && pastedInput.value.trim();
    return !!(file || pasted);
  }

  function previewText() {
    if (pastedInput && pastedInput.value.trim()) {
      return pastedInput.value.trim();
    }
    return DP ? DP.SAMPLE : "";
  }

  function updateApplyButtonState() {
    if (!applyBtn) {
      return;
    }
    applyBtn.disabled = !templateSelect || !templateSelect.value;
  }

  function updateFormatButtonState() {
    if (!formatBtn) {
      return;
    }
    formatBtn.disabled = !appliedTemplate || !hasDocumentInput();
  }

  function setActiveBadge(tpl) {
    if (!activeBadge) {
      return;
    }
    if (tpl && tpl.name) {
      activeBadge.textContent = "Active template: " + tpl.name;
      activeBadge.classList.remove("hidden");
    } else {
      activeBadge.textContent = "";
      activeBadge.classList.add("hidden");
    }
  }

  function renderTemplateDetails(tpl) {
    if (!detailsBody) {
      return;
    }
    if (!tpl) {
      detailsBody.innerHTML = "";
      if (detailsEl) {
        detailsEl.open = false;
      }
      return;
    }
    var sections =
      tpl.sections && tpl.sections.length
        ? "<ul class=\"template-sections\">" +
          tpl.sections
            .map(function (s) {
              return "<li>" + escapeHtml(s) + "</li>";
            })
            .join("") +
          "</ul>"
        : "";
    detailsBody.innerHTML =
      "<p class=\"template-card-desc\">" +
      escapeHtml(tpl.description) +
      "</p>" +
      "<dl class=\"template-meta\">" +
      "<div><dt>Spacing</dt><dd>" +
      escapeHtml(tpl.spacing) +
      "</dd></div>" +
      "<div><dt>Citation</dt><dd>" +
      escapeHtml(tpl.citationStyle) +
      "</dd></div>" +
      "<div><dt>Font</dt><dd>" +
      escapeHtml(tpl.settings.font_family + ", " + tpl.settings.font_size + " pt") +
      "</dd></div>" +
      "</dl>" +
      (sections ? "<p class=\"template-sections-label label\">Typical structure</p>" + sections : "");
  }

  function refreshPreview() {
    if (!previewSection || !DP || !appliedTemplate) {
      return;
    }
    previewSection.classList.remove("hidden");
    if (previewHint) {
      previewHint.textContent =
        "Preview for " +
        appliedTemplate.name +
        " — " +
        appliedTemplate.citationStyle +
        ", " +
        appliedTemplate.spacing +
        " spacing.";
    }
    var cfg = FC.getFormatterConfigFromDom();
    cfg.citationStyle = appliedTemplate.citationStyle;
    DP.renderPreviewPair(previewSection, previewText(), cfg);
  }

  function applySelectedTemplate() {
    var tpl = selectedTemplate();
    if (!tpl) {
      if (UI) {
        UI.showToast("Choose an assignment type first", "error");
      }
      return;
    }
    FC.applyTemplate(tpl, { toast: true });
    appliedTemplate = tpl;
    setActiveBadge(tpl);
    renderTemplateDetails(tpl);
    if (settingsSection) {
      settingsSection.classList.remove("hidden");
    }
    refreshPreview();
    updateFormatButtonState();
    if (previewSection) {
      previewSection.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }

  function loadStoredState() {
    var stored = FC.loadStoredFormatterSettings();
    if (stored) {
      FC.applyFormatterConfig(stored);
    }
    var meta = FC.getActiveTemplateMeta();
    if (meta && meta.id && templateSelect) {
      templateSelect.value = meta.id;
      appliedTemplate = AT.getById(meta.id);
      if (appliedTemplate) {
        setActiveBadge(appliedTemplate);
        renderTemplateDetails(appliedTemplate);
        if (settingsSection) {
          settingsSection.classList.remove("hidden");
        }
        refreshPreview();
      }
    }
    updateApplyButtonState();
    updateFormatButtonState();
  }

  populateTemplateSelect();
  FC.bindHomeSettingsAutosave();
  loadStoredState();

  if (templateSelect) {
    templateSelect.addEventListener("change", function () {
      renderTemplateDetails(selectedTemplate());
      updateApplyButtonState();
    });
  }

  if (applyBtn) {
    applyBtn.addEventListener("click", applySelectedTemplate);
  }

  if (fileInput) {
    fileInput.addEventListener("change", function () {
      updateFormatButtonState();
      if (appliedTemplate) {
        refreshPreview();
      }
    });
  }

  if (FC && FC.bindDocumentUploadExtract) {
    FC.bindDocumentUploadExtract("tpl_file", "tpl_pasted_text", {
      statusEl: formatStatus,
      onExtracted: function () {
        updateFormatButtonState();
        if (appliedTemplate) {
          refreshPreview();
        }
      },
    });
  }

  if (pastedInput) {
    pastedInput.addEventListener("input", function () {
      updateFormatButtonState();
      if (appliedTemplate) {
        refreshPreview();
      }
    });
  }

  [
    "font_family",
    "font_size",
    "line_spacing",
    "alignment",
    "margin_preset",
    "page_number_position",
    "first_line_indent",
    "auto_headings",
  ].forEach(function (id) {
    var el = $(id);
    if (el) {
      el.addEventListener("change", function () {
        if (appliedTemplate) {
          refreshPreview();
        }
      });
    }
  });

  if (formatBtn) {
    formatBtn.addEventListener("click", function () {
      if (!appliedTemplate) {
        if (UI) {
          UI.showToast("Apply a template first", "error");
        }
        return;
      }
      FC.formatDocument({
        fileInputId: "tpl_file",
        pastedInputId: "tpl_pasted_text",
        formatBtn: formatBtn,
        statusEl: formatStatus,
      });
    });
  }
})();
