/*
 * Yesterday / Today / Tomorrow tabs on the home page's "Today in the Church"
 * card (home/includes/_today_in_church.html).
 *
 * Progressive enhancement only: all three days are already in the HTML, and
 * without this file yesterday and tomorrow read as two compact lines under
 * today. This reveals the tablist, hides the days that aren't selected, and
 * gives the tabs the usual arrow / Home / End keys.
 */
(function () {
  "use strict";

  var card = document.querySelector("[data-today-card]");
  if (!card) return;
  var tablist = card.querySelector("[data-today-tabs]");
  if (!tablist) return;
  var tabs = Array.prototype.slice.call(tablist.querySelectorAll('[role="tab"]'));
  var panels = {};
  tabs.forEach(function (tab) {
    var panel = document.getElementById(tab.getAttribute("aria-controls"));
    if (panel) {
      panel.setAttribute("role", "tabpanel");
      panel.setAttribute("aria-labelledby", tab.id);
      panel.removeAttribute("aria-label");
      panels[tab.getAttribute("data-day")] = panel;
    }
  });

  function select(tab, focus) {
    tabs.forEach(function (other) {
      var on = other === tab;
      other.setAttribute("aria-selected", String(on));
      other.setAttribute("tabindex", on ? "0" : "-1");
      var panel = panels[other.getAttribute("data-day")];
      if (panel) {
        if (on) { panel.removeAttribute("hidden"); } else { panel.setAttribute("hidden", ""); }
      }
    });
    if (focus) tab.focus();
  }

  tabs.forEach(function (tab, i) {
    tab.addEventListener("click", function () { select(tab, false); });
    tab.addEventListener("keydown", function (event) {
      var next = null;
      if (event.key === "ArrowRight") next = tabs[(i + 1) % tabs.length];
      else if (event.key === "ArrowLeft") next = tabs[(i - 1 + tabs.length) % tabs.length];
      else if (event.key === "Home") next = tabs[0];
      else if (event.key === "End") next = tabs[tabs.length - 1];
      if (next) {
        event.preventDefault();
        select(next, true);
      }
    });
  });

  card.classList.add("is-tabbed");
  tablist.removeAttribute("hidden");
  for (var i = 0; i < tabs.length; i++) {
    if (tabs[i].getAttribute("data-day") === "today") { select(tabs[i], false); break; }
  }
})();
