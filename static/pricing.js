/**
 * Pricing page — credit checkout via Cryptomus (preferred) or Paddle fallback.
 * Package ids come from the page; availability from GET /api/economy/packages.
 */
(function () {
  "use strict";

  var statusEl = document.querySelector("[data-topup-status]");
  var buyButtons = document.querySelectorAll("[data-topup]");
  if (!buyButtons.length) return;

  var paddleReady = null;
  var packagesMeta = {
    cryptomus_configured: false,
    paddle_configured: false,
    payment_provider: null,
  };

  function setStatus(msg, isError) {
    if (!statusEl) return;
    statusEl.textContent = msg || "";
    statusEl.classList.toggle("is-error", !!isError);
  }

  function loadPaddleJs(clientToken, environment) {
    if (paddleReady) return paddleReady;
    paddleReady = new Promise(function (resolve, reject) {
      if (window.Paddle && window.Paddle.Initialized) {
        resolve(window.Paddle);
        return;
      }
      var script = document.createElement("script");
      script.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
      script.async = true;
      script.onload = function () {
        try {
          if (environment === "sandbox") {
            window.Paddle.Environment.set("sandbox");
          }
          window.Paddle.Initialize({ token: clientToken });
          resolve(window.Paddle);
        } catch (err) {
          reject(err);
        }
      };
      script.onerror = function () {
        reject(new Error("Failed to load Paddle.js"));
      };
      document.head.appendChild(script);
    });
    return paddleReady;
  }

  function openPaddleCheckout(data) {
    var txnId = data.transaction_id;
    var url = data.checkout_url;
    var token = data.client_token;
    var env = data.environment || "sandbox";

    if (token && txnId && window.Promise) {
      return loadPaddleJs(token, env)
        .then(function (Paddle) {
          Paddle.Checkout.open({ transactionId: txnId });
          setStatus("Checkout opened. Complete payment in the Paddle window.");
        })
        .catch(function () {
          if (url) {
            window.location.href = url;
            return;
          }
          setStatus("Could not open checkout. Please try again.", true);
        });
    }
    if (url) {
      window.location.href = url;
      return Promise.resolve();
    }
    setStatus("Checkout URL missing. Check Paddle configuration.", true);
    return Promise.resolve();
  }

  function openCryptomusCheckout(data) {
    var url = data.payment_url;
    if (url) {
      window.location.href = url;
      return Promise.resolve();
    }
    setStatus("Payment URL missing. Check Cryptomus configuration.", true);
    return Promise.resolve();
  }

  function setButtonAvailable(btn, available, reason) {
    btn.disabled = !available;
    if (!available) {
      btn.title = reason || "This package is not available for checkout yet.";
    } else {
      btn.removeAttribute("title");
    }
  }

  function requireAuth(btn, original) {
    btn.disabled = false;
    btn.textContent = original;
    setStatus("Create a free account to buy credits.", true);
    function goAuth() {
      window.location.href = "/register?next=/pricing";
    }
    if (window.DMAuth && typeof window.DMAuth.require === "function") {
      window.DMAuth.require({
        reason: "Create a free account to buy credits.",
      })
        .then(function () {
          btn.click();
        })
        .catch(goAuth);
      return;
    }
    setTimeout(goAuth, 700);
  }

  function postJson(url, body) {
    return fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    }).then(function (res) {
      return res
        .json()
        .catch(function () {
          return {};
        })
        .then(function (data) {
          return { status: res.status, ok: res.ok, data: data };
        });
    });
  }

  function startCryptomus(btn, pkg, original) {
    return postJson("/api/payments/create", { package: pkg }).then(function (r) {
      if (r.status === 401 || (r.data && r.data.error === "AUTH_REQUIRED")) {
        requireAuth(btn, original);
        return;
      }
      if (r.status === 503 && r.data && r.data.error === "CRYPTOMUS_NOT_CONFIGURED") {
        btn.disabled = false;
        btn.textContent = original;
        setStatus(
          "Cryptomus payments are not available right now.",
          true
        );
        return;
      }
      if (!r.ok || !r.data || !r.data.success || !r.data.payment_url) {
        btn.disabled = false;
        btn.textContent = original;
        setStatus(
          (r.data && (r.data.message || r.data.error)) ||
            "Checkout failed. Please try again.",
          true
        );
        return;
      }
      setStatus("Redirecting to Cryptomus…");
      return openCryptomusCheckout(r.data);
    });
  }

  function startPaddle(btn, pkg, original) {
    return postJson("/api/economy/checkout", { package: pkg }).then(function (r) {
      if (r.status === 401 || (r.data && r.data.error === "AUTH_REQUIRED")) {
        requireAuth(btn, original);
        return;
      }
      if (r.status === 503 && r.data && r.data.error === "PADDLE_NOT_CONFIGURED") {
        btn.disabled = false;
        btn.textContent = original;
        setStatus(
          "Paddle API key is missing. Set PADDLE_API_KEY (and PADDLE_CLIENT_TOKEN) in .env.",
          true
        );
        return;
      }
      if (!r.ok || !r.data || !r.data.success) {
        btn.disabled = false;
        btn.textContent = original;
        setStatus(
          (r.data && (r.data.message || r.data.error)) ||
            "Checkout failed. Please try again.",
          true
        );
        return;
      }
      return openPaddleCheckout(r.data).then(function () {
        btn.disabled = false;
        btn.textContent = original;
      });
    });
  }

  function bindPurchase(btn) {
    btn.addEventListener("click", function () {
      var pkg = btn.getAttribute("data-topup");
      if (!pkg || btn.disabled) return;
      var original = btn.textContent;
      btn.disabled = true;
      btn.textContent = "Opening checkout…";
      setStatus("");

      var useCryptomus = !!packagesMeta.cryptomus_configured;
      var starter = useCryptomus
        ? startCryptomus(btn, pkg, original)
        : startPaddle(btn, pkg, original);

      starter.catch(function () {
        btn.disabled = false;
        btn.textContent = original;
        setStatus("Network error. Please try again.", true);
      });
    });
  }

  buyButtons.forEach(function (btn) {
    bindPurchase(btn);
  });

  fetch("/api/economy/packages", { headers: { Accept: "application/json" } })
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
      var byId = {};
      if (r.ok && r.data) {
        packagesMeta.cryptomus_configured = !!r.data.cryptomus_configured;
        packagesMeta.paddle_configured = !!r.data.paddle_configured;
        packagesMeta.payment_provider = r.data.payment_provider || null;
        if (Array.isArray(r.data.packages)) {
          r.data.packages.forEach(function (pkg) {
            byId[pkg.id] = pkg;
          });
        }
      }
      buyButtons.forEach(function (btn) {
        var id = btn.getAttribute("data-topup");
        var pkg = byId[id];
        if (packagesMeta.cryptomus_configured) {
          setButtonAvailable(btn, !!pkg, "Unknown package.");
          return;
        }
        var hasPrice = !!(pkg && pkg.price_id && String(pkg.price_id).trim());
        setButtonAvailable(
          btn,
          hasPrice && packagesMeta.paddle_configured,
          "Configure Cryptomus or Paddle to enable checkout."
        );
      });
    })
    .catch(function () {
      /* Keep buttons enabled; checkout will surface config errors. */
    });
})();
