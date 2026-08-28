/**
 * Earn & Share — referral link, milestones, convert / withdraw.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-earn-page]");
  if (!root) return;

  var state = { profile: null };

  var REWARD_SHORT = {
    1: "Free Turnitin",
    3: "1,000 credits",
    5: "3,000 credits",
    10: "Pro status",
  };

  var els = {
    status: root.querySelector("[data-earn-status]"),
    link: root.querySelector("[data-earn-link]"),
    code: root.querySelector("[data-earn-code]"),
    totalRefs: root.querySelector("[data-earn-total-refs]"),
    qualifying: root.querySelector("[data-earn-qualifying]"),
    barFill: root.querySelector("[data-earn-progress-bar]"),
    barWrap: root.querySelector("[data-earn-progress-bar-wrap]"),
    steps: root.querySelector("[data-earn-steps]"),
    balance: root.querySelector("[data-earn-balance]"),
    copy: root.querySelector("[data-earn-copy]"),
    convert: root.querySelector("[data-earn-convert]"),
    withdraw: root.querySelector("[data-earn-withdraw]"),
    freeTt: root.querySelector("[data-earn-free-tt]"),
    proBadge: root.querySelector("[data-earn-pro-badge]"),
    refs: root.querySelector("[data-earn-refs]"),
    refsEmpty: root.querySelector("[data-earn-refs-empty]"),
    refsCount: root.querySelector("[data-earn-refs-count]"),
    refsCountWrap: root.querySelector("[data-earn-refs-count-wrap]"),
    modal: root.querySelector("[data-earn-withdraw-modal]"),
    form: root.querySelector("[data-earn-withdraw-form]"),
    amount: root.querySelector("[data-earn-withdraw-amount]"),
    wallet: root.querySelector("[data-earn-withdraw-wallet]"),
  };

  function setStatus(msg, kind) {
    if (!els.status) return;
    els.status.textContent = msg || "";
    els.status.className = "earn-status" + (kind ? " is-" + kind : "");
  }

  function money(n) {
    return "$" + (Number(n) || 0).toFixed(2);
  }

  function formatWhen(iso) {
    if (!iso) return "—";
    try {
      var d = new Date(String(iso).includes("T") ? iso : String(iso).replace(" ", "T") + "Z");
      if (isNaN(d.getTime())) return String(iso);
      return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch (e) {
      return String(iso);
    }
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function shortReward(m) {
    var t = Number(m.threshold);
    if (REWARD_SHORT[t]) return REWARD_SHORT[t];
    return m.reward || "";
  }

  function renderReferrals(list) {
    var items = Array.isArray(list) ? list : [];
    if (els.refsCount) els.refsCount.textContent = String(items.length);
    if (els.refsCountWrap) els.refsCountWrap.hidden = items.length === 0;
    if (els.refsEmpty) els.refsEmpty.hidden = items.length > 0;
    if (!els.refs) return;
    if (!items.length) {
      els.refs.innerHTML = "";
      return;
    }
    els.refs.innerHTML = items
      .map(function (ref) {
        var history = ref.history || [];
        var historyHtml = history.length
          ? '<table class="earn-ref-history-table"><thead><tr>' +
            "<th>When</th><th>Amount</th><th>Credits</th><th>Via</th><th>Your cashback</th>" +
            "</tr></thead><tbody>" +
            history
              .map(function (h) {
                return (
                  "<tr>" +
                  "<td>" +
                  escapeHtml(formatWhen(h.created_at)) +
                  "</td>" +
                  "<td>" +
                  money(h.amount_usd) +
                  "</td>" +
                  "<td>" +
                  escapeHtml(String(h.credits || 0)) +
                  "</td>" +
                  "<td>" +
                  escapeHtml(h.source || "—") +
                  "</td>" +
                  '<td class="earn-ref-cashback">' +
                  money(h.cashback_usd) +
                  "</td>" +
                  "</tr>"
                );
              })
              .join("") +
            "</tbody></table>"
          : '<p class="earn-ref-history-empty">No deposits yet.</p>';

        return (
          '<article class="earn-ref" data-earn-ref="' +
          ref.id +
          '">' +
          '<button type="button" class="earn-ref-toggle" data-earn-ref-toggle aria-expanded="false">' +
          '<span class="earn-ref-id">ID #' +
          escapeHtml(String(ref.id)) +
          "</span>" +
          '<span class="earn-ref-meta">Joined ' +
          escapeHtml(formatWhen(ref.joined_at)) +
          " · " +
          escapeHtml(String(ref.deposit_count || 0)) +
          " deposit" +
          (ref.deposit_count === 1 ? "" : "s") +
          "</span>" +
          '<span class="earn-ref-amount">' +
          money(ref.total_deposited_usd) +
          ' <span class="earn-ref-pill' +
          (ref.qualified ? " is-qualified" : "") +
          '">' +
          (ref.qualified ? "Qualified" : "Pending $10+") +
          "</span></span>" +
          '<span class="earn-ref-chevron" aria-hidden="true">▾</span>' +
          "</button>" +
          '<div class="earn-ref-history" hidden>' +
          historyHtml +
          "</div>" +
          "</article>"
        );
      })
      .join("");
  }

  function render(profile) {
    state.profile = profile;
    if (els.link) els.link.value = profile.referral_link || "";
    if (els.code) els.code.textContent = profile.referral_code || "—";
    if (els.totalRefs) els.totalRefs.textContent = String(profile.total_referrals || 0);
    if (els.qualifying) els.qualifying.textContent = String(profile.qualifying_referrals_count || 0);
    if (els.balance) els.balance.textContent = money(profile.referral_balance_usd);
    if (els.freeTt) els.freeTt.textContent = String(profile.free_turnitin_reports || 0);
    if (els.proBadge) els.proBadge.hidden = !profile.is_pro;

    var q = Number(profile.qualifying_referrals_count) || 0;
    var pct = Math.max(0, Math.min(100, (q / 10) * 100));
    if (els.barFill) els.barFill.style.width = pct + "%";
    if (els.barWrap) els.barWrap.setAttribute("aria-valuenow", String(q));

    if (els.steps) {
      var milestones = profile.milestones || [];
      if (!milestones.length) {
        milestones = [
          { threshold: 1 },
          { threshold: 3 },
          { threshold: 5 },
          { threshold: 10 },
        ];
      }
      els.steps.innerHTML = milestones
        .map(function (m) {
          var t = Number(m.threshold) || 0;
          var unlocked = !!m.unlocked || q >= t;
          return (
            '<li class="earn-milestone-label' +
            (unlocked ? " is-unlocked" : "") +
            '">' +
            '<span class="earn-milestone-n">' +
            escapeHtml(String(t)) +
            "</span>" +
            '<span class="earn-milestone-sep" aria-hidden="true">·</span>' +
            '<span class="earn-milestone-reward">' +
            escapeHtml(shortReward(m)) +
            "</span>" +
            "</li>"
          );
        })
        .join("");
    }

    renderReferrals(profile.referrals);

    if (els.withdraw) {
      var can = !!profile.can_withdraw;
      els.withdraw.disabled = !can;
      els.withdraw.title = can
        ? "Withdraw referral balance"
        : "Available when balance reaches $50";
    }
    if (els.amount && profile.referral_balance_usd != null) {
      els.amount.max = String(profile.referral_balance_usd);
      if (profile.referral_balance_usd < 50) {
        els.amount.value = "50";
      } else {
        els.amount.value = String(Number(profile.referral_balance_usd).toFixed(2));
      }
    }
  }

  function load() {
    if (!(window.DM_AUTH && window.DM_AUTH.authenticated)) {
      setStatus("");
      if (els.link) els.link.value = "Sign in to reveal your personal link";
      return Promise.resolve();
    }
    setStatus("Loading…");
    return fetch("/api/referral/me", {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res.json().then(function (d) {
          return { ok: res.ok, data: d };
        });
      })
      .then(function (r) {
        if (!r.ok || !r.data.success) {
          setStatus((r.data && r.data.error) || "Could not load referral data.", "error");
          return;
        }
        setStatus("");
        render(r.data);
      })
      .catch(function () {
        setStatus("Network error.", "error");
      });
  }

  if (els.copy) {
    els.copy.addEventListener("click", function () {
      var text = els.link ? els.link.value : "";
      if (!text) return;
      var done = function () {
        els.copy.textContent = "Copied";
        setTimeout(function () {
          els.copy.textContent = "Copy";
        }, 1600);
      };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(done, done);
      } else {
        els.link.select();
        try {
          document.execCommand("copy");
        } catch (e) {}
        done();
      }
    });
  }

  if (els.refs) {
    els.refs.addEventListener("click", function (e) {
      var btn = e.target.closest("[data-earn-ref-toggle]");
      if (!btn) return;
      var card = btn.closest(".earn-ref");
      if (!card) return;
      var open = card.classList.toggle("is-open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      var hist = card.querySelector(".earn-ref-history");
      if (hist) hist.hidden = !open;
    });
  }

  if (els.convert) {
    els.convert.addEventListener("click", function () {
      if (!state.profile) return;
      var bal = Number(state.profile.referral_balance_usd) || 0;
      if (bal <= 0) {
        setStatus("No referral balance to convert.", "error");
        return;
      }
      els.convert.disabled = true;
      fetch("/api/referral/convert", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ amount_usd: bal }),
      })
        .then(function (res) {
          return res.json().then(function (d) {
            return { ok: res.ok, data: d };
          });
        })
        .then(function (r) {
          els.convert.disabled = false;
          if (!r.ok || !r.data.success) {
            setStatus((r.data && r.data.error) || "Conversion failed.", "error");
            return;
          }
          setStatus(
            "Converted " + money(r.data.converted_usd) + " → " + r.data.credits + " credits.",
            "success"
          );
          if (typeof window.refreshCoinBalance === "function") window.refreshCoinBalance();
          return load();
        })
        .catch(function () {
          els.convert.disabled = false;
          setStatus("Network error.", "error");
        });
    });
  }

  function openModal() {
    if (!els.modal) return;
    els.modal.hidden = false;
    els.modal.removeAttribute("hidden");
  }

  function closeModal() {
    if (!els.modal) return;
    els.modal.hidden = true;
  }

  if (els.withdraw) {
    els.withdraw.addEventListener("click", function () {
      if (els.withdraw.disabled) return;
      openModal();
    });
  }

  root.querySelectorAll("[data-earn-withdraw-close]").forEach(function (el) {
    el.addEventListener("click", closeModal);
  });

  if (els.form) {
    els.form.addEventListener("submit", function (e) {
      e.preventDefault();
      var amount = els.amount ? parseFloat(els.amount.value) : 0;
      var wallet = els.wallet ? els.wallet.value : "";
      fetch("/api/referral/withdraw", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ amount_usd: amount, wallet_details: wallet }),
      })
        .then(function (res) {
          return res.json().then(function (d) {
            return { ok: res.ok, data: d };
          });
        })
        .then(function (r) {
          if (!r.ok || !r.data.success) {
            setStatus((r.data && r.data.error) || "Withdrawal failed.", "error");
            return;
          }
          closeModal();
          setStatus(
            "Withdrawal request submitted for " + money(r.data.amount_usd) + ".",
            "success"
          );
          return load();
        })
        .catch(function () {
          setStatus("Network error.", "error");
        });
    });
  }

  load();
})();
