/*
 * v2 sacred site page: "Where to Stay & Map".
 *
 * Progressive enhancement. The lodging list, its walk details and its
 * "Check availability" links are server-rendered and work without
 * JavaScript; this file reveals and draws the map, the layer toggles and the
 * info bar, and links the list to the markers.
 *
 * Data comes from <script id="site-map-data"> (catalog SacredSitePage
 * .stay_map_payload) and colors from <script id="category-styles">.
 */
(function () {
  "use strict";

  var dataEl = document.getElementById("site-map-data");
  var el = document.getElementById("siteStayMap");
  if (!dataEl || !el || !window.L || !window.SoGMaps || !window.SoGBasemap) return;

  var M = window.SoGMaps;
  var data = JSON.parse(dataEl.textContent);
  var section = document.getElementById("stay-map");
  var categoryData = M.readCategoryStyles();
  var siteCategory = el.getAttribute("data-category");

  // Point styles: sacred places in the page's own category colors, entrances
  // in navy, transit in sky; the site itself is a larger gold dot.
  var STYLES = {
    site: { fill: "#C79A42", stroke: "#032553" },
    shrine: { fill: "#032553", stroke: "#FDF9F2" },
    sacred: M.categoryStyle(categoryData, siteCategory),
    transit: { fill: "#8FB9DD", stroke: "#032553" },
  };
  var SITE_EXTRA = 4;

  el.hidden = false;
  Array.prototype.forEach.call(section.querySelectorAll("[data-needs-js]"), function (node) {
    node.hidden = false;
  });

  var map = M.createMap(el);
  var pane = M.createSitePane(map);
  var layers = { shrine: L.layerGroup(), lodging: L.layerGroup(), sacred: L.layerGroup(), transit: L.layerGroup() };
  var dots = [];
  var bounds = [];

  function addDot(latlng, style, layer, label, popup, extra) {
    var marker = M.siteMarker(latlng, style, { pane: pane, radius: M.radiusFor(15) + (extra || 0), weight: 1.5 });
    marker._sogExtra = extra || 0;
    marker.bindTooltip(M.escapeHtml(label), { direction: "top", offset: [0, -6] });
    if (popup) marker.bindPopup(popup);
    marker.addTo(layers[layer]);
    dots.push(marker);
    if (layer !== "transit") bounds.push(latlng);
    return marker;
  }

  if (data.site) {
    addDot(data.site.latlng, STYLES.site, "shrine", data.site.title,
           "<b>" + M.escapeHtml(data.site.title) + "</b>", SITE_EXTRA);
  }

  data.points.forEach(function (p) {
    var html = "<b>" + M.escapeHtml(p.name) + "</b><br>" + M.escapeHtml(p.kind_label) +
      (p.note ? "<br>" + M.escapeHtml(p.note) : "") +
      (p.url ? '<br><a href="' + M.escapeHtml(p.url) + '">Open page →</a>' : "");
    addDot(p.latlng, STYLES[p.layer] || STYLES.sacred, p.layer, p.name, html);
  });

  // Lodging: small numbered navy circles (never pins), keyboard-focusable.
  var lodgingMarkers = {};
  var route = L.polyline([], { color: "#8A6420", weight: 4, dashArray: "2 8", lineCap: "round", interactive: false });
  route.addTo(layers.lodging);

  data.lodgings.forEach(function (h) {
    var marker = L.marker(h.latlng, {
      keyboard: true,
      title: h.name,
      alt: h.n + ". " + h.name,
      icon: L.divIcon({ className: "v2-lodge-marker", html: '<span class="v2-lodge-icon">' + h.n + "</span>", iconSize: [24, 24] }),
    });
    marker.bindTooltip(M.escapeHtml(h.n + ". " + h.name), { direction: "top", offset: [0, -12] });
    marker.on("click", function () { select(h.id); });
    marker.on("keypress", function (e) {
      if (e.originalEvent && (e.originalEvent.key === "Enter" || e.originalEvent.key === " ")) select(h.id);
    });
    marker.addTo(layers.lodging);
    lodgingMarkers[h.id] = marker;
    bounds.push(h.latlng);
  });

  M.bindRadiusOnZoom(map, function () { return dots; }, function (m) { return m._sogExtra; });

  // Layer toggles: buttons with aria-pressed; transit starts off.
  Array.prototype.forEach.call(section.querySelectorAll("[data-layer]"), function (button) {
    var key = button.getAttribute("data-layer");
    if (!layers[key]) return;
    if (button.getAttribute("aria-pressed") === "true") layers[key].addTo(map);
    button.addEventListener("click", function () {
      var on = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) { layers[key].addTo(map); } else { map.removeLayer(layers[key]); }
    });
  });

  if (bounds.length > 1) {
    map.fitBounds(bounds, { padding: [30, 30], maxZoom: 16 });
  } else if (bounds.length === 1) {
    map.setView(bounds[0], 15);
  } else {
    map.setView([20, 0], 2);
  }

  // Selecting a list item or its marker highlights both, draws the route
  // only when one exists, and fills the info bar.
  var info = document.getElementById("stayInfo");
  var items = {};
  Array.prototype.forEach.call(section.querySelectorAll("[data-lodge-id]"), function (item) {
    var id = Number(item.getAttribute("data-lodge-id"));
    items[id] = item;
    item.setAttribute("role", "button");
    item.setAttribute("tabindex", "0");
    item.setAttribute("aria-pressed", "false");
    item.addEventListener("click", function (e) {
      if (e.target.closest("a")) return;
      select(id);
    });
    item.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); select(id); }
    });
  });

  function select(id) {
    var h = null;
    data.lodgings.forEach(function (x) { if (x.id === id) h = x; });
    if (!h) return;
    Object.keys(items).forEach(function (key) {
      items[key].setAttribute("aria-pressed", Number(key) === id ? "true" : "false");
    });
    Object.keys(lodgingMarkers).forEach(function (key) {
      var icon = lodgingMarkers[key].getElement();
      if (icon) icon.classList.toggle("is-selected", Number(key) === id);
    });
    route.setLatLngs(h.route || []);
    var html = '<span class="v2-stay-info-text">' + M.escapeHtml(h.summary) +
      (h.route ? "" : " <em>Walking route not yet verified.</em>") + "</span>";
    if (h.book_url) {
      html += ' <a class="btn btn-primary" href="' + M.escapeHtml(h.book_url) + '" target="_blank" rel="' +
        M.escapeHtml(h.rel) + '">Check availability <span aria-hidden="true">↗</span></a>';
    }
    info.innerHTML = html;
  }

  if (data.lodgings.length) select(data.lodgings[0].id);
})();
