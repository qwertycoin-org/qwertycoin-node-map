(function () {
  "use strict";
  const root = document.documentElement;
  const themeToggle = document.querySelector("[data-theme-toggle]");
  const themeLabel = document.querySelector("[data-theme-label]");
  const navToggle = document.querySelector("[data-nav-toggle]");
  const navMenu = document.querySelector("[data-nav-menu]");

  function storedTheme() {
    try { return localStorage.getItem("qwc-node-map-theme"); }
    catch (_) { return null; }
  }

  function applyTheme(theme, persist) {
    const selected = theme === "dark" ? "dark" : "light";
    root.dataset.theme = selected;
    if (themeToggle) themeToggle.setAttribute("aria-pressed", String(selected === "dark"));
    if (themeLabel) themeLabel.textContent = selected === "dark" ? "Dark" : "Light";
    if (persist) {
      try { localStorage.setItem("qwc-node-map-theme", selected); }
      catch (_) { /* The selected theme still applies for this page view. */ }
    }
    window.dispatchEvent(new CustomEvent("qwc-theme-change", { detail: { theme: selected } }));
  }

  applyTheme(storedTheme(), false);
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      applyTheme(root.dataset.theme === "dark" ? "light" : "dark", true);
    });
  }

  if (navToggle && navMenu) {
    const closeMenu = () => {
      navMenu.classList.remove("is-open");
      navToggle.setAttribute("aria-expanded", "false");
    };
    navToggle.addEventListener("click", () => {
      const open = navMenu.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", String(open));
    });
    navMenu.addEventListener("click", (event) => {
      if (event.target instanceof HTMLAnchorElement) closeMenu();
    });
    window.addEventListener("resize", () => {
      if (window.matchMedia("(min-width: 1201px)").matches) closeMenu();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !navMenu.classList.contains("is-open")) return;
      closeMenu();
      navToggle.focus();
    });
  }
})();

(async function () {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const mapEmpty = byId("map-empty");
  const historyPanel = byId("history-panel");
  const tabs = Array.from(document.querySelectorAll("[data-history-window]"));
  let mapComponent;
  let requestController;

  window.addEventListener("qwc-theme-change", () => {
    if (mapComponent && mapComponent.setTheme) mapComponent.setTheme();
  });

  function setText(id, value) { byId(id).textContent = value; }
  function formatAge(seconds) {
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
  }
  function formatCoverage(seconds) {
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h`;
    return `${Math.floor(seconds / 86400)}d`;
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
    setText("coverage-count", formatCoverage(data.coverage_seconds));
    setText("coverage-note", data.partial_window ? "History is still accumulating" : "Complete selected observation window");
    setText("collected-at", formatAge(data.data_age_seconds));
    setText("geoip-edition", data.geoip.edition);
    renderCountries(data.countries, summary.observed_public_ips);
    mapComponent.render(data.markers);
    mapEmpty.hidden = data.markers.length !== 0;
    if (data.stale) status("error", "History update is stale", `Last complete collection was ${formatAge(data.data_age_seconds)}. Displaying retained observations.`);
    else if (data.collector_status === "error") status("error", "Update failed", "Displaying retained observations while the collector retries automatically.");
    else if (data.partial_window) status("ok", "History is accumulating", `Tracking started ${formatAge(data.coverage_seconds)} · each public IP is counted once in this period`);
    else status("ok", "Historical view is current", `Updated ${formatAge(data.data_age_seconds)} · each public IP is counted once in this period`);
  }

  function selectTab(tab) {
    tabs.forEach((candidate) => {
      const selected = candidate === tab;
      candidate.setAttribute("aria-selected", String(selected));
      candidate.tabIndex = selected ? 0 : -1;
    });
    historyPanel.setAttribute("aria-labelledby", tab.id);
  }

  async function loadWindow(tab) {
    selectTab(tab);
    if (requestController) requestController.abort();
    requestController = new AbortController();
    historyPanel.setAttribute("aria-busy", "true");
    status("", "Loading observation history…", "Reading retained aggregate data; no new Core RPC request is triggered.");
    try {
      const url = new URL("api/v1/history", document.baseURI);
      url.searchParams.set("window", tab.dataset.historyWindow);
      const response = await fetch(url, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
        signal: requestController.signal,
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.message || "History unavailable");
      render(data);
    } catch (error) {
      if (error.name === "AbortError") return;
      status("error", "Node history unavailable", "No complete historical observation is available yet. The collector will retry automatically.");
      byId("countries-body").innerHTML = '<tr><td colspan="3">No complete history is available.</td></tr>';
      mapComponent.render([]);
      mapEmpty.hidden = false;
      mapEmpty.textContent = "The map will appear after the first successful historical observation.";
    } finally {
      historyPanel.removeAttribute("aria-busy");
    }
  }

  try {
    mapComponent = await window.QwertycoinNodeMap.mount(byId("world-map"), {});
  } catch (_) {
    status("error", "Node map unavailable", "The local map assets could not be initialized.");
    byId("countries-body").innerHTML = '<tr><td colspan="3">The map could not be initialized.</td></tr>';
    mapEmpty.hidden = false;
    return;
  }
  tabs.forEach((tab, index) => {
    tab.addEventListener("click", () => loadWindow(tab));
    tab.addEventListener("keydown", (event) => {
      if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
      event.preventDefault();
      let targetIndex = index;
      if (event.key === "ArrowLeft") targetIndex = (index - 1 + tabs.length) % tabs.length;
      if (event.key === "ArrowRight") targetIndex = (index + 1) % tabs.length;
      if (event.key === "Home") targetIndex = 0;
      if (event.key === "End") targetIndex = tabs.length - 1;
      tabs[targetIndex].focus();
      loadWindow(tabs[targetIndex]);
    });
  });
  await loadWindow(tabs[0]);
})();
