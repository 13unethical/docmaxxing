/**
 * Humanizer Engine (mock) — assignment pipeline internal engine.
 *
 * Input: Draft + Requirement JSON + Blueprint only.
 * Humanizes one paragraph at a time. Real Humanizer API replaces mock later.
 */

window.AssignmentHumanizerEngine = (function () {
  "use strict";

  var VERSION = "mock-1.0";
  var MAX_ATTEMPTS = 3;

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

  function splitParagraphs(content, blueprint) {
    var paragraphs = [];
    var sectionList = parseSections(content);
    sectionList.forEach(function (section) {
      paragraphs.push({
        paragraph_id: "p-" + (paragraphs.length + 1),
        section: section.title,
        original_text: "## " + section.title,
        humanized_text: "",
        status: "pending",
        ai_score_before: null,
        ai_score_after: null,
        attempts: 0,
      });
      var chunks = (section.body || "").split(/\n\s*\n/).filter(function (c) { return c.trim(); });
      if (!chunks.length && section.body) chunks = [section.body];
      chunks.forEach(function (chunk) {
        paragraphs.push({
          paragraph_id: "p-" + (paragraphs.length + 1),
          section: section.title,
          original_text: chunk.trim(),
          humanized_text: "",
          status: "pending",
          ai_score_before: null,
          ai_score_after: null,
          attempts: 0,
        });
      });
    });
    if (!paragraphs.length && content.trim()) {
      paragraphs.push({
        paragraph_id: "p-1",
        section: "Document",
        original_text: content.trim(),
        humanized_text: "",
        status: "pending",
        ai_score_before: null,
        ai_score_after: null,
        attempts: 0,
      });
    }
    return paragraphs;
  }

  function estimateAiScore(text) {
    if (!text || !text.trim()) return 0;
    if (text.trim().indexOf("## ") === 0) return 12;
    var score = 58 + (text.length % 28);
    if (/objective|furthermore|however/i.test(text)) score += 8;
    return Math.min(94, score);
  }

  function humanizeText(text, tone) {
    if (!text || !text.trim()) return text;
    if (text.trim().indexOf("## ") === 0) return text.trim();
    var output = text.trim();
    output = output.replace(/\bHowever,\b/g, "Nevertheless,");
    output = output.replace(/\bFurthermore,\b/g, "Moreover,");
    output = output.replace(/\butilize\b/gi, "use");
    output = output.replace(/\bThis essay\b/g, "This paper");
    if ((tone || "").toLowerCase().indexOf("formal") !== -1 && output.slice(-1) !== ".") {
      output += ".";
    }
    return output;
  }

  function validateParagraph(paragraph) {
    if ((paragraph.original_text || "").trim().indexOf("## ") === 0) {
      return { passed: true, issues: [] };
    }
    var issues = [];
    if (paragraph.attempts === 1 && /objective/i.test(paragraph.original_text)) {
      issues.push("Academic tone needs refinement on first pass");
    }
    if ((paragraph.humanized_text || "").split(/\s+/).length < Math.max(3, paragraph.original_text.split(/\s+/).length * 0.6)) {
      issues.push("Logical flow collapsed");
    }
    if (!paragraph.humanized_text) issues.push("Humanized text is empty");
    return { passed: !issues.length, issues: issues };
  }

  function estimateRemaining(paragraphs) {
    var remaining = paragraphs.filter(function (p) { return p.status !== "completed"; });
    if (!remaining.length) return "0 minutes";
    return Math.max(2, remaining.length * 2) + " minutes";
  }

  function refreshMetrics(session) {
    var completed = session.paragraphs.filter(function (p) { return p.status === "completed"; });
    session.completed_paragraph_ids = completed.map(function (p) { return p.paragraph_id; });
    session.remaining_paragraph_ids = session.paragraphs
      .filter(function (p) { return p.status !== "completed"; })
      .map(function (p) { return p.paragraph_id; });
    session.paragraphs_processed = completed.length;
    session.total_paragraphs = session.paragraphs.length;
    session.progress = session.paragraphs.length
      ? Math.round(100 * completed.length / session.paragraphs.length)
      : 0;

    var reductions = completed
      .filter(function (p) { return p.ai_score_before != null && p.ai_score_after != null; })
      .map(function (p) { return Math.max(0, p.ai_score_before - p.ai_score_after); });
    session.average_ai_reduction = reductions.length
      ? Math.round((reductions.reduce(function (a, b) { return a + b; }, 0) / reductions.length) * 10) / 10
      : 0;

    session.estimated_remaining_time = estimateRemaining(session.paragraphs);
    var active = session.paragraphs.find(function (p) { return p.status !== "completed"; });
    session.current_paragraph_id = active ? active.paragraph_id : null;
    session.current_paragraph = active || null;
    session.status = active ? "active" : "completed";
    return session;
  }

  function createSession(input) {
    var draft = input.draft || {};
    var paragraphs = splitParagraphs(draft.content || "", input.blueprint || {});
    var session = {
      id: "humanizer-" + Date.now(),
      project_id: input.projectId || input.project_id || null,
      source_draft_id: draft.id || null,
      source_draft_version: draft.version || 1,
      paragraphs: paragraphs,
      current_paragraph_id: paragraphs[0] ? paragraphs[0].paragraph_id : null,
      current_paragraph: paragraphs[0] || null,
      completed_paragraph_ids: [],
      remaining_paragraph_ids: paragraphs.map(function (p) { return p.paragraph_id; }),
      progress: 0,
      paragraphs_processed: 0,
      total_paragraphs: paragraphs.length,
      average_ai_reduction: 0,
      estimated_remaining_time: estimateRemaining(paragraphs),
      status: "active",
      humanized_draft_id: null,
      engine_version: VERSION,
      requirement_json: input.requirementJson || input.requirement_json || {},
      blueprint: input.blueprint || {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    return refreshMetrics(session);
  }

  function advance(session) {
    var tone =
      (session.requirement_json && (session.requirement_json.writing_tone || session.requirement_json.citation_style)) ||
      (session.blueprint && session.blueprint.academic_tone) ||
      "Formal academic prose";
    var active = session.paragraphs.find(function (p) { return p.status !== "completed"; });
    if (!active) {
      session.status = "completed";
      return refreshMetrics(session);
    }

    if (active.status === "pending" || active.status === "revision") {
      if (active.status === "revision") active.attempts += 1;
      else active.attempts = Math.max(active.attempts, 0) + 1;
      active.status = "humanizing";
      if (active.ai_score_before == null) active.ai_score_before = estimateAiScore(active.original_text);
      active.humanized_text = humanizeText(active.original_text, tone);
      active.ai_score_after = estimateAiScore(active.humanized_text);
      active.status = "validating";
    }

    if (active.status === "validating") {
      var validation = validateParagraph(active);
      active.last_validation = validation;
      if (validation.passed) {
        active.status = "completed";
      } else if (active.attempts >= MAX_ATTEMPTS) {
        active.status = "failed";
        active.humanized_text = active.original_text;
        active.status = "completed";
      } else {
        active.status = "revision";
      }
    }

    session.updated_at = new Date().toISOString();
    return refreshMetrics(session);
  }

  function merge(session, title) {
    var incomplete = session.paragraphs.some(function (p) { return p.status !== "completed"; });
    if (incomplete) throw new Error("All paragraphs must be completed before merge");
    var content = session.paragraphs
      .map(function (p) { return (p.humanized_text || p.original_text).trim(); })
      .filter(Boolean)
      .join("\n\n");
    return {
      id: "humanized-" + Date.now(),
      session_id: session.id,
      source_draft_id: session.source_draft_id,
      source_version: session.source_draft_version,
      title: title || "Humanized Assignment Draft",
      content: content,
      total_words: content.split(/\s+/).filter(Boolean).length,
      version: (session.source_draft_version || 1) + 1,
      paragraphs_processed: session.paragraphs_processed,
      average_ai_reduction: session.average_ai_reduction,
      created_at: new Date().toISOString(),
    };
  }

  function runAdvance(session) {
    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve(advance(session));
      }, 700);
    });
  }

  return {
    VERSION: VERSION,
    MAX_ATTEMPTS: MAX_ATTEMPTS,
    createSession: createSession,
    advance: advance,
    runAdvance: runAdvance,
    merge: merge,
  };
})();
