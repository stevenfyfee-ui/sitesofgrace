(function () {
  var el = document.getElementById('plan-data');
  if (!el) return;
  var data = JSON.parse(el.textContent);
  var dests = data.destinations, flights = data.region_flights, def = data.defaults;
  if (!dests.length) return;

  var $ = function (id) { return document.getElementById(id); };
  var fmt = function (n) {
    return def.currency === 'USD'
      ? '$' + Math.round(n).toLocaleString('en-US')
      : Math.round(n).toLocaleString() + ' ' + def.currency;
  };
  var MAX_STOPS = 3;
  var stopsEl = $('pc-stops');
  var addBtn = $('pc-add-stop');

  function destById(id) {
    for (var i = 0; i < dests.length; i++) if (String(dests[i].id) === String(id)) return dests[i];
    return dests[0];
  }
  function tierMult(t) { return t === 'budget' ? def.budget : t === 'comfort' ? def.comfort : def.mid; }
  function stopCount() { return stopsEl.querySelectorAll('.plan-stop').length; }

  function updateControls() {
    var stops = stopsEl.querySelectorAll('.plan-stop');
    Array.prototype.forEach.call(stops, function (s) {
      s.querySelector('.pc-remove-stop').style.display = stops.length > 1 ? '' : 'none';
    });
    addBtn.style.display = stops.length >= MAX_STOPS ? 'none' : '';
  }

  function makeStop(selectedId) {
    var wrap = document.createElement('div');
    wrap.className = 'plan-stop';
    var opts = dests.map(function (d) {
      return '<option value="' + d.id + '">' + d.city + (d.country ? ', ' + d.country : '') + '</option>';
    }).join('');
    wrap.innerHTML =
      '<div class="plan-field"><label>Destination</label>' +
        '<select class="pc-dest">' + opts + '</select>' +
        '<p class="plan-airport"></p></div>' +
      '<div class="plan-field plan-field-nights"><label>Nights</label>' +
        '<input type="number" class="pc-nights" min="1" max="60" step="1" value="' + def.nights + '"></div>' +
      '<button type="button" class="pc-remove-stop" aria-label="Remove stop">&times;</button>';
    if (selectedId) wrap.querySelector('.pc-dest').value = selectedId;
    wrap.querySelector('.pc-dest').addEventListener('change', recompute);
    wrap.querySelector('.pc-nights').addEventListener('input', recompute);
    wrap.querySelector('.pc-remove-stop').addEventListener('click', function () {
      wrap.parentNode.removeChild(wrap);
      updateControls(); recompute();
    });
    return wrap;
  }

  function addStop(selectedId) {
    if (stopCount() >= MAX_STOPS) return;
    stopsEl.appendChild(makeStop(selectedId));
    updateControls();
  }

  function recompute() {
    var party = Math.max(1, parseInt($('pc-party').value, 10) || def.party);
    var tier = $('pc-tier').value;
    var rooms = Math.ceil(party / def.people_per_room);
    var hotels = 0, meals = 0, transport = 0, totalNights = 0, maxRegionRt = 0;
    var itinerary = [];
    var stops = stopsEl.querySelectorAll('.plan-stop');
    Array.prototype.forEach.call(stops, function (s) {
      var d = destById(s.querySelector('.pc-dest').value);
      var nights = Math.max(1, parseInt(s.querySelector('.pc-nights').value, 10) || def.nights);
      hotels += d.hotel * tierMult(tier) * rooms * nights;
      meals += d.meal * def.meals_per_day * party * nights;
      transport += d.transport * party * nights;
      totalNights += nights;
      var rt = flights[d.region] || 0;
      if (rt > maxRegionRt) maxRegionRt = rt;
      itinerary.push(d.city + ' (' + nights + 'n)');
      s.querySelector('.plan-airport').textContent =
        d.airport ? 'Nearest airport: ' + d.airport_name + ' (' + d.airport + ')' : '';
    });
    var numStops = stops.length;
    var flightsTot = maxRegionRt * party + def.hop * party * Math.max(0, numStops - 1);
    var subtotal = flightsTot + hotels + meals + transport;
    var misc = subtotal * def.misc_pct / 100;
    var total = subtotal + misc;
    $('pc-flights').textContent = fmt(flightsTot);
    $('pc-hotels').textContent = fmt(hotels);
    $('pc-meals').textContent = fmt(meals);
    $('pc-transport').textContent = fmt(transport);
    $('pc-misc').textContent = fmt(misc);
    $('pc-total').textContent = fmt(total);
    $('pc-perperson').textContent = fmt(total / party);
    var hop = numStops > 1
      ? ' (1 international round-trip + ' + (numStops - 1) + ' inter-city hop' + (numStops - 1 > 1 ? 's' : '') + ')'
      : '';
    $('pc-basis').textContent = itinerary.join(' → ') + ' — ' + rooms +
      ' room' + (rooms > 1 ? 's' : '') + ', ' + totalNights + ' nights, ' +
      def.meals_per_day + ' meals/day, ' + def.misc_pct + '% buffer' + hop + '.';
  }

  $('pc-party').value = def.party;
  $('pc-party').addEventListener('input', recompute);
  $('pc-tier').addEventListener('change', recompute);
  addBtn.addEventListener('click', function () { addStop(null); recompute(); });

  addStop(data.selected_id || null);
  updateControls();

  Array.prototype.forEach.call(document.querySelectorAll('.plan-pick'), function (btn) {
    btn.addEventListener('click', function () {
      var first = stopsEl.querySelector('.plan-stop .pc-dest');
      if (first) { first.value = btn.getAttribute('data-dest-id'); recompute(); }
    });
  });

  recompute();
})();
