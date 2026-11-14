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

  // ---- Map zoom (the World Discovery Map and the California map): + / − / reset, drag to
  // pan with a mouse or a finger, pinch on touch, the wheel only once the map has been
  // clicked or focused (page scrolling is never taken over), and + − arrows 0 while the map
  // has focus. The stage is scaled and moved; markers are counter-scaled in CSS, so they
  // keep their size and their true spots. Panning is clamped to the map. Without this the
  // static map and the lists still work and the controls stay hidden. ----
  var initZoom = function (vp) {
    var stage = vp.querySelector(".fs-zoom-stage");
    var box = vp.parentNode;
    var max = parseFloat(vp.getAttribute("data-fs-zoom-max")) || 4;
    var vbw = parseFloat(vp.getAttribute("data-fs-vb-w")) || 1000;
    var vbh = parseFloat(vp.getAttribute("data-fs-vb-h")) || 1000;
    var z = 1, tx = 0, ty = 0, armed = false, dragged = false, detailed = false;
    var pointers = {}, gesture = null;
    var size = function () { return { w: vp.clientWidth, h: vp.clientHeight }; };
    var apply = function (animate) {
      var s = size();
      z = Math.min(max, Math.max(1, z));
      tx = Math.min(0, Math.max(s.w - s.w * z, tx));
      ty = Math.min(0, Math.max(s.h - s.h * z, ty));
      stage.classList.toggle("is-animating", Boolean(animate) && !reduceMotion);
      stage.style.setProperty("--z", z);
      stage.style.setProperty("--tx", tx + "px");
      stage.style.setProperty("--ty", ty + "px");
      vp.style.setProperty("--nudge", Math.max(0, Math.min(1, 2 - z)));
      vp.classList.toggle("is-zoomed", z > 1.001);
      vp.setAttribute("data-fs-zoom-level", z.toFixed(3));
      if (z > 2 && !detailed) {
        // The finer outline (world map: Natural Earth 1:50m), fetched only now.
        detailed = true;
        Array.prototype.forEach.call(vp.querySelectorAll("[data-fs-detail]"), function (use) {
          use.setAttribute("href", use.getAttribute("data-fs-detail"));
        });
      }
    };
    var zoomAt = function (nz, cx, cy, animate) {
      nz = Math.min(max, Math.max(1, nz));
      tx = cx - (cx - tx) * nz / z;
      ty = cy - (cy - ty) * nz / z;
      z = nz;
      apply(animate);
    };
    var api = {
      zoomBy: function (factor, animate) { var s = size(); zoomAt(z * factor, s.w / 2, s.h / 2, animate); },
      reset: function (animate) { z = 1; tx = 0; ty = 0; apply(animate); },
      // Fit a box given in map (viewBox) units.
      fit: function (x1, y1, x2, y2, animate) {
        var s = size();
        z = Math.min(max, Math.max(1, Math.min(vbw / (x2 - x1), vbh / (y2 - y1))));
        tx = s.w / 2 - (x1 + x2) / 2 / vbw * s.w * z;
        ty = s.h / 2 - (y1 + y2) / 2 / vbh * s.h * z;
        apply(animate);
      },
      // Bring a spot (map units) into view, zooming in to at least minZoom.
      focus: function (x, y, minZoom) {
        var s = size();
        z = Math.min(max, Math.max(z, minZoom || 1));
        tx = s.w / 2 - x / vbw * s.w * z;
        ty = s.h / 2 - y / vbh * s.h * z;
        apply(true);
      },
      state: function () { return { z: z, tx: tx, ty: ty }; }
    };
    vp.fsZoom = api;

    var controls = box.querySelector("[data-fs-zoom-controls]");
    if (controls) {
      controls.querySelector("[data-fs-zoom-in]").addEventListener("click", function () { api.zoomBy(1.5, true); });
      controls.querySelector("[data-fs-zoom-out]").addEventListener("click", function () { api.zoomBy(1 / 1.5, true); });
      controls.querySelector("[data-fs-zoom-reset]").addEventListener("click", function () { api.reset(true); });
      controls.hidden = false;
    }
    vp.tabIndex = 0;
    vp.setAttribute("role", "group");

    // The wheel zooms only after the map has been clicked or focused; otherwise the page scrolls.
    vp.addEventListener("focusin", function () { armed = true; });
    vp.addEventListener("focusout", function (event) { if (!vp.contains(event.relatedTarget)) { armed = false; } });
    document.addEventListener("pointerdown", function (event) { if (!box.contains(event.target)) { armed = false; } });
    vp.addEventListener("wheel", function (event) {
      if (!armed) { return; }
      event.preventDefault();
      var r = vp.getBoundingClientRect();
      zoomAt(z * (event.deltaY < 0 ? 1.2 : 1 / 1.2), event.clientX - r.left, event.clientY - r.top);
    }, { passive: false });

    vp.addEventListener("pointerdown", function (event) {
      armed = true;
      pointers[event.pointerId] = { x: event.clientX, y: event.clientY };
      var ids = Object.keys(pointers);
      dragged = false;
      if (ids.length === 2) {
        var a = pointers[ids[0]], b = pointers[ids[1]];
        gesture = { pinch: Math.hypot(a.x - b.x, a.y - b.y), z: z };
      } else {
        gesture = { x: event.clientX, y: event.clientY, tx: tx, ty: ty };
      }
    });
    vp.addEventListener("pointermove", function (event) {
      if (!pointers[event.pointerId] || !gesture) { return; }
      pointers[event.pointerId] = { x: event.clientX, y: event.clientY };
      var ids = Object.keys(pointers);
      var r = vp.getBoundingClientRect();
      if (ids.length === 2 && gesture.pinch) {
        var a = pointers[ids[0]], b = pointers[ids[1]];
        dragged = true;
        zoomAt(gesture.z * Math.hypot(a.x - b.x, a.y - b.y) / gesture.pinch, (a.x + b.x) / 2 - r.left, (a.y + b.y) / 2 - r.top);
      } else if (ids.length === 1 && gesture.x !== undefined && z > 1.001) {
        var dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
        if (!dragged && Math.hypot(dx, dy) < 5) { return; }
        if (!dragged) { vp.setPointerCapture(event.pointerId); vp.classList.add("is-dragging"); }
        dragged = true;
        tx = gesture.tx + dx;
        ty = gesture.ty + dy;
        apply(false);
      }
    });
    var lift = function (event) {
      delete pointers[event.pointerId];
      vp.classList.remove("is-dragging");
      if (!Object.keys(pointers).length) { gesture = null; }
    };
    vp.addEventListener("pointerup", lift);
    vp.addEventListener("pointercancel", lift);
    // A drag isn't a press: don't select the marker it ended on.
    vp.addEventListener("click", function (event) {
      if (dragged) { event.preventDefault(); event.stopPropagation(); dragged = false; }
    }, true);

    vp.addEventListener("keydown", function (event) {
      var step = 60, k = event.key;
      if (k === "+" || k === "=") { api.zoomBy(1.5, true); }
      else if (k === "-" || k === "_") { api.zoomBy(1 / 1.5, true); }
      else if (k === "0") { api.reset(true); }
      else if (k === "ArrowLeft") { tx += step; apply(false); }
      else if (k === "ArrowRight") { tx -= step; apply(false); }
      else if (k === "ArrowUp") { ty += step; apply(false); }
      else if (k === "ArrowDown") { ty -= step; apply(false); }
      else { return; }
      event.preventDefault();
    });
    window.addEventListener("resize", function () { apply(false); });
    apply(false);
    return api;
  };
  Array.prototype.forEach.call(document.querySelectorAll("[data-fs-zoom]"), initZoom);
  var zoomOf = function (el) {
    var vp = el && el.closest(".fs-map, .fs-wmap");
    vp = vp && vp.querySelector("[data-fs-zoom]");
    return vp && vp.fsZoom;
  };

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
    var mapBox = map.closest(".fs-map");
    var chooser = mapBox.querySelector("[data-fs-chooser]");
    var chooserList = mapBox.querySelector("[data-fs-chooser-list]");
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
    mapBox.querySelector("[data-fs-chooser-close]").addEventListener("click", function () { closeChooser(pins[0]); });

    // Arriving with ?mission=<slug> (a shared link, or a list item): bring that pin into view.
    var shared = new URL(window.location.href).searchParams.get("mission");
    var sharedPin = shared && pins.filter(function (p) { return p.value === shared; })[0];
    if (sharedPin && zoomOf(map)) {
      zoomOf(map).focus(parseFloat(sharedPin.getAttribute("data-x")), parseFloat(sharedPin.getAttribute("data-y")), 2);
    }

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
    var worldBox = world.closest(".fs-wmap");
    var worldChooser = worldBox.querySelector("[data-fs-chooser]");
    var worldChooserList = worldBox.querySelector("[data-fs-chooser-list]");
    var worldZoom = zoomOf(world);
    var worldRadius = parseFloat(world.getAttribute("data-fs-pin-radius")) || 24;
    var worldCoarse = window.matchMedia && window.matchMedia("(pointer: coarse)");

    // Bring a story's marker into view (from the list, ?story= or search; not from a marker
    // press, which is already in view). Without a marker (not on the map) nothing moves.
    var showOnMap = function (key) {
      var marker = markers.filter(function (m) { return m.value === key; })[0];
      if (!marker && stories[key] && stories[key].in_callout) {        // a mission: its place is the callout
        marker = markers.filter(function (m) { return m.value === "california-missions"; })[0];
      }
      if (marker && worldZoom) {
        worldZoom.focus(parseFloat(marker.getAttribute("data-x")), parseFloat(marker.getAttribute("data-y")), 2.5);
      }
    };
    var selectStory = function (key, focus) {
      var s = stories[key];
      if (!s) { return; }
      if (focus) {
        // From the list or search: a type filtered off is shown again, so the story is visible.
        var off = document.querySelector('[data-fs-filter="' + s.kind + '"][aria-pressed="false"]');
        if (off) { off.click(); }
        showOnMap(key);
      }
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
    worldBox.querySelector("[data-fs-chooser-close]").addEventListener("click", function () { closeWorldChooser(markers[0]); });
    window.fsSelectStory = selectStory;      // for the map's search box (it selects and zooms)

    // Arriving with ?story=<key>: bring it into view. The list's "Show on the map" links
    // select in place and zoom instead of reloading.
    var sharedStory = new URL(window.location.href).searchParams.get("story");
    if (sharedStory && stories[sharedStory]) { showOnMap(sharedStory); }
    Array.prototype.forEach.call(document.querySelectorAll(".fs-world-show"), function (link) {
      link.addEventListener("click", function (event) {
        var key = new URL(link.href).searchParams.get("story");
        if (!stories[key]) { return; }
        event.preventDefault();
        selectStory(key, true);
        worldBox.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
      });
    });

    // Region shortcuts: each zooms to a fixed box computed with the same projection.
    var regions = document.querySelector("[data-fs-regions]");
    if (regions && worldZoom) {
      var regionButtons = Array.prototype.slice.call(regions.querySelectorAll("button"));
      regionButtons.forEach(function (b) {
        b.setAttribute("aria-pressed", "false");
        b.addEventListener("click", function () {
          regionButtons.forEach(function (o) { o.setAttribute("aria-pressed", o === b ? "true" : "false"); });
          var boxValue = b.getAttribute("data-fs-region");
          if (!boxValue) { worldZoom.reset(true); return; }
          var v = boxValue.split(",").map(parseFloat);
          worldZoom.fit(v[0], v[1], v[2], v[3], true);
        });
      });
      regions.hidden = false;
    }
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

  // ---- Search (kids-safe): the type-ahead filters the cached index in the browser. Nothing
  // typed is stored or sent anywhere: no cookies, no storage, no analytics, no query logging.
  // The same rules as future_saints/search.py: accents and case ignored, every word must match
  // the start of a word, and a word of 5+ letters may be one letter off. Without this the box
  // is a plain GET form to the results page. ----
  var searchForms = document.querySelectorAll("[data-fs-search]");
  if (searchForms.length) {
    var fold = function (text) {
      return (text || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
    };
    var wordsOf = function (text) { return fold(text).match(/[a-z0-9]+/g) || []; };
    var withinOne = function (a, b) {
      if (a === b) { return true; }
      if (Math.abs(a.length - b.length) > 1) { return false; }
      if (a.length > b.length) { var t = a; a = b; b = t; }
      var i = 0;
      while (i < a.length && a[i] === b[i]) { i += 1; }
      if (a.length === b.length) { return a.slice(i + 1) === b.slice(i + 1); }
      return a.slice(i) === b.slice(i + 1);
    };
    var wordScore = function (q, w) {
      if (w.indexOf(q) === 0) { return 2; }
      if (q.length >= 5) {
        for (var size = q.length - 1; size <= q.length + 1; size += 1) {
          if (size <= w.length && withinOne(q, w.slice(0, size))) { return 1; }
        }
      }
      return 0;
    };
    var FIELDS = [["t", 4], ["p", 2], ["s", 1], ["w", 1], ["i", 1]];
    var scoreOf = function (entry, queryWords) {
      var total = 0;
      for (var n = 0; n < queryWords.length; n += 1) {
        var best = 0;
        FIELDS.forEach(function (f) {
          var value = entry[f[0]] || "";
          wordsOf(Array.isArray(value) ? value.join(" ") : value).forEach(function (w) {
            best = Math.max(best, wordScore(queryWords[n], w) * f[1]);
          });
        });
        if (!best) { return 0; }
        total += best;
      }
      return total;
    };
    var runSearch = function (entries, query) {
      var queryWords = wordsOf(query);
      if (!queryWords.length) { return []; }
      return entries.map(function (e) { return { e: e, s: scoreOf(e, queryWords) }; })
        .filter(function (x) { return x.s > 0; })
        .sort(function (a, b) { return b.s - a.s || (fold(a.e.t) < fold(b.e.t) ? -1 : 1); })
        .map(function (x) { return x.e; });
    };
    var indexes = {};
    var loadIndex = function (url) {
      if (!indexes[url]) {
        indexes[url] = fetch(url, { headers: { Accept: "application/json" } })
          .then(function (r) { if (!r.ok) { throw new Error(r.status); } return r.json(); })
          .catch(function () { delete indexes[url]; return null; });
      }
      return indexes[url];
    };
    var MAX_OPTIONS = 8;

    Array.prototype.forEach.call(searchForms, function (form) {
      var mode = form.getAttribute("data-fs-search");
      var input = form.querySelector("[data-fs-search-input]");
      var list = form.querySelector("[data-fs-search-options]");
      var status = form.querySelector("[data-fs-search-status]");
      var note = form.querySelector("[data-fs-search-note]");
      var indexUrl = form.getAttribute("data-fs-search-index");
      var data = null, results = [], active = -1, timer = null;
      input.setAttribute("role", "combobox");
      input.setAttribute("aria-autocomplete", "list");
      input.setAttribute("aria-expanded", "false");
      input.setAttribute("aria-controls", list.id);

      var labels = function () {
        var map = {};
        ((data && data.groups) || []).forEach(function (g) { map[g[0]] = g[1]; });
        return map;
      };
      var close = function () {
        list.hidden = true;
        input.setAttribute("aria-expanded", "false");
        input.removeAttribute("aria-activedescendant");
        active = -1;
      };
      var setActive = function (n) {
        var options = list.querySelectorAll("[role=option]");
        active = n;
        Array.prototype.forEach.call(options, function (o, i) { o.setAttribute("aria-selected", i === n ? "true" : "false"); });
        if (n >= 0 && options[n]) {
          input.setAttribute("aria-activedescendant", options[n].id);
          options[n].scrollIntoView({ block: "nearest" });
        } else {
          input.removeAttribute("aria-activedescendant");
        }
      };
      var choose = function (entry) {
        close();
        if (mode !== "map") { window.location.href = entry.u; return; }
        input.value = entry.t;
        if (entry.m && window.fsSelectStory) {
          if (note) { note.hidden = true; }
          window.fsSelectStory(entry.m, true);
          var box = document.querySelector(".fs-wmap");
          if (box) { box.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" }); }
        } else if (note) {
          note.hidden = false;
        }
      };
      var render = function () {
        var query = input.value;
        if (note) { note.hidden = true; }
        if (!data || !wordsOf(query).length) {
          results = [];
          list.innerHTML = "";
          status.textContent = "";
          close();
          return;
        }
        results = runSearch(data.entries, query);
        var names = labels();
        list.innerHTML = "";
        results.slice(0, MAX_OPTIONS).forEach(function (entry, i) {
          var li = document.createElement("li");
          li.id = list.id + "-" + i;
          li.className = "fs-search-option";
          li.setAttribute("role", "option");
          li.setAttribute("aria-selected", "false");
          var title = document.createElement("span");
          title.className = "fs-search-option-title";
          title.textContent = entry.t;
          var type = document.createElement("span");
          type.className = "fs-search-option-type";
          type.textContent = names[entry.k] || "";
          li.appendChild(title);
          li.appendChild(type);
          li.addEventListener("mousedown", function (event) { event.preventDefault(); });
          li.addEventListener("click", function () { choose(entry); });
          list.appendChild(li);
        });
        var n = results.length;
        status.textContent = n ? n + (n === 1 ? " story found" : " stories found") : "No stories found. Try another word!";
        active = -1;
        input.removeAttribute("aria-activedescendant");
        list.hidden = n === 0;
        input.setAttribute("aria-expanded", n ? "true" : "false");
      };
      var ready = function () {
        return loadIndex(indexUrl).then(function (d) { if (d) { data = d; } return data; });
      };

      input.addEventListener("focus", ready);
      input.addEventListener("input", function () {
        clearTimeout(timer);
        timer = setTimeout(function () { ready().then(render); }, 120);
      });
      input.addEventListener("keydown", function (event) {
        var count = list.querySelectorAll("[role=option]").length;
        if (event.key === "ArrowDown" || event.key === "ArrowUp") {
          if (!count) { return; }
          event.preventDefault();
          if (list.hidden) { list.hidden = false; input.setAttribute("aria-expanded", "true"); }
          var step = event.key === "ArrowDown" ? 1 : -1;
          setActive(active < 0 ? (step > 0 ? 0 : count - 1) : (active + step + count) % count);
        } else if (event.key === "Enter" && active >= 0 && !list.hidden) {
          event.preventDefault();
          choose(results[active]);
        } else if (event.key === "Escape") {
          if (!list.hidden) { event.preventDefault(); close(); }
          else if (input.value) { event.preventDefault(); input.value = ""; render(); }
        }
      });
      input.addEventListener("blur", function () { setTimeout(close, 100); });
      form.setAttribute("data-fs-search-ready", "");
    });
  }
})();
