/**
 * AI Detection Engine (mock) — assignment pipeline internal engine.
 *
 * Input: Humanized Draft + Requirement JSON only.
 * Analyzes one paragraph at a time. Provider-agnostic (Turnitin, GPTZero, etc. later).
 */

window.AssignmentAIDetectionEngine = (function () {
  "use strict";

  var VERSION = "mock-1.0";
  var MAX_ATTEMPTS = 3;

  var DEFAULT_THRESHOLDS = {
    excellent_max: 5,
    good_max: 10,
    acceptable_max: 15,
    needs_revision_max: 25,
  };

  function classifyScore(score, thresholds) {
    var t = thresholds || DEFAULT_THRESHOLDS;
    if (score <= t.excellent_max) return "excellent";
    if (score <= t.good_max) return "good";
    if (score <= t.acceptable_max) return "acceptable";
    if (score <= t.needs_revision_max) return "needs_revision";
    return "high_ai_probability";
  }

  function scorePasses(score, thresholds) {
    return score <= (thresholds || DEFAULT_THRESHOLDS).acceptable_max;
  }

  function parseParagraphs(content, humanizerIds) {
    var paragraphs = [];
    var sections = (content || "").split(/^##\s+/m);
    if (sections.length <= 1) {
      return splitBlock(content, "Document", paragraphs, humanizerIds);
    }
    if (sections[0].trim()) {
      splitBlock(sections[0].trim(), "Preamble", paragraphs, humanizerIds);
    }
    for (var i = 1; i < sections.length; i++) {
      var chunk = sections[i];
      var lineBreak = chunk.indexOf("\n");
      var title = lineBreak === -1 ? chunk.trim() : chunk.slice(0, lineBreak).trim();
      var body = lineBreak === -1 ? "" : chunk.slice(lineBreak + 1).trim();
      paragraphs.push({
        paragraph_id: "det-p-" + paragraphs.length,
        section: title,
        text: "## " + title,
        ai_score: null,
        status: "pending",
        attempts: 0,
        last_checked: null,
        humanizer_paragraph_id: humanizerIds ? humanizerIds[paragraphs.length] : null,
        classification: null,
        reprocessed: false,
      });
      if (body) splitBlock(body, title, paragraphs, humanizerIds);
    }
    return paragraphs;
  }

  function splitBlock(block, section, paragraphs, humanizerIds) {
    var chunks = block.split(/\n\s*\n/).filter(function (c) { return c.trim(); });
    chunks.forEach(function (chunk) {
      if (chunk.trim().indexOf("## ") === 0) return;
      paragraphs.push({
        paragraph_id: "det-p-" + paragraphs.length,
        section: section,
        text: chunk.trim(),
        ai_score: null,
        status: "pending",
        attempts: 0,
        last_checked: null,
        humanizer_paragraph_id: humanizerIds ? humanizerIds[paragraphs.length] : null,
        classification: null,
        reprocessed: false,
      });
    });
    return paragraphs;
  }

  function estimateScore(text) {
    if (!text || !text.trim()) return 0;
    if (text.trim().indexOf("## ") === 0) return 2;
    var score = 10 + (text.length % 17);
    if (/objective|however|furthermore/i.test(text)) score += 12;
    if (text.indexOf("[Rehumanized]") === 0) score = Math.max(4, score - 14);
    if (/Nevertheless,|Moreover,/.test(text)) score = Math.max(5, score - 6);
    return Math.min(94, score);
  }

  function refreshMetrics(session) {
    var completed = session.paragraphs.filter(function (p) {
      return p.status === "completed" || p.status === "manual_review";
    });
    var scored = session.paragraphs.filter(function (p) { return p.ai_score != null; });
    session.paragraphs_completed = completed.length;
    session.total_paragraphs = session.paragraphs.length;
    session.progress = session.paragraphs.length
      ? Math.round(100 * completed.length / session.paragraphs.length)
      : 0;
    session.average_ai_score = scored.length
      ? Math.round((scored.reduce(function (s, p) { return s + p.ai_score; }, 0) / scored.length) * 10) / 10
      : 0;
    var active = session.paragraphs.find(function (p) {
      return p.status !== "completed" && p.status !== "manual_review";
    });
    session.current_paragraph_id = active ? active.paragraph_id : null;
    session.current_paragraph = active || null;
    session.status = active ? "active" : (session.status === "needs_manual_review" ? "needs_manual_review" : "completed");
    return session;
  }

  function buildReport(session) {
    var scored = session.paragraphs.filter(function (p) { return p.ai_score != null; });
    var scores = scored.map(function (p) { return p.ai_score; });
    var average = scores.length ? scores.reduce(function (a, b) { return a + b; }, 0) / scores.length : 0;
    return {
      id: "det-report-" + Date.now(),
      session_id: session.id,
      overall_ai_score: Math.round(average * 10) / 10,
      average_score: Math.round(average * 10) / 10,
      highest_score: scores.length ? Math.max.apply(null, scores) : 0,
      lowest_score: scores.length ? Math.min.apply(null, scores) : 0,
      paragraphs_reprocessed: session.paragraphs.filter(function (p) { return p.reprocessed; }).length,
      final_status: session.status === "needs_manual_review" ? "needs_manual_review" : "passed",
      thresholds: session.thresholds,
      paragraph_scores: scored.map(function (p) {
        return {
          paragraph_id: p.paragraph_id,
          section: p.section,
          ai_score: p.ai_score,
          classification: p.classification,
          status: p.status,
          attempts: p.attempts,
          reprocessed: p.reprocessed,
        };
      }),
      engine_version: VERSION,
      generated_at: new Date().toISOString(),
    };
  }

  function createSession(input) {
    var draft = input.humanizedDraft || input.humanized_draft || {};
    var humanizerIds = input.humanizerParagraphIds || input.humanizer_paragraph_ids || null;
    var paragraphs = parseParagraphs(draft.content || "", humanizerIds);
    var session = {
      id: "detection-" + Date.now(),
      project_id: input.projectId || input.project_id || null,
      humanized_draft_id: draft.id || null,
      paragraphs: paragraphs,
      current_paragraph_id: paragraphs[0] ? paragraphs[0].paragraph_id : null,
      current_paragraph: paragraphs[0] || null,
      paragraphs_completed: 0,
      total_paragraphs: paragraphs.length,
      progress: 0,
      average_ai_score: 0,
      thresholds: input.thresholds || DEFAULT_THRESHOLDS,
      status: "active",
      report_id: null,
      detection_report: null,
      engine_version: VERSION,
      requirement_json: input.requirementJson || input.requirement_json || {},
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    return refreshMetrics(session);
  }

  function advance(session, rehumanize) {
    var active = session.paragraphs.find(function (p) {
      return p.status !== "completed" && p.status !== "manual_review";
    });
    if (!active) {
      session.status = "completed";
      session.detection_report = buildReport(session);
      session.report_id = session.detection_report.id;
      return refreshMetrics(session);
    }

    active.attempts += 1;
    active.status = "detecting";
    active.ai_score = estimateScore(active.text);
    active.last_checked = new Date().toISOString();
    active.classification = classifyScore(active.ai_score, session.thresholds);

    if (scorePasses(active.ai_score, session.thresholds)) {
      active.status = "completed";
    } else if (active.attempts >= MAX_ATTEMPTS) {
      active.status = "manual_review";
      session.status = "needs_manual_review";
      session.detection_report = buildReport(session);
      session.report_id = session.detection_report.id;
    } else {
      active.status = "failed";
      if (rehumanize && active.humanizer_paragraph_id) {
        active.text = rehumanize(active.humanizer_paragraph_id, active.text);
        active.reprocessed = true;
      }
      active.status = "pending";
    }

    session.updated_at = new Date().toISOString();
    session = refreshMetrics(session);
    if (!session.paragraphs.find(function (p) {
      return p.status !== "completed" && p.status !== "manual_review";
    })) {
      session.detection_report = buildReport(session);
      session.report_id = session.detection_report.id;
    }
    return session;
  }

  function runAdvance(session, rehumanize) {
    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve(advance(session, rehumanize));
      }, 750);
    });
  }

  return {
    VERSION: VERSION,
    MAX_ATTEMPTS: MAX_ATTEMPTS,
    DEFAULT_THRESHOLDS: DEFAULT_THRESHOLDS,
    classifyScore: classifyScore,
    createSession: createSession,
    advance: advance,
    runAdvance: runAdvance,
    buildReport: buildReport,
  };
})();
