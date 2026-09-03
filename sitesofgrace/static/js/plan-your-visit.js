/*
 * "Plan Your Visit" panels on a sacred site page.
 *
 * Progressive enhancement only. The panels are native <details>, so with this
 * file blocked they still open, close, and respond to the keyboard; all that
 * is lost is the expand-all button, deep links opening their own panel, and
 * the print behaviour.
 */
(function () {
  "use strict";

  var panels = Array.prototype.slice.call(
    document.querySelectorAll("[data-plan-panel]")
  );
  if (!panels.length) return;

  var toggleAll = document.querySelector("[data-plan-toggle-all]");

  function allOpen() {
    return panels.every(function (panel) {
      return panel.open;
    });
  }

  // The button describes what it will do next, so it has to follow real panel
  // state -- including when a panel is opened or closed on its own.
  function syncToggle() {
    if (!toggleAll) return;
    var open = allOpen();
    toggleAll.textContent = open ? "Collapse all" : "Expand all";
    toggleAll.setAttribute("aria-expanded", open ? "true" : "false");
  }

  if (toggleAll) {
    toggleAll.addEventListener("click", function () {
      var open = allOpen();
      panels.forEach(function (panel) {
        panel.open = !open;
      });
      syncToggle();
    });
  }

  panels.forEach(function (panel) {
    panel.addEventListener("toggle", syncToggle);
  });

  /* A shared link like /explore/.../lourdes/#where-to-stay must not land on a
     closed box. Open the panel, then re-anchor: the target moves down the page
     as the panel expands, so the browser's own jump lands in the wrong place. */
  function openFromHash() {
    if (!window.location.hash) return;
    var id;
    try {
      id = decodeURIComponent(window.location.hash.slice(1));
    } catch (err) {
      return;
    }
    var target = document.getElementById(id);
    if (!target) return;
    var panel = target.closest ? target.closest("[data-plan-panel]") : null;
    if (!panel || panel.open) return;
    panel.open = true;
    syncToggle();
    window.requestAnimationFrame(function () {
      target.scrollIntoView({ block: "start" });
    });
  }

  window.addEventListener("hashchange", openFromHash);
  openFromHash();

  // Clicking a rail sub-item when that panel is already the hash fires no
  // hashchange, so open it here too.
  document.querySelectorAll(".section-nav-sublink").forEach(function (link) {
    link.addEventListener("click", function () {
      var panel = document.getElementById(link.getAttribute("data-section-link"));
      if (panel && !panel.open) {
        panel.open = true;
        syncToggle();
      }
    });
  });

  /* Printing should produce the whole plan, not a stack of closed headings --
     the Quick Card offers a "print this plan" affordance and this is what
     honours it. The reader's own open/closed state is put back afterwards. */
  var stateBeforePrint = null;

  window.addEventListener("beforeprint", function () {
    stateBeforePrint = panels.map(function (panel) {
      return panel.open;
    });
    panels.forEach(function (panel) {
      panel.open = true;
    });
  });

  window.addEventListener("afterprint", function () {
    if (!stateBeforePrint) return;
    panels.forEach(function (panel, index) {
      panel.open = stateBeforePrint[index];
    });
    stateBeforePrint = null;
    syncToggle();
  });

  syncToggle();
})();
