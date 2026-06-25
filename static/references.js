/**
 * References page: multi-tab generation, saved list, in-text citation helper.
 */
(function () {
  var FC = window.FormatterCommon;
  var UI = window.AppUI;

  var $ = function (id) {
    return document.getElementById(id);
  };

  var REF_STORAGE_KEY = "academic_formatter_saved_references";
  var REF_STYLE_KEY = FC ? FC.REF_STYLE_KEY : "academic_formatter_citation_style";
  var savedReferences = [];
  var lastGeneratedCitation = "";
  var activeTab = "url";

  function loadSavedReferences() {
    try {
      var raw = FC ? FC.readStorage(REF_STORAGE_KEY) : sessionStorage.getItem(REF_STORAGE_KEY);
      var arr = raw ? JSON.parse(raw) : [];
      savedReferences = Array.isArray(arr) ? arr.map(String).filter(Boolean) : [];
    } catch (e) {
      savedReferences = [];
    }
  }

  function persistReferences() {
    var val = JSON.stringify(savedReferences);
    if (FC) {
      FC.writeStorage(REF_STORAGE_KEY, val);
    } else {
      try {
        sessionStorage.setItem(REF_STORAGE_KEY, val);
      } catch (e) {
        /* ignore */
      }
    }
  }

  function renderReferencesList() {
    var ul = $("references_list");
    var countEl = $("ref_count");
    var clearBtn = $("ref_clear_all_btn");
    var emptyEl = $("ref_empty_state");
    if (!ul) {
      return;
    }
    ul.innerHTML = "";
    savedReferences.forEach(function (cite, i) {
      var li = document.createElement("li");
      var span = document.createElement("span");
      span.textContent = cite;
      var copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "btn-copy btn-copy-sm";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", function () {
        if (UI) {
          UI.copyText(cite, copyBtn);
        }
      });
      var rm = document.createElement("button");
      rm.type = "button";
      rm.className = "ref-remove";
      rm.textContent = "Remove";
      rm.setAttribute("aria-label", "Remove reference " + (i + 1));
      rm.addEventListener("click", function () {
        savedReferences.splice(i, 1);
        persistReferences();
        renderReferencesList();
        if (UI) {
          UI.showToast("Reference removed", "info");
        }
      });
      li.appendChild(span);
      li.appendChild(copyBtn);
      li.appendChild(rm);
      ul.appendChild(li);
    });
    if (countEl) {
      countEl.textContent = String(savedReferences.length);
    }
    if (clearBtn) {
      clearBtn.classList.toggle("hidden", savedReferences.length === 0);
    }
    if (emptyEl) {
      emptyEl.classList.toggle("hidden", savedReferences.length > 0);
    }
  }

  function setRefGenStatus(message, kind) {
    var el = $("ref_gen_status");
    if (!el) {
      return;
    }
    el.textContent = message || "";
    el.className = "req-status" + (kind ? " " + kind : "");
  }

  function setIntextStatus(message, kind) {
    var el = $("intext_status");
    if (!el) {
      return;
    }
    el.textContent = message || "";
    el.className = "req-status" + (kind ? " " + kind : "");
  }

  function loadCitationStyle() {
    var sel = $("citation_style");
    if (!sel) {
      return;
    }
    try {
      var v = FC ? FC.readStorage(REF_STYLE_KEY) : sessionStorage.getItem(REF_STYLE_KEY);
      if (v) {
        sel.value = v;
      }
    } catch (e) {
      /* ignore */
    }
  }

  function persistCitationStyle() {
    var sel = $("citation_style");
    if (!sel) {
      return;
    }
    if (FC) {
      FC.writeStorage(REF_STYLE_KEY, sel.value);
    } else {
      try {
        sessionStorage.setItem(REF_STYLE_KEY, sel.value);
      } catch (e) {
        /* ignore */
      }
    }
  }

  function getStyle() {
    var sel = $("citation_style");
    return (sel && sel.value) || "APA";
  }

  function switchTab(tab) {
    activeTab = tab;
    document.querySelectorAll(".ref-tab").forEach(function (btn) {
      var on = btn.getAttribute("data-ref-tab") === tab;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".ref-tab-panel").forEach(function (panel) {
      panel.classList.toggle("is-active", panel.getAttribute("data-ref-panel") === tab);
    });
  }

  function buildPayload() {
    var style = getStyle();
    var base = { mode: activeTab, style: style };
    if (activeTab === "url") {
      base.url = ($("ref_url_input") && $("ref_url_input").value.trim()) || "";
    } else if (activeTab === "doi") {
      base.doi = ($("ref_doi_input") && $("ref_doi_input").value.trim()) || "";
    } else if (activeTab === "isbn") {
      base.isbn = ($("ref_isbn_input") && $("ref_isbn_input").value.trim()) || "";
    } else if (activeTab === "title") {
      base.title = ($("ref_title_input") && $("ref_title_input").value.trim()) || "";
      base.author = ($("ref_author_input") && $("ref_author_input").value.trim()) || "";
    } else if (activeTab === "manual") {
      base.manual = {
        authors: ($("man_authors") && $("man_authors").value.trim()) || "",
        year: ($("man_year") && $("man_year").value.trim()) || "",
        title: ($("man_title") && $("man_title").value.trim()) || "",
        journal: ($("man_journal") && $("man_journal").value.trim()) || "",
        publisher: ($("man_publisher") && $("man_publisher").value.trim()) || "",
        volume: ($("man_volume") && $("man_volume").value.trim()) || "",
        issue: ($("man_issue") && $("man_issue").value.trim()) || "",
        pages: ($("man_pages") && $("man_pages").value.trim()) || "",
        doi: ($("man_doi") && $("man_doi").value.trim()) || "",
        url: ($("man_url") && $("man_url").value.trim()) || "",
      };
    } else if (activeTab === "paste") {
      base.paste = ($("ref_paste_input") && $("ref_paste_input").value.trim()) || "";
    }
    return base;
  }

  function validatePayload(p) {
    if (p.mode === "url" && !p.url) {
      return "Enter a URL.";
    }
    if (p.mode === "doi" && !p.doi) {
      return "Enter a DOI.";
    }
    if (p.mode === "isbn" && !p.isbn) {
      return "Enter an ISBN.";
    }
    if (p.mode === "title" && !p.title) {
      return "Enter a title.";
    }
    if (p.mode === "manual" && !(p.manual && p.manual.title)) {
      return "Title is required for manual entry.";
    }
    if (p.mode === "paste" && !p.paste) {
      return "Paste citation text.";
    }
    return null;
  }

  function renderIntextResults(data) {
    var wrap = $("intext_results");
    var grid = $("intext_result_grid");
    if (!wrap || !grid) {
      return;
    }
    grid.innerHTML = "";
    var items = [
      { label: "Parenthetical", key: "parenthetical" },
      { label: "Narrative", key: "narrative" },
      { label: "Direct quote", key: "direct_quote" },
      { label: "Footnote", key: "footnote" },
      { label: "Endnote", key: "endnote" },
    ];
    items.forEach(function (item) {
      var val = data[item.key];
      if (!val) {
        return;
      }
      var card = document.createElement("div");
      card.className = "intext-result-card";
      var lbl = document.createElement("p");
      lbl.className = "intext-result-label";
      lbl.textContent = item.label;
      var valEl = document.createElement("p");
      valEl.className = "intext-result-value";
      valEl.textContent = val;
      var copyBtn = document.createElement("button");
      copyBtn.type = "button";
      copyBtn.className = "btn-copy btn-copy-sm";
      copyBtn.textContent = "Copy";
      copyBtn.addEventListener("click", function () {
        if (UI) {
          UI.copyText(val, copyBtn);
        }
      });
      card.appendChild(lbl);
      card.appendChild(valEl);
      card.appendChild(copyBtn);
      grid.appendChild(card);
    });
    wrap.classList.remove("hidden");
  }

  document.querySelectorAll(".ref-tab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      switchTab(btn.getAttribute("data-ref-tab") || "url");
    });
  });

  loadSavedReferences();
  loadCitationStyle();
  renderReferencesList();

  var citationStyleSel = $("citation_style");
  if (citationStyleSel) {
    citationStyleSel.addEventListener("change", persistCitationStyle);
  }

  var refGenBtn = $("ref_generate_btn");
  if (refGenBtn) {
    refGenBtn.addEventListener("click", async function () {
      var payload = buildPayload();
      var err = validatePayload(payload);
      setRefGenStatus("");
      lastGeneratedCitation = "";
      if ($("ref_add_btn")) {
        $("ref_add_btn").disabled = true;
      }
      if (err) {
        setRefGenStatus(err, "error");
        return;
      }
      if ($("ref_preview_wrap")) {
        $("ref_preview_wrap").classList.add("hidden");
      }
      if (UI) {
        UI.setButtonLoading(refGenBtn, true, "Generating…");
      } else {
        refGenBtn.disabled = true;
      }
      setRefGenStatus("Retrieving metadata…");
      try {
        var res = await fetch("/api/reference", {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(payload),
        });
        var data = {};
        try {
          data = await res.json();
        } catch (e2) {
          setRefGenStatus("Invalid response from server.", "error");
          return;
        }
        if (!res.ok) {
          setRefGenStatus(data.error || "Could not generate reference.", "error");
          return;
        }
        var cite = data.citation || "";
        if (!cite) {
          setRefGenStatus("No citation returned.", "error");
          return;
        }
        lastGeneratedCitation = cite;
        if ($("ref_preview")) {
          $("ref_preview").textContent = cite;
        }
        if ($("ref_preview_wrap")) {
          $("ref_preview_wrap").classList.remove("hidden");
        }
        if ($("ref_add_btn")) {
          $("ref_add_btn").disabled = false;
        }
        setRefGenStatus("Citation ready.", "success");
        if (UI) {
          UI.showToast("Reference generated", "success");
        }
      } catch (err2) {
        setRefGenStatus("Network error.", "error");
      } finally {
        if (UI) {
          UI.setButtonLoading(refGenBtn, false);
        } else {
          refGenBtn.disabled = false;
        }
      }
    });
  }

  var refCopyBtn = $("ref_copy_btn");
  if (refCopyBtn) {
    refCopyBtn.addEventListener("click", function () {
      if (UI) {
        UI.copyText(lastGeneratedCitation, refCopyBtn);
      }
    });
  }

  var refAddBtn = $("ref_add_btn");
  if (refAddBtn) {
    refAddBtn.addEventListener("click", function () {
      var cite = (lastGeneratedCitation || "").trim();
      if (!cite) {
        return;
      }
      if (savedReferences.indexOf(cite) === -1) {
        savedReferences.push(cite);
        persistReferences();
        renderReferencesList();
      }
      setRefGenStatus("Added to your list.", "success");
      if (UI) {
        UI.showToast("Added to references list", "success");
      }
    });
  }

  var refClearAllBtn = $("ref_clear_all_btn");
  if (refClearAllBtn) {
    refClearAllBtn.addEventListener("click", function () {
      savedReferences = [];
      persistReferences();
      renderReferencesList();
      setRefGenStatus("Cleared all saved references.", "success");
    });
  }

  var intextBtn = $("intext_generate_btn");
  if (intextBtn) {
    intextBtn.addEventListener("click", async function () {
      var author = ($("intext_author") && $("intext_author").value.trim()) || "";
      var year = ($("intext_year") && $("intext_year").value.trim()) || "n.d.";
      var page = ($("intext_page") && $("intext_page").value.trim()) || "";
      var style = ($("intext_style") && $("intext_style").value) || "APA";
      var quote = $("intext_direct_quote") && $("intext_direct_quote").checked;
      setIntextStatus("");
      if (!author) {
        setIntextStatus("Enter an author name.", "error");
        return;
      }
      if (UI) {
        UI.setButtonLoading(intextBtn, true, "Generating…");
      }
      try {
        var res = await fetch("/api/intext-citation", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            author: author,
            year: year,
            page: page || null,
            style: style,
            direct_quote: quote,
          }),
        });
        var data = await res.json();
        if (!res.ok) {
          setIntextStatus(data.error || "Failed.", "error");
          return;
        }
        renderIntextResults(data);
        setIntextStatus("In-text formats ready — copy what you need.", "success");
      } catch (e) {
        setIntextStatus("Network error.", "error");
      } finally {
        if (UI) {
          UI.setButtonLoading(intextBtn, false);
        }
      }
    });
  }
})();
