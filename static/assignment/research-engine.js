/**
 * Research Engine (mock)
 *
 * Input: Requirement JSON + parsed documents only.
 * Output: Research Plan object for the Writer Engine.
 * Replace buildPlan with Gemini 2.5 Pro later.
 */

window.AssignmentResearchEngine = (function () {
  "use strict";

  var VERSION = "mock-1.0";

  var MOCK_PARSED = {
    "Assignment Brief":
      "Assignment brief: critically evaluate organisational responses to digital transformation.",
    Rubric: "Rubric emphasis: structure 25%, critical analysis 30%, use of sources 20%.",
    "Additional files / Materials": "Supplementary material provides contextual background.",
  };

  function buildParsedDocuments(files) {
    return (files || []).map(function (file, index) {
      var text = MOCK_PARSED[file.source] || MOCK_PARSED["Additional files / Materials"];
      return {
        id: file.id || "doc-" + index,
        file_id: file.id || "file-" + index,
        file_type: mapFileType(file.source),
        filename: file.name,
        text: "[" + file.name + "] " + text,
        word_count: text.split(/\s+/).length,
      };
    });
  }

  function mapFileType(source) {
    if (source === "Assignment Brief") return "assignment_brief";
    if (source === "Rubric") return "rubric";
    return "additional_file";
  }

  function normalizeRequirement(req) {
    return {
      assignment_type: req.assignmentType || req.assignment_type || "Essay",
      title: req.title || "Academic Assignment",
      word_count: req.estimatedWordCount || req.word_count || 2500,
      citation_style: req.citationStyle || req.citation_style || "APA 7",
      required_sections: req.requiredSections || req.required_sections || [],
      minimum_sources: req.minimumReferences || req.minimum_sources || 12,
      difficulty: req.estimatedDifficulty || req.difficulty || "★★★★☆",
      learning_outcomes: req.learningOutcomes || req.learning_outcomes || [],
      missing_information: req.missingInformation || req.missing_information || [],
    };
  }

  function buildSections(req) {
    var wordCount = req.word_count || 2500;
    var sections = req.required_sections || [];
    if (sections.length) {
      return sections.map(function (title) {
        var words = title.toLowerCase() === "references" ? 120 : Math.max(180, Math.round(wordCount / sections.length));
        var purpose =
          title.toLowerCase() === "introduction"
            ? "Introduce the topic and research question."
            : title.toLowerCase().indexOf("analysis") >= 0 || title.toLowerCase().indexOf("review") >= 0
              ? "Compare theories and evaluate evidence."
              : title.toLowerCase().indexOf("conclusion") >= 0
                ? "Answer the research question."
                : "Develop a key part of the argument.";
        return {
          title: title,
          description: "Planned section aligned to assignment brief.",
          purpose: purpose,
          estimated_words: words,
        };
      });
    }
    return [
      { title: "Introduction", description: "Set scope and thesis direction.", purpose: "Introduce the topic and research question.", estimated_words: 180 },
      { title: "Literature Review", description: "Survey relevant scholarship.", purpose: "Map existing research and debates.", estimated_words: 620 },
      { title: "Critical Analysis", description: "Develop the core argument.", purpose: "Compare theories and evaluate evidence.", estimated_words: 650 },
      { title: "Conclusion", description: "Resolve the research question.", purpose: "Answer the research question.", estimated_words: 220 },
      { title: "References", description: "Document sources.", purpose: "Meet citation requirements.", estimated_words: 120 },
    ];
  }

  function buildPlan(requirementJson, parsedDocuments) {
    var req = normalizeRequirement(requirementJson || {});
    var topic = req.title;
    var sectionList = buildSections(req);
    var hours = Math.max(6, Math.round((req.word_count || 2500) / 220));

    return {
      id: "plan-" + Date.now(),
      assignment_topic: topic,
      writing_objective:
        "Produce a rigorous " +
        req.assignment_type.toLowerCase() +
        " that critically examines " +
        topic.toLowerCase() +
        " using academic evidence and evaluative argumentation.",
      main_research_question:
        "To what extent does existing evidence support current understanding of " + topic.toLowerCase() + "?",
      secondary_questions: [
        "Which theoretical frameworks best explain key dimensions of " + topic.toLowerCase() + "?",
        "What methodological limitations appear in the available literature?",
        "How do competing perspectives change the interpretation of findings?",
      ],
      target_audience: "Academic assessors familiar with discipline conventions",
      writing_tone: "Formal, objective, and evidence-led academic prose",
      recommended_structure: sectionList.map(function (s) { return s.title; }).join(" → "),
      section_list: sectionList,
      required_theories: ["Stakeholder theory", "Institutional theory", "Resource-based view"],
      required_concepts: ["Critical evaluation", "Evidence weighting", "Conceptual framing"],
      required_case_studies: ["Use comparative examples only where they strengthen argument"],
      required_arguments: [
        "Current approaches are insufficiently evidence-based",
        "Theoretical frameworks should be integrated rather than listed descriptively",
      ],
      possible_counterarguments: [
        "Limited high-quality empirical studies may weaken generalisability",
        "Alternative interpretations of the same evidence may be plausible",
      ],
      suggested_evidence: ["Peer-reviewed journal articles", "Government or institutional reports"],
      estimated_academic_sources: req.minimum_sources,
      recommended_source_types: ["Peer-reviewed journals", "Academic books", "Official reports"],
      potential_risks: (req.missing_information || []).concat([
        parsedDocuments.length ? null : "No parsed document text available",
        "Writer must avoid descriptive summary without critical evaluation",
      ]).filter(Boolean),
      notes_for_writer: [
        "Use the section plan as the only writing blueprint — do not improvise structure.",
        "Follow " + req.citation_style + " consistently.",
      ],
      estimated_difficulty: req.difficulty,
      estimated_completion_time: hours + "–" + (hours + 3) + " hours",
      engine_version: VERSION,
      created_at: new Date().toISOString(),
    };
  }

  function run(input) {
    var requirement = input.requirementJson || input.requirement_json;
    var parsed =
      input.parsedDocuments ||
      input.parsed_documents ||
      buildParsedDocuments(input.files || []);
    return new Promise(function (resolve) {
      setTimeout(function () {
        resolve(buildPlan(requirement, parsed));
      }, 1200);
    });
  }

  return {
    VERSION: VERSION,
    buildPlan: buildPlan,
    buildParsedDocuments: buildParsedDocuments,
    run: run,
  };
})();
