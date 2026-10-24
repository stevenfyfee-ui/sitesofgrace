/*
 * Destination hub map (Standing Rule 7): the Interactive Map's setup via
 * sitesofgrace/static/js/sog-maps.js -- shared basemap, maxZoom 16, category
 * dots from CATEGORY_STYLES in their own pane, the same radiusFor curve, no
 * clustering, no permanent labels. Popups give the site's name, one line and
 * a link to its page. Opens fitted to the hub's sites.
 *
 * Progressive enhancement: without JavaScript the map stays hidden and the
 * page's site cards carry the same information.
 */
(function () {
  "use strict";

  var el = document.getElementById("hubMap");
  var dataEl = document.getElementById("hub-map-data");
  if (!el || !dataEl || !window.L || !window.SoGMaps || !window.SoGBasemap) return;

  var M = window.SoGMaps;
  var sites = JSON.parse(dataEl.textContent);
  if (!sites.length) return;
  var styles = M.readCategoryStyles();

  el.hidden = false;
  var map = M.createMap(el);
  var pane = M.createSitePane(map);
  var dots = [];
  var bounds = [];

  sites.forEach(function (site) {
    var dot = M.siteMarker(site.latlng, M.categoryStyle(styles, site.category), {
      pane: pane, radius: M.radiusFor(10),
    });
    dot.bindTooltip(M.escapeHtml(site.title), { direction: "top", offset: [0, -6] });
    dot.bindPopup(
      '<div class="map-popup"><h3>' + M.escapeHtml(site.title) + "</h3>" +
      (site.line ? "<p>" + M.escapeHtml(site.line) + "</p>" : "") +
      '<a class="map-popup-link" href="' + M.escapeHtml(site.url) + '">Open site page →</a></div>'
    );
    dot.addTo(map);
    dots.push(dot);
    bounds.push(site.latlng);
  });

  M.bindRadiusOnZoom(map, function () { return dots; });
  if (bounds.length > 1) {
    map.fitBounds(bounds, { padding: [40, 40], maxZoom: 14 });
  } else {
    map.setView(bounds[0], 13);
  }
  // Fitting can land on a zoom where the dots were drawn at another radius.
  dots.forEach(function (d) { d.setRadius(M.radiusFor(map.getZoom())); });
})();
