/**
 * Admin panel — users, balances, admin role, per-user Credit Ledger.
 */
(function () {
  "use strict";

  var root = document.querySelector("[data-admin-page]");
  if (!root) {
    return;
  }

  var state = {
    users: [],
    total: 0,
    search: "",
    saving: {},
    ledgerUserId: null,
    ledgerEntries: [],
    ledgerBalance: 0,
    ledgerTotal: 0,
    ledgerUser: null,
    purchasesUserId: null,
    purchases: [],
    purchasesTotal: 0,
    purchasesUser: null,
    usageUserId: null,
    usageEvents: [],
    usageTotal: 0,
    usageUser: null,
  };

  var els = {
    body: root.querySelector("[data-adm-body]"),
    empty: root.querySelector("[data-adm-empty]"),
    search: root.querySelector("[data-adm-search]"),
    status: root.querySelector("[data-adm-status]"),
    stats: root.querySelector("[data-adm-stats]"),
    totalUsers: root.querySelector("[data-adm-total-users]"),
    ledgerOverlay: root.querySelector("[data-adm-ledger-overlay]"),
    ledgerSubtitle: root.querySelector("[data-adm-ledger-subtitle]"),
    ledgerBalance: root.querySelector("[data-adm-ledger-balance]"),
    ledgerCount: root.querySelector("[data-adm-ledger-count]"),
    ledgerStatus: root.querySelector("[data-adm-ledger-status]"),
    ledgerBody: root.querySelector("[data-adm-ledger-body]"),
    ledgerEmpty: root.querySelector("[data-adm-ledger-empty]"),
    ledgerClose: root.querySelector("[data-adm-ledger-close]"),
    purchasesOverlay: root.querySelector("[data-adm-purchases-overlay]"),
    purchasesSubtitle: root.querySelector("[data-adm-purchases-subtitle]"),
    purchasesCount: root.querySelector("[data-adm-purchases-count]"),
    purchasesStatus: root.querySelector("[data-adm-purchases-status]"),
    purchasesBody: root.querySelector("[data-adm-purchases-body]"),
    purchasesEmpty: root.querySelector("[data-adm-purchases-empty]"),
    purchasesClose: root.querySelector("[data-adm-purchases-close]"),
    usageOverlay: root.querySelector("[data-adm-usage-overlay]"),
    usageSubtitle: root.querySelector("[data-adm-usage-subtitle]"),
    usageCount: root.querySelector("[data-adm-usage-count]"),
    usageStatus: root.querySelector("[data-adm-usage-status]"),
    usageBody: root.querySelector("[data-adm-usage-body]"),
    usageEmpty: root.querySelector("[data-adm-usage-empty]"),
    usageClose: root.querySelector("[data-adm-usage-close]"),
    analyticsStatus: root.querySelector("[data-adm-analytics-status]"),
    analyticsRefresh: root.querySelector("[data-adm-analytics-refresh]"),
    kpiSold: root.querySelector("[data-adm-kpi-sold]"),
    kpiUsed: root.querySelector("[data-adm-kpi-used]"),
    kpiRevenue: root.querySelector("[data-adm-kpi-revenue]"),
    kpiFeature: root.querySelector("[data-adm-kpi-feature]"),
    kpiAvgCredits: root.querySelector("[data-adm-kpi-avg-credits]"),
    kpiAvgPurchase: root.querySelector("[data-adm-kpi-avg-purchase]"),
    topCustomersBody: root.querySelector("[data-adm-top-customers]"),
    topCustomersEmpty: root.querySelector("[data-adm-top-customers-empty]"),
    topCountriesBody: root.querySelector("[data-adm-top-countries]"),
    topCountriesEmpty: root.querySelector("[data-adm-top-countries-empty]"),
    withdrawalsStatus: root.querySelector("[data-adm-withdrawals-status]"),
    withdrawalsRefresh: root.querySelector("[data-adm-withdrawals-refresh]"),
    withdrawalsBody: root.querySelector("[data-adm-withdrawals-body]"),
    withdrawalsEmpty: root.querySelector("[data-adm-withdrawals-empty]"),
    todayStatus: root.querySelector("[data-adm-today-status]"),
    todayRefresh: root.querySelector("[data-adm-today-refresh]"),
    todayDate: root.querySelector("[data-adm-today-date]"),
    todayHumanizer: root.querySelector("[data-adm-today-humanizer]"),
    todayHumanizerUsed: root.querySelector("[data-adm-today-humanizer-used]"),
    todayHumanizerLimit: root.querySelector("[data-adm-today-humanizer-limit]"),
    todayTurnitin: root.querySelector("[data-adm-today-turnitin]"),
    promoForm: root.querySelector("[data-adm-promo-form]"),
    promoActive: root.querySelector("[data-adm-promo-active]"),
    promoPercent: root.querySelector("[data-adm-promo-percent]"),
    promoLimit: root.querySelector("[data-adm-promo-limit]"),
    turnitinBalance: root.querySelector("[data-adm-turnitin-balance]"),
    autoEnabled: root.querySelector("[data-adm-auto-enabled]"),
    autoTime: root.querySelector("[data-adm-auto-time]"),
    autoMin: root.querySelector("[data-adm-auto-min]"),
    discountLive: root.querySelector("[data-adm-discount-live]"),
    datasetStatus: root.querySelector("[data-adm-dataset-status]"),
    datasetTotal: root.querySelector("[data-adm-dataset-total]"),
    datasetStandalone: root.querySelector("[data-adm-dataset-standalone]"),
    datasetAssignment: root.querySelector("[data-adm-dataset-assignment]"),
    datasetWorkspace: root.querySelector("[data-adm-dataset-workspace]"),
    detectorTotal: root.querySelector("[data-adm-detector-total]"),
    detectorAuto: root.querySelector("[data-adm-detector-auto]"),
    detectorManual: root.querySelector("[data-adm-detector-manual]"),
    datasetRefresh: root.querySelector("[data-adm-dataset-refresh]"),
  };

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatDate(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso.includes("T") ? iso : iso.replace(" ", "T") + "Z").toLocaleString(
        undefined,
        {
          month: "short",
          day: "numeric",
          year: "numeric",
          hour: "numeric",
          minute: "2-digit",
        }
      );
    } catch (e) {
      return iso;
    }
  }

  function formatCredits(n) {
    var v = Number(n) || 0;
    return (v > 0 ? "+" : "") + String(v);
  }

  function formatNumber(n) {
    var v = Number(n);
    if (isNaN(v)) return "—";
    return Math.round(v).toLocaleString();
  }

  function formatMoney(n, currency) {
    var v = Number(n);
    if (isNaN(v)) return "—";
    var cur = currency || "USD";
    try {
      return new Intl.NumberFormat(undefined, {
        style: "currency",
        currency: cur,
        maximumFractionDigits: 2,
      }).format(v);
    } catch (e) {
      return "$" + v.toFixed(2);
    }
  }

  function setAnalyticsStatus(msg, isError) {
    if (!els.analyticsStatus) return;
    els.analyticsStatus.textContent = msg || "";
    els.analyticsStatus.classList.toggle("adm-status--error", !!isError);
  }

  function renderAnalytics(data) {
    if (!data) return;
    if (els.kpiSold) els.kpiSold.textContent = formatNumber(data.total_credits_sold);
    if (els.kpiUsed) els.kpiUsed.textContent = formatNumber(data.total_credits_used);
    if (els.kpiRevenue) {
      els.kpiRevenue.textContent = formatMoney(
        data.revenue,
        data.revenue_currency || "USD"
      );
    }
    if (els.kpiFeature) {
      var f = data.most_used_feature;
      if (f && f.feature) {
        els.kpiFeature.textContent =
          f.feature + " · " + formatNumber(f.launches) + " runs";
      } else {
        els.kpiFeature.textContent = "—";
      }
    }
    if (els.kpiAvgCredits) {
      els.kpiAvgCredits.textContent = formatNumber(data.average_credits_per_user);
    }
    if (els.kpiAvgPurchase) {
      var ap = data.average_purchase || {};
      if (data.purchase_count > 0) {
        els.kpiAvgPurchase.textContent =
          formatMoney(ap.amount, ap.currency || "USD") +
          " · " +
          formatNumber(ap.credits) +
          " credits";
      } else {
        els.kpiAvgPurchase.textContent = "—";
      }
    }

    var customers = data.top_customers || [];
    if (els.topCustomersBody) {
      els.topCustomersBody.innerHTML = customers
        .map(function (c) {
          var label = escapeHtml(c.email || ("#" + c.user_id));
          return (
            "<tr>" +
            "<td>" +
            label +
            "</td>" +
            "<td>" +
            formatNumber(c.purchase_count) +
            "</td>" +
            "<td>" +
            formatNumber(c.credits_bought) +
            "</td>" +
            "<td>" +
            formatMoney(c.revenue, "USD") +
            "</td>" +
            "</tr>"
          );
        })
        .join("");
    }
    if (els.topCustomersEmpty) {
      els.topCustomersEmpty.hidden = customers.length > 0;
    }

    var countries = data.top_countries || [];
    var hasRealCountry = countries.some(function (c) {
      return c.country && c.country !== "Unknown";
    });
    if (els.topCountriesBody) {
      els.topCountriesBody.innerHTML = hasRealCountry
        ? countries
            .map(function (c) {
              return (
                "<tr>" +
                "<td>" +
                escapeHtml(c.country || "Unknown") +
                "</td>" +
                "<td>" +
                formatNumber(c.purchase_count) +
                "</td>" +
                "<td>" +
                formatNumber(c.credits) +
                "</td>" +
                "<td>" +
                formatMoney(c.revenue, "USD") +
                "</td>" +
                "</tr>"
              );
            })
            .join("")
        : "";
    }
    if (els.topCountriesEmpty) {
      els.topCountriesEmpty.hidden = hasRealCountry;
    }
  }

  function setWithdrawalsStatus(msg, isError) {
    if (!els.withdrawalsStatus) return;
    els.withdrawalsStatus.textContent = msg || "";
    els.withdrawalsStatus.classList.toggle("adm-status--error", !!isError);
  }

  function loadWithdrawals() {
    if (!els.withdrawalsBody) return Promise.resolve();
    setWithdrawalsStatus("Loading…");
    return fetch("/api/admin/withdrawals?status=pending&limit=200", {
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res.json().catch(function () {
          return {};
        }).then(function (d) {
          return { ok: res.ok, data: d };
        });
      })
      .then(function (r) {
        if (!r.ok) {
          setWithdrawalsStatus(
            (r.data && r.data.error) || "Failed to load withdrawals.",
            true
          );
          return;
        }
        var items = (r.data && r.data.items) || [];
        els.withdrawalsBody.innerHTML = items
          .map(function (item) {
            var email = escapeHtml(item.email || "");
            var name = escapeHtml(item.name || "");
            var wallet = escapeHtml(item.wallet_details || "");
            return (
              '<tr data-adm-withdrawal-row="' +
              item.id +
              '">' +
              '<td class="adm-cell-id">#' +
              item.id +
              "</td>" +
              '<td class="adm-cell-email" title="' +
              email +
              '">#' +
              item.user_id +
              " · " +
              (name ? name + " · " : "") +
              email +
              "</td>" +
              '<td class="adm-cell-balance">$' +
              Number(item.amount_usd || 0).toFixed(2) +
              "</td>" +
              '<td class="adm-cell-wallet" title="' +
              wallet +
              '">' +
              wallet +
              "</td>" +
              '<td class="adm-cell-date">' +
              escapeHtml(item.created_at || "") +
              "</td>" +
              '<td class="adm-cell-actions">' +
              '<button type="button" class="adm-btn adm-btn--approve" data-adm-withdrawal-approve="' +
              item.id +
              '">Approve</button>' +
              '<button type="button" class="adm-btn adm-btn--reject" data-adm-withdrawal-reject="' +
              item.id +
              '">Reject</button>' +
              "</td></tr>"
            );
          })
          .join("");
        if (els.withdrawalsEmpty) {
          els.withdrawalsEmpty.hidden = items.length > 0;
        }
        setWithdrawalsStatus(
          items.length
            ? items.length + " pending"
            : "No pending withdrawals."
        );
      })
      .catch(function () {
        setWithdrawalsStatus("Network error loading withdrawals.", true);
      });
  }

  function resolveWithdrawal(requestId, approve) {
    var path = approve ? "approve" : "reject";
    var label = approve ? "Approve" : "Reject";
    if (
      !window.confirm(
        label + " withdrawal #" + requestId + "?" +
          (approve
            ? " Confirm you have already sent the funds."
            : " This refunds the amount to the user’s referral balance.")
      )
    ) {
      return;
    }
    setWithdrawalsStatus(label + "ing…");
    fetch("/api/admin/withdrawals/" + requestId + "/" + path, {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then(function (res) {
        return res.json().catch(function () {
          return {};
        }).then(function (d) {
          return { ok: res.ok, data: d };
        });
      })
      .then(function (r) {
        if (!r.ok) {
          setWithdrawalsStatus(
            (r.data && (r.data.error || r.data.message)) ||
              "Failed to " + path + " withdrawal.",
            true
          );
          return;
        }
        loadWithdrawals();
      })
      .catch(function () {
        setWithdrawalsStatus("Network error.", true);
      });
  }

  function setTodayStatus(msg, isError) {
    if (!els.todayStatus) return;
    els.todayStatus.textContent = msg || "";
    els.todayStatus.classList.toggle("adm-status--error", !!isError);
  }

  function applyTodayPayload(data) {
    var today = (data && data.today) || {};
    var settings = (data && data.settings) || {};
    var discount = (data && data.discount) || {};

    if (els.todayDate) els.todayDate.textContent = today.date || "today";
    if (els.todayHumanizer) {
      els.todayHumanizer.textContent = String(
        today.humanizer_remaining != null
          ? today.humanizer_remaining
          : Math.max(
              0,
              (today.humanizer_daily_limit || settings.humanizer_daily_limit || 50) -
                (today.humanizer_requests_count || 0)
            )
      );
    }
    if (els.todayHumanizerUsed) {
      els.todayHumanizerUsed.textContent = String(today.humanizer_requests_count || 0);
    }
    if (els.todayHumanizerLimit) {
      els.todayHumanizerLimit.textContent = String(
        today.humanizer_daily_limit != null
          ? today.humanizer_daily_limit
          : settings.humanizer_daily_limit || 50
      );
    }
    if (els.todayTurnitin) {
      var turnitinBal =
        today.turnitin_global_balance != null
          ? today.turnitin_global_balance
          : settings.turnitin_global_balance != null
            ? settings.turnitin_global_balance
            : 0;
      els.todayTurnitin.textContent = String(turnitinBal);
    }
    if (els.promoActive) {
      els.promoActive.checked = !!settings.is_humanizer_discount_active;
    }
    if (els.promoPercent) {
      els.promoPercent.value = String(
        settings.humanizer_discount_percent != null
          ? settings.humanizer_discount_percent
          : 50
      );
    }
    if (els.promoLimit) {
      els.promoLimit.value = String(
        settings.humanizer_daily_limit != null ? settings.humanizer_daily_limit : 50
      );
    }
    if (els.turnitinBalance) {
      els.turnitinBalance.value = String(
        settings.turnitin_global_balance != null ? settings.turnitin_global_balance : 0
      );
    }
    if (els.autoEnabled) {
      els.autoEnabled.checked = !!settings.auto_discount_enabled;
    }
    if (els.autoTime) {
      els.autoTime.value = settings.auto_discount_time || "20:00";
    }
    if (els.autoMin) {
      els.autoMin.value = String(
        settings.auto_discount_min_remaining != null
          ? settings.auto_discount_min_remaining
          : 10
      );
    }
    if (els.discountLive) {
      if (discount.active) {
        els.discountLive.textContent =
          "Live now: −" +
          (discount.percent || 0) +
          "% (" +
          (discount.source || "active") +
          ")";
      } else if (discount.source === "auto_waiting") {
        els.discountLive.textContent =
          "Auto-Pilot waiting — triggers at " +
          (discount.trigger_time || settings.auto_discount_time || "20:00") +
          " GMT+5 if remaining ≥ " +
          (discount.min_remaining != null
            ? discount.min_remaining
            : settings.auto_discount_min_remaining || 10);
      } else {
        els.discountLive.textContent = "Discount inactive.";
      }
    }
  }

  function loadTodayUsage() {
    if (!els.todayHumanizer && !els.promoForm) return Promise.resolve();
    setTodayStatus("Loading…");
    return fetch("/api/admin/daily-stats", { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (d) {
            return { ok: res.ok, status: res.status, data: d };
          });
      })
      .then(function (r) {
        if (!r.ok) {
          setTodayStatus(
            (r.data && (r.data.error || r.data.message)) ||
              "Failed to load today’s usage. (HTTP " + r.status + ")",
            true
          );
          return;
        }
        applyTodayPayload(r.data || {});
        if (r.data && r.data.warning) {
          setTodayStatus("Loaded with warning: " + r.data.warning, true);
        } else {
          setTodayStatus("");
        }
      })
      .catch(function () {
        setTodayStatus("Network error loading today’s usage.", true);
      });
  }

  function savePromo(e) {
    if (e) e.preventDefault();
    if (!els.promoForm) return;
    setTodayStatus("Saving settings…");
    var body = {
      is_humanizer_discount_active: !!(els.promoActive && els.promoActive.checked),
      humanizer_discount_percent: els.promoPercent
        ? parseInt(els.promoPercent.value, 10)
        : 50,
      humanizer_daily_limit: els.promoLimit ? parseInt(els.promoLimit.value, 10) : 50,
      turnitin_global_balance: els.turnitinBalance
        ? parseInt(els.turnitinBalance.value, 10)
        : 0,
      auto_discount_enabled: !!(els.autoEnabled && els.autoEnabled.checked),
      auto_discount_time: els.autoTime ? els.autoTime.value || "20:00" : "20:00",
      auto_discount_min_remaining: els.autoMin ? parseInt(els.autoMin.value, 10) : 10,
    };
    fetch("/api/admin/site-settings", {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (d) {
            return { ok: res.ok, data: d };
          });
      })
      .then(function (r) {
        if (!r.ok || !r.data || !r.data.success) {
          setTodayStatus((r.data && r.data.error) || "Could not save settings.", true);
          return;
        }
        applyTodayPayload(r.data);
        setTodayStatus("Settings saved.");
      })
      .catch(function () {
        setTodayStatus("Network error saving settings.", true);
      });
  }

  function loadAnalytics() {
    setAnalyticsStatus("Loading analytics…");
    return fetch("/api/admin/analytics")
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, status: res.status, data: data };
          });
      })
      .then(function (r) {
        if (r.status === 401 || r.status === 403) {
          setAnalyticsStatus("Admin access required.", true);
          return;
        }
        if (!r.ok || !r.data || !r.data.success) {
          setAnalyticsStatus(
            (r.data && r.data.error) || "Failed to load analytics.",
            true
          );
          return;
        }
        renderAnalytics(r.data);
        setAnalyticsStatus("");
      })
      .catch(function () {
        setAnalyticsStatus("Network error loading analytics.", true);
      });
  }

  function setDatasetStatus(msg, isError) {
    if (!els.datasetStatus) return;
    els.datasetStatus.textContent = msg || "";
    els.datasetStatus.classList.toggle("adm-status--error", !!isError);
  }

  function loadDatasetStats() {
    if (!els.datasetTotal && !els.datasetStatus) return;
    setDatasetStatus("Loading dataset stats…");
    return fetch("/api/admin/dataset-stats", { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, status: res.status, data: data };
          });
      })
      .then(function (r) {
        if (r.status === 401 || r.status === 403) {
          setDatasetStatus("Admin access required.", true);
          return;
        }
        if (!r.ok || !r.data || !r.data.success) {
          setDatasetStatus((r.data && r.data.error) || "Failed to load dataset stats.", true);
          return;
        }
        if (els.datasetTotal) els.datasetTotal.textContent = formatNumber(r.data.total);
        if (els.datasetStandalone) {
          els.datasetStandalone.textContent = formatNumber(r.data.standalone);
        }
        if (els.datasetAssignment) {
          els.datasetAssignment.textContent = formatNumber(r.data.assignment);
        }
        if (els.datasetWorkspace) {
          els.datasetWorkspace.textContent = formatNumber(r.data.workspace_partial);
        }
        if (els.detectorTotal) {
          els.detectorTotal.textContent = formatNumber(r.data.detector_total);
        }
        if (els.detectorAuto) {
          els.detectorAuto.textContent = formatNumber(r.data.auto_report_over_20);
        }
        if (els.detectorManual) {
          els.detectorManual.textContent = formatNumber(r.data.manual_highlights);
        }
        setDatasetStatus("");
      })
      .catch(function () {
        setDatasetStatus("Network error loading dataset stats.", true);
      });
  }

  function setStatus(msg, isError) {
    if (!els.status) return;
    els.status.textContent = msg || "";
    els.status.classList.toggle("adm-status--error", !!isError);
  }

  function setLedgerStatus(msg, isError) {
    if (!els.ledgerStatus) return;
    els.ledgerStatus.textContent = msg || "";
    els.ledgerStatus.classList.toggle("adm-status--error", !!isError);
  }

  function renderTable() {
    if (!els.body) return;

    if (els.empty) {
      els.empty.hidden = state.users.length > 0;
    }
    if (els.stats) {
      els.stats.hidden = false;
    }
    if (els.totalUsers) {
      els.totalUsers.textContent = String(state.total);
    }

    els.body.innerHTML = state.users
      .map(function (user) {
        var saving = !!state.saving[user.id];
        return (
          "<tr data-adm-row=\"" +
          user.id +
          "\">" +
          '<td class="adm-cell-id">#' +
          user.id +
          "</td>" +
          '<td class="adm-cell-email" title="' +
          escapeHtml(user.email) +
          '">' +
          escapeHtml(user.email) +
          "</td>" +
          '<td class="adm-cell-name">' +
          escapeHtml(user.name || "—") +
          "</td>" +
          '<td class="adm-cell-balance">' +
          '<form class="adm-balance-form" data-adm-balance-form="' +
          user.id +
          '" data-adm-current-balance="' +
          Number(user.balance) +
          '" title="Enter the exact new balance (replaces current, does not add)">' +
          '<span class="adm-balance-current">' +
          '<span class="adm-balance-current-label">Now </span>' +
          escapeHtml(formatNumber(user.balance)) +
          "</span>" +
          '<div class="adm-balance-input-row">' +
          '<input type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off" ' +
          'class="adm-balance-input" value="" placeholder="New balance" ' +
          'data-adm-balance-input="' +
          user.id +
          '" aria-label="New exact balance for user ' +
          user.id +
          '" />' +
          '<button type="submit" class="adm-btn adm-btn--save"' +
          (saving ? " disabled" : "") +
          ">Set</button>" +
          "</div></form></td>" +
          '<td class="adm-cell-date">' +
          formatDate(user.createdAt) +
          "</td>" +
          '<td class="adm-cell-admin">' +
          '<label class="adm-admin-toggle">' +
          '<input type="checkbox" data-adm-admin-toggle="' +
          user.id +
          '"' +
          (user.isAdmin ? " checked" : "") +
          (saving ? " disabled" : "") +
          " />" +
          '<span class="adm-admin-toggle-ui"></span>' +
          "</label></td>" +
          '<td class="adm-cell-actions">' +
          '<button type="button" class="adm-btn adm-btn--ledger" data-adm-ledger="' +
          user.id +
          '">Ledger</button>' +
          '<button type="button" class="adm-btn adm-btn--purchases" data-adm-purchases="' +
          user.id +
          '">Purchases</button>' +
          '<button type="button" class="adm-btn adm-btn--usage" data-adm-usage="' +
          user.id +
          '">Usage</button>' +
          '<button type="button" class="adm-btn adm-btn--delete" data-adm-delete="' +
          user.id +
          '" data-adm-delete-email="' +
          escapeHtml(user.email) +
          '"' +
          (saving ? " disabled" : "") +
          ">Delete</button>" +
          (user.isAdmin
            ? '<span class="adm-badge adm-badge--admin">Admin</span>'
            : '<span class="adm-badge adm-badge--user">User</span>') +
          "</td></tr>"
        );
      })
      .join("");
  }

  function renderLedger() {
    if (!els.ledgerBody) return;
    var user = state.ledgerUser;
    if (els.ledgerSubtitle) {
      els.ledgerSubtitle.textContent = user
        ? "#" + user.id + " · " + (user.email || "") + (user.name ? " · " + user.name : "")
        : "";
    }
    if (els.ledgerBalance) {
      els.ledgerBalance.textContent = String(state.ledgerBalance);
    }
    if (els.ledgerCount) {
      els.ledgerCount.textContent = state.ledgerTotal + " entries";
    }
    if (els.ledgerEmpty) {
      els.ledgerEmpty.hidden = state.ledgerEntries.length > 0;
    }

    els.ledgerBody.innerHTML = state.ledgerEntries
      .map(function (tx) {
        var credits = Number(tx.credits) || 0;
        var creditClass = credits >= 0 ? "adm-credits--pos" : "adm-credits--neg";
        var type = escapeHtml(tx.type || "—");
        var creditsLabel =
          tx.type === "ADMIN_SET"
            ? "→ " + formatNumber(tx.balance_after)
            : formatCredits(credits);
        return (
          "<tr>" +
          "<td>" +
          escapeHtml(formatDate(tx.created_at)) +
          "</td>" +
          '<td><span class="adm-type adm-type--' +
          type +
          '">' +
          type +
          "</span></td>" +
          '<td class="adm-credits ' +
          creditClass +
          '">' +
          escapeHtml(creditsLabel) +
          "</td>" +
          "<td>" +
          escapeHtml(String(tx.balance_before)) +
          "</td>" +
          "<td>" +
          escapeHtml(String(tx.balance_after)) +
          "</td>" +
          "<td>" +
          escapeHtml(tx.reference_type || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(tx.reference_id || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(tx.status || "completed") +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function openLedger(userId) {
    state.ledgerUserId = userId;
    if (els.ledgerOverlay) {
      els.ledgerOverlay.hidden = false;
    }
    setLedgerStatus("Loading ledger…");
    state.ledgerEntries = [];
    renderLedger();

    fetch("/api/admin/users/" + userId + "/ledger?limit=200", {
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, status: res.status, data: data };
          });
      })
      .then(function (r) {
        if (!r.ok || !r.data || !r.data.success) {
          setLedgerStatus((r.data && r.data.error) || "Failed to load ledger.", true);
          return;
        }
        state.ledgerUser = r.data.user || null;
        state.ledgerBalance = r.data.balance || 0;
        state.ledgerTotal = r.data.total || 0;
        state.ledgerEntries = r.data.entries || [];
        setLedgerStatus("");
        renderLedger();
      })
      .catch(function () {
        setLedgerStatus("Network error.", true);
      });
  }

  function closeLedger() {
    state.ledgerUserId = null;
    if (els.ledgerOverlay) {
      els.ledgerOverlay.hidden = true;
    }
  }

  function setPurchasesStatus(msg, isError) {
    if (!els.purchasesStatus) return;
    els.purchasesStatus.textContent = msg || "";
    els.purchasesStatus.classList.toggle("adm-status--error", !!isError);
  }

  function renderPurchases() {
    if (!els.purchasesBody) return;
    var user = state.purchasesUser;
    if (els.purchasesSubtitle) {
      els.purchasesSubtitle.textContent = user
        ? "#" + user.id + " · " + (user.email || "") + (user.name ? " · " + user.name : "")
        : "";
    }
    if (els.purchasesCount) {
      els.purchasesCount.textContent = state.purchasesTotal + " purchases";
    }
    if (els.purchasesEmpty) {
      els.purchasesEmpty.hidden = state.purchases.length > 0;
    }

    els.purchasesBody.innerHTML = state.purchases
      .map(function (p) {
        var st = escapeHtml(p.status || "Pending");
        return (
          "<tr>" +
          "<td>" +
          escapeHtml(formatDate(p.created_at)) +
          "</td>" +
          '<td><span class="adm-pay-status adm-pay-status--' +
          st +
          '">' +
          st +
          "</span></td>" +
          "<td>" +
          escapeHtml(String(p.credits)) +
          "</td>" +
          "<td>" +
          escapeHtml(String(p.amount)) +
          "</td>" +
          "<td>" +
          escapeHtml(p.currency || "USD") +
          "</td>" +
          "<td>" +
          escapeHtml(p.product_id || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(p.price_id || "—") +
          "</td>" +
          "<td title=\"" +
          escapeHtml(p.paddle_transaction_id || "") +
          '">' +
          escapeHtml(p.paddle_transaction_id || "—") +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function openPurchases(userId) {
    state.purchasesUserId = userId;
    if (els.purchasesOverlay) {
      els.purchasesOverlay.hidden = false;
    }
    setPurchasesStatus("Loading purchases…");
    state.purchases = [];
    renderPurchases();

    fetch("/api/admin/users/" + userId + "/purchases?limit=200", {
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, data: data };
          });
      })
      .then(function (r) {
        if (!r.ok || !r.data || !r.data.success) {
          setPurchasesStatus((r.data && r.data.error) || "Failed to load purchases.", true);
          return;
        }
        state.purchasesUser = r.data.user || null;
        state.purchasesTotal = r.data.total || 0;
        state.purchases = r.data.purchases || [];
        setPurchasesStatus("");
        renderPurchases();
      })
      .catch(function () {
        setPurchasesStatus("Network error.", true);
      });
  }

  function closePurchases() {
    state.purchasesUserId = null;
    if (els.purchasesOverlay) {
      els.purchasesOverlay.hidden = true;
    }
  }

  function setUsageStatus(msg, isError) {
    if (!els.usageStatus) return;
    els.usageStatus.textContent = msg || "";
    els.usageStatus.classList.toggle("adm-status--error", !!isError);
  }

  function renderUsage() {
    if (!els.usageBody) return;
    var user = state.usageUser;
    if (els.usageSubtitle) {
      els.usageSubtitle.textContent = user
        ? "#" + user.id + " · " + (user.email || "") + (user.name ? " · " + user.name : "")
        : "";
    }
    if (els.usageCount) {
      els.usageCount.textContent = state.usageTotal + " events";
    }
    if (els.usageEmpty) {
      els.usageEmpty.hidden = state.usageEvents.length > 0;
    }

    els.usageBody.innerHTML = state.usageEvents
      .map(function (u) {
        var feat = escapeHtml(u.feature || "—");
        var cost =
          u.provider_cost === null || u.provider_cost === undefined
            ? "—"
            : String(u.provider_cost);
        var latency =
          u.latency === null || u.latency === undefined ? "—" : String(u.latency);
        return (
          "<tr>" +
          "<td>" +
          escapeHtml(formatDate(u.created_at)) +
          "</td>" +
          '<td><span class="adm-feature">' +
          feat +
          "</span></td>" +
          "<td>" +
          escapeHtml(String(u.credits_used)) +
          "</td>" +
          "<td>" +
          escapeHtml(u.provider || "—") +
          "</td>" +
          "<td>" +
          escapeHtml(cost) +
          "</td>" +
          "<td>" +
          escapeHtml(latency) +
          "</td>" +
          "<td title=\"" +
          escapeHtml(u.request_id || "") +
          '">' +
          escapeHtml(u.request_id || "—") +
          "</td>" +
          "</tr>"
        );
      })
      .join("");
  }

  function openUsage(userId) {
    state.usageUserId = userId;
    if (els.usageOverlay) {
      els.usageOverlay.hidden = false;
    }
    setUsageStatus("Loading usage…");
    state.usageEvents = [];
    renderUsage();

    fetch("/api/admin/users/" + userId + "/usage?limit=200", {
      headers: { Accept: "application/json" },
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, data: data };
          });
      })
      .then(function (r) {
        if (!r.ok || !r.data || !r.data.success) {
          setUsageStatus((r.data && r.data.error) || "Failed to load usage.", true);
          return;
        }
        state.usageUser = r.data.user || null;
        state.usageTotal = r.data.total || 0;
        state.usageEvents = r.data.usage || [];
        setUsageStatus("");
        renderUsage();
      })
      .catch(function () {
        setUsageStatus("Network error.", true);
      });
  }

  function closeUsage() {
    state.usageUserId = null;
    if (els.usageOverlay) {
      els.usageOverlay.hidden = true;
    }
  }

  function loadUsers() {
    var url = "/api/admin/users?limit=200";
    if (state.search) {
      url += "&q=" + encodeURIComponent(state.search);
    }
    setStatus("Loading…");
    fetch(url, { headers: { Accept: "application/json" } })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, status: res.status, data: data };
          });
      })
      .then(function (r) {
        if (r.status === 403) {
          setStatus("Admin access required.", true);
          return;
        }
        if (!r.ok || !r.data || !r.data.success) {
          setStatus((r.data && r.data.error) || "Failed to load users.", true);
          return;
        }
        state.users = r.data.users || [];
        state.total = r.data.total || state.users.length;
        setStatus("");
        renderTable();
      })
      .catch(function () {
        setStatus("Network error.", true);
      });
  }

  function updateUserLocal(userId, patch) {
    var idx = state.users.findIndex(function (u) {
      return u.id === userId;
    });
    if (idx >= 0) {
      Object.keys(patch).forEach(function (k) {
        state.users[idx][k] = patch[k];
      });
      renderTable();
    }
  }

  function parseBalanceInput(raw, currentBalance) {
    var cleaned = String(raw == null ? "" : raw).trim().replace(/,/g, "").replace(/\s/g, "");
    if (!cleaned || !/^\d+$/.test(cleaned)) {
      return { ok: false, error: "Enter a whole number for the new balance." };
    }
    var value = Number(cleaned);
    if (!Number.isFinite(value) || value < 0 || value > Number.MAX_SAFE_INTEGER) {
      return { ok: false, error: "Enter a valid non-negative whole number." };
    }
    value = Math.trunc(value);

    var current = Number(currentBalance);
    if (Number.isFinite(current) && current >= 0) {
      var currentStr = String(Math.trunc(current));
      var valueStr = String(value);
      // Catch accidental append: e.g. current 505050110 + typing "500" → 505050110500
      if (
        valueStr.length > currentStr.length &&
        valueStr.indexOf(currentStr) === 0 &&
        value !== current
      ) {
        return {
          ok: false,
          error:
            "That looks like digits appended to the current balance (" +
            formatNumber(current) +
            "). Enter only the new total (e.g. 1500), not the old balance plus extra digits.",
        };
      }
    }

    return { ok: true, value: value };
  }

  function saveBalance(userId, inputEl, currentBalance) {
    var parsed = parseBalanceInput(inputEl.value, currentBalance);
    if (!parsed.ok) {
      setStatus(parsed.error, true);
      return;
    }
    var value = parsed.value;
    var current = Number(currentBalance);
    if (!Number.isFinite(current)) {
      current = 0;
    }

    if (
      !window.confirm(
        "Set user #" +
          userId +
          " balance?\n\nCurrent: " +
          formatNumber(current) +
          " coins\nNew:     " +
          formatNumber(value) +
          " coins\n\nThis replaces the balance (does not add)."
      )
    ) {
      return;
    }

    state.saving[userId] = true;
    renderTable();
    setStatus("Setting balance for user #" + userId + " to " + formatNumber(value) + "…");

    fetch("/api/admin/users/" + userId + "/balance", {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ balance: value, reason: "Admin set balance" }),
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, data: data };
          });
      })
      .then(function (r) {
        delete state.saving[userId];
        if (!r.ok || !r.data || !r.data.success) {
          setStatus((r.data && r.data.error) || "Could not set balance.", true);
          renderTable();
          return;
        }
        var next = Number(r.data.balance);
        if (!Number.isFinite(next)) {
          next = value;
        }
        updateUserLocal(userId, { balance: Math.trunc(next) });
        setStatus(
          "Balance set to " +
            formatNumber(Math.trunc(next)) +
            " for user #" +
            userId +
            " (was " +
            formatNumber(r.data.previousBalance != null ? r.data.previousBalance : current) +
            ")."
        );
        if (state.ledgerUserId === userId) {
          state.ledgerBalance = Math.trunc(next);
          openLedger(userId);
        }
      })
      .catch(function () {
        delete state.saving[userId];
        setStatus("Network error while setting balance.", true);
        renderTable();
      });
  }

  function toggleAdmin(userId, isAdmin) {
    state.saving[userId] = true;
    renderTable();
    setStatus((isAdmin ? "Granting" : "Revoking") + " admin for user #" + userId + "…");

    fetch("/api/admin/users/" + userId + "/admin", {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ is_admin: isAdmin }),
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, data: data };
          });
      })
      .then(function (r) {
        delete state.saving[userId];
        if (!r.ok || !r.data || !r.data.success) {
          setStatus((r.data && r.data.error) || "Could not update admin role.", true);
          renderTable();
          return;
        }
        updateUserLocal(userId, { isAdmin: r.data.isAdmin });
        setStatus("Admin access updated for " + (r.data.email || "user #" + userId) + ".");
      })
      .catch(function () {
        delete state.saving[userId];
        setStatus("Network error while updating admin role.", true);
        renderTable();
      });
  }

  function deleteUser(userId, email) {
    var label = email || ("#" + userId);
    if (
      !window.confirm(
        "Delete account " +
          label +
          " permanently?\n\nThis removes their wallet, ledger, and purchases. This cannot be undone."
      )
    ) {
      return;
    }
    state.saving[userId] = true;
    renderTable();
    setStatus("Deleting user #" + userId + "…");

    fetch("/api/admin/users/" + userId + "/delete", {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: "{}",
    })
      .then(function (res) {
        return res
          .json()
          .catch(function () {
            return {};
          })
          .then(function (data) {
            return { ok: res.ok, data: data };
          });
      })
      .then(function (r) {
        delete state.saving[userId];
        if (!r.ok || !r.data || !r.data.success) {
          setStatus((r.data && r.data.error) || "Could not delete user.", true);
          renderTable();
          return;
        }
        state.users = state.users.filter(function (u) {
          return u.id !== userId;
        });
        state.total = Math.max(0, (state.total || 0) - 1);
        if (state.ledgerUser && state.ledgerUser.id === userId) {
          closeLedger();
        }
        renderTable();
        setStatus("Deleted " + (r.data.email || "user #" + userId) + ".");
      })
      .catch(function () {
        delete state.saving[userId];
        setStatus("Network error while deleting user.", true);
        renderTable();
      });
  }

  if (els.search) {
    var searchTimer = null;
    els.search.addEventListener("input", function () {
      clearTimeout(searchTimer);
      searchTimer = setTimeout(function () {
        state.search = els.search.value.trim();
        loadUsers();
      }, 250);
    });
  }

  if (els.body) {
    els.body.addEventListener("focusin", function (e) {
      var input = e.target.closest("[data-adm-balance-input]");
      if (input && typeof input.select === "function") {
        input.select();
      }
    });

    els.body.addEventListener("submit", function (e) {
      var form = e.target.closest("[data-adm-balance-form]");
      if (!form) return;
      e.preventDefault();
      var userId = parseInt(form.getAttribute("data-adm-balance-form"), 10);
      var input = form.querySelector("[data-adm-balance-input]");
      var currentBalance = form.getAttribute("data-adm-current-balance");
      if (userId && input) {
        saveBalance(userId, input, currentBalance);
      }
    });

    els.body.addEventListener("change", function (e) {
      var toggle = e.target.closest("[data-adm-admin-toggle]");
      if (!toggle) return;
      var userId = parseInt(toggle.getAttribute("data-adm-admin-toggle"), 10);
      if (!userId) return;
      toggleAdmin(userId, toggle.checked);
    });

    els.body.addEventListener("click", function (e) {
      var ledgerBtn = e.target.closest("[data-adm-ledger]");
      if (ledgerBtn) {
        var ledgerUserId = parseInt(ledgerBtn.getAttribute("data-adm-ledger"), 10);
        if (ledgerUserId) {
          openLedger(ledgerUserId);
        }
        return;
      }
      var purchasesBtn = e.target.closest("[data-adm-purchases]");
      if (purchasesBtn) {
        var purchasesUserId = parseInt(purchasesBtn.getAttribute("data-adm-purchases"), 10);
        if (purchasesUserId) {
          openPurchases(purchasesUserId);
        }
        return;
      }
      var usageBtn = e.target.closest("[data-adm-usage]");
      if (usageBtn) {
        var usageUserId = parseInt(usageBtn.getAttribute("data-adm-usage"), 10);
        if (usageUserId) {
          openUsage(usageUserId);
        }
        return;
      }
      var deleteBtn = e.target.closest("[data-adm-delete]");
      if (deleteBtn) {
        var deleteUserId = parseInt(deleteBtn.getAttribute("data-adm-delete"), 10);
        var deleteEmail = deleteBtn.getAttribute("data-adm-delete-email") || "";
        if (deleteUserId) {
          deleteUser(deleteUserId, deleteEmail);
        }
      }
    });
  }

  if (els.ledgerClose) {
    els.ledgerClose.addEventListener("click", closeLedger);
  }
  if (els.ledgerOverlay) {
    els.ledgerOverlay.addEventListener("click", function (e) {
      if (e.target === els.ledgerOverlay) {
        closeLedger();
      }
    });
  }
  if (els.purchasesClose) {
    els.purchasesClose.addEventListener("click", closePurchases);
  }
  if (els.purchasesOverlay) {
    els.purchasesOverlay.addEventListener("click", function (e) {
      if (e.target === els.purchasesOverlay) {
        closePurchases();
      }
    });
  }
  if (els.usageClose) {
    els.usageClose.addEventListener("click", closeUsage);
  }
  if (els.usageOverlay) {
    els.usageOverlay.addEventListener("click", function (e) {
      if (e.target === els.usageOverlay) {
        closeUsage();
      }
    });
  }
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    if (els.ledgerOverlay && !els.ledgerOverlay.hidden) {
      closeLedger();
    }
    if (els.purchasesOverlay && !els.purchasesOverlay.hidden) {
      closePurchases();
    }
    if (els.usageOverlay && !els.usageOverlay.hidden) {
      closeUsage();
    }
  });

  if (els.analyticsRefresh) {
    els.analyticsRefresh.addEventListener("click", function () {
      loadAnalytics();
    });
  }

  if (els.datasetRefresh) {
    els.datasetRefresh.addEventListener("click", function () {
      loadDatasetStats();
    });
  }

  if (els.todayRefresh) {
    els.todayRefresh.addEventListener("click", function () {
      loadTodayUsage();
    });
  }
  if (els.promoForm) {
    els.promoForm.addEventListener("submit", savePromo);
  }

  if (els.withdrawalsRefresh) {
    els.withdrawalsRefresh.addEventListener("click", function () {
      loadWithdrawals();
    });
  }
  if (els.withdrawalsBody) {
    els.withdrawalsBody.addEventListener("click", function (e) {
      var approveBtn = e.target.closest("[data-adm-withdrawal-approve]");
      if (approveBtn) {
        var approveId = parseInt(
          approveBtn.getAttribute("data-adm-withdrawal-approve"),
          10
        );
        if (approveId) resolveWithdrawal(approveId, true);
        return;
      }
      var rejectBtn = e.target.closest("[data-adm-withdrawal-reject]");
      if (rejectBtn) {
        var rejectId = parseInt(
          rejectBtn.getAttribute("data-adm-withdrawal-reject"),
          10
        );
        if (rejectId) resolveWithdrawal(rejectId, false);
      }
    });
  }

  loadTodayUsage();
  loadAnalytics();
  loadDatasetStats();
  loadWithdrawals();
  loadUsers();
})();
