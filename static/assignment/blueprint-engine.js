/**
 * Blueprint Engine (mock)
 *
 * Input: Requirement JSON + Research Plan only.
 * Output: Blueprint object for the Writer Engine.
 */

window.AssignmentBlueprintEngine = (function () {
  "use strict";

  var VERSION = "mock-1.0";

  function slug(title) {
    return String(title || "section")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-+|-+$/g, "");
  }

  function keyPointsFor(title) {
    var lower = (title || "").toLowerCase();
    if (lower.indexOf("introduction") >= 0) return ["Background", "Thesis Statement", "Scope"];
    if (lower.indexOf("literature") >= 0 || lower.indexOf("review") >= 0) {
      return ["Theme mapping", "Key debates", "Research gap"];
    }
    if (lower.indexOf("analysis") >= 0) {
      return ["Advantages", "Disadvantages", "Evidence", "Counterargument"];
    }
    if (lower.indexOf("discussion") >= 0) return ["Synthesis", "Implications", "Limitations"];
    if (lower.indexOf("conclusion") >= 0) return ["Direct answer", "Summary of argument", "Final implication"];
    if (lower.indexOf("reference") >= 0) return ["Complete source list", "Consistent formatting"];
    return ["Core claim", "Supporting logic", "Link to research question"];
  }

  function citationTarget(title, words) {
    var lower = (title || "").toLowerCase();
    if (lower.indexOf("reference") >= 0) return 0;
    if (lower.indexOf("introduction") >= 0) return Math.max(2, Math.round(words / 90));
    if (lower.indexOf("analysis") >= 0 || lower.indexOf("review") >= 0) return Math.max(4, Math.round(words / 70));
    return Math.max(1, Math.round(words / 110));
  }

  function buildBlueprint(requirementJson, researchPlan) {
    var req = requirementJson || {};
    var plan = researchPlan || {};
    var citationStyle = req.citationStyle || req.citation_style || "APA 7";
    var sections = (plan.section_list || []).map(function (spec, index) {
      var title = spec.title || "Section " + (index + 1);
      var words = spec.estimated_words || 180;
      return {
        id: slug(title),
        title: title,
        objective: spec.purpose || spec.objective || "Develop this section according to the research plan.",
        estimated_words: words,
        key_points: keyPointsFor(title),
        required_arguments: [
          "Advance the section objective with evaluative argumentation",
          "Maintain progression within " + title,
        ],
        required_evidence: ["Peer-reviewed studies", "Supporting examples"],
        required_theories: (plan.required_theories || []).slice(0, 2),
        transition_from_previous: "",
        transition_to_next: "",
        citation_target: citationTarget(title, words),
        completion_status: "pending",
      };
    });

    for (var i = 0; i < sections.length; i++) {
      sections[i].transition_from_previous = i === 0
        ? "Open the assignment and establish relevance immediately."
        : "Bridge from " + sections[i - 1].title + " into " + sections[i].title + ".";
      sections[i].transition_to_next = i === sections.length - 1
        ? "Close with a sentence reinforcing the research question."
        : "Prepare the reader for " + sections[i + 1].title + ".";
    }

    var writingQueue = sections
      .filter(function (s) { return s.title.toLowerCase() !== "references"; })
      .map(function (s) { return s.title; });

    var wordDistribution = sections.map(function (s) {
      return { title: s.title, estimated_words: s.estimated_words };
    });

    var totalWords = wordDistribution.reduce(function (sum, item) {
      return sum + item.estimated_words;
    }, 0);

    return {
      id: "blueprint-" + Date.now(),
      total_target_words: totalWords,
      total_target_sections: sections.length,
      writing_order: sections.filter(function (s) {
        return s.title.toLowerCase() !== "references";
      }).map(function (s) { return s.id; }),
      transition_rules: [
        "Each section must open with a signpost linking to the previous section.",
        "Use explicit comparative language in analysis sections.",
        "Conclusion must not introduce new sources or major claims.",
      ],
      citation_strategy:
        "Use " + citationStyle + " throughout. Integrate citations inside analytical sentences.",
      academic_tone: plan.writing_tone || "Formal academic prose",
      critical_analysis_locations: sections
        .filter(function (s) { return /analysis|review|discussion/i.test(s.title); })
        .map(function (s) { return s.title; }),
      comparison_locations: sections
        .filter(function (s) { return /analysis|review|discussion/i.test(s.title); })
        .map(function (s) { return s.title; }),
      counterargument_locations: sections
        .filter(function (s) { return /analysis|discussion/i.test(s.title); })
        .map(function (s) { return s.title; }),
      conclusion_goals: [
        "Answer the main research question directly.",
        "Summarise the strongest evaluative findings.",
        "State one limitation and one implication.",
      ],
      sections: sections,
      word_distribution: wordDistribution,
      writing_queue: writingQueue,
      estimated_completion_time: plan.estimated_completion_time || "8–11 hours",
      engine_version: VERSION,
      created_at: new Date().toISOString(),
    };
  }

  function run(input) {
    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve(buildBlueprint(input.requirementJson || input.requirement_json, input.researchPlan || input.research_plan));
      }, 1100);
    });
  }

  return {
    VERSION: VERSION,
    buildBlueprint: buildBlueprint,
    run: run,
  };
})();
