/*
 * v2 sacred site page: "Read more" on The Story and Church Recognition.
 *
 * Progressive enhancement only. The server renders the full text with the
 * button hidden; this file clamps a section to about eight lines only after
 * measuring that it is actually taller than that, and only then reveals the
 * button. Without JavaScript nothing is clamped. Print CSS undoes the clamp.
 */
(function () {
  "use strict";

  var LINES = 8;

  function lineHeight(el) {
    var style = window.getComputedStyle(el);
    var value = parseFloat(style.lineHeight);
    return isNaN(value) ? parseFloat(style.fontSize) * 1.6 : value;
  }

  function init() {
  Array.prototype.forEach.call(document.querySelectorAll("[data-clamp]"), function (wrap) {
    var body = wrap.querySelector("[data-clamp-body]");
    var button = wrap.querySelector("[data-clamp-toggle]");
    if (!body || !button) return;

    var limit = Math.round(lineHeight(body) * LINES);
    // Only clamp when there's at least half a line more to reveal.
    if (body.scrollHeight <= limit + lineHeight(body) / 2) return;

    body.style.setProperty("--v2-clamp-height", limit + "px");
    // Scroll back to the section (it carries the scroll-margin that clears
    // the sticky header and section bar), which puts its heading in view.
    var section = wrap.closest("section");

    function collapse(scrollBack) {
      body.classList.add("is-clamped");
      button.setAttribute("aria-expanded", "false");
      button.textContent = "Read more";
      if (scrollBack && section && section.scrollIntoView) {
        section.scrollIntoView({ block: "start" });
      }
    }

    function expand() {
      body.classList.remove("is-clamped");
      button.setAttribute("aria-expanded", "true");
      button.textContent = "Show less";
    }

    button.hidden = false;
    collapse(false);
    button.addEventListener("click", function () {
      if (body.classList.contains("is-clamped")) {
        expand();
      } else {
        collapse(true);
      }
    });
  });
  }

  // Measure with the page's web fonts in place: the fallback font sets
  // fewer lines, which would leave long text unclamped.
  if (document.fonts && document.fonts.ready) {
    document.fonts.ready.then(init, init);
  } else {
    window.addEventListener("load", init);
  }
})();
