/**
 * Check page: requirements + text/docx → report (validations, action plan, AI review).
 */
(function () {
  var $ = function (id) {
    return document.getElementById(id);
  };

  var CR = window.CheckReport || {};

  var requirementsInput = $("check_requirements");
  var requirementsFileInput = $("check_requirements_file");
  var pastedInput = $("check_pasted_text");
  var fileInput = $("check_file");
  var docTypeSelect = $("check_doc_type");
  var checkBtn = $("check_document_btn");
  var statusEl = $("check_status");
  var resultsWrap = $("check_results");
  var reportBody = $("check_report_body");
  var emptyReport = $("check_empty_report");
  var emptyReportText = $("check_empty_report_text");
  var scorePanel = $("check_score_panel");
  var notEnoughPanel = $("check_not_enough_panel");
  var notEnoughTitle = $("check_not_enough_title");
  var notEnoughText = $("check_not_enough_text");
  var notEnoughActions = $("check_not_enough_actions");
  var documentSourceEl = $("check_document_source");
  var scoreValue = $("check_score_value");
  var scoreRing = $("check_score_ring");
  var verdictEl = $("check_verdict");
  var coverageLine = $("check_coverage_line");
  var whatsMissingEl = $("check_whats_missing");
  var notCheckedList = $("check_not_checked_list");
  var notCheckedCard = $("check_not_checked_card");
  var actionPlanEl = $("check_action_plan");
  var aiSummaryEl = $("check_ai_summary");
  var aiRisksEl = $("check_ai_risks");
  var detectedCard = $("detected_requirements_card");
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

  function hasRequirementInput() {
    var text = (requirementsInput && requirementsInput.value.trim()) || "";
    var file = requirementsFileInput && requirementsFileInput.files && requirementsFileInput.files[0];
    return !!(text || file);
  }

  function hasDocxInput() {
    var file = fileInput && fileInput.files && fileInput.files[0];
    if (!file) {
      return false;
    }
    return /\.docx$/i.test(file.name || "");
  }

  function scrollToBrief() {
    if (requirementsInput) {
      requirementsInput.focus();
      requirementsInput.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function scrollToDocx() {
    if (fileInput) {
      fileInput.focus();
      fileInput.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }

  function bindGotoButtons() {
    [
      ["check_goto_brief_btn", scrollToBrief],
      ["check_empty_goto_brief", scrollToBrief],
      ["check_goto_docx_btn", scrollToDocx],
      ["check_empty_goto_docx", scrollToDocx],
    ].forEach(function (pair) {
      var el = $(pair[0]);
      if (el) {
        el.addEventListener("click", pair[1]);
      }
    });
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
    var total = detectedRows(req).length;
    if (detectedSummary) {
      detectedSummary.textContent = n
        ? n + " of " + total + " requirements found in your brief"
        : "No requirements were found in your brief.";
    }
    if (applyDetectedBtn) {
      applyDetectedBtn.disabled = !form || !Object.keys(form).length;
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

  function renderLowCoverageActions(actions) {
    if (!notEnoughActions) {
      return;
    }
    notEnoughActions.innerHTML = "";
    (actions || []).forEach(function (action) {
      if (!action) {
        return;
      }
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-secondary";
      btn.textContent = action.label || "Continue";
      btn.addEventListener("click", function () {
        if (action.action === "upload_docx") {
          scrollToDocx();
        } else {
          scrollToBrief();
        }
      });
      notEnoughActions.appendChild(btn);
    });
  }

  function renderDocumentSource(data) {
    if (!documentSourceEl) {
      return;
    }
    var source = (data.meta && data.meta.document_source) || {};
    documentSourceEl.textContent = source.label || "";
    documentSourceEl.classList.toggle("hidden", !source.label);
  }

  function renderState(data, hasBrief, hasDocx) {
    var weight = Number(data.applicable_weight) || 0;
    var wordCount = Number((data.meta && data.meta.word_count) || 0);
    var enough = CR.hasEnoughCoverage ? CR.hasEnoughCoverage(weight) : weight >= 50;

    if (scorePanel) {
      scorePanel.classList.toggle("hidden", !enough);
    }
    if (notEnoughPanel) {
      notEnoughPanel.classList.toggle("hidden", enough);
    }

    if (enough) {
      updateScoreRing(data.score);
      if (verdictEl) {
        verdictEl.textContent = data.verdict || "—";
        verdictEl.className = "check-verdict " + verdictClass(data.verdict);
      }
      if (coverageLine) {
        coverageLine.textContent = CR.formatCoverageLine
          ? CR.formatCoverageLine(data.score, data.checks_applied, data.not_checked)
          : String(data.score) + " / 100";
      }
    } else {
      var state = CR.resolveLowCoverageState
        ? CR.resolveLowCoverageState({ hasBrief: hasBrief, hasDocx: hasDocx, wordCount: wordCount })
        : {
            title: "Limited checks so far",
            message: "Add your assignment brief and upload a .docx to run a fuller check.",
            actions: [],
          };
      if (notEnoughTitle) {
        notEnoughTitle.textContent = state.title || "Limited checks so far";
      }
      if (notEnoughText) {
        notEnoughText.textContent = state.message || "";
      }
      renderLowCoverageActions(state.actions || []);
    }
  }

  function renderWhatsMissing(validations) {
    if (!whatsMissingEl) {
      return;
    }
    whatsMissingEl.innerHTML = "";
    var items = CR.sortMissingValidations ? CR.sortMissingValidations(validations) : [];
    if (!items.length) {
      var clear = document.createElement("p");
      clear.className = "check-all-clear";
      clear.textContent = "No failed checks — requirements look met for the checks we ran.";
      whatsMissingEl.appendChild(clear);
      return;
    }
    items.forEach(function (v) {
      var row = document.createElement("article");
      row.className = "check-missing-row";
      var head = document.createElement("div");
      head.className = "check-missing-head";
      var title = document.createElement("h4");
      title.className = "check-missing-title";
      title.textContent = v.label || v.id || "Requirement";
      var badge = document.createElement("span");
      badge.className = "check-missing-badge status-" + String(v.status || "fail").toLowerCase();
      badge.textContent = CR.formatStatusLabel ? CR.formatStatusLabel(v.status) : v.status;
      head.appendChild(title);
      head.appendChild(badge);
      var summary = document.createElement("p");
      summary.className = "check-missing-summary";
      var summaryText = CR.formatValidationSummary ? CR.formatValidationSummary(v) : "";
      if (summaryText) {
        summary.textContent = summaryText;
        row.appendChild(head);
        row.appendChild(summary);
      } else {
        row.appendChild(head);
      }
      if (v.id === "formatting" && CR.formattingDetailLines) {
        var fmtLines = CR.formattingDetailLines(v);
        if (fmtLines.length) {
          var fmtUl = document.createElement("ul");
          fmtUl.className = "check-formatting-lines";
          fmtLines.forEach(function (line) {
            var li = document.createElement("li");
            li.textContent = line;
            fmtUl.appendChild(li);
          });
          row.appendChild(fmtUl);
        }
      }
      if (v.details && v.details.checklist && v.details.checklist.length) {
        var ul = document.createElement("ul");
        ul.className = "check-section-checklist";
        v.details.checklist.forEach(function (item) {
          var li = document.createElement("li");
          li.className = item.present ? "is-ok" : "is-miss";
          li.textContent = (item.present ? "✓ " : "✗ ") + (item.section || "Section");
          ul.appendChild(li);
        });
        row.appendChild(ul);
      }
      if (v.details && v.details.mismatches && v.details.mismatches.length) {
        var misUl = document.createElement("ul");
        misUl.className = "check-citation-mismatches";
        v.details.mismatches.forEach(function (item) {
          var li = document.createElement("li");
          li.textContent = String(item);
          misUl.appendChild(li);
        });
        row.appendChild(misUl);
      }
      if (v.fix) {
        var fix = document.createElement("p");
        fix.className = "check-missing-fix";
        fix.textContent = v.fix;
        row.appendChild(fix);
      }
      whatsMissingEl.appendChild(row);
    });
  }

  function renderNotChecked(notChecked) {
    if (!notCheckedList) {
      return;
    }
    notCheckedList.innerHTML = "";
    var items = notChecked || [];
    if (notCheckedCard) {
      notCheckedCard.classList.toggle("hidden", !items.length);
    }
    if (!items.length) {
      return;
    }
    items.forEach(function (item) {
      if (!item) {
        return;
      }
      var li = document.createElement("li");
      li.className = "check-not-checked-item";
      var main = document.createElement("div");
      main.className = "check-not-checked-main";
      var label = document.createElement("span");
      label.className = "check-not-checked-label";
      label.textContent = item.id ? String(item.id).replace(/_/g, " ") : "Check";
      var reason = document.createElement("span");
      reason.className = "check-not-checked-reason";
      reason.textContent = item.reason || "Not run";
      main.appendChild(label);
      main.appendChild(reason);
      li.appendChild(main);
      var actionMeta = CR.notCheckedAction ? CR.notCheckedAction(item.reason) : { action: "add_brief", label: "Add requirements" };
      var btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn-secondary check-not-checked-btn";
      btn.textContent = actionMeta.label;
      btn.setAttribute("data-not-checked-action", actionMeta.action);
      btn.addEventListener("click", function () {
        if (actionMeta.action === "upload_docx") {
          scrollToDocx();
        } else {
          scrollToBrief();
        }
      });
      li.appendChild(btn);
      notCheckedList.appendChild(li);
    });
  }

  function renderActionPlan(plan) {
    if (!actionPlanEl) {
      return;
    }
    actionPlanEl.innerHTML = "";
    if (!plan || !plan.length) {
      var empty = document.createElement("p");
      empty.className = "card-hint";
      empty.textContent = "No action steps — requirements appear met for the checks we ran.";
      actionPlanEl.appendChild(empty);
      return;
    }
    plan.forEach(function (step) {
      if (!step) {
        return;
      }
      var block = document.createElement("article");
      block.className = "check-action-step" + (step.priority === "critical" ? " is-critical" : "");
      var title = document.createElement("p");
      title.className = "check-action-step-title";
      title.textContent = "Step " + (step.step_number || "—") + ": " + (step.title || "Fix");
      var action = document.createElement("p");
      action.textContent = step.action || "";
      var meta = document.createElement("p");
      meta.className = "check-action-step-meta";
      meta.textContent = "Could improve score by about +" + (step.estimated_improvement || 0) + " points";
      block.appendChild(title);
      block.appendChild(action);
      block.appendChild(meta);
      actionPlanEl.appendChild(block);
    });
  }

  function renderAiReview(data) {
    var compliance = (data.meta && data.meta.compliance_analysis) || {};
    if (aiSummaryEl) {
      aiSummaryEl.textContent = compliance.summary || "No AI summary available.";
    }
    renderBulletList(aiRisksEl, compliance.major_risks || [], "No major risks flagged.");
  }

  function renderCheckResults(data, opts) {
    opts = opts || {};
    var hasBrief = opts.hasBrief != null ? opts.hasBrief : hasRequirementInput();
    var hasDocx = opts.hasDocx != null ? opts.hasDocx : hasDocxInput();

    if (resultsWrap) {
      resultsWrap.classList.remove("hidden");
    }

    var empty = CR.isEmptyReport ? CR.isEmptyReport(data) : false;
    if (emptyReport) {
      emptyReport.classList.toggle("hidden", !empty);
    }
    if (reportBody) {
      reportBody.classList.toggle("hidden", empty);
    }
    if (empty && emptyReportText) {
      emptyReportText.textContent =
        "We couldn't run any checks on this input. Paste your assignment brief and full document text (or upload a .docx), then run Check again.";
      return;
    }

    renderDocumentSource(data);
    renderState(data, hasBrief, hasDocx);
    renderWhatsMissing(data.validations || []);
    renderNotChecked(data.not_checked || []);
    renderActionPlan(data.action_plan || []);
    renderAiReview(data);
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
      fillPasted: false,
    });
  }

  bindGotoButtons();

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
      }

      if (!pasted && !file) {
        setStatus("Requirements detected. Paste your document text or upload a .docx or .pdf file to run the check.", "success");
        return;
      }

      setStatus("Checking your document…");
      var fd = new FormData();
      fd.append("requirements", requirements);
      fd.append("document_type", docType);
      if (file) {
        fd.append("file", file);
        fd.append("pasted_text", "");
      } else {
        fd.append("pasted_text", pastedInput ? pastedInput.value : "");
      }
      if (extractedData && extractedData.requirements) {
        fd.append("parsed_requirements", JSON.stringify(extractedData.requirements));
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

      renderCheckResults(data, {
        hasBrief: !!(requirements || requirementsFile),
        hasDocx: !!(file && /\.docx$/i.test(file.name || "")),
      });

      setStatus("Check complete — scroll down for details.", "success");
      if (resultsWrap) {
        resultsWrap.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      if (window.DMToolHistory) {
        var reqText = (requirementsInput && requirementsInput.value) || "";
        var docText = (pastedInput && pastedInput.value) || "";
        window.DMToolHistory.push("check", {
          title: window.DMToolHistory.titleFromText(
            docText || reqText,
            "Check · score " + (Number(data.score) || 0)
          ),
          payload: {
            requirements: reqText,
            pasted_text: docText,
            document_type: docType,
            result: data,
          },
        });
        if (window.DM_refreshToolHistory) window.DM_refreshToolHistory();
      }
    } catch (err) {
      setStatus((err && err.message) || "Network error. Please try again.", "error");
      hideResults();
    } finally {
      checkBtn.disabled = false;
    }
  });

  (function restoreCheckHistory() {
    if (!window.DMToolHistory) return;
    var hid = window.DMToolHistory.historyParam();
    if (!hid) return;
    var item = window.DMToolHistory.get("check", hid);
    if (!item || !item.payload) return;
    var p = item.payload;
    if (requirementsInput && p.requirements != null) requirementsInput.value = p.requirements;
    if (pastedInput && p.pasted_text != null) pastedInput.value = p.pasted_text;
    if (docTypeSelect && p.document_type) docTypeSelect.value = p.document_type;
    var data = p.result;
    if (!data) return;
    renderCheckResults(data, { hasBrief: !!(p.requirements || "").trim() });
    setStatus("Restored from history.", "success");
  })();
})();
