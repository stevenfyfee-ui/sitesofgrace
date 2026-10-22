// Contact page: progressive enhancement for the contact form -- topic cards
// that set the topic, per-topic label/placeholder swaps, the site/saint
// picker, and moving focus to the error summary or the thank-you panel.
// Everything here is a courtesy -- the form posts and validates on the
// server with JavaScript off, and the server is the only authority.
(function () {
  var thanks = document.querySelector('[data-contact-thanks]');
  if (thanks) {
    thanks.scrollIntoView({ block: 'start' });
    thanks.focus({ preventScroll: true });
  }

  var form = document.querySelector('[data-contact-form]');
  var copyEl = document.getElementById('contactTopicCopy');
  if (!form || !copyEl) return;

  var copy = JSON.parse(copyEl.textContent);
  var select = form.querySelector('[data-contact-topic]');
  var cards = document.querySelectorAll('.contact-topic[data-topic]');
  var label = form.querySelector('[data-contact-message-label]');
  var message = form.querySelector('[data-contact-message]');
  var prayerNote = form.querySelector('[data-contact-prayer]');
  var billingNote = form.querySelector('[data-contact-billing]');
  var related = form.querySelector('[data-contact-related]');
  var relInput = form.querySelector('[data-contact-related-input]');
  var relId = form.querySelector('[data-contact-related-id]');
  var relHelp = form.querySelector('[data-contact-related-help]');
  var chip = form.querySelector('[data-contact-chip]');
  var chipName = form.querySelector('[data-contact-chip-name]');
  var chipRemove = form.querySelector('[data-contact-chip-remove]');
  var suggest = form.querySelector('[data-contact-suggest]');
  var suggestUrl = form.getAttribute('data-suggest-url');
  var i;

  // ---------- Topic ----------

  function setTopic(key, scroll) {
    var c = copy[key];
    if (!c) return;
    select.value = key;
    label.textContent = c.label;
    message.placeholder = c.placeholder;
    if (related) related.hidden = !c.related;
    if (relHelp && c.help) relHelp.textContent = c.help;
    if (prayerNote) prayerNote.hidden = key !== 'prayer';
    if (billingNote) billingNote.hidden = key !== 'billing';
    for (var j = 0; j < cards.length; j++) {
      cards[j].setAttribute('aria-pressed', cards[j].getAttribute('data-topic') === key ? 'true' : 'false');
    }
    if (scroll) {
      form.scrollIntoView({ behavior: 'smooth', block: 'start' });
      select.focus({ preventScroll: true });
    }
  }

  // The cards are links to ?topic=<key>#contact-form without JS; here
  // they become toggle buttons that set the select in place.
  for (i = 0; i < cards.length; i++) {
    cards[i].setAttribute('role', 'button');
    cards[i].classList.remove('is-selected');
    cards[i].addEventListener('click', function (e) {
      e.preventDefault();
      setTopic(this.getAttribute('data-topic'), true);
    });
    cards[i].addEventListener('keydown', function (e) {
      if (e.key === ' ' || e.key === 'Spacebar') {
        e.preventDefault();
        setTopic(this.getAttribute('data-topic'), true);
      }
    });
  }
  select.addEventListener('change', function () { setTopic(select.value, false); });

  // ---------- Related site or saint ----------

  var options = [];
  var active = -1;
  var timer = null;
  var lastQuery = '';

  function showChip(name) {
    chipName.textContent = name;
    chipRemove.setAttribute('aria-label', 'Remove ' + name);
    chip.hidden = false;
    relInput.hidden = true;
  }

  function closeSuggest() {
    suggest.hidden = true;
    suggest.innerHTML = '';
    relInput.setAttribute('aria-expanded', 'false');
    relInput.removeAttribute('aria-activedescendant');
    options = [];
    active = -1;
  }

  function pick(option) {
    relId.value = option.getAttribute('data-id');
    showChip(option.getAttribute('data-name'));
    closeSuggest();
    chipRemove.focus();
  }

  function setActive(index) {
    if (!options.length) return;
    if (active >= 0) options[active].classList.remove('is-active');
    active = (index + options.length) % options.length;
    options[active].classList.add('is-active');
    relInput.setAttribute('aria-activedescendant', options[active].id);
  }

  function render(groups) {
    suggest.innerHTML = '';
    options = [];
    active = -1;
    var n = 0;
    groups.forEach(function (group) {
      var heading = document.createElement('div');
      heading.className = 'contact-suggest-group';
      heading.setAttribute('role', 'presentation');
      heading.textContent = group.label;
      suggest.appendChild(heading);
      group.results.forEach(function (result) {
        var option = document.createElement('div');
        option.className = 'contact-suggest-option';
        option.id = 'contactSuggestOption' + n++;
        option.setAttribute('role', 'option');
        option.setAttribute('data-id', result.id);
        option.setAttribute('data-name', result.title);
        option.textContent = result.title;
        if (result.meta) {
          var meta = document.createElement('small');
          meta.textContent = result.meta;
          option.appendChild(meta);
        }
        // mousedown, not click, so the input's blur doesn't close the list first.
        option.addEventListener('mousedown', function (e) {
          e.preventDefault();
          pick(option);
        });
        suggest.appendChild(option);
        options.push(option);
      });
    });
    if (!options.length) {
      var empty = document.createElement('div');
      empty.className = 'contact-suggest-empty';
      empty.textContent = 'No matching sites or saints.';
      suggest.appendChild(empty);
    }
    suggest.hidden = false;
    relInput.setAttribute('aria-expanded', 'true');
  }

  function lookup() {
    var q = relInput.value.trim();
    if (q.length < 2) { closeSuggest(); return; }
    lastQuery = q;
    var xhr = new XMLHttpRequest();
    xhr.open('GET', suggestUrl + '?types=sites,saints&q=' + encodeURIComponent(q));
    xhr.onload = function () {
      if (xhr.status !== 200 || q !== lastQuery) return;
      try {
        render(JSON.parse(xhr.responseText).groups || []);
      } catch (err) {
        closeSuggest();
      }
    };
    xhr.send();
  }

  if (related && relInput && suggestUrl) {
    chipRemove.hidden = false;
    if (chip.hidden) relInput.hidden = false;

    relInput.addEventListener('input', function () {
      clearTimeout(timer);
      timer = setTimeout(lookup, 180);
    });
    relInput.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowDown' || e.key === 'Down') { e.preventDefault(); setActive(active + 1); }
      else if (e.key === 'ArrowUp' || e.key === 'Up') { e.preventDefault(); setActive(active - 1); }
      else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); pick(options[active]); }
      else if (e.key === 'Escape' || e.key === 'Esc') { closeSuggest(); }
    });
    relInput.addEventListener('blur', function () { setTimeout(closeSuggest, 150); });
    chipRemove.addEventListener('click', function () {
      relId.value = '';
      chip.hidden = true;
      relInput.hidden = false;
      relInput.value = '';
      relInput.focus();
    });
  }

  setTopic(select.value, false);

  // ---------- Errors ----------

  var errors = form.querySelector('[data-contact-errors]');
  if (errors) {
    errors.scrollIntoView({ block: 'center' });
    errors.focus({ preventScroll: true });
  }
})();
