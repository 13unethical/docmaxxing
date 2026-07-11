/**
 * Assignment Pipeline Orchestrator
 * Single source of truth for assignment workflow state.
 */
(function () {
  "use strict";

  var EventBus = window.AssignmentEventBus;

  var STAGES = [
    { id: "requirement_analysis", title: "Requirement Analysis" },
    { id: "research_blueprint", title: "Research & Blueprint" },
    { id: "writing", title: "Writing" },
    { id: "humanization", title: "Humanization" },
    { id: "academic_review", title: "Academic Review" },
    { id: "ai_detection", title: "AI Detection" },
    { id: "delivery", title: "Delivery" },
  ];

  function nowIso() {
    return new Date().toISOString();
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function createEmptyProjectState(input) {
    input = input || {};
    var now = nowIso();
    return {
      id: "proj-" + Date.now().toString(36),
      title: input.title || "Assignment Project",
      status: "queued",
      progress: 0,
      currentStage: null,
      createdAt: now,
      updatedAt: now,
      uploadedFiles: {
        assignmentBrief: [],
        rubric: [],
        lectureSlides: [],
        readingMaterials: [],
        sampleAssignment: [],
        professorNotes: [],
        additionalFiles: [],
      },
      requirementAnalysis: {
        requirementJson: null,
        missingInformation: [],
        complexity: null,
        estimatedPrice: null,
      },
      research: {
        researchPlan: null,
      },
      blueprint: {
        blueprint: null,
      },
      writing: {
        draftVersions: [],
        currentDraft: null,
        writingProgress: 0,
        completedSections: [],
      },
      humanization: {
        humanizedDraft: null,
        humanizationHistory: [],
        paragraphStatus: [],
      },
      academicReview: {
        reviewHistory: [],
        latestReview: null,
        reviewScore: null,
      },
      aiDetection: {
        detectionHistory: [],
        latestDetection: null,
        overallAIScore: null,
        paragraphScores: [],
      },
      delivery: {
        deliveryPackage: null,
        downloadLinks: [],
        completionTime: null,
      },
    };
  }
  
  function createImmutableProject(input) {
    input = input || {};
    var now = nowIso();
    var name = input.title || "Assignment Project";
    return {
      id: "proj-" + Date.now().toString(36),
      createdAt: now,
      owner: input.owner || "local-user",
      projectName: name,
      assignmentInformation: {
        assignmentType: input.assignmentType || null,
        deadline: input.deadline || null,
        university: input.university || null,
        module: input.module || null,
        professor: input.professor || null,
      },
      uploadedFiles: {
        assignmentBrief: [],
        rubric: [],
        lectureSlides: [],
        readingMaterials: [],
        sampleAssignments: [],
        professorNotes: [],
        additionalFiles: [],
      },
      originalUserSettings: {
        targetWords: input.targetWords || null,
        citationStyle: input.citationStyle || null,
        preferredEnglish: input.preferredEnglish || null,
        requestedGrade: input.requestedGrade || null,
        additionalInstructions: input.note || null,
      },
      requirementAnalysis: {
        requirementJson: null,
      },
    };
  }

  function createRuntimeProject() {
    return {
      pipeline: {
        currentStage: null,
        progress: 0,
        status: "queued",
      },
      research: {
        researchPlan: null,
      },
      blueprint: {
        blueprint: null,
      },
      writing: {
        drafts: [],
        currentDraft: null,
        completedSections: [],
      },
      humanization: {
        humanizedDraft: null,
        paragraphHistory: [],
      },
      academicReview: {
        reviewHistory: [],
        latestReview: null,
      },
      aiDetection: {
        detectionHistory: [],
        latestDetection: null,
      },
      delivery: {
        package: null,
        downloadLinks: [],
      },
      logs: {
        events: [],
        errors: [],
      },
      metrics: {
        totalDuration: 0,
        totalTokens: 0,
        totalCost: 0,
      },
    };
  }

  function applyInputFiles(projectState, input) {
    var files = (input && input.files) || [];
    files.forEach(function (file) {
      var row = { name: file.name || "file", size: file.size || 0, source: file.source || "" };
      var source = String(file.source || "").toLowerCase();
      if (source.indexOf("assignment brief") >= 0) projectState.uploadedFiles.assignmentBrief.push(row);
      else if (source.indexOf("rubric") >= 0) projectState.uploadedFiles.rubric.push(row);
      else if (source.indexOf("lecture") >= 0) projectState.uploadedFiles.lectureSlides.push(row);
      else if (source.indexOf("reading") >= 0) projectState.uploadedFiles.readingMaterials.push(row);
      else if (source.indexOf("sample") >= 0) projectState.uploadedFiles.sampleAssignments.push(row);
      else if (source.indexOf("professor") >= 0) projectState.uploadedFiles.professorNotes.push(row);
      else projectState.uploadedFiles.additionalFiles.push(row);
    });
  }

  function createStageState(stage) {
    return {
      id: stage.id,
      title: stage.title,
      status: "queued",
      startedAt: null,
      completedAt: null,
      duration: 0,
      progress: 0,
      logs: [],
    };
  }

  function AssignmentPipelineManager(options) {
    options = options || {};
    this.runners = options.runners || {};
    this.subscribers = new Set();
    this.eventBus = options.eventBus || (EventBus ? new EventBus() : null);
    this.state = {
      stages: STAGES.map(createStageState),
      stageOrder: STAGES.map(function (stage) { return stage.id; }),
      activeStageId: null,
      immutableProject: createImmutableProject(options.initialInput || {}),
      runtimeProject: createRuntimeProject(),
      immutableLocked: false,
      status: "idle",
      error: null,
      updatedAt: nowIso(),
    };
    this.currentIndex = 0;
    this.baseInput = null;
    this.projectId = this.state.immutableProject.id;
    if (this.eventBus) {
      this.eventBus.publish({
        projectId: this.projectId,
        stage: "project",
        type: "ProjectCreated",
        status: "completed",
        title: "Project Created",
        description: "Assignment project initialized",
        metadata: { projectName: this.state.immutableProject.projectName },
      });
    }
  }

  AssignmentPipelineManager.prototype.subscribe = function (handler) {
    var self = this;
    this.subscribers.add(handler);
    handler(this.getState());
    return function () {
      self.subscribers.delete(handler);
    };
  };

  AssignmentPipelineManager.prototype.getState = function () {
    return clone(this.state);
  };

  AssignmentPipelineManager.prototype.emit = function () {
    this.state.updatedAt = nowIso();
    var snapshot = this.getState();
    this.subscribers.forEach(function (handler) {
      handler(snapshot);
    });
  };

  AssignmentPipelineManager.prototype.publishEvent = function (payload) {
    if (!this.eventBus) return null;
    var evt = this.eventBus.publish(payload);
    if (this.state.runtimeProject && this.state.runtimeProject.logs) {
      this.state.runtimeProject.logs.events.push({
        at: evt.timestamp,
        stage: evt.stage,
        type: evt.type,
        status: evt.status,
        title: evt.title,
        description: evt.description,
      });
      if (evt.status === "failed") {
        this.state.runtimeProject.logs.errors.push({
          at: evt.timestamp,
          stage: evt.stage,
          message: evt.description || evt.title || evt.type,
        });
      }
    }
    return evt;
  };

  AssignmentPipelineManager.prototype.reset = function () {
    this.state.stages = STAGES.map(createStageState);
    this.state.activeStageId = null;
    this.state.status = "idle";
    this.state.error = null;
    this.state.immutableProject = createImmutableProject(this.baseInput || {});
    this.state.runtimeProject = createRuntimeProject();
    this.state.immutableLocked = false;
    this.currentIndex = 0;
    this.baseInput = null;
    this.projectId = this.state.immutableProject.id;
    if (this.eventBus) this.eventBus.clear();
    this.publishEvent({
      projectId: this.projectId,
      stage: "project",
      type: "ProjectCreated",
      status: "completed",
      title: "Project Created",
      description: "Assignment project initialized",
      metadata: { projectName: this.state.immutableProject.projectName },
    });
    this.emit();
  };

  AssignmentPipelineManager.prototype.initialize = function (input) {
    if (!this.baseInput) {
      this.baseInput = clone(input || {});
      this.state.immutableProject = createImmutableProject(this.baseInput);
      applyInputFiles(this.state.immutableProject, this.baseInput);
      this.state.runtimeProject = createRuntimeProject();
      this.projectId = this.state.immutableProject.id;
      this.publishEvent({
        projectId: this.projectId,
        stage: "project",
        type: "FilesUploaded",
        status: "completed",
        title: "Files Uploaded",
        description: "Project files were added",
        metadata: { fileCount: ((this.baseInput && this.baseInput.files) || []).length },
      });
      this.publishEvent({
        projectId: this.projectId,
        stage: "project",
        type: "FilesParsed",
        status: "completed",
        title: "Files Parsed",
        description: "Uploaded files parsed for pipeline intake",
        metadata: {},
      });
    }
  };

  AssignmentPipelineManager.prototype.getStage = function (id) {
    return this.state.stages.find(function (stage) { return stage.id === id; }) || null;
  };

  AssignmentPipelineManager.prototype.log = function (stage, message) {
    stage.logs.push("[" + new Date().toLocaleTimeString() + "] " + message);
    if (stage.logs.length > 30) stage.logs.shift();
    this.emit();
  };

  AssignmentPipelineManager.prototype.setProgress = function (stage, value) {
    stage.progress = Math.max(0, Math.min(100, Math.round(value)));
    this.emit();
  };

  AssignmentPipelineManager.prototype.simulateProgress = function (stage, endValue) {
    var self = this;
    return new Promise(function (resolve) {
      var target = endValue || 95;
      var value = stage.progress;
      function tick() {
        value += Math.max(1, Math.round((target - value) * 0.2));
        if (value >= target) {
          self.setProgress(stage, target);
          resolve();
          return;
        }
        self.setProgress(stage, value);
        setTimeout(tick, 120);
      }
      tick();
    });
  };

  AssignmentPipelineManager.prototype.runUntil = async function (targetStageId, input) {
    if (this.state.status === "running") return;
    this.initialize(input || this.baseInput || {});
    this.state.status = "running";
    this.emit();
    var targetIndex = targetStageId
      ? this.state.stageOrder.indexOf(targetStageId)
      : this.state.stageOrder.length - 1;
    if (targetIndex < 0) targetIndex = this.state.stageOrder.length - 1;

    while (this.currentIndex <= targetIndex && this.currentIndex < this.state.stageOrder.length) {
      var stageId = this.state.stageOrder[this.currentIndex];
      await this.runStage(stageId);
      var stage = this.getStage(stageId);
      if (!stage || stage.status === "failed") {
        this.state.status = "failed";
        this.emit();
        return;
      }
      this.currentIndex += 1;
    }

    this.state.status = this.currentIndex >= this.state.stageOrder.length ? "completed" : "paused";
    this.state.activeStageId = null;
    this.emit();
  };

  AssignmentPipelineManager.prototype.resume = async function () {
    return this.runUntil(null, this.baseInput || {});
  };

  AssignmentPipelineManager.prototype.runStage = async function (stageId) {
    var stage = this.getStage(stageId);
    if (!stage) return;
    if (stage.status === "completed") return;
    this.state.activeStageId = stageId;
    this.state.error = null;
    stage.status = "running";
    stage.startedAt = nowIso();
    stage.progress = Math.max(5, stage.progress);
    this.log(stage, "Stage started");
    this.publishEvent(this.mapStageEvent(stageId, "started"));
    this.emit();

    try {
      var runner = this.runners[stageId];
      if (typeof runner !== "function") {
        throw new Error("Missing stage runner: " + stageId);
      }
      await this.simulateProgress(stage, 70);
      var nextProjectState = await runner({
        input: clone(this.baseInput || {}),
        immutableProject: clone(this.state.immutableProject),
        runtimeProject: clone(this.state.runtimeProject),
        stage: clone(stage),
        publishEvent: this.publishEvent.bind(this),
        projectId: this.projectId || this.state.immutableProject.id,
      });
      await this.simulateProgress(stage, 95);
      this.storeProjectState(stageId, nextProjectState);
      stage.status = "completed";
      stage.progress = 100;
      stage.completedAt = nowIso();
      stage.duration = Math.max(
        1,
        Math.round((new Date(stage.completedAt).getTime() - new Date(stage.startedAt).getTime()) / 1000)
      );
      this.log(stage, "Stage completed");
      this.publishEvent(this.mapStageEvent(stageId, "completed", { duration: stage.duration }));
      this.emit();
    } catch (error) {
      stage.status = "failed";
      stage.completedAt = nowIso();
      stage.duration = Math.max(
        1,
        Math.round((new Date(stage.completedAt).getTime() - new Date(stage.startedAt).getTime()) / 1000)
      );
      this.state.error = error && error.message ? error.message : "Stage failed";
      this.log(stage, "Failed: " + this.state.error);
      this.publishEvent(this.mapStageEvent(stageId, "failed", { error: this.state.error }));
      this.emit();
      throw error;
    }
  };

  AssignmentPipelineManager.prototype.mapStageEvent = function (stageId, phase, extra) {
    var map = {
      requirement_analysis: {
        started: ["RequirementAnalysisStarted", "Requirement Analysis Started"],
        completed: ["RequirementAnalysisCompleted", "Requirement Analysis Completed"],
        failed: ["RequirementAnalysisFailed", "Requirement Analysis Failed"],
      },
      research_blueprint: {
        started: ["ResearchStarted", "Research Started"],
        completed: ["BlueprintCompleted", "Research & Blueprint Completed"],
        failed: ["ProjectFailed", "Research & Blueprint Failed"],
      },
      writing: {
        started: ["WritingStarted", "Writing Started"],
        completed: ["WritingCompleted", "Writing Completed"],
        failed: ["ProjectFailed", "Writing Failed"],
      },
      humanization: {
        started: ["HumanizationStarted", "Humanization Started"],
        completed: ["HumanizationCompleted", "Humanization Completed"],
        failed: ["ProjectFailed", "Humanization Failed"],
      },
      academic_review: {
        started: ["AcademicReviewStarted", "Academic Review Started"],
        completed: ["AcademicReviewCompleted", "Academic Review Completed"],
        failed: ["ProjectFailed", "Academic Review Failed"],
      },
      ai_detection: {
        started: ["AIDetectionStarted", "AI Detection Started"],
        completed: ["AIDetectionCompleted", "AI Detection Completed"],
        failed: ["ProjectFailed", "AI Detection Failed"],
      },
      delivery: {
        started: ["DeliveryStarted", "Delivery Started"],
        completed: ["DeliveryCompleted", "Delivery Completed"],
        failed: ["ProjectFailed", "Delivery Failed"],
      },
    };
    var tuple = (map[stageId] && map[stageId][phase]) || ["UnknownEvent", "Event"];
    return {
      projectId: this.projectId || this.state.immutableProject.id,
      stage: stageId,
      type: tuple[0],
      status: phase === "failed" ? "failed" : phase === "started" ? "running" : "completed",
      title: tuple[1],
      description: tuple[1],
      metadata: extra || {},
    };
  };

  AssignmentPipelineManager.prototype.storeProjectState = function (stageId, payload) {
    if (!payload || typeof payload !== "object" || !payload.runtimeProject) {
      throw new Error("Stage " + stageId + " must return { runtimeProject }");
    }
    if (payload.immutableProject && !this.state.immutableLocked) {
      this.state.immutableProject = clone(payload.immutableProject);
    }
    if (stageId === "requirement_analysis") {
      this.state.immutableLocked = true;
    }
    this.state.runtimeProject = clone(payload.runtimeProject);
    this.state.runtimeProject.pipeline.currentStage = stageId;
    this.state.runtimeProject.pipeline.progress = Math.round(
      ((this.currentIndex + 1) / this.state.stageOrder.length) * 100
    );
    this.state.runtimeProject.pipeline.status =
      this.currentIndex + 1 >= this.state.stageOrder.length ? "completed" : "running";
    this.state.runtimeProject.logs.events.push({
      at: nowIso(),
      stage: stageId,
      message: "Stage completed",
    });
    if (stageId === "delivery" && this.state.runtimeProject.pipeline.status === "completed") {
      this.publishEvent({
        projectId: this.projectId || this.state.immutableProject.id,
        stage: "project",
        type: "ProjectCompleted",
        status: "completed",
        title: "Project Completed",
        description: "Assignment pipeline finished successfully",
        metadata: {},
      });
    }
  };

  AssignmentPipelineManager.prototype.getEventBus = function () {
    return this.eventBus;
  };

  window.AssignmentPipelineManager = AssignmentPipelineManager;
})();
