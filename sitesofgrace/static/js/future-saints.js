/* Future Saints: small progressive enhancements. Pages work without this file.
   No cookies. One sessionStorage key ("fs-reading-level"), tab-scoped, never sent anywhere. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("fs-js");

  // ---- Section menu: a disclosure at <=900px. Esc closes and returns focus. ----
  var button = document.querySelector("[data-fs-menu-button]");
  var nav = button && document.getElementById(button.getAttribute("aria-controls"));
  if (button && nav) {
    var setOpen = function (open) {
      button.setAttribute("aria-expanded", open ? "true" : "false");
      nav.classList.toggle("is-open", open);
    };
    setOpen(false);
    button.addEventListener("click", function () {
      setOpen(button.getAttribute("aria-expanded") !== "true");
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && button.getAttribute("aria-expanded") === "true") {
        setOpen(false);
        button.focus();
      }
    });
  }

  // ---- Reading level: ?level= in the address and sessionStorage only. ----
  var KEY = "fs-reading-level";
  var LEVELS = ["explorer", "researcher"];
  var buttons = Array.prototype.slice.call(document.querySelectorAll("[data-fs-level]"));
  if (!buttons.length) { return; }
  var status = document.querySelector("[data-fs-level-status]");

  var read = function () {
    try { return window.sessionStorage.getItem(KEY) || ""; } catch (e) { return ""; }
  };
  var write = function (level) {
    try { window.sessionStorage.setItem(KEY, level); } catch (e) { /* storage blocked: fine */ }
  };
  var show = function (level) {
    buttons.forEach(function (b) {
      b.setAttribute("aria-pressed", b.value === level ? "true" : "false");
    });
    if (status) {
      var chosen = buttons.filter(function (b) { return b.value === level; })[0];
      status.textContent = chosen ? chosen.getAttribute("data-fs-level-label") : "";
    }
  };

  var params = new URLSearchParams(window.location.search);
  var fromUrl = params.get("level");
  if (LEVELS.indexOf(fromUrl) !== -1) {
    write(fromUrl);
    show(fromUrl);
  } else if (LEVELS.indexOf(read()) !== -1) {
    show(read());
  }

  buttons.forEach(function (b) {
    b.addEventListener("click", function (event) {
      event.preventDefault();
      var level = b.value;
      write(level);
      show(level);
      params.set("level", level);
      var url = window.location.pathname + "?" + params.toString() + window.location.hash;
      window.history.replaceState(null, "", url);
    });
  });
})();
