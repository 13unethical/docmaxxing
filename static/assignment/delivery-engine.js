/**
 * Delivery Engine (mock) — final pipeline stage.
 *
 * Packages prior outputs only. Never regenerates, modifies, humanizes, or detects.
 */

window.AssignmentDeliveryEngine = (function () {
  "use strict";

  var VERSION = "mock-1.0";
  var STATUS_SEQUENCE = [
    "preparing_files",
    "generating_reports",
    "packaging",
    "ready",
  ];

  function safeFilename(value) {
    return String(value || "Assignment")
      .trim()
      .replace(/[^A-Za-z0-9._-]+/g, "-")
      .replace(/^-+|-+$/g, "") || "Assignment";
  }

  function buildSummary(input) {
    var draft = input.final_draft || {};
    var req = input.requirement_json || {};
    var review = input.review_report || {};
    var detection = input.detection_report || {};
    var plan = input.research_plan || {};
    var title = safeFilename(draft.title || req.title || req.assignmentType || "Assignment");
    var reviewScore = Number(review.overall_score || review.overallScore || 0);
    var aiScore = Number(detection.overall_ai_score || detection.average_score || 0);
    var quality = Math.round((reviewScore + Math.max(0, 100 - aiScore)) / 2);

    return {
      project_name: title,
      assignment_type: req.assignment_type || req.assignmentType || "Essay",
      word_count: Number(draft.total_words || req.word_count || req.estimatedWordCount || 0),
      citation_style: req.citation_style || req.citationStyle || "APA 7",
      difficulty: req.difficulty || req.estimatedDifficulty || plan.estimated_difficulty || "—",
      completion_time: input.completion_time || plan.estimated_completion_time || "—",
      total_revisions: Number(input.revision_attempts || 0),
      total_humanization_attempts: Number(input.humanization_attempts || 0),
      overall_review_score: reviewScore,
      final_ai_score: aiScore,
      pipeline_completion_date: new Date().toISOString().slice(0, 10),
      overall_quality_score: quality,
    };
  }

  function buildFiles(title, draft, projectId) {
    var base = "data/projects/" + (projectId || "local") + "/delivery";
    var words = Number(draft.total_words || 0);
  function file(label, filename, fileType, mime, size) {
      var id = "dlf-" + Math.random().toString(36).slice(2, 10);
      return {
        id: id,
        label: label,
        filename: filename,
        file_type: fileType,
        mime_type: mime,
        size_bytes: size,
        storage_path: base + "/" + filename,
        download_url: "/api/delivery/files/" + id,
        ready: false,
      };
    }

    return [
      file("Final Assignment", title + ".docx", "final_assignment_docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 48000 + words * 6),
      file("Final Assignment", title + ".pdf", "final_assignment_pdf", "application/pdf", 62000 + words * 5),
      file("Requirements Report", "Requirements-Report.pdf", "requirements_report", "application/pdf", 24000),
      file("Academic Review Report", "Review-Report.pdf", "review_report", "application/pdf", 28000),
      file("AI Detection Report", "AI-Detection-Report.pdf", "detection_report", "application/pdf", 22000),
      file("Project Summary", "Project-Summary.pdf", "project_summary", "application/pdf", 16000),
    ];
  }

  function preparePackage(input) {
    var draft = input.final_draft || {};
    var title = safeFilename(draft.title || (input.requirement_json && (input.requirement_json.title || input.requirement_json.assignmentType)) || "Assignment");
    var packageId = "dlv-" + Date.now().toString(36);
    var files = buildFiles(title, draft, input.project_id);
    var summary = buildSummary(input);
    var packageSize = files.reduce(function (sum, item) { return sum + item.size_bytes; }, 0) + 12000;

    return {
      id: packageId,
      project_id: input.project_id || null,
      status: "preparing_files",
      files: files,
      project_summary: summary,
      package_download_url: "/api/delivery/packages/" + packageId + "/download",
      package_size_bytes: packageSize,
      final_draft_id: draft.id || null,
      engine_version: VERSION,
      prepared_at: new Date().toISOString(),
      ready_at: null,
    };
  }

  function advanceStatus(packageData) {
    var current = packageData.status || "preparing_files";
    var index = STATUS_SEQUENCE.indexOf(current);
    var next = index < STATUS_SEQUENCE.length - 1 ? STATUS_SEQUENCE[index + 1] : current;
    packageData.status = next;
    if (next === "ready") {
      packageData.ready_at = new Date().toISOString();
      packageData.files.forEach(function (file) {
        file.ready = true;
      });
    }
    return packageData;
  }

  function statusLabel(status) {
    return {
      preparing_files: "Preparing Files",
      generating_reports: "Generating Reports",
      packaging: "Packaging",
      ready: "Ready",
    }[status] || status;
  }

  function formatBytes(bytes) {
    if (!bytes) return "—";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / (1024 * 1024)).toFixed(1) + " MB";
  }

  return {
    VERSION: VERSION,
    STATUS_SEQUENCE: STATUS_SEQUENCE,
    preparePackage: preparePackage,
    advanceStatus: advanceStatus,
    statusLabel: statusLabel,
    formatBytes: formatBytes,
  };
})();
