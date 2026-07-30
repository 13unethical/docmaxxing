/**
 * Guided tour catalogs per DocMaxxing service page.
 * Keys must match data-dm-tour-page on the page root.
 */
window.DMTourCatalog = {
  format: {
    storageKey: "docmaxxing_tour_format_done",
    autoStart: false,
    steps: [
      {
        id: "welcome",
        title: "👋 Welcome to Format",
        body: "Format turns your brief + draft into a clean academic DOCX — fonts, margins, cover page, references, and citations. This short tour shows each part.",
        target: "[data-tour='format-page']",
        placement: "center",
      },
      {
        id: "brief",
        title: "1. Requirements",
        body: "Paste your assignment brief or upload a PDF/DOCX/image. We use it to detect style, word limits, and required sections.",
        target: "[data-tour='format-brief']",
        placement: "right",
      },
      {
        id: "text-settings",
        title: "2. Text & layout",
        body: "Open Text settings to pick Harvard / APA / MLA presets, or customize font, size, spacing, and margins.",
        target: "[data-tour='format-text']",
        placement: "right",
      },
      {
        id: "document",
        title: "3. Your document",
        body: "Paste the essay body or upload a .docx. This is the content that will be reformatted.",
        target: "[data-tour='format-doc']",
        placement: "left",
      },
      {
        id: "advanced",
        title: "4. Cover, references & citations",
        body: "Optional panels below let you add a cover page, generate a reference list, and insert in-text citations.",
        target: "[data-tour='format-advanced']",
        placement: "top",
      },
      {
        id: "run",
        title: "5. Format document",
        body: "When everything looks right, click Format document. Download the DOCX when it’s ready — Format itself is free.",
        target: "[data-tour='format-run']",
        placement: "top",
        last: true,
      },
    ],
  },

  humanizer: {
    storageKey: "docmaxxing_tour_humanizer_done",
    autoStart: false,
    steps: [
      {
        id: "welcome",
        title: "👋 Welcome to Humanizer",
        body: "Humanizer rewrites AI-sounding prose into more natural academic English via StealthWriter. Here’s how to use it.",
        target: "[data-tour='hz-page']",
        placement: "center",
      },
      {
        id: "source",
        title: "1. Paste or upload",
        body: "Switch between Paste Text and Upload DOC. Large texts are handled in batches up to ~5,000 words.",
        target: "[data-tour='hz-source']",
        placement: "bottom",
      },
      {
        id: "input",
        title: "2. Your draft",
        body: "Paste the paragraphs you want rewritten. Watch the word count — you’ll confirm cost before the run starts.",
        target: "[data-tour='hz-input']",
        placement: "right",
      },
      {
        id: "run",
        title: "3. Humanize",
        body: "Click Humanize to start. This spends credits (usually 10). Failed jobs that never run are refunded.",
        target: "[data-tour='hz-run']",
        placement: "top",
      },
      {
        id: "result",
        title: "4. Result & copy",
        body: "After a successful run, the rewritten text appears on the right. Copy it, tweak formatting with the toolbar, then paste back into your document.",
        target: "[data-hz-stage]",
        placement: "left",
        last: true,
      },
    ],
  },

  assignment: {
    storageKey: "docmaxxing_tour_assignment_done",
    autoStart: false,
    steps: [
      {
        id: "welcome",
        title: "👋 Welcome to Assignment",
        body: "Upload a brief, get a price, pay once, then we research → write → cite → humanize → format → deliver a ZIP.",
        target: "[data-tour='asg-page']",
        placement: "center",
      },
      {
        id: "brief",
        title: "1. Requirements file",
        body: "Drop your assignment brief (PDF or DOCX). Extra materials are optional — lecture notes, rubrics, samples.",
        target: "[data-tour='asg-brief']",
        placement: "bottom",
      },
      {
        id: "deadline",
        title: "2. Deadline & notes",
        body: "Set the deadline and any notes for the writer (tone, must-include sources, preferred structure).",
        target: "[data-tour='asg-deadline']",
        placement: "bottom",
      },
      {
        id: "analyze",
        title: "3. Analyze & get price",
        body: "We parse the brief, estimate words/complexity, and show a credit price in Project Summary before you pay.",
        target: "[data-tour='asg-analyze']",
        placement: "top",
      },
      {
        id: "summary",
        title: "4. Project Summary",
        body: "Words, type, complexity, ETA, and Total stay pinned on the right. Review them before Start Writing.",
        target: "[data-tour='asg-summary']",
        placement: "left",
      },
      {
        id: "start",
        title: "5. Start Writing",
        body: "After payment, the pipeline runs automatically. When it’s ready, download the assignment ZIP from this page.",
        target: "[data-tour='asg-start']",
        placement: "left",
        last: true,
      },
    ],
  },

  turnitin: {
    storageKey: "docmaxxing_tour_turnitin_done",
    autoStart: false,
    steps: [
      {
        id: "welcome",
        title: "👋 Welcome to Turnitin",
        body: "Run a similarity-style check on your files with credit-based reports. Here’s the flow.",
        target: "[data-tour='tt-page']",
        placement: "center",
      },
      {
        id: "options",
        title: "1. Exclude options",
        body: "Toggle Exclude Bibliography / Quotes so reference lists and quoted material don’t inflate the score.",
        target: "[data-tour='tt-options']",
        placement: "bottom",
      },
      {
        id: "submit",
        title: "2. Submit files",
        body: "Click Submit Files and pick DOC/PDF/TXT. Each check spends credits (shown on the button).",
        target: "[data-tour='tt-submit']",
        placement: "bottom",
      },
      {
        id: "status",
        title: "3. Status updates",
        body: "Progress and errors appear here while the provider processes your upload.",
        target: "[data-tour='tt-status']",
        placement: "bottom",
      },
      {
        id: "reports",
        title: "4. My Reports",
        body: "Finished checks land in this table. Download the report when status is ready — search helps find older runs.",
        target: "[data-tour='tt-reports']",
        placement: "top",
        last: true,
      },
    ],
  },

  check: {
    storageKey: "docmaxxing_tour_check_done",
    autoStart: false,
    steps: [
      {
        id: "welcome",
        title: "👋 Welcome to Academic Check",
        body: "Check compares your draft against the brief — word count, style, sections, and other requirements.",
        target: "[data-tour='check-page']",
        placement: "center",
      },
      {
        id: "brief",
        title: "1. Requirements",
        body: "Paste the brief/rubric or upload a file so we know what “correct” looks like.",
        target: "[data-tour='check-brief']",
        placement: "right",
      },
      {
        id: "doc",
        title: "2. Document input",
        body: "Choose document type, then paste text or upload the draft you want checked.",
        target: "[data-tour='check-doc']",
        placement: "left",
      },
      {
        id: "run",
        title: "3. Run check",
        body: "Click Check document. Results show a score plus fix suggestions you can apply back to Format.",
        target: "[data-tour='check-run']",
        placement: "top",
        last: true,
      },
    ],
  },
};
