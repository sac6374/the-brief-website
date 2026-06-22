/* The Brief — AJAX subscribe form handler */
(function () {
  "use strict";

  var ENDPOINT = "https://formspree.io/f/xpqegpgb";

  /* ── Inline styles that match the site design system ── */
  var TOAST_CSS = [
    "position:fixed",
    "bottom:28px",
    "left:50%",
    "transform:translateX(-50%) translateY(20px)",
    "background:#111010",
    "color:#f7f3ec",
    "font-family:'DM Mono',monospace",
    "font-size:11px",
    "letter-spacing:.14em",
    "text-transform:uppercase",
    "padding:16px 28px",
    "border-top:3px solid #1a5432",
    "max-width:calc(100vw - 48px)",
    "width:420px",
    "text-align:center",
    "line-height:1.7",
    "z-index:9999",
    "opacity:0",
    "transition:opacity .25s ease, transform .25s ease",
    "pointer-events:none",
  ].join(";");

  var ERROR_CSS = [
    "position:fixed",
    "bottom:28px",
    "left:50%",
    "transform:translateX(-50%) translateY(20px)",
    "background:#111010",
    "color:#f7f3ec",
    "font-family:'DM Mono',monospace",
    "font-size:11px",
    "letter-spacing:.14em",
    "text-transform:uppercase",
    "padding:16px 28px",
    "border-top:3px solid #b02020",
    "max-width:calc(100vw - 48px)",
    "width:420px",
    "text-align:center",
    "line-height:1.7",
    "z-index:9999",
    "opacity:0",
    "transition:opacity .25s ease, transform .25s ease",
    "pointer-events:none",
  ].join(";");

  function showToast(message, isError) {
    /* Remove any existing toast */
    var existing = document.getElementById("brief-toast");
    if (existing) existing.parentNode.removeChild(existing);

    var toast = document.createElement("div");
    toast.id = "brief-toast";
    toast.setAttribute("role", "status");
    toast.setAttribute("aria-live", "polite");
    toast.setAttribute("aria-atomic", "true");
    toast.style.cssText = isError ? ERROR_CSS : TOAST_CSS;
    toast.textContent = message;
    document.body.appendChild(toast);

    /* Trigger animation on next frame */
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        toast.style.opacity = "1";
        toast.style.transform = "translateX(-50%) translateY(0)";
      });
    });

    /* Auto-dismiss after 6 s */
    setTimeout(function () {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(-50%) translateY(20px)";
      setTimeout(function () {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 300);
    }, 6000);
  }

  function showInlineSuccess(form) {
    /* Replace the form with a confirmation card that matches site styles */
    var card = document.createElement("div");
    card.style.cssText = [
      "border:1px solid #d5cfc4",
      "border-top:2.5px solid #1a5432",
      "padding:22px 24px",
      "font-family:'DM Mono',monospace",
      "max-width:" + form.parentNode.style.maxWidth || "420px",
    ].join(";");

    card.innerHTML =
      '<div style="font-size:9px;letter-spacing:.22em;text-transform:uppercase;' +
      'color:#1a5432;margin-bottom:10px">Subscribed</div>' +
      '<div style="font-size:13px;line-height:1.74;color:#111010">' +
      "You're on the list. Check your inbox to confirm your subscription — " +
      "then look for The Brief every weekday morning." +
      "</div>";

    form.parentNode.replaceChild(card, form);
  }

  function handleSubmit(form) {
    var btn = form.querySelector("button[type=submit]");
    var email = form.querySelector('input[type="email"]');

    if (!email || !email.value.trim()) return;

    /* Disable button and show loading state */
    btn.disabled = true;
    var originalText = btn.textContent;
    btn.textContent = "Sending…";

    var body = new URLSearchParams();
    body.append("email", email.value.trim());

    /* Copy any hidden fields (e.g. _subject) */
    var hidden = form.querySelectorAll('input[type="hidden"]');
    for (var i = 0; i < hidden.length; i++) {
      /* Skip the _next redirect field — we're handling navigation ourselves */
      if (hidden[i].name !== "_next") {
        body.append(hidden[i].name, hidden[i].value);
      }
    }

    fetch(ENDPOINT, {
      method: "POST",
      headers: { Accept: "application/json" },
      body: body,
    })
      .then(function (res) {
        if (res.ok) {
          showInlineSuccess(form);
          showToast("You’re subscribed — see you tomorrow morning.", false);
        } else {
          return res.json().then(function (data) {
            throw new Error((data.errors || []).map(function (e) { return e.message; }).join(", ") || "Submission failed");
          });
        }
      })
      .catch(function (err) {
        btn.disabled = false;
        btn.textContent = originalText;
        var msg = err.message && err.message.length < 120
          ? err.message
          : "Something went wrong. Please try again or email us directly.";
        showToast("Error: " + msg, true);
      });
  }

  function init() {
    var forms = document.querySelectorAll("form.subscribe-form");
    for (var i = 0; i < forms.length; i++) {
      (function (form) {
        form.addEventListener("submit", function (e) {
          e.preventDefault();
          handleSubmit(form);
        });
      })(forms[i]);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
