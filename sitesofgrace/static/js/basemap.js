/* The ground under every Leaflet map on the site.
 *
 * Two pages draw maps -- the interactive map and a trail page -- and both want
 * the same ground beneath them, so the tile layers live here once and each
 * page just calls SoGBasemap.add(map).
 *
 * Deliberately NOT OpenStreetMap's tiles. Their servers are volunteer-run and
 * their usage policy does not cover a production site; they blocked this
 * domain, and the map served grey "Access blocked" squares instead of a map.
 * Esri's Light Gray Canvas replaces them, and it fixes a second thing at the
 * same time: OSM's standard tiles label places in the LOCAL language
 * ("Deutschland", "Polska", "Italia"), baked into the image with no parameter
 * to change it. This one is English worldwide.
 *
 * Light Gray Canvas is two layers, a base carrying no labels and a labels
 * overlay, which is why there are two tileLayer calls below rather than one.
 * Its near-white ground is also the reason the navy and gold pins read as
 * clearly as they do; a coloured basemap fought them.
 *
 * Note the tile path is {z}/{y}/{x}. Esri orders it row-then-column, the
 * opposite of the {z}/{x}/{y} that every OSM-style URL uses. Swapping those
 * two produces a scrambled map rather than an error, so it is an easy half
 * hour to lose.
 *
 * This endpoint takes no API key, which also means no contract and no usage
 * dashboard -- the same shape of dependency that just broke. When the map is
 * worth protecting, move to a keyed free tier (MapTiler, ArcGIS Location
 * Platform) and change the two URLs below. Nothing else needs to know.
 */
(function (window) {
  'use strict';

  var ESRI = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/';

  /* Light Gray Canvas stops at zoom 16. Without this Leaflet would request
   * zoom 17 and 18 tiles that do not exist and blank the map at exactly the
   * zooms someone uses to find a shrine's street. */
  var MAX_ZOOM = 16;

  function addBasemap(map) {
    L.tileLayer(ESRI + 'World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: MAX_ZOOM,
      attribution: 'Tiles &copy; Esri &mdash; Esri, DeLorme, NAVTEQ',
    }).addTo(map);

    /* Place names, in English, over the base. Leaflet keeps every tile pane
     * below every marker pane, so pins and trail lines still sit on top of
     * this without any z-index work here. */
    L.tileLayer(ESRI + 'World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
      maxZoom: MAX_ZOOM,
    }).addTo(map);
  }

  window.SoGBasemap = {
    add: addBasemap,
    maxZoom: MAX_ZOOM,
  };
})(window);
