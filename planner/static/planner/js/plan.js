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
  var sel = $('pc-dest');
  dests.forEach(function (d) {
    var o = document.createElement('option');
    o.value = d.id;
    o.textContent = d.city + (d.country ? ', ' + d.country : '');
    sel.appendChild(o);
  });
  if (data.selected_id) sel.value = data.selected_id;
  $('pc-party').value = def.party;
  $('pc-nights').value = def.nights;
  function destById(id) {
    for (var i = 0; i < dests.length; i++) if (String(dests[i].id) === String(id)) return dests[i];
    return dests[0];
  }
  function tierMult(t) { return t === 'budget' ? def.budget : t === 'comfort' ? def.comfort : def.mid; }
  function recompute() {
    var d = destById(sel.value);
    var party = Math.max(1, parseInt($('pc-party').value, 10) || def.party);
    var nights = Math.max(1, parseInt($('pc-nights').value, 10) || def.nights);
    var flightPp = flights[d.region] || 0;
    var rooms = Math.ceil(party / def.people_per_room);
    var flightsTot = flightPp * party;
    var hotels = d.hotel * tierMult($('pc-tier').value) * rooms * nights;
    var meals = d.meal * def.meals_per_day * party * nights;
    var transport = d.transport * party * nights;
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
    $('pc-airport').textContent = d.airport ? 'Nearest airport: ' + d.airport_name + ' (' + d.airport + ')' : '';
    $('pc-basis').textContent = rooms + ' room' + (rooms > 1 ? 's' : '') + ', ' +
      def.meals_per_day + ' meals/day, includes a ' + def.misc_pct + '% buffer for fees and extras.';
  }
  ['pc-dest', 'pc-party', 'pc-nights', 'pc-tier'].forEach(function (id) {
    $(id).addEventListener('input', recompute);
    $(id).addEventListener('change', recompute);
  });
  Array.prototype.forEach.call(document.querySelectorAll('.plan-pick'), function (btn) {
    btn.addEventListener('click', function () {
      sel.value = btn.getAttribute('data-dest-id');
      recompute();
    });
  });
  recompute();
})();
