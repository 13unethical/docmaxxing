/**
 * Academic Reviewer Engine
 *
 * Input: Requirement JSON + Research Plan + Blueprint + Final Draft only.
 * Output: Review Report — never modifies the draft.
 * AI analysis uses AIOrchestrator-compatible review via POST /api/ai/orchestrator/review.
 */

window.AssignmentReviewerEngine = (function () {
  "use strict";

  var VERSION = "mock-1.0";

  function normalizeRequirement(req) {
    return {
      assignment_type: req.assignmentType || req.assignment_type || "Essay",
      title: req.title || "Academic Assignment",
      word_count: req.estimatedWordCount || req.word_count || 2500,
      citation_style: req.citationStyle || req.citation_style || "APA 7",
      required_sections: req.requiredSections || req.required_sections || [],
      learning_outcomes: req.learningOutcomes || req.learning_outcomes || [],
      rubric: req.rubricCriteria || req.rubric || [],
    };
  }

  function normalizeResearchPlan(plan) {
    return {
      writing_tone: plan.writing_tone || "Formal academic prose",
      critical_analysis_locations: plan.critical_analysis_locations || [],
      main_research_question: plan.main_research_question || "",
    };
  }

  function normalizeBlueprint(blueprint) {
    return {
      total_target_words: blueprint.total_target_words || 2500,
      writing_queue: blueprint.writing_queue || blueprint.writing_order || [],
      sections: blueprint.sections || [],
    };
  }

  function normalizeDraft(draft) {
    return {
      title: draft.title || "Assignment Draft",
      content: draft.content || "",
      total_words: draft.total_words || 0,
      version: draft.version || 1,
    };
  }

  function sectionPresent(content, title) {
    return content.toLowerCase().indexOf(String(title || "").toLowerCase()) !== -1;
  }

  function requirementChecklist(req, plan, blueprint, draft) {
    var content = draft.content || "";
    var draftWords = draft.total_words || content.split(/\s+/).filter(Boolean).length;
    var targetWords = req.word_count || blueprint.total_target_words || 2500;
    var wordRatio = targetWords ? draftWords / targetWords : 0;
    var wordPass = wordRatio >= 0.85 && wordRatio <= 1.15;
    var sections = req.required_sections.length
      ? req.required_sections
      : (blueprint.sections || []).map(function (s) { return s.title; });
    var structurePass = sections.every(function (title) {
      return title.toLowerCase() === "references" || sectionPresent(content, title);
    });
    var tone = plan.writing_tone || "Formal academic prose";

    return [
      { id: "assignment_type", label: "Assignment Type", passed: true, score: 90, notes: "Expected: " + req.assignment_type },
      { id: "word_count", label: "Word Count", passed: wordPass, score: wordPass ? 88 : 62, notes: draftWords + "/" + targetWords + " words" },
      { id: "structure", label: "Structure", passed: structurePass, score: structurePass ? 86 : 58, notes: "Blueprint section coverage" },
      { id: "required_sections", label: "Required Sections", passed: structurePass, score: structurePass ? 84 : 55, notes: sections.join(", ") || "—" },
      { id: "learning_outcomes", label: "Learning Outcomes", passed: true, score: 82, notes: "Outcomes addressed in analytical sections" },
      { id: "critical_analysis", label: "Critical Analysis", passed: /analysis|compare/i.test(content), score: 78, notes: "Evaluative depth" },
      { id: "logical_flow", label: "Logical Flow", passed: !!(blueprint.writing_queue && blueprint.writing_queue.length), score: 85, notes: "Queue-aligned progression" },
      { id: "argument_quality", label: "Argument Quality", passed: /argument|objective/i.test(content), score: 80, notes: "Argument development" },
      { id: "counterarguments", label: "Counterarguments", passed: /counter|however/i.test(content), score: 72, notes: "Opposing views" },
      { id: "evidence_usage", label: "Evidence Usage", passed: /evidence|source/i.test(content), score: 79, notes: "Evidence integration" },
      { id: "citation_placement", label: "Citation Placement", passed: /citation|apa/i.test(content), score: 76, notes: req.citation_style },
      { id: "formatting", label: "Formatting Requirements", passed: true, score: 88, notes: "Formatting profile from requirements" },
      { id: "writing_tone", label: "Writing Tone", passed: !!tone, score: 87, notes: tone },
      { id: "conclusion_quality", label: "Conclusion Quality", passed: sectionPresent(content, "Conclusion"), score: 81, notes: "Conclusion resolves research question" },
    ];
  }

  function rubricChecklist(req) {
    var rubric = req.rubric || [];
    if (!rubric.length) {
      return [
        { id: "structure", label: "Structure & coherence", passed: true, score: 84, notes: "Inferred from brief" },
        { id: "analysis", label: "Critical analysis", passed: true, score: 78, notes: "Needs stronger comparison" },
        { id: "sources", label: "Use of sources", passed: true, score: 80, notes: "Citation density acceptable" },
        { id: "writing", label: "Academic writing", passed: true, score: 86, notes: "Tone is formal" },
        { id: "referencing", label: "Referencing", passed: true, score: 82, notes: req.citation_style },
      ];
    }
    return rubric.map(function (criterion, index) {
      var score = index % 2 === 0 ? 85 : 76;
      return {
        id: "rubric-" + (index + 1),
        label: criterion.criterion || "Criterion " + (index + 1),
        passed: score >= 75,
        score: score,
        notes: criterion.description || "",
      };
    });
  }

  function buildIssues(content, plan) {
    var issues = [];
    if (!/compare|comparison/i.test(content)) {
      issues.push({
        issue_id: "issue-critical-analysis-1",
        category: "Critical Analysis",
        severity: "high",
        section: "Discussion",
        description: "No comparison between competing theories.",
        suggested_fix: "Add comparison before conclusion.",
      });
    }
    if (!/counter/i.test(content)) {
      issues.push({
        issue_id: "issue-counterargument-1",
        category: "Counterarguments",
        severity: "medium",
        section: "Critical Analysis",
        description: "Counterarguments are not explicitly evaluated.",
        suggested_fix: "Introduce one counterargument and rebuttal in the analysis section.",
      });
    }
    var locations = plan.critical_analysis_locations || [];
    var hasLocation = locations.some(function (loc) {
      return content.toLowerCase().indexOf(String(loc).toLowerCase()) !== -1;
    });
    if (locations.length && !hasLocation) {
      issues.push({
        issue_id: "issue-evidence-1",
        category: "Evidence Usage",
        severity: "medium",
        section: "Literature Review",
        description: "Evidence weighting is uneven across themes.",
        suggested_fix: "Balance peer-reviewed sources across all major themes.",
      });
    }
    return issues;
  }

  function avgScores(items) {
    if (!items.length) return 0;
    var sum = items.reduce(function (acc, item) { return acc + item.score; }, 0);
    return Math.round(sum / items.length);
  }

  function scoreForLabels(items, labels) {
    var matched = items.filter(function (item) {
      return labels.indexOf(item.label) !== -1;
    });
    return avgScores(matched);
  }

  function qualityScores(requirementChecklist, rubricChecklist, issues) {
    var structure = scoreForLabels(requirementChecklist, ["Structure", "Required Sections", "Logical Flow"]);
    var research = scoreForLabels(requirementChecklist, ["Evidence Usage", "Learning Outcomes"]);
    var critical = scoreForLabels(requirementChecklist, ["Critical Analysis", "Argument Quality", "Counterarguments"]);
    var evidence = scoreForLabels(requirementChecklist, ["Evidence Usage", "Citation Placement"]);
    var formatting = scoreForLabels(requirementChecklist, ["Formatting Requirements"]);
    var language = scoreForLabels(requirementChecklist, ["Writing Tone", "Conclusion Quality"]);
    var tone = scoreForLabels(requirementChecklist, ["Writing Tone"]);
    var rubricAvg = avgScores(rubricChecklist);
    var penalty = 0;
    issues.forEach(function (issue) {
      if (issue.severity === "high" || issue.severity === "critical") penalty += 8;
      else if (issue.severity === "medium") penalty += 4;
    });
    var overall = Math.max(
      0,
      Math.round((structure + research + critical + evidence + formatting + language + tone + rubricAvg) / 8 - penalty)
    );
    return {
      structure: structure,
      research: research,
      critical_thinking: critical,
      evidence: evidence,
      formatting: formatting,
      language: language,
      academic_tone: tone,
      overall: overall,
    };
  }

  function buildRecommendations(issues, passed) {
    var recs = issues.map(function (issue) { return issue.suggested_fix; });
    if (passed) {
      recs.push("Proceed to citation generation after minor polish.");
    } else {
      recs.push("Send to Revision Engine to address high-severity issues before delivery.");
    }
    return recs;
  }

  function callOrchestratorReview(text) {
    return fetch("/api/ai/orchestrator/review", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: text || "" }),
    })
      .then(function (response) {
        return response.json().then(function (body) {
          if (!response.ok) {
            return {
              success: false,
              provider: "zerogpt",
              pipeline: null,
              review: {
                improved: false,
                originalAiScore: null,
                finalAiScore: null,
                humanizedText: null,
                message: (body && body.error) || "AI provider is unavailable",
                error: {
                  step: "provider-setup",
                  message: (body && body.error) || "AI provider is unavailable",
                },
              },
            };
          }
          return body;
        });
      })
      .catch(function (err) {
        return {
          success: false,
          provider: "zerogpt",
          pipeline: null,
          review: {
            improved: false,
            originalAiScore: null,
            finalAiScore: null,
            humanizedText: null,
            message: "AI provider is unavailable: " + (err && err.message ? err.message : "network error"),
            error: {
              step: "provider-setup",
              message: err && err.message ? err.message : "network error",
            },
          },
        };
      });
  }

  function attachOrchestratorData(report, orchestratorResult) {
    report.ai_orchestrator = orchestratorResult || null;
    if (!orchestratorResult || !orchestratorResult.review) {
      return report;
    }

    var review = orchestratorResult.review;
    report.ai_analysis = {
      original_ai_score: review.originalAiScore,
      final_ai_score: review.finalAiScore,
      improved: !!review.improved,
      humanized_text: review.humanizedText || "",
      review_message: review.message || "",
      provider: orchestratorResult.provider || "zerogpt",
      success: !!orchestratorResult.success,
    };

    if (!orchestratorResult.success) {
      report.recommendations = (report.recommendations || []).concat([review.message]);
    } else if (review.message) {
      report.recommendations = (report.recommendations || []).concat([review.message]);
    }

    return report;
  }

  function review(payload) {
    var req = normalizeRequirement(payload.requirementJson || payload.requirement_json || {});
    var plan = normalizeResearchPlan(payload.researchPlan || payload.research_plan || {});
    var blueprint = normalizeBlueprint(payload.blueprint || {});
    var draft = normalizeDraft(payload.draft || {});

    var reqChecklist = requirementChecklist(req, plan, blueprint, draft);
    var rubChecklist = rubricChecklist(req);
    var issues = buildIssues(draft.content, plan);
    var scores = qualityScores(reqChecklist, rubChecklist, issues);
    var hasHighSeverity = issues.some(function (issue) {
      return issue.severity === "high" || issue.severity === "critical";
    });
    var passed = scores.overall >= 75 && !hasHighSeverity;

    return {
      id: "review-" + Date.now() + "-" + Math.random().toString(16).slice(2, 8),
      project_id: payload.projectId || payload.project_id || null,
      overall_score: scores.overall,
      passed: passed,
      requirement_checklist: reqChecklist,
      rubric_checklist: rubChecklist,
      issues: issues,
      recommendations: buildRecommendations(issues, passed),
      quality_scores: scores,
      engine_version: VERSION,
      reviewed_at: new Date().toISOString(),
    };
  }

  function run(payload) {
    var draft = normalizeDraft(payload.draft || {});
    var baseReport = review(payload);

    return callOrchestratorReview(draft.content || "").then(function (orchestratorResult) {
      return new Promise(function (resolve) {
        setTimeout(function () {
          resolve(attachOrchestratorData(baseReport, orchestratorResult));
        }, 1200);
      });
    });
  }

  return {
    VERSION: VERSION,
    review: review,
    run: run,
  };
})();
