// Support page: progressive enhancement for the give form, plus moving
// focus to the thank-you panel when Stripe sends the visitor back.
// Everything here is a courtesy -- the form posts and validates on the
// server with JavaScript off, and the server is the only authority.
(function () {
  var thanks = document.querySelector('[data-support-thanks]');
  if (thanks) {
    thanks.scrollIntoView({ block: 'start' });
    thanks.focus({ preventScroll: true });
  }

  var form = document.querySelector('[data-support-form]');
  if (!form) return;

  var custom = form.querySelector('[data-support-custom]');
  var customInput = custom ? custom.querySelector('input') : null;
  var label = form.querySelector('[data-support-label]');
  var pers = form.querySelectorAll('[data-support-per]');
  // Once the visitor picks an amount themselves, switching frequency
  // leaves it alone; until then it follows that frequency's default.
  var amountTouched = false;

  function checked(name) {
    var el = form.querySelector('input[name="' + name + '"]:checked');
    return el ? el.value : '';
  }

  function frequency() {
    // A hidden input stands in when monthly is turned off.
    return checked('frequency') || 'once';
  }

  function selectAmount(value) {
    var el = form.querySelector('input[name="amount"][value="' + value + '"]');
    if (el) el.checked = true;
  }

  function update() {
    var monthly = frequency() === 'monthly';
    var amount = checked('amount');
    var other = amount === 'other';
    var i;

    for (i = 0; i < pers.length; i++) pers[i].textContent = monthly ? '/mo' : '';

    if (custom) {
      custom.className = other ? 'support-custom is-on' : 'support-custom';
      // Disabled when hidden, so a stale value is never submitted.
      customInput.disabled = !other;
    }

    var shown = other ? customInput.value.replace(/[^0-9.]/g, '') : amount;
    if (label) {
      label.textContent = shown
        ? 'Support with $' + shown + (monthly ? ' a month' : '')
        : 'Choose an amount';
    }
  }

  form.addEventListener('change', function (e) {
    var target = e.target;
    if (target.name === 'amount') {
      amountTouched = true;
    } else if (target.name === 'frequency' && !amountTouched) {
      selectAmount(form.getAttribute(target.value === 'monthly' ? 'data-default-monthly' : 'data-default-once'));
    }
    update();
    if (target.name === 'amount' && target.value === 'other' && customInput) customInput.focus();
  });
  if (customInput) customInput.addEventListener('input', update);

  // A re-rendered form (an error, a preserved choice) already carries the
  // visitor's own pick.
  if (form.querySelector('.support-error') || (customInput && customInput.value)) amountTouched = true;

  form.className += ' is-enhanced';
  update();
})();
