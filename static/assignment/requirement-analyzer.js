/**
 * Assignment Requirement Analyzer
 *
 * Extracts structured requirements from uploaded documents.
 * Replace `analyzeRequirements` implementation with Gemini 2.5 Pro when ready.
 *
 * @typedef {Object} RubricCriterion
 * @property {string} criterion
 * @property {string} weight
 * @property {string} description
 *
 * @typedef {Object} RequirementFileRef
 * @property {string} id
 * @property {string} source
 * @property {string} name
 * @property {number} size
 *
 * @typedef {Object} RequirementJSON
 * @property {string} assignmentType
 * @property {number|null} estimatedWordCount
 * @property {string|null} citationStyle
 * @property {string[]} requiredSections
 * @property {number|null} minimumReferences
 * @property {string[]} learningOutcomes
 * @property {RubricCriterion[]} rubricCriteria
 * @property {string|null} deadline ISO-like display string
 * @property {string} estimatedDifficulty
 * @property {string[]} missingInformation
 * @property {string} analyzedAt
 * @property {RequirementFileRef[]} sourceFiles
 * @property {string} analyzerVersion
 * @property {string} confidence
 */

window.AssignmentRequirementAnalyzer = (function () {
  "use strict";

  var ANALYZER_VERSION = "mock-1.0";

  function hasSource(files, source) {
    return files.some(function (f) {
      return f.source === source;
    });
  }

  function inferType(files, note) {
    var text = (note || "").toLowerCase();
    if (text.indexOf("literature review") >= 0) return "Literature Review";
    if (text.indexOf("case study") >= 0) return "Case Study";
    if (text.indexOf("report") >= 0) return "Report";
    if (text.indexOf("reflection") >= 0) return "Reflection";
    if (text.indexOf("dissertation") >= 0) return "Dissertation Chapter";
    if (hasSource(files, "Rubric")) return "Essay";
    return "Essay";
  }

  function formatDeadline(dateStr, timeStr) {
    if (!dateStr) return null;
    var timeValue = timeStr || "23:59";
    try {
      var d = new Date(dateStr + "T" + timeValue + ":00");
      return d.toLocaleString(undefined, {
        weekday: "short",
        year: "numeric",
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch (e) {
      return dateStr;
    }
  }

  function buildMissing(files, note, deadlineDate, requirement) {
    var missing = [];
    if (!hasSource(files, "Assignment Brief")) {
      missing.push("Assignment brief not uploaded");
    }
    if (!hasSource(files, "Rubric")) {
      missing.push("Rubric not provided — grading criteria inferred from brief only");
    }
    if (!deadlineDate && !requirement.deadline) {
      missing.push("Deadline not found in documents");
    }
    if (!note || !note.trim()) {
      missing.push("No additional notes from student");
    }
    if (!hasSource(files, "Additional files / Materials")) {
      missing.push("Supporting materials not attached");
    }
    if (requirement.minimumReferences === null) {
      missing.push("Minimum reference count not specified");
    }
    return missing;
  }

  /**
   * Mock analyzer — swap this function body for Gemini 2.5 Pro API.
   * @param {{ files: RequirementFileRef[], note: string, deadlineDate: string, deadlineTime: string }} input
   * @returns {Promise<RequirementJSON>}
   */
  function analyzeRequirements(input) {
    var files = input.files || [];
    var note = input.note || "";
    var hasRubric = hasSource(files, "Rubric");
    var hasBrief = hasSource(files, "Assignment Brief");
    var fileCount = files.length;

    return new Promise(function (resolve) {
      setTimeout(function () {
        var assignmentType = inferType(files, note);
        var estimatedWordCount = hasBrief ? 2500 : null;
        var citationStyle = "APA 7";
        var requiredSections = [
          "Introduction",
          "Literature Review",
          "Methodology",
          "Analysis",
          "Conclusion",
          "References",
        ];
        var minimumReferences = hasBrief ? 12 : null;
        var learningOutcomes = [
          "Demonstrate critical analysis of academic literature",
          "Apply theoretical frameworks to a real-world case",
          "Communicate findings using formal academic writing",
          "Use evidence-based argumentation with correct citations",
        ];
        var rubricCriteria = hasRubric
          ? [
              { criterion: "Structure & coherence", weight: "25%", description: "Clear intro, body, conclusion" },
              { criterion: "Critical analysis", weight: "30%", description: "Depth of argument and evaluation" },
              { criterion: "Use of sources", weight: "20%", description: "Quality and integration of references" },
              { criterion: "Academic writing", weight: "15%", description: "Grammar, tone, formatting" },
              { criterion: "Referencing", weight: "10%", description: "APA 7 accuracy" },
            ]
          : [
              { criterion: "Structure", weight: "—", description: "Inferred — upload rubric for exact weights" },
              { criterion: "Analysis quality", weight: "—", description: "Inferred from brief" },
            ];
        var deadline = formatDeadline(input.deadlineDate, input.deadlineTime);
        var estimatedDifficulty =
          fileCount >= 4 ? "★★★★★" : fileCount >= 2 || hasRubric ? "★★★★☆" : "★★★☆☆";

        if (assignmentType === "Literature Review") {
          requiredSections = ["Introduction", "Thematic Review", "Critical Discussion", "Conclusion", "References"];
          estimatedWordCount = 3000;
          minimumReferences = 15;
        } else if (assignmentType === "Case Study") {
          requiredSections = ["Introduction", "Background", "Case Analysis", "Recommendations", "Conclusion", "References"];
          estimatedWordCount = 2200;
        }

        var requirement = {
          assignmentType: assignmentType,
          estimatedWordCount: estimatedWordCount,
          citationStyle: citationStyle,
          requiredSections: requiredSections,
          minimumReferences: minimumReferences,
          learningOutcomes: learningOutcomes,
          rubricCriteria: rubricCriteria,
          deadline: deadline,
          estimatedDifficulty: estimatedDifficulty,
          missingInformation: [],
          analyzedAt: new Date().toISOString(),
          sourceFiles: files.map(function (f) {
            return { id: f.id, source: f.source, name: f.name, size: f.size };
          }),
          analyzerVersion: ANALYZER_VERSION,
          confidence: hasRubric && hasBrief ? "high" : hasBrief ? "medium" : "low",
        };

        requirement.missingInformation = buildMissing(files, note, input.deadlineDate, requirement);
        resolve(requirement);
      }, 1400);
    });
  }

  return {
    VERSION: ANALYZER_VERSION,
    analyze: analyzeRequirements,
  };
})();
