/**
 * Admin panel — user management.
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
  };

  var els = {
    body: root.querySelector("[data-adm-body]"),
    empty: root.querySelector("[data-adm-empty]"),
    search: root.querySelector("[data-adm-search]"),
    status: root.querySelector("[data-adm-status]"),
    stats: root.querySelector("[data-adm-stats]"),
    totalUsers: root.querySelector("[data-adm-total-users]"),
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
      return new Date(iso).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "numeric",
        minute: "2-digit",
      });
    } catch (e) {
      return iso;
    }
  }

  function setStatus(msg, isError) {
    if (!els.status) return;
    els.status.textContent = msg || "";
    els.status.classList.toggle("adm-status--error", !!isError);
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
          (user.isAdmin
            ? '<span class="adm-badge adm-badge--admin">Admin</span>'
            : '<span class="adm-badge adm-badge--user">User</span>') +
          "</td></tr>"
        );
      })
      .join("");
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
  }

  loadUsers();
})();
