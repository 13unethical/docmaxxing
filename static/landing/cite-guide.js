(function () {
  var root = document.querySelector(".cite-guide");
  var form = document.getElementById("cite-gen-form");
  if (!root || !form) return;

  var style = root.getAttribute("data-cite-style") || "APA";
  var mode = root.getAttribute("data-cite-mode") || "url";
  var input = document.getElementById("cite-gen-input");
  var status = document.getElementById("cite-gen-status");
  var out = document.getElementById("cite-gen-out");

  function setStatus(msg, isError) {
    status.textContent = msg || "";
    status.classList.toggle("is-error", !!isError);
  }

  form.addEventListener("submit", function (ev) {
    ev.preventDefault();
    var value = (input.value || "").trim();
    if (!value) {
      setStatus("Enter a value first.", true);
      return;
    }
    var payload = { mode: mode, style: style };
    if (mode === "url") payload.url = value;
    else if (mode === "doi") payload.doi = value;
    else if (mode === "isbn") payload.isbn = value;
    else payload.paste = value;

    setStatus("Generating…");
    out.hidden = true;
    fetch("/api/reference", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(payload),
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          setStatus((result.data && result.data.error) || "Could not generate citation.", true);
          return;
        }
        var citation = (result.data && result.data.citation) || "";
        out.textContent = citation;
        out.hidden = !citation;
        setStatus(citation ? "Done — copy the reference below." : "Empty response.");
      })
      .catch(function () {
        setStatus("Network error — try again.", true);
      });
  });
})();
