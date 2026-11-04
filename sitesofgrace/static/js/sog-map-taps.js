/*
 * Taps on small map dots, for every Leaflet map with site dots (the
 * Interactive Map, the site page's Where to Stay map, destination hub maps,
 * the pilgrim passport map). Load after Leaflet.
 *
 * - Tap to nearest: a click on the map that missed every dot opens the
 *   nearest visible dot's popup if it's within 22px on a touch screen
 *   (8px with a mouse). Only dots currently on the map count, so legend and
 *   search filters are respected. Nothing zooms.
 * - Popups fit the map: content at most 300px, and the whole popup never
 *   wider than the map less 48px, with auto-pan padding; recomputed on resize.
 * - minRadius(): touch screens get a 4px minimum dot radius (sog-maps.js and
 *   the Interactive Map's radiusFor use it); mouse sizes are unchanged.
 *
 * Dot colors, the no-labels rule and the no-clustering rule are untouched.
 */
(function () {
  "use strict";

  function coarse() {
    return !!(window.matchMedia && window.matchMedia("(pointer: coarse)").matches);
  }

  function minRadius() { return coarse() ? 4 : 2.4; }

  // Leaflet's maxWidth is the content box only; map.css adds 20px of margin
  // each side plus 4px of border and padding around it.
  var POPUP_CHROME = 44;

  /* The whole popup stays at least 48px narrower than the map. */
  function popupOptions(map) {
    return {
      maxWidth: Math.max(160, Math.min(300, map.getSize().x - 48 - POPUP_CHROME)),
      autoPanPadding: [16, 16],
      keepInView: true,
    };
  }

  /* getMarkers() returns the map's site dots (all of them; the ones not on
     the map right now are skipped here). */
  function attach(map, getMarkers) {
    map.on("popupopen", function (e) {
      L.setOptions(e.popup, popupOptions(map));
      e.popup.update();
    });
    map.on("resize", function () {
      map.eachLayer(function (layer) {
        if (layer instanceof L.Popup) {
          L.setOptions(layer, popupOptions(map));
          layer.update();
        }
      });
    });
    map.on("click", function (e) {
      // A click that landed on a dot (or a line) bubbles here too; that
      // layer has already handled it.
      if (e.sourceTarget && e.sourceTarget !== map) return;
      var limit = coarse() ? 22 : 8;
      var best = null;
      var bestDistance = Infinity;
      getMarkers().forEach(function (marker) {
        if (!map.hasLayer(marker)) return;
        var d = map.latLngToContainerPoint(marker.getLatLng()).distanceTo(e.containerPoint);
        if (d < bestDistance) { best = marker; bestDistance = d; }
      });
      if (!best || bestDistance > limit) return;
      if (best.getPopup()) {
        best.openPopup();
      } else {
        best.fire("click", { latlng: best.getLatLng() });
      }
    });
  }

  window.SoGMapTaps = { attach: attach, minRadius: minRadius, popupOptions: popupOptions, coarse: coarse };
})();
