(async function () {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const apiUrl = new URL("api/v1/map", document.baseURI).href;
  const mapEmpty = byId("map-empty");
  let mapComponent;

  function setText(id, value) { byId(id).textContent = value; }
  function formatAge(seconds) {
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    return `${Math.floor(seconds / 3600)}h ago`;
  }
  function status(kind, title, detail) {
    byId("status-dot").className = `status-dot ${kind}`;
    setText("status-title", title);
    setText("status-detail", detail);
  }
  function renderCountries(rows, total) {
    const body = byId("countries-body");
    body.replaceChildren();
    if (!rows.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td"); cell.colSpan = 3; cell.textContent = "No public peer IPs were observed.";
      row.appendChild(cell); body.appendChild(row); return;
    }
    rows.forEach((country) => {
      const row = document.createElement("tr");
      const name = document.createElement("td"); name.className = "country-name";
      const code = document.createElement("span"); code.className = "country-code"; code.textContent = country.code;
      const label = document.createElement("span"); label.textContent = country.name;
      name.append(code, label);
      const count = document.createElement("td"); count.textContent = country.count.toLocaleString("en");
      const share = document.createElement("td"); share.textContent = `${country.share_percent.toFixed(1)}%`;
      row.append(name, count, share); body.appendChild(row);
    });
    setText("country-total", `${total.toLocaleString("en")} observed public IPs`);
  }
  function render(data) {
    const summary = data.summary;
    setText("peer-count", summary.observed_public_ips.toLocaleString("en"));
    setText("country-count", summary.represented_countries.toLocaleString("en"));
    setText("anonymous-count", summary.anonymous_connections.toLocaleString("en"));
    setText("collected-at", formatAge(data.data_age_seconds));
    setText("geoip-edition", data.geoip.edition);
    renderCountries(data.countries, summary.observed_public_ips);
    mapComponent.render(data.markers);
    mapEmpty.hidden = data.markers.length !== 0;
    if (data.stale) status("error", "Snapshot is stale", `Last complete collection was ${formatAge(data.data_age_seconds)}. Displaying the last valid data.`);
    else if (data.collector_status === "error") status("error", "Update failed", "Displaying the last valid snapshot while the collector retries automatically.");
    else status("ok", "Current snapshot", `Collected ${formatAge(data.data_age_seconds)} · refresh interval ${Math.round(data.poll_interval_seconds / 60)} minutes`);
  }
  try {
    mapComponent = await window.QwertycoinNodeMap.mount(byId("world-map"), {});
    const response = await fetch(apiUrl, { headers: { Accept: "application/json" }, credentials: "same-origin" });
    const data = await response.json();
    if (!response.ok) throw new Error(data.message || "Snapshot unavailable");
    render(data);
  } catch (error) {
    status("error", "Node map unavailable", "No complete network snapshot is available yet. The collector will retry automatically.");
    byId("countries-body").innerHTML = '<tr><td colspan="3">No complete snapshot is available.</td></tr>';
    mapEmpty.hidden = false;
    mapEmpty.textContent = "The map will appear after the first successful collection.";
  }
})();
