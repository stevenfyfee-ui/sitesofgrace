/*
 * "On this page" section navigation.
 *
 * Progressive enhancement only: the rail is server-rendered and its links are
 * plain fragment anchors, so everything still works with this file blocked.
 * All this adds is highlighting whichever section you are currently reading --
 * and, in the mobile chip-bar layout, keeping that chip scrolled into view.
 */
(function () {
  "use strict";

  var nav = document.querySelector("[data-section-nav]");
  if (!nav || !("IntersectionObserver" in window)) return;

  var links = Array.prototype.slice.call(nav.querySelectorAll("[data-section-link]"));
  if (!links.length) return;

  var linksById = {};
  var targets = [];

  links.forEach(function (link) {
    var id = link.getAttribute("data-section-link");
    var target = document.getElementById(id);
    if (!target) return;
    linksById[id] = link;
    targets.push(target);
  });
  if (!targets.length) return;

  var activeId = null;

  function setActive(id) {
    if (id === activeId || !linksById[id]) return;
    if (activeId && linksById[activeId]) {
      linksById[activeId].removeAttribute("aria-current");
    }
    activeId = id;
    var link = linksById[id];
    link.setAttribute("aria-current", "true");

    // Chip-bar layout only: keep the active chip visible. The list does not
    // scroll in the desktop rail layout, so this is a no-op there.
    if (nav.scrollWidth > nav.clientWidth && link.scrollIntoView) {
      link.scrollIntoView({ block: "nearest", inline: "center" });
    }
  }

  // Track how much of each section is on screen and light up the one nearest
  // the top of the reading area. rootMargin pulls the top edge below the sticky
  // header so a section counts as "current" once its heading clears it.
  var visible = {};

  var observer = new IntersectionObserver(
    function (entries) {
      entries.forEach(function (entry) {
        if (entry.isIntersecting) {
          visible[entry.target.id] = entry.boundingClientRect.top;
        } else {
          delete visible[entry.target.id];
        }
      });

      var ids = Object.keys(visible);
      if (!ids.length) return;

      ids.sort(function (a, b) {
        return Math.abs(visible[a]) - Math.abs(visible[b]);
      });
      setActive(ids[0]);
    },
    { rootMargin: "-140px 0px -55% 0px", threshold: 0 }
  );

  targets.forEach(function (target) {
    observer.observe(target);
  });

  // Clicking a chip should feel immediate rather than waiting for the scroll to
  // settle and the observer to catch up.
  links.forEach(function (link) {
    link.addEventListener("click", function () {
      setActive(link.getAttribute("data-section-link"));
    });
  });
})();
