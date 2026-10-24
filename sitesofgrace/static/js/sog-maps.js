/*
 * Shared map code for every new Sites of Grace map (Standing Rule 7).
 *
 * Every v2 map is Leaflet drawn exactly like the Interactive Map: the shared
 * basemap (SoGBasemap.add, never a new L.tileLayer), maxZoom 16, sites as
 * L.circleMarker dots colored from catalog.models.CATEGORY_STYLES in their own
 * pane above lines, radius from the same radiusFor(zoom) curve, no
 * clustering, no permanent labels. Load after Leaflet and js/basemap.js.
 *
 * The three pre-v2 maps (Interactive Map, trail pages, pilgrim passport)
 * keep their own inline code for now; moving them here is a separate,
 * behavior-checked step (docs/v2/phase0-findings.md, section e).
 */
(function () {
  "use strict";

  // Same curve as the Interactive Map (sitesofgrace/templates/home/map_page.html).
  function radiusFor(z) { return Math.max(2.4, Math.min(7, 2.4 + (z - 2) * 0.62)); }

  /* {styles, default} from the {% category_styles_json %} block. */
  function readCategoryStyles(id) {
    var el = document.getElementById(id || "category-styles");
    if (!el) return { styles: {}, default: { fill: "#173A61", stroke: "#0D2440" } };
    return JSON.parse(el.textContent);
  }

  function categoryStyle(data, category) {
    return (data.styles && data.styles[category]) || data.default;
  }

  /* A map with the shared basemap and maxZoom 16. Scroll-wheel zoom stays off
     until the map is clicked, so the page scrolls past it normally. */
  function createMap(el, options) {
    var opts = options || {};
    opts.maxZoom = window.SoGBasemap.maxZoom;
    opts.scrollWheelZoom = false;
    var map = L.map(el, opts);
    window.SoGBasemap.add(map);
    map.once("click", function () { map.scrollWheelZoom.enable(); });
    return map;
  }

  /* Site dots get their own pane above overlayPane (where lines go), so a
     click on a dot under a line opens the dot. */
  function createSitePane(map, name) {
    var pane = name || "sitesPane";
    map.createPane(pane).style.zIndex = 450;
    return pane;
  }

  function siteMarker(latlng, style, opts) {
    var o = opts || {};
    return L.circleMarker(latlng, {
      pane: o.pane || "sitesPane",
      radius: o.radius,
      fillColor: style.fill,
      color: style.stroke,
      weight: o.weight || 1.1,
      opacity: 1,
      fillOpacity: o.fillOpacity || 0.85,
    });
  }

  /* Resize every dot getMarkers() returns on zoom. extra(marker) lets a
     larger dot (the site itself) keep its offset. */
  function bindRadiusOnZoom(map, getMarkers, extra) {
    map.on("zoomend", function () {
      var r = radiusFor(map.getZoom());
      getMarkers().forEach(function (m) { m.setRadius(r + (extra ? extra(m) : 0)); });
    });
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  window.SoGMaps = {
    radiusFor: radiusFor,
    readCategoryStyles: readCategoryStyles,
    categoryStyle: categoryStyle,
    createMap: createMap,
    createSitePane: createSitePane,
    siteMarker: siteMarker,
    bindRadiusOnZoom: bindRadiusOnZoom,
    escapeHtml: escapeHtml,
  };
})();
