/**
 * Pricing page — mock top-up. Real checkout wires in later; for now clicking a
 * package instantly credits coins via POST /api/economy/topup.
 */
(function () {
  "use strict";

  var statusEl = document.querySelector("[data-topup-status]");
  var buttons = document.querySelectorAll("[data-topup]");
  if (!buttons.length) return;

  function setStatus(msg, isError) {
    if (!statusEl) return;
    statusEl.textContent = msg;
    statusEl.classList.toggle("is-error", !!isError);
  }

  Array.prototype.forEach.call(buttons, function (btn) {
    btn.addEventListener("click", function () {
      var pkg = btn.getAttribute("data-topup");
      var original = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Processing…";
      setStatus("");

      fetch("/api/economy/topup", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ package: pkg }),
      })
        .then(function (res) {
          return res
            .json()
            .catch(function () { return {}; })
            .then(function (data) { return { status: res.status, ok: res.ok, data: data }; });
        })
        .then(function (r) {
          btn.disabled = false;
          btn.textContent = original;
          if (r.status === 401 || (r.data && r.data.error === "AUTH_REQUIRED")) {
            setStatus("Please sign in to buy coins.", true);
            setTimeout(function () { window.location.href = "/login?next=/pricing"; }, 900);
            return;
          }
          if (!r.ok || !r.data || !r.data.success) {
            setStatus((r.data && r.data.error) || "Top-up failed. Please try again.", true);
            return;
          }
          if (typeof window.refreshCoinBalance === "function") {
            window.refreshCoinBalance();
          }
          setStatus(
            "Added " + r.data.coins_added + " coins. New balance: " + r.data.balance + " coins."
          );
        })
        .catch(function () {
          btn.disabled = false;
          btn.textContent = original;
          setStatus("Network error. Please try again.", true);
        });
    });
  });
})();
