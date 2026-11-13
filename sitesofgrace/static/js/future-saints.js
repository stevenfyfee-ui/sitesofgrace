/* Future Saints: small progressive enhancements. Pages work without this file.
   No cookies and no browser storage. The quiz keeps its state in memory only:
   nothing is stored or sent. */
(function () {
  "use strict";
  var root = document.documentElement;
  root.classList.add("fs-js");
  var reduceMotion = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

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

  // ---- Print Research Sheet: the browser's print, using the print stylesheet. ----
  Array.prototype.forEach.call(document.querySelectorAll("[data-fs-print]"), function (link) {
    link.addEventListener("click", function (event) {
      event.preventDefault();
      window.print();
    });
  });

  // ---- Quiz: one question at a time, friendly feedback, nothing stored. ----
  var quiz = document.querySelector("[data-fs-quiz]");
  var dataNode = document.getElementById("fs-quiz-data");
  if (quiz && dataNode) {
    var questions = [];
    try { questions = JSON.parse(dataNode.textContent) || []; } catch (e) { questions = []; }
    if (questions.length) {
      var el = function (sel) { return quiz.querySelector(sel); };
      var progress = el("[data-fs-quiz-progress]");
      var prompt = el("[data-fs-quiz-prompt]");
      var choices = el("[data-fs-quiz-choices]");
      var feedback = el("[data-fs-quiz-feedback]");
      var next = el("[data-fs-quiz-next]");
      var finish = el("[data-fs-quiz-finish]");
      var retry = el("[data-fs-quiz-retry]");
      var index = 0;
      var score = 0;
      prompt.id = "fs-quiz-prompt-label";

      var focusQuietly = function (node) {
        node.focus({ preventScroll: reduceMotion });
      };
      var render = function () {
        var q = questions[index];
        progress.textContent = "Question " + (index + 1) + " of " + questions.length;
        prompt.textContent = q.prompt;
        feedback.textContent = "";
        feedback.className = "fs-quiz-feedback";
        next.hidden = true;
        finish.hidden = true;
        retry.hidden = true;
        choices.innerHTML = "";
        q.choices.forEach(function (choice) {
          var b = document.createElement("button");
          b.type = "button";
          b.className = "fs-quiz-choice";
          b.textContent = choice.text;
          b.addEventListener("click", function () { answer(b, choice, q); });
          choices.appendChild(b);
        });
      };
      var answer = function (picked, choice, q) {
        Array.prototype.forEach.call(choices.querySelectorAll("button"), function (b, i) {
          b.disabled = true;
          if (q.choices[i].correct) { b.classList.add("is-correct"); }
        });
        if (choice.correct) {
          score += 1;
          feedback.textContent = "Yes, that's right! " + (q.explanation || "");
          feedback.classList.add("is-right");
        } else {
          picked.classList.add("is-wrong");
          var right = q.choices.filter(function (c) { return c.correct; })[0];
          feedback.textContent = "Good try! The answer is: " + (right ? right.text : "") + ". " + (q.explanation || "");
          feedback.classList.add("is-learning");
        }
        var last = index === questions.length - 1;
        next.hidden = last;
        finish.hidden = !last;
        focusQuietly(last ? finish : next);
      };
      next.addEventListener("click", function () {
        index += 1;
        render();
        focusQuietly(prompt);
      });
      finish.addEventListener("click", function () {
        progress.textContent = "All done!";
        prompt.textContent = "You got " + score + " out of " + questions.length + ".";
        choices.innerHTML = "";
        feedback.className = "fs-quiz-feedback is-right";
        feedback.textContent = score === questions.length ? "Wonderful! You remembered everything." : "Well done! Read the story again and try once more.";
        finish.hidden = true;
        retry.hidden = false;
        focusQuietly(prompt);
      });
      retry.addEventListener("click", function () {
        index = 0;
        score = 0;
        render();
        focusQuietly(prompt);
      });
      quiz.hidden = false;
      render();
    }
  }

  // ---- Missions hub: select a pin in place, share it as ?mission=<slug>. ----
  // Without this the pins are submit buttons of a GET form and the server
  // renders the selected panel, so nothing here is required.
  var map = document.querySelector("[data-fs-map]");
  var panel = document.querySelector("[data-fs-panel]");
  var missionData = document.getElementById("fs-mission-data");
  if (map && panel && missionData) {
    var missions = {};
    try {
      JSON.parse(missionData.textContent).forEach(function (m) { missions[m.slug] = m; });
    } catch (e) { missions = {}; }
    var pins = Array.prototype.slice.call(map.querySelectorAll("[data-fs-pin]"));
    var part = function (name) { return panel.querySelector("[data-fs-panel-" + name + "]"); };
    var chooser = map.querySelector("[data-fs-chooser]");
    var chooserList = map.querySelector("[data-fs-chooser-list]");
    var radius = parseFloat(map.getAttribute("data-fs-pin-radius")) || 24;
    var coarse = window.matchMedia && window.matchMedia("(pointer: coarse)");

    var select = function (slug) {
      var m = missions[slug];
      if (!m) { return; }
      pins.forEach(function (pin) { pin.setAttribute("aria-pressed", pin.value === slug ? "true" : "false"); });
      part("name").textContent = m.name;
      part("founded").textContent = m.founded;
      part("number").textContent = m.number;
      var hasStory = Boolean(m.story_url);
      part("story").hidden = !hasStory;
      part("soon").hidden = hasStory;
      part("subtitle").textContent = m.subtitle || "";
      part("intro").innerHTML = m.intro || "";   // the page's own rich text, rendered by the server
      part("read").setAttribute("href", m.story_url || "#");
      part("build").hidden = !m.project_url;
      part("build").setAttribute("href", m.project_url || "#");
      if (window.history && window.history.replaceState) {
        var url = new URL(window.location.href);
        url.searchParams.set("mission", slug);
        url.hash = "";
        window.history.replaceState(null, "", url.toString());
      }
    };

    var closeChooser = function (returnTo) {
      chooser.hidden = true;
      chooserList.innerHTML = "";
      if (returnTo) { returnTo.focus(); }
    };
    var openChooser = function (near, returnTo) {
      chooserList.innerHTML = "";
      near.forEach(function (pin) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "fs-pin-choice";
        b.textContent = "#" + missions[pin.value].number + " " + missions[pin.value].name;
        b.addEventListener("click", function () { select(pin.value); closeChooser(pin); });
        chooserList.appendChild(b);
      });
      chooser.hidden = false;
      chooserList.querySelector("button").focus();
      chooser.onkeydown = function (event) {
        if (event.key === "Escape") { closeChooser(returnTo); }
      };
    };
    map.querySelector("[data-fs-chooser-close]").addEventListener("click", function () { closeChooser(pins[0]); });

    map.addEventListener("click", function (event) {
      var pin = event.target.closest("[data-fs-pin]");
      if (!pin) { return; }
      event.preventDefault();
      // A touch tap (not a keyboard press) near two or more pins asks which one.
      if (coarse && coarse.matches && event.detail > 0) {
        var near = pins.filter(function (p) {
          var r = p.getBoundingClientRect();
          return Math.hypot(r.left + r.width / 2 - event.clientX, r.top + r.height / 2 - event.clientY) <= radius;
        });
        if (near.length > 1) { openChooser(near, pin); return; }
        if (near.length === 1) { pin = near[0]; }
      }
      select(pin.value);
    });
  }

  // ---- World Discovery Map: select in place (?story=<key>), the close-marker chooser,
  // and the type filters (markers and list items hide together). Without this the markers
  // are submit buttons of a GET form and the list reaches every story. ----
  var world = document.querySelector("[data-fs-world]");
  var worldCard = document.querySelector("[data-fs-world-card]");
  var worldData = document.getElementById("fs-world-data");
  if (world && worldCard && worldData) {
    var stories = {};
    try {
      JSON.parse(worldData.textContent).forEach(function (s) { stories[s.key] = s; });
    } catch (e) { stories = {}; }
    var markers = Array.prototype.slice.call(world.querySelectorAll("[data-fs-world-pin]"));
    var cardPart = function (name) { return worldCard.querySelector("[data-fs-card-" + name + "]"); };
    var worldChooser = world.querySelector("[data-fs-chooser]");
    var worldChooserList = world.querySelector("[data-fs-chooser-list]");
    var worldRadius = parseFloat(world.getAttribute("data-fs-pin-radius")) || 24;
    var worldCoarse = window.matchMedia && window.matchMedia("(pointer: coarse)");

    var selectStory = function (key) {
      var s = stories[key];
      if (!s) { return; }
      markers.forEach(function (m) { m.setAttribute("aria-pressed", m.value === key ? "true" : "false"); });
      worldCard.className = worldCard.className.replace(/\bfs-wm-[a-z_]+/, "fs-wm-" + s.kind);
      cardPart("type").textContent = s.type_label;
      cardPart("title").textContent = s.title;
      cardPart("subtitle").textContent = s.subtitle || "";
      cardPart("subtitle").hidden = !s.subtitle;
      cardPart("place-text").textContent = s.place_line || "";
      cardPart("place").hidden = !s.place_line;
      cardPart("link").setAttribute("href", s.url);
      cardPart("link-text").textContent = s.link_label;
      var use = worldCard.querySelector(".fs-art--placeholder use");
      if (use) { use.setAttribute("href", "#fs-i-" + s.icon); }
      if (window.history && window.history.replaceState) {
        var url = new URL(window.location.href);
        url.searchParams.set("story", key);
        url.hash = "";
        window.history.replaceState(null, "", url.toString());
      }
    };

    var closeWorldChooser = function (returnTo) {
      worldChooser.hidden = true;
      worldChooserList.innerHTML = "";
      if (returnTo) { returnTo.focus(); }
    };
    world.querySelector("[data-fs-chooser-close]").addEventListener("click", function () { closeWorldChooser(markers[0]); });
    worldChooser.addEventListener("keydown", function (event) {
      if (event.key === "Escape") { closeWorldChooser(markers[0]); }
    });

    world.addEventListener("click", function (event) {
      var pin = event.target.closest("[data-fs-world-pin]");
      if (!pin) { return; }
      event.preventDefault();
      if (worldCoarse && worldCoarse.matches && event.detail > 0) {
        var near = markers.filter(function (m) {
          if (m.closest("[data-fs-kind]").hidden) { return false; }
          var r = m.getBoundingClientRect();
          return Math.hypot(r.left + r.width / 2 - event.clientX, r.top + r.height / 2 - event.clientY) <= worldRadius;
        });
        if (near.length > 1) {
          worldChooserList.innerHTML = "";
          near.forEach(function (m) {
            var b = document.createElement("button");
            b.type = "button";
            b.className = "fs-pin-choice";
            b.textContent = stories[m.value].title + " (" + stories[m.value].type_label + ")";
            b.addEventListener("click", function () { selectStory(m.value); closeWorldChooser(m); });
            worldChooserList.appendChild(b);
          });
          worldChooser.hidden = false;
          worldChooserList.querySelector("button").focus();
          return;
        }
        if (near.length === 1) { pin = near[0]; }
      }
      selectStory(pin.value);
    });

    var filterBar = document.querySelector("[data-fs-world-filters]");
    if (filterBar) {
      var toggles = Array.prototype.slice.call(filterBar.querySelectorAll("[data-fs-filter]"));
      var applyFilters = function () {
        var on = {};
        toggles.forEach(function (t) { on[t.getAttribute("data-fs-filter")] = t.getAttribute("aria-pressed") === "true"; });
        Array.prototype.forEach.call(document.querySelectorAll(".fs-world [data-fs-kind]"), function (el) {
          el.hidden = !on[el.getAttribute("data-fs-kind")];
        });
      };
      toggles.forEach(function (t) {
        t.addEventListener("click", function () {
          t.setAttribute("aria-pressed", t.getAttribute("aria-pressed") === "true" ? "false" : "true");
          applyFilters();
        });
      });
      filterBar.querySelector("[data-fs-filter-all]").addEventListener("click", function () {
        toggles.forEach(function (t) { t.setAttribute("aria-pressed", "true"); });
        applyFilters();
      });
      filterBar.hidden = false;
    }
  }

  // ---- "Find a Mission" lists: tabs when JavaScript is on, three lists when it's off. ----
  Array.prototype.forEach.call(document.querySelectorAll("[data-fs-tabs]"), function (box) {
    var bar = box.querySelector("[data-fs-tab-buttons]");
    var tabs = Array.prototype.slice.call(bar.querySelectorAll("[role=tab]"));
    var show = function (tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
      });
      if (focus) { tab.focus(); }
    };
    tabs.forEach(function (tab, i) {
      tab.addEventListener("click", function () { show(tab, false); });
      tab.addEventListener("keydown", function (event) {
        var step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
        if (step) { event.preventDefault(); show(tabs[(i + step + tabs.length) % tabs.length], true); }
      });
    });
    box.classList.add("is-tabbed");
    bar.hidden = false;
    show(tabs[0], false);
  });
})();
