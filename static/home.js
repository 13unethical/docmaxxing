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
      format_style: "harvard",
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
      format_style: "apa7",
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
      format_style: "mla9",
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
  var REF_STORAGE_KEY = "academic_formatter_saved_references";
  var CITATION_STORAGE_KEY = "academic_formatter_saved_citations";
  var REF_COUNT_KEY = "academic_formatter_references_count";
  var CITATION_COUNT_KEY = "academic_formatter_citations_count";
  var MAX_REF_ITEMS = 20;

  function applyPreset(name) {
    var cfg = PRESETS[name];
    presetChipButtons().forEach(function (btn) {
      btn.classList.toggle("is-active", btn.getAttribute("data-preset") === name);
    });
    if (!cfg) {
      return;
    }
    FC.applyFormatterConfig(cfg);
    if ($("format_style")) {
      $("format_style").value = cfg.format_style || "harvard";
    }
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
    if (form && form.format_style && $("format_style")) {
      $("format_style").value = String(form.format_style);
    }
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
    syncCitationStyleSelects(v);
  }

  function citationStyleSelects() {
    return document.querySelectorAll("[data-citation-style-select]");
  }

  function syncCitationStyleSelects(value) {
    citationStyleSelects().forEach(function (el) {
      if (Array.prototype.some.call(el.options, function (o) { return o.value === value; })) {
        el.value = value;
      }
    });
  }

  function getSelectedCitationStyle() {
    var selects = citationStyleSelects();
    var i;
    for (i = 0; i < selects.length; i += 1) {
      if (selects[i].value) {
        return selects[i].value;
      }
    }
    return FC.readStorage(REF_STYLE_KEY) || "APA";
  }

  function loadCitationStyleIntoFormat() {
    var selects = citationStyleSelects();
    if (!selects.length) {
      return;
    }
    var stored = FC.readStorage(REF_STYLE_KEY);
    if (stored) {
      syncCitationStyleSelects(stored);
    }
    selects.forEach(function (styleSelect) {
      styleSelect.addEventListener("change", function () {
        FC.writeStorage(REF_STYLE_KEY, styleSelect.value);
        syncCitationStyleSelects(styleSelect.value);
      });
    });
  }

  function setReferencesStatus(message, kind) {
    var el = $("references_status");
    if (!el) {
      return;
    }
    el.textContent = message || "";
    el.className = "format-status status" + (kind ? " " + kind : "");
  }

  function setCitationsStatus(message, kind) {
    var el = $("citations_status");
    if (!el) {
      return;
    }
    el.textContent = message || "";
    el.className = "format-status status" + (kind ? " " + kind : "");
  }

  function clampCount(value, fallback) {
    var n = parseInt(value, 10);
    if (!isFinite(n)) {
      n = fallback;
    }
    if (n < 0) {
      n = 0;
    }
    if (n > MAX_REF_ITEMS) {
      n = MAX_REF_ITEMS;
    }
    return n;
  }

  function readCountInput(id, storageKey, fallback) {
    var el = $(id);
    var stored = FC.readStorage(storageKey);
    var initial = clampCount(el && el.value !== "" ? el.value : stored, fallback);
    if (el) {
      el.value = String(initial);
    }
    return initial;
  }

  function bindCountInput(id, storageKey, fallback) {
    var el = $(id);
    if (!el) {
      return;
    }
    readCountInput(id, storageKey, fallback);
    el.addEventListener("change", function () {
      var n = clampCount(el.value, fallback);
      el.value = String(n);
      FC.writeStorage(storageKey, String(n));
    });
    el.addEventListener("input", function () {
      var raw = el.value;
      if (raw === "") {
        return;
      }
      var n = clampCount(raw, fallback);
      if (String(n) !== raw) {
        el.value = String(n);
      }
    });
  }

  function getReferencesCount() {
    return clampCount(($("references_count") && $("references_count").value) || FC.readStorage(REF_COUNT_KEY), 3);
  }

  function getCitationsCount() {
    return clampCount(($("citations_count") && $("citations_count").value) || FC.readStorage(CITATION_COUNT_KEY), 3);
  }

  function saveGeneratedReferences(list) {
    var capped = (list || []).slice(0, MAX_REF_ITEMS);
    FC.writeStorage(REF_STORAGE_KEY, JSON.stringify(capped));
  }

  function saveGeneratedCitations(list) {
    var capped = (list || []).slice(0, MAX_REF_ITEMS);
    FC.writeStorage(CITATION_STORAGE_KEY, JSON.stringify(capped));
  }

  function renderGeneratedReferences(list) {
    var el = $("references_preview_list");
    if (!el) {
      return;
    }
    var refs = Array.isArray(list) ? list.slice(0, MAX_REF_ITEMS) : [];
    el.innerHTML = "";
    refs.forEach(function (ref) {
      var li = document.createElement("li");
      var span = document.createElement("span");
      span.textContent = ref;
      li.appendChild(span);
      el.appendChild(li);
    });
    el.classList.toggle("hidden", refs.length === 0);
  }

  function renderGeneratedCitations(list) {
    var el = $("citations_preview_list");
    if (!el) {
      return;
    }
    var cites = Array.isArray(list) ? list.slice(0, MAX_REF_ITEMS) : [];
    el.innerHTML = "";
    cites.forEach(function (cite) {
      var li = document.createElement("li");
      var span = document.createElement("span");
      span.textContent = cite;
      li.appendChild(span);
      el.appendChild(li);
    });
    el.classList.toggle("hidden", cites.length === 0);
  }

  function selectedReferenceSource() {
    var node = document.querySelector("input[name='reference_source']:checked");
    return node ? node.value : "none";
  }

  var MOCK_REF_POOL = [
    "Smith, J. (2024). Renewable transition planning in modern grids. Journal of Energy Systems, 14(2), 44-61.",
    "Lopez, M., & Kim, S. (2023). AI-assisted citation generation for academic writing workflows. Computing in Education, 9(4), 201-219.",
    "Chen, L. (2022). Evidence-based writing in higher education. Academic Practice Review, 11(1), 18-36.",
    "Patel, R., & Nguyen, T. (2021). Digital libraries and scholarly discovery. Information Studies Quarterly, 7(3), 90-112.",
    "Brown, A. (2020). Peer review and research integrity. Science Policy Notes, 5(2), 55-70.",
    "Ivanova, K. (2024). Citation density and argument quality in student essays. Writing Research Forum, 16(1), 12-29.",
    "Garcia, P., & Lee, H. (2019). Open access publishing trends. Scholarly Communication Today, 3(4), 140-158.",
    "Williams, D. (2023). Method sections that graders trust. Journal of Academic Skills, 8(2), 77-94.",
    "Ahmed, S. (2021). Cross-disciplinary referencing practices. Interdisciplinary Review, 12(3), 201-220.",
    "Thompson, E., & Rossi, F. (2022). Paraphrase quality and plagiarism risk. Integrity in Learning, 4(1), 33-49.",
    "Nakamura, Y. (2020). Structured abstracts for applied research. Methods Digest, 6(2), 88-101.",
    "Okafor, C. (2024). Local case studies in global literature reviews. Comparative Education Briefs, 10(1), 5-22.",
    "Martin, B. (2018). Footnotes versus parenthetical citations. Style & Rhetoric, 2(3), 41-57.",
    "Silva, R., & Costa, M. (2023). Dataset citation standards. Data Stewardship Journal, 1(2), 15-31.",
    "Hughes, N. (2021). Reading strategies for dense academic sources. Student Learning Review, 9(4), 110-126.",
    "Zhou, W. (2022). Meta-analysis reporting checklists. Quantitative Methods Today, 14(3), 66-84.",
    "Andersson, L. (2019). Nordic approaches to source evaluation. Library Pedagogy, 5(1), 23-39.",
    "Khan, A., & Park, J. (2024). Generative tools and academic honesty. Ethics in Education, 13(2), 150-169.",
    "Diaz, V. (2020). Grey literature in policy essays. Public Policy Writing, 7(1), 8-24.",
    "Foster, G. (2023). Closing the loop between in-text citations and reference lists. Editor Notes, 18(4), 200-214.",
  ];

  var MOCK_CITE_AUTHORS = [
    ["Smith", 2024],
    ["Lopez & Kim", 2023],
    ["Chen", 2022],
    ["Patel & Nguyen", 2021],
    ["Brown", 2020],
    ["Ivanova", 2024],
    ["Garcia & Lee", 2019],
    ["Williams", 2023],
    ["Ahmed", 2021],
    ["Thompson & Rossi", 2022],
    ["Nakamura", 2020],
    ["Okafor", 2024],
    ["Martin", 2018],
    ["Silva & Costa", 2023],
    ["Hughes", 2021],
    ["Zhou", 2022],
    ["Andersson", 2019],
    ["Khan & Park", 2024],
    ["Diaz", 2020],
    ["Foster", 2023],
  ];

  function formatInTextCitation(style, author, year, index) {
    var s = (style || "APA").toUpperCase();
    if (s === "IEEE") {
      return "[" + (index + 1) + "]";
    }
    if (s === "MLA") {
      return "(" + author + ")";
    }
    if (s === "CHICAGO") {
      return "(" + author + " " + year + ")";
    }
    if (s === "HARVARD") {
      return "(" + author + ", " + year + ")";
    }
    return "(" + author + ", " + year + ")";
  }

  function buildMockReferences(style, source, count) {
    var n = clampCount(count, 0);
    var styleLabel = style || "APA";
    var sourceLabel = source || "auto_ai";
    var out = [];
    var i;
    for (i = 0; i < n; i += 1) {
      out.push(MOCK_REF_POOL[i % MOCK_REF_POOL.length]);
    }
    if (n > 0) {
      out[n - 1] =
        out[n - 1].replace(/\.$/, "") +
        " [Source: " +
        sourceLabel +
        " · Style: " +
        styleLabel +
        "].";
    }
    return out;
  }

  function buildMockCitations(style, count) {
    var n = clampCount(count, 0);
    var out = [];
    var i;
    for (i = 0; i < n; i += 1) {
      var pair = MOCK_CITE_AUTHORS[i % MOCK_CITE_AUTHORS.length];
      out.push(formatInTextCitation(style, pair[0], pair[1], i));
    }
    return out;
  }

  function runReferencesWorkflow() {
    var source = selectedReferenceSource();
    var style = getSelectedCitationStyle();
    var refCount = getReferencesCount();
    FC.writeStorage(REF_STYLE_KEY, style);
    FC.writeStorage(REF_COUNT_KEY, String(refCount));
    syncCitationStyleSelects(style);

    if (source === "none") {
      saveGeneratedReferences([]);
      renderGeneratedReferences([]);
      setReferencesStatus("Reference source: None. No references will be generated.", "warn");
      return;
    }

    if (refCount === 0) {
      saveGeneratedReferences([]);
      renderGeneratedReferences([]);
      setReferencesStatus("Set references count (1–20) before generating.", "warn");
      return;
    }

    setReferencesStatus("Building bibliography…");
    var btn = $("generate_references_btn");
    if (btn) {
      btn.disabled = true;
    }

    var steps = [
      "Searching academic sources…",
      "Formatting bibliography entries…",
      "Preparing References section…",
    ];
    var i = 0;
    var timer = setInterval(function () {
      if (i < steps.length) {
        setReferencesStatus(steps[i]);
        i += 1;
        return;
      }
      clearInterval(timer);
      var refs = buildMockReferences(style, source, refCount);
      saveGeneratedReferences(refs);
      renderGeneratedReferences(refs);
      setReferencesStatus("Generated " + refs.length + " reference(s).", "success");
      if (btn) {
        btn.disabled = false;
      }
      if (window.AppUI) {
        window.AppUI.showToast("References generated", "success");
      }
    }, 450);
  }

  function runCitationsWorkflow() {
    var style = getSelectedCitationStyle();
    var citeCount = getCitationsCount();
    FC.writeStorage(REF_STYLE_KEY, style);
    FC.writeStorage(CITATION_COUNT_KEY, String(citeCount));
    syncCitationStyleSelects(style);

    if (citeCount === 0) {
      saveGeneratedCitations([]);
      renderGeneratedCitations([]);
      setCitationsStatus("Set citations count (1–20) before generating.", "warn");
      return;
    }

    setCitationsStatus("Building in-text citations…");
    var btn = $("generate_citations_btn");
    if (btn) {
      btn.disabled = true;
    }

    var steps = [
      "Matching sources to claims…",
      "Formatting in-text citations…",
      "Preparing citation list…",
    ];
    var i = 0;
    var timer = setInterval(function () {
      if (i < steps.length) {
        setCitationsStatus(steps[i]);
        i += 1;
        return;
      }
      clearInterval(timer);
      var cites = buildMockCitations(style, citeCount);
      saveGeneratedCitations(cites);
      renderGeneratedCitations(cites);
      setCitationsStatus("Generated " + cites.length + " citation(s).", "success");
      if (btn) {
        btn.disabled = false;
      }
      if (window.AppUI) {
        window.AppUI.showToast("Citations generated", "success");
      }
    }, 450);
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
    if ($("format_style") && stored.format_style) {
      $("format_style").value = String(stored.format_style);
    }
  } else {
    applyPreset("harvard");
  }

  loadCitationStyleIntoFormat();
  bindCountInput("references_count", REF_COUNT_KEY, 3);
  bindCountInput("citations_count", CITATION_COUNT_KEY, 3);
  try {
    var savedRefs = JSON.parse(FC.readStorage(REF_STORAGE_KEY) || "[]");
    renderGeneratedReferences(Array.isArray(savedRefs) ? savedRefs : []);
  } catch (e) {
    renderGeneratedReferences([]);
  }
  try {
    var savedCites = JSON.parse(FC.readStorage(CITATION_STORAGE_KEY) || "[]");
    renderGeneratedCitations(Array.isArray(savedCites) ? savedCites : []);
  } catch (e2) {
    renderGeneratedCitations([]);
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

  ["font_family", "font_size", "line_spacing", "alignment", "first_line_indent", "auto_headings", "requirement_headings", "heading_size_pt", "citation_style_format"].forEach(
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

  (function bindHomeDocSegment() {
    var card = document.querySelector("[data-home-doc-card]");
    if (!card) {
      return;
    }
    var segment = card.querySelector("[data-home-doc-segment]");
    var sourceBtns = card.querySelectorAll("[data-home-doc-source]");
    var panels = card.querySelectorAll("[data-home-doc-panel]");
    var pasted = $("pasted_text");

    function setDocSource(src) {
      var isUpload = src === "upload";
      if (segment) {
        segment.classList.toggle("is-upload", isUpload);
      }
      sourceBtns.forEach(function (btn) {
        var active = btn.getAttribute("data-home-doc-source") === src;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
      panels.forEach(function (panel) {
        // Upload is file-picker only (no visible panel); keep paste available.
        if (panel.getAttribute("data-home-doc-panel") === "paste") {
          panel.hidden = false;
          return;
        }
        panel.hidden = panel.getAttribute("data-home-doc-panel") !== src;
      });
      if (!isUpload && pasted) {
        pasted.focus();
      }
    }

    sourceBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var src = btn.getAttribute("data-home-doc-source");
        setDocSource(src);
        if (src === "upload") {
          var fileInput = $("file");
          if (fileInput) {
            fileInput.click();
          }
        }
      });
    });
  })();

  var requirementsText = $("requirements_text");
  var requirementsAttach = $("requirements_attach");
  var requirementsAttachBtn = $("requirements_attach_btn");
  var analyzeBtn = $("analyze_requirements_btn");
  var requirementsStatus = $("requirements_status");
  var setBriefSource = null;

  (function bindHomeBriefSegment() {
    var root = document.querySelector("[data-home-brief-card]");
    if (!root) {
      return;
    }
    var segment = root.querySelector("[data-home-brief-segment]");
    var sourceBtns = root.querySelectorAll("[data-home-brief-source]");

    setBriefSource = function (src) {
      var isUpload = src === "upload";
      if (segment) {
        segment.classList.toggle("is-upload", isUpload);
      }
      sourceBtns.forEach(function (btn) {
        var active = btn.getAttribute("data-home-brief-source") === src;
        btn.classList.toggle("is-active", active);
        btn.setAttribute("aria-selected", active ? "true" : "false");
      });
      if (!isUpload && requirementsText) {
        requirementsText.focus();
      }
    };

    sourceBtns.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var src = btn.getAttribute("data-home-brief-source");
        setBriefSource(src);
        if (src === "upload" && requirementsAttach) {
          requirementsAttach.click();
        }
      });
    });
  })();

  function setReqStatus(message, kind) {
    if (!requirementsStatus) {
      return;
    }
    requirementsStatus.textContent = message || "";
    requirementsStatus.className = "req-chat-status req-status" + (kind ? " " + kind : "");
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

      if (requirementsAttachBtn) {
        requirementsAttachBtn.disabled = true;
      }

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
          }
          if (setBriefSource) {
            setBriefSource("paste");
          }
          setReqStatus("Brief loaded into Requirements.", "success");
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
        }
        if (setBriefSource) {
          setBriefSource("paste");
        }
        setReqStatus("Brief loaded into Requirements.", "success");
      } catch (err) {
        setReqStatus("Could not read file.", "error");
      } finally {
        if (requirementsAttachBtn) {
          requirementsAttachBtn.disabled = false;
        }
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
  var workspaceCta = $("home_workspace_cta");

  formatBtn.addEventListener("click", function () {
    FC.formatDocument({
      fileInputId: "file",
      pastedInputId: "pasted_text",
      formatBtn: formatBtn,
      statusEl: formatStatusEl,
      onSuccess: function () {
        var pasted = ($("pasted_text") && $("pasted_text").value) || "";
        if (window.WorkspaceDraft && pasted.trim()) {
          window.WorkspaceDraft.saveFromText(pasted, "Formatted draft");
        } else if (pasted.trim()) {
          try {
            var payload = JSON.stringify({
              text: pasted,
              title: "Formatted draft",
              updatedAt: Date.now(),
            });
            sessionStorage.setItem("docmaxxing_workspace_draft", payload);
            localStorage.setItem("docmaxxing_workspace_draft", payload);
          } catch (e) {
            /* ignore */
          }
        }
        if (workspaceCta) {
          workspaceCta.classList.remove("is-hidden");
        }
      },
    });
  });

  var generateReferencesBtn = $("generate_references_btn");
  if (generateReferencesBtn) {
    generateReferencesBtn.addEventListener("click", runReferencesWorkflow);
  }

  var generateCitationsBtn = $("generate_citations_btn");
  if (generateCitationsBtn) {
    generateCitationsBtn.addEventListener("click", runCitationsWorkflow);
  }
})();
