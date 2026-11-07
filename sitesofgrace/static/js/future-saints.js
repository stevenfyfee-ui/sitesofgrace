/* Future Saints: small progressive enhancements. Pages work without this file.
   No cookies. One sessionStorage key ("fs-reading-level"), tab-scoped, never sent anywhere.
   The quiz keeps its state in memory only: nothing is stored or sent. */
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

  // ---- Reading level: ?level= in the address and sessionStorage only. ----
  // On learning pages the text for both levels is in the page; the body's
  // fs-level-* class shows one, so switching never moves the layout.
  var KEY = "fs-reading-level";
  var LEVELS = ["explorer", "researcher"];
  var levelButtons = Array.prototype.slice.call(document.querySelectorAll("[data-fs-level]"));
  if (levelButtons.length) {
    var status = document.querySelector("[data-fs-level-status]");
    var read = function () {
      try { return window.sessionStorage.getItem(KEY) || ""; } catch (e) { return ""; }
    };
    var write = function (level) {
      try { window.sessionStorage.setItem(KEY, level); } catch (e) { /* storage blocked: fine */ }
    };
    var show = function (level) {
      levelButtons.forEach(function (b) {
        b.setAttribute("aria-pressed", b.value === level ? "true" : "false");
      });
      LEVELS.forEach(function (l) { document.body.classList.toggle("fs-level-" + l, l === level); });
      if (status) {
        var chosen = levelButtons.filter(function (b) { return b.value === level; })[0];
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
    levelButtons.forEach(function (b) {
      b.addEventListener("click", function (event) {
        event.preventDefault();
        var level = b.value;
        write(level);
        show(level);
        params.set("level", level);
        window.history.replaceState(null, "", window.location.pathname + "?" + params.toString() + window.location.hash);
      });
    });
  }

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
})();
