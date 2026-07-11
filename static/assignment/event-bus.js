/**
 * Assignment Event Bus
 * Independent communication layer for pipeline architecture.
 */
(function () {
  "use strict";

  function nowIso() {
    return new Date().toISOString();
  }

  function uuid() {
    return "evt-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 10);
  }

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function createEvent(payload) {
    payload = payload || {};
    return {
      id: payload.id || uuid(),
      projectId: payload.projectId || "unknown-project",
      timestamp: payload.timestamp || nowIso(),
      stage: payload.stage || "system",
      type: payload.type || "UnknownEvent",
      status: payload.status || "info",
      title: payload.title || payload.type || "Event",
      description: payload.description || "",
      metadata: payload.metadata || {},
    };
  }

  function AssignmentEventBus() {
    this.subscribers = new Set();
    this.events = [];
  }

  AssignmentEventBus.prototype.publish = function (payload) {
    var event = createEvent(payload);
    this.events.push(event);
    if (this.events.length > 2000) this.events.shift();
    var snapshot = this.getEvents();
    this.subscribers.forEach(function (handler) {
      handler(event, snapshot);
    });
    return event;
  };

  AssignmentEventBus.prototype.subscribe = function (handler) {
    var self = this;
    this.subscribers.add(handler);
    return function () {
      self.subscribers.delete(handler);
    };
  };

  AssignmentEventBus.prototype.getEvents = function () {
    return clone(this.events);
  };

  AssignmentEventBus.prototype.clear = function () {
    this.events = [];
  };

  window.AssignmentEventBus = AssignmentEventBus;
})();
