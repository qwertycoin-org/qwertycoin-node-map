(function (global) {
  "use strict";

  function markerRadius(count) {
    return Math.max(6, Math.min(25, 4 + Math.sqrt(count) * 4));
  }

  async function loadCountries(url) {
    const response = await fetch(url, { credentials: "same-origin" });
    if (!response.ok) throw new Error("Country boundaries unavailable");
    return response.json();
  }

  async function mount(container, options) {
    if (!container || !global.L) throw new Error("Node Map prerequisites are unavailable");
    const countriesUrl = options.countriesUrl || new URL("assets/countries.geojson", document.baseURI).href;
    const countries = await loadCountries(countriesUrl);
    const map = global.L.map(container, {
      minZoom: 1,
      maxZoom: 6,
      zoomControl: true,
      attributionControl: true,
      worldCopyJump: false,
      maxBounds: [[-88, -190], [88, 190]],
      maxBoundsViscosity: 1,
    }).setView([18, 5], 2);
    map.attributionControl.setPrefix(false);
    map.attributionControl.addAttribution('<a href="https://www.naturalearthdata.com/" rel="external noopener">Natural Earth</a>');
    global.L.geoJSON(countries, {
      style: { color: "#5e594f", weight: 0.7, fillColor: "#2b2924", fillOpacity: 1 },
      interactive: false,
    }).addTo(map);
    const markerLayer = global.L.layerGroup().addTo(map);

    function render(markers) {
      markerLayer.clearLayers();
      markers.forEach((marker) => {
        const circle = global.L.circleMarker([marker.latitude, marker.longitude], {
          radius: markerRadius(marker.count),
          color: "#141414",
          weight: 2,
          fillColor: "#ffaf00",
          fillOpacity: 0.86,
          keyboard: true,
        });
        const noun = marker.count === 1 ? "observed IP" : "observed IPs";
        circle.bindTooltip(`${marker.country_code} · ${marker.count} ${noun}`, {
          direction: "top",
          className: "peer-tooltip",
        });
        circle.addTo(markerLayer);
      });
    }

    return { render, invalidateSize: () => map.invalidateSize() };
  }

  global.QwertycoinNodeMap = { mount };
})(window);
