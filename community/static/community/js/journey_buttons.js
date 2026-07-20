(function () {
  if (window.__journeyButtonsBound) return;
  window.__journeyButtonsBound = true;

  var LABELS = {
    saved: ['Save to my journey', '✓ Saved to my journey'],
    visited: ['Mark as visited', '✓ Visited'],
  };

  function getCookie(name) {
    var value = '; ' + document.cookie;
    var parts = value.split('; ' + name + '=');
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
  }

  function applyState(wrap, status) {
    wrap.querySelectorAll('.journey-btn[data-status]').forEach(function (btn) {
      var pair = LABELS[btn.dataset.status];
      if (!pair) return;
      var active = btn.dataset.status === status;
      btn.textContent = active ? pair[1] : pair[0];
      btn.classList.toggle('active', active);
    });
  }

  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.journey-btn[data-status]');
    if (!btn) return;
    var wrap = btn.closest('.journey-buttons');
    if (!wrap) return;

    e.preventDefault();
    fetch(wrap.dataset.setUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
        'X-CSRFToken': getCookie('csrftoken'),
      },
      body: new URLSearchParams({ site_id: wrap.dataset.siteId, status: btn.dataset.status }),
    })
      .then(function (response) { return response.json(); })
      .then(function (data) { applyState(wrap, data.status); });
  });
})();
