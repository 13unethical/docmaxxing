/**
 * Revision Engine (mock)
 *
 * Input: Requirement JSON + Research Plan + Blueprint + Draft + Review Report.
 * Fixes ONLY sections referenced in review issues — never rewrites the whole assignment.
 */

window.AssignmentRevisionEngine = (function () {
  "use strict";

  var VERSION = "mock-1.0";
  var MAX_ATTEMPTS = 3;
  var histories = {};

  function parseSections(content) {
    var text = (content || "").trim();
    if (!text) return [];
    var parts = text.split(/^##\s+/m);
    if (parts.length <= 1) return [{ title: "Document", body: text }];
    var sections = [];
    if (parts[0].trim()) sections.push({ title: "Preamble", body: parts[0].trim() });
    for (var i = 1; i < parts.length; i++) {
      var chunk = parts[i];
      var lineBreak = chunk.indexOf("\n");
      var title = lineBreak === -1 ? chunk.trim() : chunk.slice(0, lineBreak).trim();
      var body = lineBreak === -1 ? "" : chunk.slice(lineBreak + 1).trim();
      sections.push({ title: title, body: body });
    }
    return sections;
  }

  function findSectionIndex(sections, target) {
    var lower = String(target || "").toLowerCase();
    for (var i = 0; i < sections.length; i++) {
      if (sections[i].title.toLowerCase() === lower) return i;
    }
    for (var j = 0; j < sections.length; j++) {
      if (sections[j].title.toLowerCase().indexOf(lower) !== -1) return j;
    }
    return -1;
  }

  function renderSections(sections) {
    return sections
      .map(function (section) {
        if (section.title === "Preamble" || section.title === "Document") return section.body;
        return "## " + section.title + "\n" + section.body;
      })
      .filter(Boolean)
      .join("\n\n");
  }

  function countWords(text) {
    return (text || "").trim().split(/\s+/).filter(Boolean).length;
  }

  function ensureHistory(projectId) {
    if (!histories[projectId]) {
      histories[projectId] = {
        project_id: projectId,
        versions: [],
        revision_attempts: 0,
        max_attempts: MAX_ATTEMPTS,
        needs_manual_review: false,
      };
    }
    return histories[projectId];
  }

  function applyFix(sectionTitle, body, issue) {
    var category = String(issue.category || "").toLowerCase();
    var issueId = String(issue.issue_id || "");

    if (category.indexOf("critical") !== -1 || issueId === "issue-critical-analysis-1") {
      if (body.toLowerCase().indexOf("comparison") === -1) {
        return {
          body:
            body +
            "\n\nComparative evaluation: Competing theories are weighed directly. Theory A emphasises structural constraints, whereas Theory B foregrounds agency.",
          change: "Added comparison in " + sectionTitle,
        };
      }
    }
    if (category.indexOf("counter") !== -1 || issueId === "issue-counterargument-1") {
      if (body.toLowerCase().indexOf("counterargument") === -1) {
        return {
          body:
            body +
            "\n\nCounterargument: An alternative reading suggests limited generalisability. However, peer-reviewed evidence supports the primary argument after rebuttal.",
          change: "Added counterargument evaluation in " + sectionTitle,
        };
      }
    }
    if (category.indexOf("evidence") !== -1 || issueId === "issue-evidence-1") {
      if (body.toLowerCase().indexOf("smith") === -1) {
        return {
          body: body + "\n\nAdditional academic references strengthen thematic balance: (Smith, 2021; Patel, 2022).",
          change: "Added 2 academic references in " + sectionTitle,
        };
      }
    }
    if (sectionTitle.toLowerCase().indexOf("conclusion") !== -1) {
      return {
        body: body + "\n\nThe conclusion now explicitly resolves the research question with synthesised implications.",
        change: "Improved conclusion",
      };
    }
    return {
      body: body + "\n\n[Revision: " + (issue.suggested_fix || "Targeted fix applied") + "]",
      change: "Applied fix in " + sectionTitle,
    };
  }

  function registerInitialDraft(draft, projectId) {
    var pid = projectId || draft.project_id || "local";
    var history = ensureHistory(pid);
    if (history.versions.length) return history;
    history.versions.push({
      version: draft.version || 1,
      draft_id: draft.id || "draft-v1",
      title: draft.title || "Assignment Draft",
      content: draft.content || "",
      total_words: draft.total_words || countWords(draft.content),
      created_at: draft.created_at || new Date().toISOString(),
      changes: ["Initial draft from writer merge"],
      review_score: null,
      source: "merge",
    });
    return history;
  }

  function revise(payload) {
    var projectId = payload.projectId || payload.project_id || "local";
    var history = ensureHistory(projectId);
    if (history.revision_attempts >= MAX_ATTEMPTS || history.needs_manual_review) {
      throw new Error("Maximum automatic revision attempts reached — project needs manual review");
    }

    var draft = JSON.parse(JSON.stringify(payload.draft || {}));
    var report = payload.reviewReport || payload.review_report || {};
    if (report.passed) throw new Error("Review report passed — revision is not required");

    var issues = report.issues || [];
    if (!issues.length) throw new Error("Review report has no issues to fix");

    if (!history.versions.length) registerInitialDraft(draft, projectId);

    var sections = parseSections(draft.content || "");
    var changes = [];
    var sectionsRevised = [];
    var issuesAddressed = [];

    issues.forEach(function (issue) {
      var index = findSectionIndex(sections, issue.section);
      if (index === -1) return;
      var original = sections[index].body;
      var fixed = applyFix(sections[index].title, original, issue);
      if (fixed.body === original) return;
      sections[index].body = fixed.body;
      changes.push(fixed.change);
      sectionsRevised.push({
        issue_id: issue.issue_id,
        section: sections[index].title,
        category: issue.category,
        change_description: fixed.change,
      });
      issuesAddressed.push(issue.issue_id);
    });

    if (!sectionsRevised.length) throw new Error("No affected sections could be located for revision");

    var newContent = renderSections(sections);
    var previousVersion = draft.version || 1;
    var newVersion = previousVersion + 1;
    var attemptNumber = history.revision_attempts + 1;

    draft.id = "draft-" + Date.now() + "-" + Math.random().toString(16).slice(2, 8);
    draft.content = newContent;
    draft.total_words = countWords(newContent);
    draft.version = newVersion;
    draft.created_at = new Date().toISOString();

    history.revision_attempts = attemptNumber;
    history.versions.push({
      version: newVersion,
      draft_id: draft.id,
      title: draft.title,
      content: newContent,
      total_words: draft.total_words,
      created_at: draft.created_at,
      changes: changes,
      review_score: null,
      source: "revision",
    });

    return {
      id: "revision-" + Date.now(),
      project_id: projectId,
      draft: draft,
      previous_version: previousVersion,
      new_version: newVersion,
      changes: changes,
      sections_revised: sectionsRevised,
      issues_addressed: issuesAddressed,
      attempt_number: attemptNumber,
      engine_version: VERSION,
      revised_at: new Date().toISOString(),
    };
  }

  function getHistory(projectId) {
    var history = ensureHistory(projectId || "local");
    return {
      project_id: history.project_id,
      current_version: history.versions.length ? history.versions[history.versions.length - 1].version : 0,
      revision_attempts: history.revision_attempts,
      max_attempts: history.max_attempts,
      needs_manual_review: history.needs_manual_review,
      versions: history.versions.slice(),
    };
  }

  function restoreVersion(projectId, version) {
    var history = ensureHistory(projectId || "local");
    var record = null;
    history.versions.forEach(function (item) {
      if (item.version === version) record = item;
    });
    if (!record) throw new Error("Draft version not found");
    return {
      id: record.draft_id,
      project_id: projectId,
      title: record.title,
      content: record.content,
      total_words: record.total_words,
      version: record.version,
      created_at: record.created_at,
    };
  }

  function markNeedsManualReview(projectId) {
    var history = ensureHistory(projectId || "local");
    history.needs_manual_review = true;
    return getHistory(projectId);
  }

  function updateReviewScore(projectId, version, score, passed) {
    var history = ensureHistory(projectId || "local");
    history.versions.forEach(function (item) {
      if (item.version === version) item.review_score = score;
    });
    if (
      passed === false &&
      !history.needs_manual_review &&
      history.revision_attempts >= MAX_ATTEMPTS
    ) {
      history.needs_manual_review = true;
    }
    return getHistory(projectId);
  }

  function compareVersions(projectId, versionA, versionB) {
    var history = ensureHistory(projectId || "local");
    var a = null;
    var b = null;
    history.versions.forEach(function (item) {
      if (item.version === versionA) a = item;
      if (item.version === versionB) b = item;
    });
    if (!a || !b) throw new Error("One or both versions not found");
    var sectionsA = parseSections(a.content);
    var sectionsB = parseSections(b.content);
    var diffs = [];
    sectionsB.forEach(function (section) {
      var index = findSectionIndex(sectionsA, section.title);
      if (index === -1) {
        diffs.push({ section: section.title, type: "added", summary: "Section added in v" + versionB });
        return;
      }
      if (sectionsA[index].body !== section.body) {
        diffs.push({
          section: section.title,
          type: "modified",
          summary: "Section revised between v" + versionA + " and v" + versionB,
          before: sectionsA[index].body.slice(0, 180) + (sectionsA[index].body.length > 180 ? "…" : ""),
          after: section.body.slice(0, 180) + (section.body.length > 180 ? "…" : ""),
        });
      }
    });
    return {
      version_a: versionA,
      version_b: versionB,
      diffs: diffs,
    };
  }

  function run(payload) {
    return new Promise(function (resolve, reject) {
      setTimeout(function () {
        try {
          resolve(revise(payload));
        } catch (err) {
          reject(err);
        }
      }, 1300);
    });
  }

  return {
    VERSION: VERSION,
    MAX_ATTEMPTS: MAX_ATTEMPTS,
    registerInitialDraft: registerInitialDraft,
    revise: revise,
    run: run,
    getHistory: getHistory,
    restoreVersion: restoreVersion,
    updateReviewScore: updateReviewScore,
    markNeedsManualReview: markNeedsManualReview,
    compareVersions: compareVersions,
  };
})();
