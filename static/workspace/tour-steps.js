/**
 * Guided tour step definitions — targets use [data-tour="..."] anchors.
 */
window.WSTourSteps = [
  {
    id: "welcome",
    title: "👋 Welcome to the Document Editor",
    body:
      "This one-minute tour shows how to humanize AI-flagged text, use the AI assistant, add citations and write together in real time. Reopen it anytime with the ? button in the top bar.",
    target: "[data-tour='editor-page']",
    tab: null,
    placement: "center",
  },
  {
    id: "toolbar",
    title: "A full word processor",
    body:
      "Write and format like in Word — headings, lists, tables, images, links. Everything autosaves (watch \"All changes saved\" next to the title), and you can export back to .docx anytime.",
    target: "[data-tour='toolbar']",
    tab: null,
    placement: "bottom",
  },
  {
    id: "coins",
    title: "Your coins wallet",
    body:
      "Humanize, AI detection and other actions are paid with coins. Top up anytime — your balance stays valid for 30 days after each purchase.",
    target: "[data-tour='coins']",
    tab: null,
    placement: "bottom",
  },
  {
    id: "mark",
    title: "Step 1 — mark what to humanize",
    body:
      "Select text in the document, then click Mark selection. Marked passages stay highlighted until you humanize or unmark them. One batch run saves coins.",
    target: "[data-tour='mark-selection']",
    tab: "humanize",
    placement: "left",
  },
  {
    id: "mark-all",
    title: "Mark everything first — it saves coins",
    body:
      "Don't humanize piece by piece! Running each paragraph separately charges a full call every time. Mark everything you need first and run once — many small selections humanize together for the same price.",
    target: "[data-tour='mark-all']",
    tab: "humanize",
    placement: "left",
    warn: true,
  },
  {
    id: "detect",
    title: "Detect AI",
    body:
      "Not sure what a detector would flag? Run our built-in AI check on the whole document: likely AI-written parts come back as purple highlights with an overall AI score. Costs 10 coins per check.",
    target: "[data-tour='detect-ai']",
    tab: "humanize",
    placement: "left",
  },
  {
    id: "highlights",
    title: "Your AI report highlights",
    body:
      "Violet highlights are parts our detector flagged as likely AI-written. Jump between them, toggle visibility, or mark all flagged parts for humanization in one click.",
    target: "[data-tour='ai-highlights']",
    tab: "humanize",
    placement: "left",
  },
  {
    id: "humanize-run",
    title: "Step 2 — run humanization",
    body:
      "When you're ready, click Humanize marked selections. You'll see a cost confirmation, then a short lock while we rewrite. Success shows green highlights; failures are refunded.",
    target: "[data-tour='humanize-run']",
    tab: "humanize",
    placement: "left",
  },
  {
    id: "ai-tab",
    title: "AI writing assistant",
    body:
      "Select text, pick an action (Improve, Paraphrase, Shorten…), preview the result below, then Replace selection when you're happy. Costs 0.1 coin per 500 words selected.",
    target: "[data-tour='ai-panel']",
    tab: "ai",
    placement: "left",
  },
  {
    id: "cite",
    title: "Real citations",
    body:
      "Search real published papers (via CrossRef) and insert APA, MLA or Harvard citations with one click. Scan your document to catch missing or mismatched references.",
    target: "[data-tour='cite-panel']",
    tab: "cite",
    placement: "left",
  },
  {
    id: "share",
    title: "Live collaboration",
    body:
      "Share with up to 5 people and edit in real time. Everyone sees the same highlights, comments and version history.",
    target: "[data-tour='share']",
    tab: null,
    placement: "bottom",
  },
  {
    id: "comments",
    title: "Comments",
    body:
      "Select text and leave threaded comments — the selected text is kept as a quote you can jump back to. Great for feedback from collaborators.",
    target: "[data-tour='comments-panel']",
    tab: "comments",
    placement: "left",
  },
  {
    id: "history",
    title: "Document timeline",
    body:
      "Every editing session, import, humanize run and restore gets its own version. Preview any of them and restore with one click — you can always go back.",
    target: "[data-tour='history']",
    tab: null,
    placement: "bottom",
  },
  {
    id: "export",
    title: "Export when you're done",
    body:
      "Download the document as .docx — images, tables and formatting included. Your highlights and comments are stripped for a clean submission file.",
    target: "[data-tour='export']",
    tab: null,
    placement: "bottom",
  },
  {
    id: "done",
    title: "You're all set",
    body:
      "Start writing, mark AI parts, humanize in one batch, and export when ready. Reopen this tour anytime from the help button.",
    target: "[data-tour='editor-page']",
    tab: null,
    placement: "center",
    last: true,
  },
];
