/*
 * Signed-in account menu in the header (includes/_account_menu.html).
 *
 * Progressive enhancement only: the menu is a <details>/<summary>, so it
 * opens and closes on click and Enter/Space with this file blocked. All this
 * adds is what a disclosure doesn't do by itself -- close on Escape (handing
 * focus back to the trigger), on a click anywhere outside, and when keyboard
 * focus moves out of it -- and keeping aria-expanded on the summary in step
 * with the open state.
 */
(function () {
  "use strict";

  var menu = document.querySelector("[data-account-menu]");
  if (!menu) return;
  var trigger = menu.querySelector("summary");

  function sync() {
    trigger.setAttribute("aria-expanded", String(menu.open));
  }

  function close(returnFocus) {
    if (!menu.open) return;
    menu.open = false;
    sync(); // "toggle" fires a task later; screen readers shouldn't hear a stale state
    if (returnFocus) trigger.focus();
  }

  menu.addEventListener("toggle", sync);
  sync();

  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && menu.open) {
      close(menu.contains(document.activeElement));
    }
  });

  document.addEventListener("click", function (event) {
    if (!menu.contains(event.target)) close(false);
  });

  menu.addEventListener("focusout", function (event) {
    // relatedTarget is null when focus leaves the page entirely (or goes to
    // something unfocusable); only close when it has landed somewhere else.
    if (event.relatedTarget && !menu.contains(event.relatedTarget)) close(false);
  });
})();
