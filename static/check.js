/**
 * Check page: requirements + text/docx → score, categories, issue cards.
 */
(function () {
  var $ = function (id) {
    return document.getElementById(id);
  };

  var requirementsInput = $("check_requirements");
  var requirementsFileInput = $("check_requirements_file");
  var pastedInput = $("check_pasted_text");
  var fileInput = $("check_file");
  var docTypeSelect = $("check_doc_type");
  var checkBtn = $("check_document_btn");
  var statusEl = $("check_status");
  var resultsWrap = $("check_results");
  var topProblems = $("check_top_problems");
  var fixFirst = $("check_fix_first");
  var scoreValue = $("check_score_value");
  var scoreRing = $("check_score_ring");
  var verdictEl = $("check_verdict");
  var summaryEl = $("check_summary");
  var complianceText = $("check_compliance_text");
  var complianceList = $("check_compliance_list");
  var citationList = $("check_citation_list");
  var categoriesList = $("check_categories_list");
  var positivesList = $("check_positives_list");
  var needsList = $("check_needs_list");
  var issuesList = $("check_issues_list");
  var nextSteps = $("check_next_steps");
  var structureHealthScore = $("structure_health_score");
  var structureDetectedSections = $("structure_detected_sections");
  var structureMissingSections = $("structure_missing_sections");
  var structureParagraphIssues = $("structure_paragraph_issues");
  var structureHeadingIssues = $("structure_heading_issues");
  var structureSuggestions = $("structure_suggestions");
  var structureRecoveryMeta = $("structure_recovery_meta");
  var structureTree = $("structure_tree");
  var detectedCard = $("detected_requirements_card");
  var parserEmpty = $("check_parser_empty");
  var detectedSummary = $("detected_requirements_summary");
  var detectedList = $("detected_requirements_list");
  var applyDetectedBtn = $("apply_detected_requirements_btn");
  var detectedPayload = null;

  var RING_C = 2 * Math.PI * 52;

  function setStatus(msg, kind) {
    if (!statusEl) {
      return;
    }
    statusEl.textContent = msg || "";
    statusEl.className = "req-status" + (kind ? " " + kind : "");
  }

  function hideResults() {
    if (resultsWrap) {
      resultsWrap.classList.add("hidden");
    }
  }

  function clearTopSummary() {
    renderBulletList(topProblems, [], "Top issues will appear after analysis.");
    renderBulletList(fixFirst, [], "Action plan will appear after analysis.");
  }

  function hasRequirementInput() {
    var text = (requirementsInput && requirementsInput.value.trim()) || "";
    var file = requirementsFileInput && requirementsFileInput.files && requirementsFileInput.files[0];
    return !!(text || file);
  }

  function formatDetectedValue(value) {
    if (value == null || value === "" || (Array.isArray(value) && !value.length)) {
      return "Not detected";
    }
    if (typeof value === "boolean") {
      return value ? "Required" : "Not required";
    }
    if (Array.isArray(value)) {
      return value.join(", ");
    }
    if (typeof value === "number") {
      return String(value);
    }
    return String(value);
  }

  function detectedRows(req) {
    var r = req || {};
    return [
      ["Citation style", r.citation_style],
      ["Font family", r.font_family],
      ["Font size", r.font_size ? r.font_size + " pt" : null],
      ["Line spacing", r.spacing != null ? r.spacing : r.line_spacing],
      ["Margins", r.margins],
      ["Word count", r.word_count],
      ["Required sections", r.required_sections],
      ["Cover page", r.cover_page_required],
      ["Page numbers", r.page_numbers_required],
      ["References", r.references_required],
      ["Submission format", r.submission_format],
    ];
  }

  function countDetected(req) {
    return detectedRows(req).filter(function (row) {
      var v = row[1];
      return !(v == null || v === "" || (Array.isArray(v) && !v.length));
    }).length;
  }

  function renderDetectedRequirements(req, form) {
    detectedPayload = { requirements: req || {}, form: form || {} };
    if (!detectedCard || !detectedList) {
      return;
    }
    detectedCard.classList.remove("hidden");
    detectedList.innerHTML = "";
    detectedRows(req).forEach(function (row) {
      var dt = document.createElement("dt");
      var dd = document.createElement("dd");
      dt.textContent = row[0];
      dd.textContent = formatDetectedValue(row[1]);
      if (dd.textContent === "Not detected") {
        dd.className = "is-muted";
      }
      detectedList.appendChild(dt);
      detectedList.appendChild(dd);
    });
    var n = countDetected(req);
    var confidence = Number(req && req.confidence_score);
    var confidenceText = Number.isFinite(confidence) ? " · confidence " + Math.round(confidence * 100) + "%" : "";
    if (detectedSummary) {
      detectedSummary.textContent = n
        ? n + " formatting requirement" + (n === 1 ? "" : "s") + " detected" + confidenceText + "."
        : "No formatting-specific requirements were detected. The parser ignored unrelated rubric/policy content.";
    }
    if (applyDetectedBtn) {
      applyDetectedBtn.disabled = !form || !Object.keys(form).length;
    }
    if (parserEmpty) {
      parserEmpty.classList.add("hidden");
    }
  }

  async function extractRequirementsIfPresent() {
    if (!hasRequirementInput()) {
      return null;
    }
    var reqFile = requirementsFileInput && requirementsFileInput.files && requirementsFileInput.files[0];
    if (reqFile) {
      var lower = (reqFile.name || "").toLowerCase();
      if (!/\.(docx|pdf|txt|md|jpe?g|png)$/i.test(lower)) {
        throw new Error("Use DOCX, PDF, TXT, MD, JPG, or PNG for the requirements brief.");
      }
    }
    var fd = new FormData();
    fd.append("requirements_text", requirementsInput ? requirementsInput.value : "");
    if (reqFile) {
      fd.append("file", reqFile);
    }
    var res = await fetch("/api/extract-requirements", { method: "POST", body: fd });
    var data = {};
    try {
      data = await res.json();
    } catch (e) {
      throw new Error("Invalid requirements parser response.");
    }
    if (!res.ok) {
      throw new Error(data.error || "Could not extract requirements.");
    }
    renderDetectedRequirements(data.requirements || {}, data.form || {});
    return data;
  }

  function verdictClass(verdict) {
    var v = (verdict || "").toLowerCase();
    if (v === "excellent") {
      return "verdict-excellent";
    }
    if (v === "good") {
      return "verdict-good";
    }
    if (v === "needs improvement") {
      return "verdict-needs";
    }
    return "verdict-major";
  }

  function updateScoreRing(score) {
    if (!scoreRing || !scoreValue) {
      return;
    }
    var s = Math.max(0, Math.min(100, Number(score) || 0));
    scoreValue.textContent = String(s);
    var offset = RING_C * (1 - s / 100);
    scoreRing.style.strokeDasharray = RING_C + " " + RING_C;
    scoreRing.style.strokeDashoffset = String(offset);
    scoreRing.classList.remove("score-high", "score-mid", "score-low");
    if (s >= 75) {
      scoreRing.classList.add("score-high");
    } else if (s >= 55) {
      scoreRing.classList.add("score-mid");
    } else {
      scoreRing.classList.add("score-low");
    }
  }

  function renderCategories(categories) {
    if (!categoriesList) {
      return;
    }
    categoriesList.innerHTML = "";
    var entries = categories && typeof categories === "object" ? Object.keys(categories) : [];
    entries.forEach(function (key) {
      var cat = categories[key];
      if (!cat) {
        return;
      }
      var li = document.createElement("li");
      li.className = "check-category-item";
      var label = document.createElement("span");
      label.className = "check-category-label";
      label.textContent = cat.label || key;
      var barWrap = document.createElement("div");
      barWrap.className = "check-category-bar-wrap";
      var bar = document.createElement("div");
      bar.className = "check-category-bar";
      var sc = Math.max(0, Math.min(100, Number(cat.score) || 0));
      bar.style.width = sc + "%";
      if (sc >= 75) {
        bar.classList.add("bar-high");
      } else if (sc >= 55) {
        bar.classList.add("bar-mid");
      } else {
        bar.classList.add("bar-low");
      }
      var scoreSpan = document.createElement("span");
      scoreSpan.className = "check-category-score";
      scoreSpan.textContent = sc;
      barWrap.appendChild(bar);
      li.appendChild(label);
      li.appendChild(barWrap);
      li.appendChild(scoreSpan);
      categoriesList.appendChild(li);
    });
  }

  function renderBulletList(el, items, emptyText) {
    if (!el) {
      return;
    }
    el.innerHTML = "";
    var list = (items || []).filter(Boolean);
    if (!list.length) {
      var li = document.createElement("li");
      li.className = "check-empty-item";
      li.textContent = emptyText || "Nothing to show.";
      el.appendChild(li);
      return;
    }
    list.forEach(function (text) {
      var li = document.createElement("li");
      li.textContent = String(text);
      el.appendChild(li);
    });
  }

  function pickMainProblems(data) {
    var out = [];
    var issues = Array.isArray(data.issues) ? data.issues : [];
    issues
      .slice()
      .sort(function (a, b) {
        var aw = a && a.severity === "high" ? 2 : a && a.severity === "medium" ? 1 : 0;
        var bw = b && b.severity === "high" ? 2 : b && b.severity === "medium" ? 1 : 0;
        return bw - aw;
      })
      .forEach(function (item) {
        if (out.length >= 3 || !item) {
          return;
        }
        var msg = item.title || item.message;
        if (msg && out.indexOf(msg) === -1) {
          out.push(msg);
        }
      });
    (data.needs_work || []).forEach(function (item) {
      if (out.length >= 3) {
        return;
      }
      if (item && out.indexOf(item) === -1) {
        out.push(item);
      }
    });
    return out.slice(0, 3);
  }

  function renderCitationAndCompliance(data) {
    var parsed = (data.meta && data.meta.parsed_requirements) || {};
    var citeStyle = parsed.citation_style || "Not detected";
    var citationNotes = [];
    var issues = (data.issues || []).filter(function (issue) {
      var txt = [issue.title || "", issue.message || "", issue.fix || ""].join(" ").toLowerCase();
      return txt.indexOf("citation") !== -1 || txt.indexOf("reference") !== -1 || txt.indexOf("apa") !== -1 || txt.indexOf("mla") !== -1 || txt.indexOf("harvard") !== -1;
    });
    citationNotes.push("Required style: " + citeStyle);
    if (issues.length) {
      issues.slice(0, 4).forEach(function (issue) {
        citationNotes.push((issue.title || "Citation issue") + ": " + (issue.fix || issue.message || "Review citation formatting."));
      });
    } else {
      citationNotes.push("No major citation-specific issues were flagged in this pass.");
    }
    renderBulletList(citationList, citationNotes, "No citation notes.");

    if (complianceText) {
      complianceText.textContent = "Overall readiness is " + (data.score || 0) + "/100 (" + (data.verdict || "—") + ").";
    }
    var complianceItems = [];
    var categories = data.categories || {};
    Object.keys(categories).forEach(function (key) {
      var item = categories[key];
      if (!item) {
        return;
      }
      complianceItems.push((item.label || key) + ": " + (item.score || 0) + "/100");
    });
    renderBulletList(complianceList, complianceItems, "No compliance details available.");
  }

  function setupAnalysisTabs() {
    var tabs = document.querySelectorAll(".check-analysis-tab");
    var panels = document.querySelectorAll(".check-analysis-panel");
    if (!tabs.length || !panels.length) {
      return;
    }
    function activate(name) {
      tabs.forEach(function (btn) {
        var isOn = btn.getAttribute("data-analysis-tab") === name;
        btn.classList.toggle("is-active", isOn);
        btn.setAttribute("aria-selected", isOn ? "true" : "false");
      });
      panels.forEach(function (panel) {
        panel.classList.toggle("is-active", panel.getAttribute("data-analysis-panel") === name);
      });
    }
    tabs.forEach(function (btn) {
      btn.addEventListener("click", function () {
        activate(btn.getAttribute("data-analysis-tab"));
      });
    });
    activate("parser");
  }

  function appendStructureEmpty(el, text) {
    if (!el) {
      return;
    }
    var li = document.createElement("li");
    li.className = "structure-empty";
    li.textContent = text;
    el.appendChild(li);
  }

  function renderStructureList(el, items, emptyText, mapper) {
    if (!el) {
      return;
    }
    el.innerHTML = "";
    var list = (items || []).filter(Boolean);
    if (!list.length) {
      appendStructureEmpty(el, emptyText);
      return;
    }
    list.forEach(function (item) {
      var li = document.createElement("li");
      li.textContent = mapper ? mapper(item) : String(item);
      el.appendChild(li);
    });
  }

  function renderStructureAnalysis(data) {
    var analysis = data || {};
    if (structureHealthScore) {
      var score = Math.max(0, Math.min(100, Number(analysis.health_score) || 0));
      structureHealthScore.textContent = String(score);
      structureHealthScore.parentElement.classList.remove("structure-high", "structure-mid", "structure-low");
      if (score >= 80) {
        structureHealthScore.parentElement.classList.add("structure-high");
      } else if (score >= 55) {
        structureHealthScore.parentElement.classList.add("structure-mid");
      } else {
        structureHealthScore.parentElement.classList.add("structure-low");
      }
    }
    if (structureRecoveryMeta) {
      var mode = analysis.recovery_mode || "unknown";
      var docType = analysis.inferred_document_type || "other";
      var typeConf = analysis.document_type_confidence;
      var overall = analysis.overall_confidence;
      var headings = analysis.headings_present ? "Headings preserved" : "Headings reconstructed";
      var parts = [headings, "Mode: " + mode, "Type: " + docType.replace(/_/g, " ")];
      if (typeConf != null) {
        parts.push("Type confidence " + Math.round(Number(typeConf) * 100) + "%");
      }
      if (overall != null) {
        parts.push("Structure confidence " + Math.round(Number(overall) * 100) + "%");
      }
      structureRecoveryMeta.textContent = parts.join(" · ");
    }
    if (structureTree) {
      structureTree.innerHTML = "";
      var tree = analysis.structure_tree || [];
      if (!tree.length) {
        var emptyLi = document.createElement("li");
        emptyLi.textContent = "Run Check to recover document structure.";
        structureTree.appendChild(emptyLi);
      } else {
        tree.forEach(function (node) {
          var li = document.createElement("li");
          var title = document.createElement("span");
          title.className = "structure-tree-title";
          title.textContent = node.title || node.canonical || "Untitled section";
          li.appendChild(title);
          var meta = document.createElement("span");
          meta.className = "structure-tree-meta";
          var metaParts = [];
          if (node.confidence != null) {
            metaParts.push(Math.round(Number(node.confidence) * 100) + "% confidence");
          }
          if (node.paragraph_range && node.paragraph_range[0]) {
            metaParts.push(
              "¶ " + node.paragraph_range[0] + (node.paragraph_range[1] !== node.paragraph_range[0] ? "–" + node.paragraph_range[1] : "")
            );
          }
          if (node.paragraph_count) {
            metaParts.push(node.paragraph_count + " paragraph" + (node.paragraph_count === 1 ? "" : "s"));
          }
          meta.textContent = metaParts.join(" · ");
          li.appendChild(meta);
          structureTree.appendChild(li);
        });
      }
    }
    renderStructureList(
      structureDetectedSections,
      analysis.detected_sections,
      "No clear section headings detected.",
      function (section) {
        var text = section.title || section.canonical || "Untitled section";
        var para = section.paragraph_number ? "Paragraph " + section.paragraph_number : "";
        var style = section.style ? section.style : "";
        return [text, para, style].filter(Boolean).join(" · ");
      }
    );
    renderStructureList(
      structureMissingSections,
      analysis.missing_sections,
      "No missing expected sections detected.",
      function (section) {
        return String(section);
      }
    );
    renderStructureList(
      structureParagraphIssues,
      analysis.paragraph_issues,
      "No paragraph break issues detected.",
      function (issue) {
        return issue.message || issue.suggestion || "Paragraph issue";
      }
    );
    renderStructureList(
      structureHeadingIssues,
      analysis.heading_issues,
      "No heading consistency issues detected.",
      function (issue) {
        return issue.message || issue.suggestion || "Heading issue";
      }
    );
    renderStructureList(
      structureSuggestions,
      analysis.suggestions,
      "No structure restoration suggestions right now.",
      function (item) {
        return String(item);
      }
    );
  }

  function formatLocation(loc) {
    if (!loc || typeof loc !== "object") {
      return "Approximate: throughout document";
    }
    var parts = [];
    if (loc.paragraph_number) {
      parts.push("Paragraph " + loc.paragraph_number);
    }
    if (loc.section) {
      parts.push("Section: " + loc.section);
    }
    if (loc.heading) {
      parts.push("Heading: " + loc.heading);
    }
    if (loc.position) {
      parts.push(loc.position.charAt(0).toUpperCase() + loc.position.slice(1));
    }
    if (loc.snippet) {
      parts.push('"' + loc.snippet + '"');
    }
    return parts.length ? parts.join(" · ") : "Approximate: throughout document";
  }

  function renderIssues(issues) {
    if (!issuesList) {
      return;
    }
    issuesList.innerHTML = "";
    if (!issues || !issues.length) {
      var empty = document.createElement("p");
      empty.className = "check-all-clear";
      empty.textContent = "No issues flagged — great work on these checks.";
      issuesList.appendChild(empty);
      return;
    }
    issues.forEach(function (issue) {
      if (!issue) {
        return;
      }
      var card = document.createElement("article");
      var sev = (issue.severity || "medium").toLowerCase();
      card.className = "check-issue-card severity-" + sev;
      var head = document.createElement("div");
      head.className = "check-issue-head";
      var badge = document.createElement("span");
      badge.className = "check-issue-badge";
      badge.textContent = sev === "high" ? "High" : sev === "low" ? "Low" : "Medium";
      var title = document.createElement("h4");
      title.className = "check-issue-title";
      title.textContent = issue.title || "Issue";
      head.appendChild(badge);
      head.appendChild(title);
      var msg = document.createElement("p");
      msg.className = "check-issue-message";
      msg.textContent = issue.message || "";
      var loc = document.createElement("p");
      loc.className = "check-issue-location";
      loc.textContent = formatLocation(issue.location);
      var fix = document.createElement("p");
      fix.className = "check-issue-fix";
      fix.innerHTML = "<strong>Suggested fix:</strong> " + (issue.fix || "Review and adjust.");
      card.appendChild(head);
      card.appendChild(msg);
      card.appendChild(loc);
      card.appendChild(fix);
      issuesList.appendChild(card);
    });
  }

  function renderNextSteps(steps) {
    if (!nextSteps) {
      return;
    }
    nextSteps.innerHTML = "";
    (steps || []).forEach(function (step) {
      if (!step) {
        return;
      }
      var li = document.createElement("li");
      li.textContent = String(step);
      nextSteps.appendChild(li);
    });
    if (!nextSteps.children.length) {
      var li = document.createElement("li");
      li.textContent = "Review the issue cards above and align your document with the brief.";
      nextSteps.appendChild(li);
    }
  }

  if (applyDetectedBtn) {
    applyDetectedBtn.addEventListener("click", function () {
      if (!detectedPayload || !detectedPayload.form || !Object.keys(detectedPayload.form).length) {
        setStatus("No detected format settings to apply.", "warn");
        return;
      }
      var FC = window.FormatterCommon;
      if (FC) {
        FC.saveFormatterSettingsSnapshot(detectedPayload.form);
        var cite = detectedPayload.requirements && detectedPayload.requirements.citation_style;
        if (cite && ["APA", "MLA", "Harvard", "Chicago", "IEEE", "Vancouver"].indexOf(cite) !== -1) {
          FC.writeStorage(FC.REF_STYLE_KEY, cite);
        }
      }
      window.location.href = "/";
    });
  }

  if (!checkBtn) {
    return;
  }

  var FC = window.FormatterCommon;
  if (FC && FC.bindDocumentUploadExtract) {
    FC.bindDocumentUploadExtract("check_file", "check_pasted_text", {
      statusEl: statusEl,
    });
  }

  setupAnalysisTabs();
  clearTopSummary();

  checkBtn.addEventListener("click", async function () {
    var requirements = (requirementsInput && requirementsInput.value.trim()) || "";
    var requirementsFile = requirementsFileInput && requirementsFileInput.files && requirementsFileInput.files[0];
    var pasted = (pastedInput && pastedInput.value.trim()) || "";
    var file = fileInput && fileInput.files && fileInput.files[0];
    var docType = (docTypeSelect && docTypeSelect.value) || "other";

    if (file && !(FC && FC.isSupportedDocumentFile(file))) {
      setStatus("Please choose a valid .docx or .pdf file.", "error");
      hideResults();
      return;
    }
    if (requirementsFile && !/\.(docx|pdf|txt|md|jpe?g|png)$/i.test(requirementsFile.name || "")) {
      setStatus("Use DOCX, PDF, TXT, MD, JPG, or PNG for the requirements brief.", "error");
      hideResults();
      return;
    }

    hideResults();
    setStatus("");
    checkBtn.disabled = true;
    setStatus(hasRequirementInput() ? "Extracting requirements…" : "Checking your document…");

    try {
      var extractedData = null;
      if (hasRequirementInput()) {
        extractedData = await extractRequirementsIfPresent();
        if (!requirements && extractedData && extractedData.source_text) {
          requirements = String(extractedData.source_text || "");
        }
      } else if (detectedCard) {
        detectedCard.classList.add("hidden");
        if (parserEmpty) {
          parserEmpty.classList.remove("hidden");
        }
      }

      if (!pasted && !file) {
        setStatus("Requirements detected. Paste your document text or upload a .docx or .pdf file to run the check.", "success");
        return;
      }

      setStatus("Checking your document…");
      var fd = new FormData();
      fd.append("requirements", requirements);
      fd.append("pasted_text", pastedInput ? pastedInput.value : "");
      fd.append("document_type", docType);
      if (file) {
        fd.append("file", file);
      }

      var res = await fetch("/api/check-document", { method: "POST", body: fd });
      var data = {};
      try {
        data = await res.json();
      } catch (e2) {
        setStatus("Invalid server response.", "error");
        return;
      }

      if (!res.ok) {
        setStatus(data.error || "Check failed.", "error");
        return;
      }

      if (resultsWrap) {
        resultsWrap.classList.remove("hidden");
      }

      updateScoreRing(data.score);
      if (verdictEl) {
        verdictEl.textContent = data.verdict || "—";
        verdictEl.className = "check-verdict " + verdictClass(data.verdict);
      }
      if (summaryEl) {
        summaryEl.textContent = data.summary || "";
      }

      renderCategories(data.categories);
      renderStructureAnalysis(data.structure_analysis);
      renderBulletList(positivesList, data.positives, "Run Check again after fixes to see strengths.");
      renderBulletList(needsList, data.needs_work, "No major gaps flagged in these categories.");
      renderIssues(data.issues);
      renderNextSteps(data.next_steps);
      renderBulletList(topProblems, pickMainProblems(data), "No critical issues detected.");
      renderBulletList(fixFirst, data.next_steps, "Review the issue cards and adjust your draft.");
      renderCitationAndCompliance(data);

      var score = Number(data.score) || 0;
      var kind = "success";
      if (score < 55) {
        kind = "error";
      } else if (score < 75) {
        kind = "warn";
      }
      setStatus("Check complete — scroll down for details.", kind);
      if (resultsWrap) {
        resultsWrap.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    } catch (err) {
      setStatus((err && err.message) || "Network error. Please try again.", "error");
      hideResults();
    } finally {
      checkBtn.disabled = false;
    }
  });
})();
