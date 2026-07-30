/**
 * Shared DocMaxxing guided tour engine.
 * Pages opt in with: data-dm-tour="format|humanizer|assignment|turnitin|check"
 * and a button [data-dm-tutorial]. Steps live in window.DMTourCatalog.
 */
(function () {
  "use strict";

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  function ensureOverlay() {
    var existing = $("[data-dm-tour]");
    if (existing) return existing;

    var wrap = document.createElement("div");
    wrap.className = "dm-tour";
    wrap.setAttribute("data-dm-tour", "");
    wrap.hidden = true;
    wrap.innerHTML =
      '<div class="dm-tour-backdrop" data-dm-tour-backdrop></div>' +
      '<div class="dm-tour-spot" data-dm-tour-spot hidden></div>' +
      '<div class="dm-tour-card" data-dm-tour-card role="dialog" aria-modal="true" aria-labelledby="dm_tour_title">' +
      '  <button type="button" class="dm-tour-close" data-dm-tour-close aria-label="Close tour">×</button>' +
      '  <h3 class="dm-tour-title" id="dm_tour_title" data-dm-tour-title></h3>' +
      '  <p class="dm-tour-body" data-dm-tour-body></p>' +
      '  <div class="dm-tour-foot">' +
      '    <span class="dm-tour-progress" data-dm-tour-progress>1 / 1</span>' +
      '    <div class="dm-tour-nav">' +
      '      <button type="button" class="dm-tour-btn" data-dm-tour-back>Back</button>' +
      '      <button type="button" class="dm-tour-btn dm-tour-btn--primary" data-dm-tour-next>Next →</button>' +
      "    </div>" +
      "  </div>" +
      "</div>";
    document.body.appendChild(wrap);
    return wrap;
  }

  function scrollIntoViewSafe(el) {
    if (!el || typeof el.scrollIntoView !== "function") return;
    try {
      el.scrollIntoView({ behavior: "smooth", block: "center", inline: "nearest" });
    } catch (e) {
      el.scrollIntoView(true);
    }
  }

  function openDetailsAround(el) {
    if (!el) return;
    var node = el;
    while (node && node !== document.body) {
      if (node.tagName === "DETAILS" && !node.open) node.open = true;
      node = node.parentElement;
    }
  }

  function createTour(pageKey) {
    var catalog = (window.DMTourCatalog && window.DMTourCatalog[pageKey]) || null;
    if (!catalog || !catalog.steps || !catalog.steps.length) return null;

    var steps = catalog.steps;
    var storageKey = catalog.storageKey || ("docmaxxing_tour_" + pageKey + "_done");
    var tourEl = ensureOverlay();
    var idx = 0;
    var active = false;

    function setText(sel, text) {
      var el = $(sel, tourEl);
      if (el) el.textContent = text || "";
    }

    function position(step) {
      var spot = $("[data-dm-tour-spot]", tourEl);
      var card = $("[data-dm-tour-card]", tourEl);
      if (!spot || !card) return;

      card.classList.toggle("is-warn", !!step.warn);
      var target = step.target ? document.querySelector(step.target) : null;

      if (!target || step.placement === "center") {
        spot.hidden = true;
        card.style.top = "50%";
        card.style.left = "50%";
        card.style.transform = "translate(-50%, -50%)";
        return;
      }

      openDetailsAround(target);
      scrollIntoViewSafe(target);

      // Temporarily reveal [hidden] targets so the highlight has a box
      var wasHidden = target.hasAttribute("hidden");
      if (wasHidden) target.removeAttribute("hidden");

      requestAnimationFrame(function () {
        var r = target.getBoundingClientRect();
        var pad = 6;
        card.style.transform = "none";
        spot.hidden = false;
        spot.style.top = r.top - pad + "px";
        spot.style.left = r.left - pad + "px";
        spot.style.width = Math.max(r.width, 40) + pad * 2 + "px";
        spot.style.height = Math.max(r.height, 24) + pad * 2 + "px";

        var cw = card.offsetWidth || 340;
        var ch = card.offsetHeight || 200;
        var place = step.placement || "bottom";
        var top;
        var left;
        if (place === "left") {
          left = r.left - cw - 16;
          top = r.top;
        } else if (place === "right") {
          left = r.right + 16;
          top = r.top;
        } else if (place === "top") {
          left = r.left;
          top = r.top - ch - 14;
        } else {
          left = r.left;
          top = r.bottom + 14;
        }
        left = Math.max(12, Math.min(left, window.innerWidth - cw - 12));
        top = Math.max(12, Math.min(top, window.innerHeight - ch - 12));
        card.style.left = left + "px";
        card.style.top = top + "px";

        if (wasHidden) target.setAttribute("hidden", "");
      });
    }

    function render() {
      var step = steps[idx];
      if (!step) return end(true);
      if (typeof catalog.onStep === "function") {
        try {
          catalog.onStep(step, idx);
        } catch (e) {}
      }
      setText("[data-dm-tour-title]", step.title);
      setText("[data-dm-tour-body]", step.body);
      setText("[data-dm-tour-progress]", idx + 1 + " / " + steps.length);
      var back = $("[data-dm-tour-back]", tourEl);
      var next = $("[data-dm-tour-next]", tourEl);
      if (back) back.style.visibility = idx === 0 ? "hidden" : "visible";
      if (next) next.textContent = step.last || idx === steps.length - 1 ? "Done" : "Next →";
      position(step);
    }

    function start() {
      idx = 0;
      active = true;
      tourEl.hidden = false;
      render();
    }

    function end(complete) {
      active = false;
      tourEl.hidden = true;
      if (complete) {
        try {
          localStorage.setItem(storageKey, "1");
        } catch (e) {}
      }
    }

    function next() {
      var step = steps[idx];
      if (step && (step.last || idx >= steps.length - 1)) return end(true);
      idx = Math.min(steps.length - 1, idx + 1);
      render();
    }

    function back() {
      idx = Math.max(0, idx - 1);
      render();
    }

    var nextBtn = $("[data-dm-tour-next]", tourEl);
    var backBtn = $("[data-dm-tour-back]", tourEl);
    var closeBtn = $("[data-dm-tour-close]", tourEl);
    var backdrop = $("[data-dm-tour-backdrop]", tourEl);

    if (nextBtn && !nextBtn._dmTourBound) {
      nextBtn.addEventListener("click", function () {
        if (!active) return;
        next();
      });
      nextBtn._dmTourBound = true;
    }
    if (backBtn && !backBtn._dmTourBound) {
      backBtn.addEventListener("click", function () {
        if (!active) return;
        back();
      });
      backBtn._dmTourBound = true;
    }
    if (closeBtn && !closeBtn._dmTourBound) {
      closeBtn.addEventListener("click", function () {
        if (!active) return;
        end(true);
      });
      closeBtn._dmTourBound = true;
    }
    if (backdrop && !backdrop._dmTourBound) {
      backdrop.addEventListener("click", function () {
        if (!active) return;
        end(true);
      });
      backdrop._dmTourBound = true;
    }

    window.addEventListener("resize", function () {
      if (active) position(steps[idx]);
    });
    window.addEventListener("keydown", function (e) {
      if (!active) return;
      if (e.key === "Escape") end(true);
      if (e.key === "ArrowRight") next();
      if (e.key === "ArrowLeft") back();
    });

    return {
      start: start,
      end: end,
      storageKey: storageKey,
      autoStart: !!catalog.autoStart,
    };
  }

  function init() {
    var pageEl = $("[data-dm-tour-page]");
    if (!pageEl) return;
    var pageKey = pageEl.getAttribute("data-dm-tour-page");
    if (!pageKey) return;

    var tour = createTour(pageKey);
    if (!tour) return;

    document.querySelectorAll("[data-dm-tutorial]").forEach(function (btn) {
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        tour.start();
      });
    });

    if (tour.autoStart) {
      try {
        if (!localStorage.getItem(tour.storageKey)) {
          setTimeout(function () {
            tour.start();
          }, 450);
        }
      } catch (e) {}
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }

  window.DMTour = { create: createTour };
})();
