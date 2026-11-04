/* Trip Planner v2. The page works without this file: every control is a
   link or GET form carrying the whole plan. Here those are taken over: each
   change asks /plan/build/ for the new plan and swaps in the fragments it
   returns (the same templates the page was rendered with), so the page never
   reloads and the URL always holds the plan. */
(function () {
  var root = document.getElementById('pv2');
  if (!root) return;

  var buildUrl = root.getAttribute('data-build-url');
  var searchUrl = root.getAttribute('data-search-url');
  var pageUrl = root.getAttribute('data-page-url');
  var query = root.getAttribute('data-query') || '';
  var tripId = root.getAttribute('data-trip');
  var $ = function (id) { return document.getElementById(id); };
  var targets = { stops: 'pv2-stops', days: 'pv2-days', route: 'pv2-route', budget: 'pv2-budget', mbar: 'pv2-mbar-total' };
  var pending = null, timer = null, lastTotal = null;

  function toast(msg) {
    var t = $('pv2-toast');
    if (!t) return;
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast.h);
    toast.h = setTimeout(function () { t.hidden = true; }, 3200);
  }

  // The canonical address (https://sitesofgrace.com/plan/ in production), from the server.
  var shareBase = root.getAttribute('data-share-base') || (window.location.origin + pageUrl);
  function shareUrl() { return shareBase + '?' + query; }

  function syncLinks() {
    Array.prototype.forEach.call(root.querySelectorAll('input[type="hidden"][name="t"]'), function (input) {
      var m = /(?:^|&)t=([^&]*)/.exec(query);
      input.value = m ? decodeURIComponent(m[1]) : '';
    });
    Array.prototype.forEach.call(root.querySelectorAll('[data-share]'), function (a) { a.href = pageUrl + '?' + query; });
    Array.prototype.forEach.call(root.querySelectorAll('[data-share-url]'), function (el) { el.textContent = shareUrl(); });
    var saveQ = root.querySelector('[data-save-form] input[name="q"]');
    if (saveQ) saveQ.value = query;
    Array.prototype.forEach.call(root.querySelectorAll('[data-login]'), function (a) {
      a.href = a.href.split('?next=')[0] + '?next=' + encodeURIComponent(pageUrl + '?' + query);
    });
  }

  function apply(data) {
    query = data.query;
    root.setAttribute('data-query', query);
    Object.keys(targets).forEach(function (name) {
      var el = $(targets[name]);
      if (el && data.html && data.html[name] != null) el.innerHTML = data.html[name];
    });
    if (window.history && history.replaceState) history.replaceState(null, '', pageUrl + '?' + query + (tripId ? '&trip=' + tripId : ''));
    // "From your journey" is rendered once (it's per user); keep it and Popular from repeating the plan.
    var chosen = {}, journey = {};
    ((data.state && data.state.stops) || []).forEach(function (s) { chosen[s.slug] = true; });
    Array.prototype.forEach.call(root.querySelectorAll('[data-journey] a[data-add]'), function (a) {
      var slug = a.getAttribute('data-add');
      a.hidden = !!chosen[slug];
      journey[slug] = true;
    });
    Array.prototype.forEach.call(root.querySelectorAll('#pv2-stops .pv2-chips a[data-add]'), function (a) {
      if (journey[a.getAttribute('data-add')]) a.hidden = true;
    });
    syncLinks();
    var budget = data.itinerary && data.itinerary.budget;
    var total = budget ? budget.total : null;
    if (total !== lastTotal) {
      $('pv2-live').textContent = total ? 'Estimated total ' + total + ', ' + budget.per_person + ' per person.' : 'No stops in the plan.';
      lastTotal = total;
    }
    (data.messages || []).forEach(toast);
  }

  function build(q) {
    if (pending) pending.abort();
    pending = window.AbortController ? new AbortController() : null;
    root.setAttribute('aria-busy', 'true');
    return fetch(buildUrl + '?' + q, { headers: { Accept: 'application/json' }, signal: pending && pending.signal })
      .then(function (r) {
        if (r.status === 429) { toast('Too many changes at once. Try again in a minute.'); throw new Error('rate'); }
        if (!r.ok) throw new Error(r.status);
        return r.json();
      })
      .then(apply)
      .catch(function (e) { if (e && e.name !== 'AbortError' && e.message !== 'rate') toast('Something went wrong. Reload the page to try again.'); })
      .then(function () { root.removeAttribute('aria-busy'); });
  }

  function buildSoon(q) {
    clearTimeout(timer);
    timer = setTimeout(function () { build(q); }, 250);
  }

  function queryOf(href) {
    var i = href.indexOf('?');
    return i < 0 ? '' : href.slice(i + 1);
  }

  /* Stop controls, Popular, journey chips, Near your route, no-JS search results. */
  root.addEventListener('click', function (e) {
    var a = e.target.closest('a[data-action], a[data-add], .pv2-results a[rel="nofollow"]');
    if (!a || e.metaKey || e.ctrlKey || e.shiftKey) return;
    e.preventDefault();
    closeResults();
    var focusIndex = a.getAttribute('data-index'), action = a.getAttribute('data-action');
    var add = a.getAttribute('data-add');
    // An "add" always applies to the plan as it is now, not as it was when the link was rendered.
    build(add ? query + '&add=' + encodeURIComponent(add) : queryOf(a.getAttribute('href'))).then(function () {
      if (action && focusIndex !== null) {
        var i = +focusIndex + (action === 'up' ? -1 : action === 'down' ? 1 : 0);
        var sel = action === 'remove' ? '#pv2-add-input' : '.pv2-stop:nth-child(' + (i + 1) + ') [data-action="' + action + '"]';
        var el = root.querySelector(sel) || root.querySelector('.pv2-stop:nth-child(' + (i + 1) + ') a[data-action]');
        if (el) el.focus();
      }
    });
  });

  /* Step 2 */
  var tripForm = $('pv2-trip-form');
  if (tripForm) {
    tripForm.addEventListener('change', function () {
      var params = [];
      Array.prototype.forEach.call(tripForm.elements, function (el) {
        if (el.name && !el.disabled) params.push(encodeURIComponent(el.name) + '=' + encodeURIComponent(el.value));
      });
      buildSoon(params.join('&'));
    });
    tripForm.addEventListener('submit', function (e) { e.preventDefault(); });
  }

  /* Step 1 search: a combobox with a listbox of destinations and sites. */
  var input = $('pv2-add-input'), list = $('pv2-results'), options = [], active = -1, searchTimer = null, searchSeq = 0;

  function closeResults() {
    if (!list) return;
    list.hidden = true;
    input.setAttribute('aria-expanded', 'false');
    input.removeAttribute('aria-activedescendant');
    active = -1;
  }

  function highlight(i) {
    active = i;
    options.forEach(function (o, j) { o.el.setAttribute('aria-selected', j === i ? 'true' : 'false'); });
    if (options[i]) {
      input.setAttribute('aria-activedescendant', options[i].el.id);
      options[i].el.scrollIntoView({ block: 'nearest' });
    }
  }

  function choose(i) {
    var o = options[i];
    if (!o) return;
    input.value = '';
    closeResults();
    if (o.dest) build(query + '&add=' + encodeURIComponent(o.dest));
    else toast('We can’t plan around ' + o.label + ' yet. Its page has travel details.');
  }

  function showResults(results) {
    list.innerHTML = '';
    options = [];
    if (!results.length) {
      list.innerHTML = '<p class="pv2-noresults">No matches. Try a town, shrine or saint.</p>';
    }
    results.forEach(function (r, i) {
      var el = document.createElement('div');
      el.id = 'pv2-opt-' + i;
      el.setAttribute('role', 'option');
      el.setAttribute('aria-selected', 'false');
      var sub = r.sub || '';
      if (r.kind === 'site') sub += r.dest ? ' · adds ' + r.dest_city : ' · not plannable yet';
      var b = document.createElement('b'); b.textContent = r.label;
      var small = document.createElement('small'); small.textContent = sub;
      var span = document.createElement('span'); span.appendChild(b); span.appendChild(document.createTextNode(' ')); span.appendChild(small);
      var kind = document.createElement('span'); kind.className = 'pv2-kind'; kind.textContent = r.kind === 'site' ? 'Sacred site' : 'Destination';
      el.appendChild(span); el.appendChild(kind);
      el.addEventListener('mousedown', function (e) { e.preventDefault(); });
      el.addEventListener('click', function () { choose(i); });
      list.appendChild(el);
      options.push({ el: el, dest: r.dest, label: r.label });
    });
    list.hidden = false;
    input.setAttribute('aria-expanded', 'true');
    highlight(options.length ? 0 : -1);
  }

  if (input && list) {
    input.addEventListener('input', function () {
      var q = input.value.trim();
      clearTimeout(searchTimer);
      if (q.length < 2) { closeResults(); return; }
      searchTimer = setTimeout(function () {
        var seq = ++searchSeq;
        fetch(searchUrl + '?q=' + encodeURIComponent(q), { headers: { Accept: 'application/json' } })
          .then(function (r) { return r.ok ? r.json() : { results: [] }; })
          .then(function (data) { if (seq === searchSeq && input.value.trim() === q) showResults(data.results || []); })
          .catch(function () {});
      }, 200);
    });
    input.addEventListener('keydown', function (e) {
      if (list.hidden) return;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (options.length) highlight(Math.max(0, Math.min(options.length - 1, active + (e.key === 'ArrowDown' ? 1 : -1))));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        choose(active);
      } else if (e.key === 'Escape') {
        closeResults();
      }
    });
    input.addEventListener('blur', function () { setTimeout(closeResults, 150); });
    input.form.addEventListener('submit', function (e) { e.preventDefault(); });
  }

  /* Share and print */
  root.addEventListener('click', function (e) {
    var share = e.target.closest('[data-share]');
    if (share) {
      e.preventDefault();
      var url = shareUrl();
      var done = function () { toast('Link copied. Anyone with it can see this plan.'); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(done, function () { window.prompt('Copy this link:', url); });
      } else {
        window.prompt('Copy this link:', url);
      }
      return;
    }
    if (e.target.closest('[data-print]')) window.print();
  });
  /* Save (signed in): the form posts the plan; here it's sent in place. */
  var saveForm = root.querySelector('[data-save-form]');
  if (saveForm) {
    saveForm.addEventListener('submit', function (e) {
      e.preventDefault();
      syncLinks();
      fetch(saveForm.action, { method: 'POST', body: new FormData(saveForm), credentials: 'same-origin',
                               headers: { 'X-Requested-With': 'fetch', Accept: 'application/json' } })
        .then(function (r) { return r.json(); })
        .then(function (data) {
          if (!data.success) { toast(data.message || 'Couldn’t save the trip.'); return; }
          if (!tripId) {
            tripId = String(data.trip);
            var hidden = document.createElement('input');
            hidden.type = 'hidden'; hidden.name = 'trip'; hidden.value = tripId;
            saveForm.appendChild(hidden);
            root.setAttribute('data-trip', tripId);
            var btn = $('pv2-save');
            if (btn) btn.textContent = 'Save changes to My Pilgrimage';
            syncLinks();
            if (window.history && history.replaceState) history.replaceState(null, '', pageUrl + '?' + query + '&trip=' + tripId);
          }
          toast('Saved to My Pilgrimage › My Trips.');
        })
        .catch(function () { toast('Couldn’t save the trip. Try again.'); });
    });
  }

  var printBtn = $('pv2-print');
  if (printBtn) printBtn.hidden = false;

  syncLinks();
})();
