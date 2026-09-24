/*
 * Site-wide search: type-ahead dropdown for every ".sog-search" form.
 *
 * Progressive enhancement only -- each form is a real <form method="get"
 * action="/search/">, so it already works with this file blocked. All this
 * adds is the grouped suggestion panel layered on top of the input.
 *
 * Every form on the page is wired up independently: the header bar, the
 * mobile-nav copy of it, a hero bar, an inline bar, and the map bar can all
 * be present at once, each with its own debounce timer, in-flight request,
 * and row list.
 */
(function () {
  "use strict";

  var DEBOUNCE_MS = 180;
  var MIN_CHARS = 2;
  var BLUR_CLOSE_MS = 150;

  var forms = Array.prototype.slice.call(document.querySelectorAll(".sog-search"));
  forms.forEach(setupSearch);

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  // Escape title and query first, then find the match on the ESCAPED
  // strings and split there -- the raw query is never inserted into HTML,
  // only the (already-escaped) slice of the title that matched it.
  function highlightTitle(rawTitle, rawQuery) {
    var escapedTitle = escapeHtml(rawTitle);
    var escapedQuery = escapeHtml(rawQuery);
    if (!escapedQuery) return escapedTitle;
    var idx = escapedTitle.toLowerCase().indexOf(escapedQuery.toLowerCase());
    if (idx === -1) return escapedTitle;
    var before = escapedTitle.slice(0, idx);
    var match = escapedTitle.slice(idx, idx + escapedQuery.length);
    var after = escapedTitle.slice(idx + escapedQuery.length);
    return before + "<mark>" + match + "</mark>" + after;
  }

  function setupSearch(form) {
    var input = form.querySelector('input[name="query"]');
    var panel = form.querySelector(".sog-search-panel");
    var status = form.querySelector(".sog-search-status");
    if (!input || !panel) return;

    var suggestUrl = form.getAttribute("data-suggest-url");
    var types = form.getAttribute("data-types");

    var debounceTimer = null;
    var blurTimer = null;
    var abortController = null;
    var rows = []; // flat, in DOM/group order: { el, result } -- result is
                    // null for the non-suggestion "see all" footer row.
    var activeIndex = -1;
    var rowSerial = 0;

    input.addEventListener("input", onInput);
    input.addEventListener("keydown", onKeydown);
    input.addEventListener("blur", onBlur);
    input.addEventListener("focus", function () {
      clearTimeout(blurTimer);
    });
    document.addEventListener("click", onDocumentClick);

    function onInput() {
      var trimmed = input.value.trim();
      clearTimeout(debounceTimer);
      if (abortController) {
        abortController.abort();
        abortController = null;
      }
      if (trimmed.length < MIN_CHARS) {
        closePanel();
        if (trimmed === "") {
          dispatchQueryEvent("", null);
        }
        return;
      }
      debounceTimer = setTimeout(function () {
        runSearch(trimmed);
      }, DEBOUNCE_MS);
    }

    function runSearch(query) {
      if (abortController) abortController.abort();
      abortController = new AbortController();

      var url = suggestUrl + "?q=" + encodeURIComponent(query);
      if (types) url += "&types=" + encodeURIComponent(types);

      fetch(url, { signal: abortController.signal })
        .then(function (response) {
          return response.json();
        })
        .then(function (data) {
          abortController = null;
          renderPanel(data);
          dispatchQueryEvent(query, data);
        })
        .catch(function (err) {
          if (err && err.name === "AbortError") return;
          abortController = null;
          closePanel();
        });
    }

    function dispatchQueryEvent(query, data) {
      form.dispatchEvent(
        new CustomEvent("sog:search-query", {
          cancelable: true,
          detail: { query: query, data: data },
        })
      );
    }

    // Returns whether the default action (navigating) should proceed --
    // false means a listener (e.g. the map page) claimed it.
    function fireChoose(result) {
      return form.dispatchEvent(
        new CustomEvent("sog:search-choose", {
          cancelable: true,
          detail: { result: result },
        })
      );
    }

    function seeAllUrl(query) {
      return form.getAttribute("action") + "?query=" + encodeURIComponent(query);
    }

    function buildRow(groupKey, result, query) {
      var row = document.createElement("a");
      row.className = "sog-search-row";
      row.setAttribute("role", "option");
      row.id = form.id + "-row-" + rowSerial++;
      row.href = result.url;

      var text = document.createElement("span");
      text.className = "sog-search-row-text";

      var titleEl = document.createElement("span");
      titleEl.className = "sog-search-row-title";
      titleEl.innerHTML = highlightTitle(result.title, query);
      text.appendChild(titleEl);

      if (result.meta) {
        var metaEl = document.createElement("span");
        metaEl.className = "sog-search-row-meta";
        metaEl.textContent = result.meta;
        text.appendChild(metaEl);
      }
      row.appendChild(text);

      if (groupKey === "sites" && result.chip) {
        var chipEl = document.createElement("span");
        chipEl.className = "sog-search-row-chip";
        chipEl.textContent = result.chip;
        chipEl.style.background = result.chip_fill;
        chipEl.style.borderColor = result.chip_stroke;
        chipEl.style.color = result.chip_dot;
        row.appendChild(chipEl);
      }

      row.addEventListener("click", function (e) {
        var proceed = fireChoose(result);
        if (!proceed) e.preventDefault();
      });

      rows.push({ el: row, result: result });
      return row;
    }

    function buildSeeAllRow(query, total) {
      var row = document.createElement("a");
      row.className = "sog-search-row sog-search-row--seeall";
      row.setAttribute("role", "option");
      row.id = form.id + "-row-" + rowSerial++;
      row.href = seeAllUrl(query);
      row.textContent =
        typeof total === "number"
          ? 'See all ' + total + ' results for “' + query + '”'
          : 'See all results for “' + query + '”';
      rows.push({ el: row, result: null });
      return row;
    }

    function renderPanel(data) {
      panel.innerHTML = "";
      rows = [];
      activeIndex = -1;
      rowSerial = 0;

      if (!data.groups.length) {
        var empty = document.createElement("div");
        empty.className = "sog-search-row sog-search-row--empty";
        empty.textContent = 'No matches for “' + data.query + '”';
        panel.appendChild(empty);
        panel.appendChild(buildSeeAllRow(data.query));
        openPanel();
        updateStatus('No results for “' + data.query + '”');
        return;
      }

      var totalResults = 0;
      data.groups.forEach(function (group) {
        totalResults += group.total;

        var groupEl = document.createElement("div");
        groupEl.className = "sog-search-group";

        var head = document.createElement("div");
        head.className = "sog-search-group-head";
        head.textContent = group.label + " (" + group.total + ")";
        groupEl.appendChild(head);

        group.results.forEach(function (result) {
          groupEl.appendChild(buildRow(group.key, result, data.query));
        });

        panel.appendChild(groupEl);
      });

      panel.appendChild(buildSeeAllRow(data.query, totalResults));
      openPanel();
      updateStatus(
        totalResults +
          (totalResults === 1 ? " result, " : " results, ") +
          data.groups.length +
          (data.groups.length === 1 ? " category" : " categories")
      );
    }

    function updateStatus(text) {
      if (status) status.textContent = text;
    }

    function openPanel() {
      panel.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    function closePanel() {
      panel.hidden = true;
      panel.innerHTML = "";
      rows = [];
      activeIndex = -1;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }

    function moveActive(delta) {
      if (!rows.length) return;
      if (activeIndex === -1) {
        activeIndex = delta > 0 ? 0 : rows.length - 1;
      } else {
        activeIndex = (activeIndex + delta + rows.length) % rows.length;
      }
      setActiveRow();
    }

    function setActiveRow() {
      rows.forEach(function (row, i) {
        row.el.classList.toggle("is-active", i === activeIndex);
      });
      var active = rows[activeIndex];
      if (active) {
        input.setAttribute("aria-activedescendant", active.el.id);
        if (active.el.scrollIntoView) active.el.scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
    }

    function onKeydown(e) {
      if (e.key === "ArrowDown") {
        if (panel.hidden) return;
        e.preventDefault();
        moveActive(1);
      } else if (e.key === "ArrowUp") {
        if (panel.hidden) return;
        e.preventDefault();
        moveActive(-1);
      } else if (e.key === "Enter") {
        var active = rows[activeIndex];
        if (active) {
          e.preventDefault();
          if (active.result) {
            var proceed = fireChoose(active.result);
            if (proceed) window.location.href = active.result.url;
          } else {
            window.location.href = active.el.href;
          }
        }
        // else: no active row -- let the form submit normally.
      } else if (e.key === "Escape") {
        closePanel();
        input.focus();
      } else if (e.key === "Tab") {
        closePanel();
      }
    }

    function onBlur() {
      // Closing immediately would eat the click on a row -- the mousedown
      // that blurs the input fires well before the click event that
      // navigates, so a short delay lets that click land first.
      blurTimer = setTimeout(closePanel, BLUR_CLOSE_MS);
    }

    function onDocumentClick(e) {
      if (!form.contains(e.target)) {
        closePanel();
      }
    }
  }
})();
