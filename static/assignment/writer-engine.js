/**
 * Writer Engine (mock)
 *
 * Input: Requirement JSON + Research Plan + Blueprint only.
 * Writes one section at a time. Claude Opus replaces mock writer later.
 */

window.AssignmentWriterEngine = (function () {
  "use strict";

  var VERSION = "mock-1.0";

  function slug(title) {
    return String(title || "section")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function buildSections(blueprint) {
    var order = blueprint.writing_order || [];
    var specs = {};
    (blueprint.sections || []).forEach(function (s) {
      specs[s.id || slug(s.title)] = s;
    });
    if (!order.length) {
      order = (blueprint.sections || [])
        .filter(function (s) { return (s.title || "").toLowerCase() !== "references"; })
        .map(function (s) { return s.id || slug(s.title); });
    }
    return order.map(function (id) {
      var spec = specs[id] || {};
      return {
        id: id,
        title: spec.title || id,
        objective: spec.objective || "",
        estimated_words: spec.estimated_words || 180,
        generated_text: "",
        status: "pending",
        review_score: null,
        revision_count: 0,
        started_at: null,
        completed_at: null,
        last_review: null,
        key_points: spec.key_points || [],
      };
    });
  }

  function sectionText(section, topic, revision) {
    var prefix = revision ? "[REVISED] " : "";
    var bullets = (section.key_points || []).map(function (p) { return "- " + p; }).join("\n");
    return (
      prefix + "## " + section.title + "\n\n" +
      "Section objective: " + section.objective + "\n" +
      "Topic context: " + topic + "\n\n" +
      "Planned coverage (" + section.estimated_words + " words target):\n" +
      (bullets || "- Core argument development") + "\n\n" +
      "[Mock section output — generated in isolation for " + section.title + " only.]"
    );
  }

  function reviewSection(section) {
    if (!section.generated_text) {
      return { passed: false, score: 0, issues: ["Section text is empty"], recommendations: ["Regenerate this section only"] };
    }
    if (section.revision_count === 0 && /analysis/i.test(section.title)) {
      return {
        passed: false,
        score: 64,
        issues: ["Critical analysis needs stronger comparative evaluation"],
        recommendations: ["Increase theory comparison and evidence weighting"],
      };
    }
    return { passed: true, score: 91, issues: [], recommendations: ["Section meets blueprint objective"] };
  }

  function countWords(text) {
    return (text || "").trim().split(/\s+/).filter(Boolean).length;
  }

  function estimateRemaining(sections) {
    if (!sections.length) return "0 minutes";
    var minutes = Math.max(5, sections.reduce(function (sum, s) {
      return sum + Math.max(s.estimated_words || 120, 120);
    }, 0) / 45);
    return Math.round(minutes) + " minutes";
  }

  function refreshMetrics(session) {
    var completed = session.sections.filter(function (s) { return s.status === "completed"; });
    session.completed_section_ids = completed.map(function (s) { return s.id; });
    session.remaining_section_ids = session.sections
      .filter(function (s) { return s.status !== "completed"; })
      .map(function (s) { return s.id; });
    session.progress = session.sections.length
      ? Math.round(100 * completed.length / session.sections.length)
      : 0;
    session.total_words_written = session.sections.reduce(function (sum, s) {
      return sum + countWords(s.generated_text);
    }, 0);
    session.estimated_remaining_time = estimateRemaining(
      session.sections.filter(function (s) { return s.status !== "completed"; })
    );
    var active = session.sections.find(function (s) { return s.status !== "completed"; });
    session.current_section_id = active ? active.id : null;
    session.current_section = active || null;
    session.status = active ? "active" : "completed";
    session.writing_queue = session.sections.map(function (s) { return s.title; });
    return session;
  }

  function createSession(input) {
    var topic =
      (input.requirementJson && (input.requirementJson.title || input.requirementJson.assignment_type)) ||
      (input.researchPlan && input.researchPlan.assignment_topic) ||
      "Assignment";
    var sections = buildSections(input.blueprint || {});
    var session = {
      id: "writer-" + Date.now(),
      project_id: input.project_id || null,
      sections: sections,
      current_section_id: sections[0] ? sections[0].id : null,
      current_section: sections[0] || null,
      completed_section_ids: [],
      remaining_section_ids: sections.map(function (s) { return s.id; }),
      progress: 0,
      total_words_written: 0,
      estimated_remaining_time: estimateRemaining(sections),
      status: "active",
      draft_id: null,
      engine_version: VERSION,
      topic: topic,
      requirement_json: input.requirementJson || input.requirement_json || {},
      research_plan: input.researchPlan || input.research_plan || {},
      blueprint: input.blueprint || {},
      writing_queue: sections.map(function (s) { return s.title; }),
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    };
    return refreshMetrics(session);
  }

  function advance(session) {
    var active = session.sections.find(function (s) { return s.status !== "completed"; });
    if (!active) {
      session.status = "completed";
      return refreshMetrics(session);
    }

    if (active.status === "pending" || active.status === "revision") {
      var isRevision = active.status === "revision";
      if (isRevision) active.revision_count += 1;
      active.status = "writing";
      active.started_at = active.started_at || new Date().toISOString();
      active.generated_text = sectionText(active, session.topic, isRevision);
      active.status = "section_review";
    }

    if (active.status === "section_review") {
      var review = reviewSection(active);
      active.last_review = review;
      active.review_score = review.score;
      active.status = review.passed ? "completed" : "revision";
      if (review.passed) active.completed_at = new Date().toISOString();
    }

    session.updated_at = new Date().toISOString();
    return refreshMetrics(session);
  }

  function revise(session, sectionId) {
    var section = session.sections.find(function (s) { return s.id === sectionId; });
    if (!section || section.status !== "revision") {
      throw new Error("Section is not awaiting revision");
    }
    session.current_section_id = section.id;
    return advance(session);
  }

  function merge(session, title) {
    var incomplete = session.sections.some(function (s) { return s.status !== "completed"; });
    if (incomplete) throw new Error("All sections must be completed before merge");
    var content = session.sections
      .filter(function (s) { return s.generated_text; })
      .map(function (s) { return s.generated_text.trim(); })
      .join("\n\n");
    return {
      id: "draft-" + Date.now(),
      session_id: session.id,
      title: title || "Assignment Draft",
      content: content,
      total_words: countWords(content),
      version: 1,
      created_at: new Date().toISOString(),
    };
  }

  return {
    VERSION: VERSION,
    createSession: createSession,
    advance: advance,
    revise: revise,
    merge: merge,
  };
})();
