/* Drawing pilgrimage trails on a Leaflet map.
 *
 * Two pages draw trails: the interactive map (every trail, alongside the
 * category pins) and a trail page (one trail, on its own). They want the same
 * line, the same numbered stops and the same popups, so the drawing lives here
 * once and each page decides only WHICH trails to ask for and what to do with
 * the result.
 *
 * Colors are not defined here. They arrive in the JSON, from
 * catalog.models.TRAIL_COLORS, so a palette change is one Python edit.
 */
(function (window) {
  'use strict';

  function stopIcon(trail, stop) {
    var label = stop.number;
    var size = label > 99 ? 30 : 26;
    var html =
      '<span class="trail-stop-dot" style="background:' + trail.color + '">' + label + '</span>';
    return L.divIcon({
      html: html,
      className: 'trail-stop-icon',
      iconSize: [size, size],
      iconAnchor: [size / 2, size / 2],
      popupAnchor: [0, -(size / 2) - 2],
    });
  }

  function escapeHtml(value) {
    return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {
      return {
        '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
      }[character];
    });
  }

  function stopPopup(trail, stop) {
    var parts = ['<div class="map-popup trail-popup">'];
    parts.push(
      '<span class="trail-popup-kicker" style="color:' + trail.color + '">Stop ' +
      stop.number + ' &middot; ' + escapeHtml(trail.title) + '</span>'
    );
    parts.push('<h3>' + escapeHtml(stop.title) + '</h3>');
    if (stop.locality) {
      parts.push('<p class="map-popup-meta">' + escapeHtml(stop.locality) + '</p>');
    }
    if (stop.note) {
      parts.push('<p>' + escapeHtml(stop.note) + '</p>');
    }
    if (stop.url) {
      parts.push('<a class="map-popup-link" href="' + stop.url + '">Read more &rarr;</a>');
    }
    parts.push('</div>');
    return parts.join('');
  }

  function linePopup(trail) {
    var parts = ['<div class="map-popup trail-popup">'];
    parts.push(
      '<span class="trail-popup-kicker" style="color:' + trail.color + '">' +
      escapeHtml(trail.trail_type) + '</span>'
    );
    parts.push('<h3>' + escapeHtml(trail.title) + '</h3>');
    if (trail.length_display) {
      parts.push('<p class="map-popup-meta">' + escapeHtml(trail.length_display) + '</p>');
    }
    if (trail.summary_short) {
      parts.push('<p>' + escapeHtml(trail.summary_short) + '</p>');
    }
    if (trail.url) {
      parts.push('<a class="map-popup-link" href="' + trail.url + '">Follow the route &rarr;</a>');
    }
    parts.push('</div>');
    return parts.join('');
  }

  /* Draw one trail. Returns { trail, line, markers, bounds } so the caller can
   * fit the view or toggle the whole route on and off as one thing. */
  function drawTrail(map, trail, options) {
    options = options || {};
    var coordinates = trail.stops.map(function (stop) {
      return [stop.latitude, stop.longitude];
    });

    var line = L.polyline(coordinates, {
      color: trail.color,
      weight: options.weight || 4,
      opacity: 0.85,
      // A dashed line reads as a route rather than a border or a boundary,
      // which matters on a map already carrying roads and coastlines.
      dashArray: '1 9',
      lineCap: 'round',
      lineJoin: 'round',
    });
    line.bindPopup(linePopup(trail));

    // The whole-world map already carries a category pin for every stop that
    // has a page, so numbering them there would stack two markers on one
    // point. It draws the line alone; a trail's own map draws the numbers.
    var markers = options.showStops === false ? [] : trail.stops.map(function (stop) {
      var marker = L.marker([stop.latitude, stop.longitude], {
        icon: stopIcon(trail, stop),
        // Above the line, below an open popup.
        zIndexOffset: 200,
      });
      marker.bindPopup(stopPopup(trail, stop));
      return marker;
    });

    var group = L.layerGroup([line].concat(markers));
    if (options.addTo !== false) {
      group.addTo(map);
    }

    return {
      trail: trail,
      line: line,
      markers: markers,
      group: group,
      bounds: line.getBounds(),
    };
  }

  function fetchTrails(url) {
    return fetch(url)
      .then(function (response) { return response.json(); })
      .then(function (data) { return (data && data.trails) || []; });
  }

  window.SoGTrails = {
    fetch: fetchTrails,
    draw: drawTrail,
  };
})(window);
