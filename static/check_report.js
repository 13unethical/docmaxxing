/**
 * Pure helpers for Academic Check report rendering (testable, no DOM).
 */
(function (global) {
  var COVERAGE_THRESHOLD = 50;
  var FRAGMENT_WORD_THRESHOLD = 100;

  function hasEnoughCoverage(applicableWeight) {
    return Number(applicableWeight) >= COVERAGE_THRESHOLD;
  }

  function totalCheckCount(checksApplied, notChecked) {
    var applied = Number(checksApplied) || 0;
    var skipped = Array.isArray(notChecked) ? notChecked.length : 0;
    return applied + skipped;
  }

  function formatCoverageLine(score, checksApplied, notChecked) {
    var total = totalCheckCount(checksApplied, notChecked);
    var applied = Number(checksApplied) || 0;
    var s = Math.max(0, Math.min(100, Number(score) || 0));
    if (total <= 0) {
      return s + " / 100";
    }
    return s + " / 100 · based on " + applied + " of " + total + " checks";
  }

  function pointsLost(v) {
    var possible = Number(v && (v.points_possible != null ? v.points_possible : v.weight)) || 0;
    var earned = Number(v && v.points_earned) || 0;
    return Math.max(0, possible - earned);
  }

  function sortMissingValidations(validations) {
    return (validations || [])
      .filter(function (v) {
        if (!v || !Number(v.weight)) {
          return false;
        }
        var status = String(v.status || "").toUpperCase();
        return status === "FAIL" || status === "PARTIAL" || status === "CANNOT_VERIFY";
      })
      .slice()
      .sort(function (a, b) {
        return pointsLost(b) - pointsLost(a);
      });
  }

  function formatStatusLabel(status) {
    var s = String(status || "").toUpperCase();
    if (s === "NEEDS_CONFIRMATION") {
      return "Can't verify without your .docx";
    }
    if (s === "CANNOT_VERIFY") {
      return "Couldn't verify";
    }
    if (s === "FAIL") {
      return "Not met";
    }
    if (s === "PARTIAL") {
      return "Partly met";
    }
    if (s === "PASS") {
      return "Met";
    }
    return "Unknown";
  }

  function formatFormattingLine(item) {
    if (!item) {
      return "";
    }
    var rawName = String(item.item || "Rule");
    var title =
      rawName === "font"
        ? "Font"
        : rawName === "font size"
          ? "Font size"
          : rawName === "line spacing"
            ? "Line spacing"
            : rawName === "page numbers"
              ? "Page numbers"
              : rawName.charAt(0).toUpperCase() + rawName.slice(1);
    if (item.ok == null) {
      return title + ": can't verify";
    }
    if (item.ok === true) {
      return title + ": " + (item.required || item.detected) + " — matched";
    }
    if (item.ok === false) {
      return title + ": required " + item.required + ", found " + item.detected + " — not matched";
    }
    return title + ": can't verify";
  }

  function formattingDetailLines(v) {
    var items = v && v.details && v.details.items;
    if (!Array.isArray(items) || !items.length) {
      return [];
    }
    return items.map(formatFormattingLine).filter(Boolean);
  }

  function formatValidationSummary(v) {
    if (!v) {
      return "";
    }
    var id = String(v.id || "");
    var detected = String(v.detected || "").trim();
    var required = String(v.required || "").trim();
    var status = String(v.status || "").toUpperCase();

    if (id === "formatting") {
      return "";
    }

    if (status === "NEEDS_CONFIRMATION") {
      return "Can't verify without your .docx";
    }

    if (status === "CANNOT_VERIFY") {
      return detected || "couldn't verify";
    }

    if (id === "sections") {
      var m = detected.match(/^(\d+)\s*\/\s*(\d+)$/);
      if (m) {
        return m[1] + " of " + m[2] + " required sections found";
      }
    }

    if (id === "word_count") {
      if (detected && required) {
        return detected.replace(/,/g, "") + " words · required: " + required;
      }
    }

    if (id === "references") {
      if (detected !== "" && required !== "") {
        return detected + " of " + required + " references found";
      }
    }

    if (id === "in_text_citations") {
      if (detected) {
        return detected;
      }
    }

    if (detected && required) {
      return "Required: " + required + " · Found: " + detected;
    }
    if (detected) {
      return "Found: " + detected;
    }
    if (required) {
      return "Required: " + required;
    }
    return v.label || id || "Requirement";
  }

  function resolveLowCoverageState(opts) {
    opts = opts || {};
    var wordCount = Number(opts.wordCount) || 0;
    var hasBrief = !!opts.hasBrief;
    var hasDocx = !!opts.hasDocx;

    if (wordCount > 0 && wordCount < FRAGMENT_WORD_THRESHOLD) {
      return {
        kind: "fragment",
        title: "Short document",
        message:
          "This looks like a fragment, not a full paper. Paste or upload your complete draft before relying on the readiness score.",
        actions: [],
      };
    }
    if (!hasBrief) {
      return {
        kind: "no_brief",
        title: "Brief needed for readiness score",
        message:
          "Add your assignment brief to get a readiness score. We've checked structure so far.",
        actions: [{ action: "add_brief", label: "Add assignment brief" }],
      };
    }
    if (!hasDocx) {
      return {
        kind: "no_docx",
        title: "Upload .docx for formatting checks",
        message: "Upload your .docx to check formatting (font, spacing, page numbers).",
        actions: [{ action: "upload_docx", label: "Upload .docx" }],
      };
    }
    return {
      kind: "generic",
      title: "Limited checks so far",
      message: "Add your assignment brief and upload a .docx to run a fuller check.",
      actions: [
        { action: "add_brief", label: "Add assignment brief" },
        { action: "upload_docx", label: "Upload .docx" },
      ],
    };
  }

  function notCheckedAction(reason) {
    var r = String(reason || "").toLowerCase();
    if (r.indexOf(".docx") !== -1 || r.indexOf("docx") !== -1) {
      return { action: "upload_docx", label: "Upload .docx" };
    }
    if (r.indexOf("бриф") !== -1 || r.indexOf("brief") !== -1) {
      return { action: "add_brief", label: "Add assignment brief" };
    }
    return { action: "add_brief", label: "Add requirements" };
  }

  function isEmptyReport(data) {
    var applied = Number(data && data.checks_applied) || 0;
    var validations = (data && data.validations) || [];
    var weighted = validations.filter(function (v) {
      return v && Number(v.weight) > 0;
    });
    return applied <= 0 && weighted.length === 0;
  }

  global.CheckReport = {
    COVERAGE_THRESHOLD: COVERAGE_THRESHOLD,
    FRAGMENT_WORD_THRESHOLD: FRAGMENT_WORD_THRESHOLD,
    hasEnoughCoverage: hasEnoughCoverage,
    totalCheckCount: totalCheckCount,
    formatCoverageLine: formatCoverageLine,
    pointsLost: pointsLost,
    sortMissingValidations: sortMissingValidations,
    formatStatusLabel: formatStatusLabel,
    formatValidationSummary: formatValidationSummary,
    formatFormattingLine: formatFormattingLine,
    formattingDetailLines: formattingDetailLines,
    resolveLowCoverageState: resolveLowCoverageState,
    notCheckedAction: notCheckedAction,
    isEmptyReport: isEmptyReport,
  };
})(typeof window !== "undefined" ? window : globalThis);
