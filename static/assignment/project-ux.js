/**
 * Assignment Project UX — timelines, pipelines, and progress surfaces.
 * Mock-only, production-ready presentation layer. No backend calls.
 */

window.AssignmentProjectUX = (function () {
  "use strict";

  var INIT_STAGES = [
    { id: "files_uploaded", label: "Files Uploaded" },
    { id: "documents_parsed", label: "Documents Parsed" },
    { id: "requirements_extracted", label: "Requirements Extracted" },
    { id: "rubric_understood", label: "Rubric Understood" },
    { id: "learning_outcomes", label: "Learning Outcomes Found" },
    { id: "word_count", label: "Word Count Detected" },
    { id: "complexity", label: "Complexity Calculated" },
    { id: "price", label: "Price Calculated" },
  ];

  var PRE_WRITING_PIPELINE = [
    { id: "research", label: "Research Planning" },
    { id: "blueprint", label: "Building Writing Blueprint" },
    { id: "writing_queue", label: "Preparing Writing Queue" },
  ];

  var REVIEW_CHECKS = [
    { id: "rubric", label: "Checking Rubric" },
    { id: "outcomes", label: "Checking Learning Outcomes" },
    { id: "structure", label: "Checking Structure" },
    { id: "word_count", label: "Checking Word Count" },
    { id: "references", label: "Checking References" },
    { id: "formatting", label: "Checking Formatting" },
  ];

  var REVISION_FLOW = [
    { id: "issues", label: "Reviewer found issues" },
    { id: "applying", label: "Applying Revision" },
    { id: "recheck", label: "Checking Again" },
    { id: "passed", label: "Passed" },
  ];

  var DELIVERY_STEPS = [
    { id: "docx", label: "Preparing DOCX" },
    { id: "pdf", label: "Preparing PDF" },
    { id: "reports", label: "Generating Reports" },
    { id: "packaging", label: "Packaging Files" },
    { id: "completed", label: "Project Completed" },
  ];

  var STAGE_PROGRESS = {
    upload: 0,
    initializing: 4,
    requirements: 12,
    payment: 14,
    research: 22,
    blueprint: 30,
    writing: 48,
    review: 62,
    revision: 68,
    humanizer: 78,
    detection: 88,
    delivery: 96,
    completed: 100,
  };

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatDateTime(value) {
    if (!value) return "—";
    var d = value instanceof Date ? value : new Date(value);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  }

  function deriveProjectName(files, requirement) {
    if (requirement) {
      var topic = requirement.title || requirement.assignmentTopic || requirement.assignment_topic;
      var type = requirement.assignmentType || requirement.assignment_type;
      if (topic && type) return topic + " " + type;
      if (topic) return topic;
      if (type) return type;
    }
    var brief = (files || []).find(function (f) {
      return f.source === "Assignment Brief";
    });
    if (brief && brief.name) {
      return brief.name.replace(/\.(pdf|docx)$/i, "").replace(/[-_]+/g, " ");
    }
    return "Untitled Assignment";
  }

  function createProject(files, requirement) {
    var now = new Date();
    return {
      id: "proj-" + now.getTime().toString(36),
      name: deriveProjectName(files, requirement),
      status: "Initializing Project…",
      currentStage: "Initializing",
      overallProgress: 0,
      eta: "Calculating…",
      startedAt: now.toISOString(),
      lastUpdated: now.toISOString(),
      paid: false,
    };
  }

  function touchProject(project, patch) {
    if (!project) return null;
    Object.keys(patch || {}).forEach(function (key) {
      project[key] = patch[key];
    });
    project.lastUpdated = new Date().toISOString();
    return project;
  }

  function stageLabel(step) {
    return {
      upload: "Upload",
      initializing: "Initializing",
      requirements: "Requirement Analysis",
      payment: "Awaiting Payment",
      research: "Research Planning",
      blueprint: "Blueprint",
      writing: "Writing",
      review: "Academic Review",
      revision: "Revision",
      humanizer: "Humanization",
      detection: "AI Detection",
      delivery: "Delivery",
      completed: "Completed",
    }[step] || step;
  }

  function estimateRemaining(step, sessionProgress) {
    var map = {
      initializing: "2 min",
      requirements: "1 min",
      payment: "—",
      research: "8 min",
      blueprint: "6 min",
      writing: sessionProgress != null ? Math.max(1, Math.round((100 - sessionProgress) * 0.12)) + " min" : "18 min",
      review: "4 min",
      revision: "6 min",
      humanizer: "12 min",
      detection: "8 min",
      delivery: "2 min",
      completed: "—",
    };
    return map[step] || "—";
  }

  function progressBar(percent, label) {
    var value = Math.max(0, Math.min(100, Number(percent) || 0));
    var blocks = 12;
    var filled = Math.round((value / 100) * blocks);
  var visual = "";
    for (var i = 0; i < blocks; i++) {
      visual += i < filled ? "█" : "░";
    }
    return (
      '<div class="asg-pipeline-bar" role="progressbar" aria-valuenow="' +
      value +
      '" aria-valuemin="0" aria-valuemax="100"' +
      (label ? ' aria-label="' + escapeHtml(label) + '"' : "") +
      "><span class=\"asg-pipeline-bar-visual\" aria-hidden=\"true\">" +
      visual +
      '</span><span class="asg-pipeline-bar-pct">' +
      value +
      "%</span></div>"
    );
  }

  function renderProjectHeader(root, project, step) {
    if (!root || !project) return;
    var header = root.querySelector("[data-asg-project-header]");
    if (!header) return;

    header.hidden = false;
    var progress = STAGE_PROGRESS[step] != null ? STAGE_PROGRESS[step] : project.overallProgress;
    if (step === "writing" && project.writingProgress != null) {
      progress = 35 + Math.round(project.writingProgress * 0.2);
    }
    project.overallProgress = progress;

    var set = function (sel, value) {
      var el = root.querySelector(sel);
      if (el) el.textContent = value != null && value !== "" ? String(value) : "—";
    };

    set("[data-asg-project-name]", project.name);
    set("[data-asg-project-status]", project.status);
    set("[data-asg-project-stage]", stageLabel(step));
    set("[data-asg-project-eta]", project.eta || estimateRemaining(step, project.writingProgress));
    set("[data-asg-project-started]", formatDateTime(project.startedAt));
    set("[data-asg-project-updated]", formatDateTime(project.lastUpdated));
    set("[data-asg-overall-progress]", progress + "%");

    var barHost = root.querySelector("[data-asg-overall-progress-bar]");
    if (barHost) {
      barHost.innerHTML = progressBar(progress, "Overall project progress");
    }
  }

  function renderInitTimeline(container, completedCount) {
    if (!container) return;
    container.innerHTML = "";
    INIT_STAGES.forEach(function (stage, index) {
      var li = document.createElement("li");
      var done = index < completedCount;
      var active = index === completedCount;
      li.className =
        "asg-timeline-item" +
        (done ? " asg-timeline-item--done" : "") +
        (active ? " asg-timeline-item--active" : "");
      li.innerHTML =
        '<span class="asg-timeline-icon" aria-hidden="true">' +
        (done ? "✓" : active ? "◉" : "○") +
        "</span><span>" +
        escapeHtml(stage.label) +
        "</span>";
      container.appendChild(li);
    });
  }

  function renderLivePipeline(container, stages, activeId, progressMap) {
    if (!container) return;
    container.innerHTML = "";
    stages.forEach(function (stage) {
      var progress = progressMap && progressMap[stage.id] != null ? progressMap[stage.id] : 0;
      var isDone = progress >= 100;
      var isActive = stage.id === activeId && !isDone;
      var row = document.createElement("div");

      if (isDone) {
        row.className = "asg-live-pipeline-row asg-live-pipeline-row--done";
      } else if (isActive) {
        row.className = "asg-live-pipeline-row asg-live-pipeline-row--active";
      } else {
        row.className = "asg-live-pipeline-row";
      }

      row.innerHTML =
        "<div class=\"asg-live-pipeline-head\"><span>" +
        escapeHtml(stage.label) +
        "</span>" +
        (isDone ? '<span class="asg-live-pipeline-check">✓</span>' : "") +
        "</div>" +
        (isActive ? progressBar(progress, stage.label) : isDone ? progressBar(100, stage.label) : "");

      container.appendChild(row);
    });
  }

  function renderSectionList(container, sections, currentId) {
    if (!container) return;
    container.innerHTML = "";
    (sections || []).forEach(function (section) {
      var li = document.createElement("li");
      li.className = "asg-section-progress-item";
      var icon = "⬜";
      if (section.status === "completed") icon = "✓";
      else if (section.id === currentId) icon = "🟦";
      li.innerHTML =
        '<span class="asg-section-progress-icon" aria-hidden="true">' +
        icon +
        "</span><span>" +
        escapeHtml(section.title || section.label) +
        "</span>";
      container.appendChild(li);
    });
  }

  function renderReviewChecks(container, completedCount) {
    if (!container) return;
    container.innerHTML = "";
    REVIEW_CHECKS.forEach(function (check, index) {
      var li = document.createElement("li");
      var done = index < completedCount;
      var active = index === completedCount;
      li.className =
        "asg-timeline-item" +
        (done ? " asg-timeline-item--done" : "") +
        (active ? " asg-timeline-item--active" : "");
      li.innerHTML =
        '<span class="asg-timeline-icon" aria-hidden="true">' +
        (done ? "✓" : active ? "◉" : "○") +
        "</span><span>" +
        escapeHtml(check.label) +
        "</span>";
      container.appendChild(li);
    });
  }

  function renderRevisionFlow(container, activeIndex) {
    if (!container) return;
    container.innerHTML = "";
    REVISION_FLOW.forEach(function (step, index) {
      var row = document.createElement("div");
      var done = index < activeIndex;
      var active = index === activeIndex;
      row.className =
        "asg-revision-flow-step" +
        (done ? " asg-revision-flow-step--done" : "") +
        (active ? " asg-revision-flow-step--active" : "");
      row.innerHTML =
        '<span class="asg-revision-flow-icon" aria-hidden="true">' +
        (done ? "✓" : active ? "↓" : "○") +
        "</span><span>" +
        escapeHtml(step.label) +
        "</span>";
      container.appendChild(row);
      if (index < REVISION_FLOW.length - 1) {
        var arrow = document.createElement("div");
        arrow.className = "asg-revision-flow-arrow" + (done ? " asg-revision-flow-arrow--done" : "");
        arrow.setAttribute("aria-hidden", "true");
        arrow.textContent = "↓";
        container.appendChild(arrow);
      }
    });
  }

  function renderDeliverySteps(container, activeIndex) {
    if (!container) return;
    container.innerHTML = "";
    DELIVERY_STEPS.forEach(function (step, index) {
      var li = document.createElement("li");
      var done = index < activeIndex;
      var active = index === activeIndex;
      li.className =
        "asg-timeline-item" +
        (done ? " asg-timeline-item--done" : "") +
        (active ? " asg-timeline-item--active" : "");
      li.innerHTML =
        '<span class="asg-timeline-icon" aria-hidden="true">' +
        (done ? "✓" : active ? "◉" : "○") +
        "</span><span>" +
        escapeHtml(step.label) +
        "</span>";
      container.appendChild(li);
    });
  }

  function animateSequence(count, delayMs, onTick, onDone) {
    var index = 0;
    function tick() {
      if (index <= count) {
        onTick(index);
        index += 1;
        if (index <= count) {
          setTimeout(tick, delayMs);
        } else if (onDone) {
          onDone();
        }
      }
    }
    tick();
  }

  function animateProgress(from, to, durationMs, onTick, onDone) {
    var start = Date.now();
    function frame() {
      var elapsed = Date.now() - start;
      var ratio = Math.min(1, elapsed / durationMs);
      var value = Math.round(from + (to - from) * ratio);
      onTick(value);
      if (ratio < 1) {
        requestAnimationFrame(frame);
      } else if (onDone) {
        onDone();
      }
    }
    requestAnimationFrame(frame);
  }

  function updateProjectSummary(root, req, researchPlan, price) {
    if (!root || !req) return;
    var set = function (sel, value) {
      var el = root.querySelector(sel);
      if (el) el.textContent = value != null && value !== "" ? String(value) : "—";
    };
    set("[data-asg-summary-type]", req.assignmentType);
    set("[data-asg-summary-words]", req.estimatedWordCount != null ? req.estimatedWordCount.toLocaleString() : "—");
    set("[data-asg-summary-deadline]", req.deadline);
    set("[data-asg-summary-citation]", req.citationStyle);
    set("[data-asg-summary-difficulty]", req.estimatedDifficulty);
    set(
      "[data-asg-summary-sources]",
      researchPlan && researchPlan.estimated_academic_sources != null
        ? String(researchPlan.estimated_academic_sources)
        : req.minimumReferences != null
          ? String(req.minimumReferences) + "+"
          : "—"
    );
    set(
      "[data-asg-summary-completion]",
      (researchPlan && researchPlan.estimated_completion_time) || "—"
    );
    if (price != null) {
      set("[data-asg-summary-price]", "$" + price);
      set("[data-asg-summary-total]", "$" + price);
    }
  }

  return {
    INIT_STAGES: INIT_STAGES,
    PRE_WRITING_PIPELINE: PRE_WRITING_PIPELINE,
    REVIEW_CHECKS: REVIEW_CHECKS,
    REVISION_FLOW: REVISION_FLOW,
    DELIVERY_STEPS: DELIVERY_STEPS,
    STAGE_PROGRESS: STAGE_PROGRESS,
    createProject: createProject,
    touchProject: touchProject,
    deriveProjectName: deriveProjectName,
    renderProjectHeader: renderProjectHeader,
    renderInitTimeline: renderInitTimeline,
    renderLivePipeline: renderLivePipeline,
    renderSectionList: renderSectionList,
    renderReviewChecks: renderReviewChecks,
    renderRevisionFlow: renderRevisionFlow,
    renderDeliverySteps: renderDeliverySteps,
    animateSequence: animateSequence,
    animateProgress: animateProgress,
    updateProjectSummary: updateProjectSummary,
    progressBar: progressBar,
    stageLabel: stageLabel,
    estimateRemaining: estimateRemaining,
  };
})();
