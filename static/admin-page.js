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
          '">' +
          '<input type="number" min="0" step="1" class="adm-balance-input" value="' +
          user.balance +
          '" data-adm-balance-input="' +
          user.id +
          '" aria-label="Coin balance for user ' +
          user.id +
          '" />' +
          '<button type="submit" class="adm-btn adm-btn--save"' +
          (saving ? " disabled" : "") +
          ">Save</button>" +
          "</form></td>" +
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
          escapeHtml(formatCredits(credits)) +
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

  function saveBalance(userId, inputEl) {
    var value = parseInt(inputEl.value, 10);
    if (isNaN(value) || value < 0) {
      setStatus("Balance must be a non-negative number.", true);
      return;
    }
    state.saving[userId] = true;
    renderTable();
    setStatus("Saving balance for user #" + userId + "…");

    fetch("/api/admin/users/" + userId + "/balance", {
      method: "PATCH",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ balance: value }),
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
          setStatus((r.data && r.data.error) || "Could not update balance.", true);
          renderTable();
          return;
        }
        updateUserLocal(userId, { balance: r.data.balance });
        setStatus("Balance updated for user #" + userId + ".");
      })
      .catch(function () {
        delete state.saving[userId];
        setStatus("Network error while saving balance.", true);
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
    els.body.addEventListener("submit", function (e) {
      var form = e.target.closest("[data-adm-balance-form]");
      if (!form) return;
      e.preventDefault();
      var userId = parseInt(form.getAttribute("data-adm-balance-form"), 10);
      var input = form.querySelector("[data-adm-balance-input]");
      if (userId && input) {
        saveBalance(userId, input);
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

  loadAnalytics();
  loadUsers();
})();
