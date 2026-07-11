/**
 * Mock service layer — replace with real API clients later.
 */
window.WSMock = (function () {
  "use strict";

  var COINS_KEY = "docmaxxing_workspace_coins";
  var DRAFT_KEY = "docmaxxing_workspace_draft";

  var SAMPLE_HTML =
    '<h1>The Impact of Renewable Energy on Modern Power Grids</h1>' +
    "<p>Renewable energy sources are transforming how electricity is generated and distributed across modern power systems.</p>" +
    "<h2>Introduction</h2>" +
    '<p>Over the past decade, solar and wind capacity has grown rapidly worldwide. ' +
    '<span class="ws-ai-highlight" data-ai-part="1">Governments and utilities are investing heavily in grid modernization to accommodate variable generation from renewables.</span> ' +
    "This shift requires new planning tools, storage solutions, and regulatory frameworks. " +
    '<span class="ws-ai-highlight" data-ai-part="2">Understanding these dynamics is essential for policymakers, engineers, and researchers working on sustainable energy transitions.</span></p>';

  function getCoins() {
    try {
      var raw = localStorage.getItem(COINS_KEY);
      if (raw == null) {
        localStorage.setItem(COINS_KEY, "0");
        return 0;
      }
      var n = parseInt(raw, 10);
      return isNaN(n) ? 0 : n;
    } catch (e) {
      return 0;
    }
  }

  function setCoins(n) {
    try {
      localStorage.setItem(COINS_KEY, String(n));
    } catch (e) {
      /* ignore */
    }
  }

  function loadDraft() {
    try {
      var raw = sessionStorage.getItem(DRAFT_KEY) || localStorage.getItem(DRAFT_KEY);
      if (!raw) {
        return null;
      }
      return JSON.parse(raw);
    } catch (e) {
      return null;
    }
  }

  function saveDraft(payload) {
    try {
      var json = JSON.stringify(payload);
      sessionStorage.setItem(DRAFT_KEY, json);
      localStorage.setItem(DRAFT_KEY, json);
    } catch (e) {
      /* ignore */
    }
  }

  function humanizePreview(text, style) {
    return (
      "[Mock humanized — " +
      (style || "Academic") +
      "]\n\n" +
      String(text || "")
        .replace(/\s+/g, " ")
        .trim()
    );
  }

  function aiAssistPreview(action, text) {
    return (
      "[Mock " +
      action +
      "]\n\n" +
      String(text || "")
        .slice(0, 600)
        .trim()
    );
  }

  function detectAI() {
    return {
      score: 34,
      flaggedParts: 2,
      flaggedWords: 90,
      highlights: [1, 2],
    };
  }

  function searchCitations(query) {
    return [
      {
        title: "Attention Is All You Need",
        authors: "Vaswani et al.",
        year: "2017",
        doi: "10.48550/arXiv.1706.03762",
      },
    ].filter(function (item) {
      return !query || item.title.toLowerCase().includes(String(query).toLowerCase());
    });
  }

  function scanCitations() {
    return { found: 3, issues: 1, style: "APA 7" };
  }

  return {
    COINS_KEY: COINS_KEY,
    DRAFT_KEY: DRAFT_KEY,
    SAMPLE_HTML: SAMPLE_HTML,
    SAMPLE_TITLE: "Welcome tour — sample document",
    getCoins: getCoins,
    setCoins: setCoins,
    loadDraft: loadDraft,
    saveDraft: saveDraft,
    humanizePreview: humanizePreview,
    aiAssistPreview: aiAssistPreview,
    detectAI: detectAI,
    searchCitations: searchCitations,
    scanCitations: scanCitations,
    HUMANIZE_COST: 10,
    DETECT_COST: 10,
    AI_COST_PER_500: 0.1,
  };
})();
