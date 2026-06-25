/**
 * Before / After HTML preview from plain text + formatter settings.
 */
(function (global) {
  var SAMPLE =
    "Effects of Sleep on Academic Performance\n\nIntroduction\n\nSleep quality affects memory consolidation and exam results. This paper reviews recent findings.\n\nBody\n\nStudents who sleep seven to nine hours perform better on assessments (Smith, 2023). Poor sleep is linked to lower GPA.\n\nReferences\n\nSmith, J. (2023). Sleep and learning. Journal of Education, 12(2), 45–60.";

  function splitParagraphs(text) {
    return String(text || "")
      .trim()
      .split(/\n\s*\n/)
      .map(function (p) {
        return p.trim();
      })
      .filter(Boolean);
  }

  function isHeadingLine(text, index) {
    var t = (text || "").trim();
    if (!t) {
      return false;
    }
    // When heading and body share one pasted block, judge the first line only.
    var firstLine = t.split(/\n/)[0].trim();
    var line = firstLine || t;
    var words = line.split(/\s+/);
    var normalized = line.toLowerCase().replace(/\s+/g, " ");
    var common = {
      introduction: 1,
      conclusion: 1,
      methods: 1,
      results: 1,
      discussion: 1,
      references: 1,
      bibliography: 1,
      reflection: 1,
      "works cited": 1,
    };
    // Numbered report sections: "1. Introduction", "4.Main problem", etc.
    if (/^\d+(?:\.\d+)*\.?\s*[A-Za-z]/.test(line)) {
      return true;
    }
    // Learning-journal section titles (long descriptive lines).
    if (/^this\s+journal entry\b/i.test(line)) {
      return true;
    }
    if (/^the students make journal entries\b/i.test(line)) {
      return true;
    }
    if (/^journal entry\s+\d+(\s|:)/i.test(line)) {
      return true;
    }
    if (/journal entry\s*[–\-—:]/i.test(line)) {
      return true;
    }
    if (/^a\s+.+\bjournal entry\b/i.test(line)) {
      return true;
    }
    // Other numbered section labels: "Section 2: …", "Part 3: …".
    if (/^(section|part|chapter|unit|module|week|entry)\s+\d+\s*:/i.test(line)) {
      return true;
    }
    // "Reflection:" / "References:" style labels.
    if (/^(reflection|references|bibliography|works cited|abstract|appendix)\s*:?\s*$/i.test(line)) {
      return true;
    }
    if (index === 0 && words.length >= 6 && !/\.$/.test(line) && !common[normalized]) {
      return true;
    }
    if (common[normalized]) {
      return true;
    }
    if (/[A-Za-z]/.test(line) && line === line.toUpperCase()) {
      return true;
    }
    if (words.length <= 5 && !/\.$/.test(line)) {
      var stop = {
        a: 1,
        an: 1,
        and: 1,
        are: 1,
        as: 1,
        at: 1,
        by: 1,
        for: 1,
        from: 1,
        in: 1,
        is: 1,
        it: 1,
        of: 1,
        on: 1,
        or: 1,
        that: 1,
        the: 1,
        this: 1,
        to: 1,
        was: 1,
        were: 1,
        with: 1,
      };
      var hasStop = words.some(function (w) {
        return !!stop[w.toLowerCase()];
      });
      if (!hasStop) {
        return true;
      }
    }
    return false;
  }

  function splitHeadingBodyBlock(text) {
    var t = (text || "").trim();
    if (!t || t.indexOf("\n") < 0) {
      return [t];
    }
    var firstLine = t.split(/\n/)[0].trim();
    var rest = t.slice(t.indexOf("\n") + 1).trim();
    if (firstLine && rest && isHeadingLine(firstLine, 0)) {
      return [firstLine, rest];
    }
    return [t];
  }

  function lineHeightFromSpacing(ls) {
    var n = parseFloat(String(ls)) || 1.5;
    return Math.round(n * 100) / 100;
  }

  function buildBeforeHtml(text) {
    var paras = splitParagraphs(text || SAMPLE);
    var html = paras
      .map(function (p) {
        return '<p class="preview-p preview-p--raw">' + escapeHtml(p) + "</p>";
      })
      .join("");
    return (
      '<div class="preview-doc preview-doc--before" style="font-family:Calibri,sans-serif;font-size:11pt;line-height:1.15;text-align:left;">' +
      html +
      "</div>"
    );
  }

  function buildAfterHtml(text, settings) {
    var cfg = settings || {};
    var paras = splitParagraphs(text || SAMPLE);
    var font = cfg.font_family || "Times New Roman";
    var size = cfg.font_size || "12";
    var lh = lineHeightFromSpacing(cfg.line_spacing || "1.5");
    var align = cfg.align || cfg.alignment || "left";
    var indent = cfg.first_line_indent ? "2em" : "0";
    var blocks = [];
    paras.forEach(function (p) {
      splitHeadingBodyBlock(p).forEach(function (block) {
        blocks.push(block);
      });
    });
    var html = blocks
      .map(function (p, i) {
        var cls = isHeadingLine(p, i) ? "preview-p preview-p--heading" : "preview-p preview-p--body";
        var tag = cls.indexOf("heading") >= 0 ? "h3" : "p";
        var extra =
          tag === "p"
            ? "text-indent:" + indent + ";"
            : "font-size:16pt;font-weight:700;text-align:left;";
        return (
          "<" +
          tag +
          ' class="' +
          cls +
          '" style="' +
          extra +
          '">' +
          escapeHtml(p) +
          "</" +
          tag +
          ">"
        );
      })
      .join("");
    return (
      '<div class="preview-doc preview-doc--after" style="font-family:' +
      escapeAttr(font) +
      ",serif;font-size:" +
      size +
      "pt;line-height:" +
      lh +
      ";text-align:" +
      align +
      ';">' +
      html +
      "</div>"
    );
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeAttr(s) {
    return String(s).replace(/"/g, "&quot;");
  }

  function diffSummary(beforeSettings, afterSettings) {
    var items = [];
    var b = beforeSettings || {};
    var a = afterSettings || {};
    if ((a.font_family || "") !== (b.font_family || "Calibri")) {
      items.push("Font → " + (a.font_family || "—"));
    }
    if (String(a.font_size) !== String(b.font_size || "11")) {
      items.push("Size → " + (a.font_size || "—") + " pt");
    }
    if (String(a.line_spacing) !== String(b.line_spacing || "1.15")) {
      items.push("Line spacing → " + (a.line_spacing || "—"));
    }
    if ((a.alignment || a.align) !== (b.alignment || "left")) {
      items.push("Alignment → " + (a.alignment || a.align || "—"));
    }
    if (!!a.first_line_indent !== !!b.first_line_indent) {
      items.push(a.first_line_indent ? "First-line indent enabled" : "First-line indent removed");
    }
    if (a.auto_headings) {
      items.push("Auto-detect headings → Heading styles");
    }
    if (a.citationStyle) {
      items.push("Reference list style → " + a.citationStyle);
    }
    return items;
  }

  function renderPreviewPair(container, text, settings) {
    if (!container) {
      return Promise.resolve();
    }
    var beforeEl = container.querySelector("[data-preview-before]");
    var afterEl = container.querySelector("[data-preview-after]");
    var diffEl = container.querySelector("[data-preview-diff]");
    var sample = (text || "").trim() || SAMPLE;
    if (beforeEl) {
      beforeEl.innerHTML = buildBeforeHtml(sample);
    }
    var afterPromise = Promise.resolve();
    if (afterEl) {
      afterEl.innerHTML = '<p class="preview-diff-empty">Updating preview…</p>';
      afterPromise = fetch("/api/preview-formatted", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: sample, settings: settings || {} }),
      })
        .then(function (res) {
          return res.json().then(function (data) {
            return { ok: res.ok, data: data };
          });
        })
        .then(function (result) {
          if (result.ok && result.data && result.data.html) {
            afterEl.innerHTML = result.data.html;
            return;
          }
          afterEl.innerHTML = buildAfterHtml(sample, settings);
        })
        .catch(function () {
          afterEl.innerHTML = buildAfterHtml(sample, settings);
        });
    }
    if (diffEl) {
      var diffs = diffSummary(
        { font_family: "Calibri", font_size: "11", line_spacing: "1.15", alignment: "left" },
        settings
      );
      diffEl.innerHTML = "";
      if (!diffs.length) {
        diffEl.innerHTML = '<p class="preview-diff-empty">Adjust settings to see highlighted changes.</p>';
      } else {
        diffs.forEach(function (d) {
          var li = document.createElement("li");
          li.textContent = d;
          diffEl.appendChild(li);
        });
      }
    }
    return afterPromise;
  }

  global.DocPreview = {
    SAMPLE: SAMPLE,
    renderPreviewPair: renderPreviewPair,
    buildBeforeHtml: buildBeforeHtml,
    buildAfterHtml: buildAfterHtml,
    diffSummary: diffSummary,
  };
})(typeof window !== "undefined" ? window : this);
