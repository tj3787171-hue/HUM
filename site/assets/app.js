/* app.js — HUM.org Lab client-side interactivity */

const HUM = (() => {
  "use strict";

  /* ---- SVG Map builder ---- */
  function renderSvgMap(containerId, topology) {
    const wrap = document.getElementById(containerId);
    if (!wrap || !topology) return;

    const ifaces = topology.interfaces || [];
    const routes  = topology.routes || [];
    const veths   = topology.veth_peers || [];
    const ns      = topology.namespaces || [];
    const docker  = topology.docker_networks || [];

    const W = 820, H = 340;
    const xmlns = "http://www.w3.org/2000/svg";

    const svg = document.createElementNS(xmlns, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    svg.setAttribute("xmlns", xmlns);

    /* background */
    const bg = rect(svg, 0, 0, W, H, "#0d1117", 0);

    /* hostname label */
    text(svg, W / 2, 28, topology.hostname || "hum-lab", "#58a6ff", 16, "bold");
    text(svg, W / 2, 46, topology.timestamp || "", "#8b949e", 9);

    /* render interfaces as boxes */
    const boxW = 180, boxH = 80, gap = 30;
    const startX = (W - (ifaces.length * (boxW + gap) - gap)) / 2;

    ifaces.forEach((iface, i) => {
      const x = startX + i * (boxW + gap);
      const y = 70;
      const stateColor = iface.state === "UP" ? "#3fb950"
                       : iface.state === "DOWN" ? "#f85149" : "#d29922";

      roundRect(svg, x, y, boxW, boxH, "#161b22", "#30363d");
      circle(svg, x + 14, y + 16, 5, stateColor);
      text(svg, x + boxW / 2, y + 18, iface.name, "#c9d1d9", 13, "bold");
      text(svg, x + boxW / 2, y + 36, iface.mac || "", "#8b949e", 8);
      (iface.addresses || []).forEach((addr, ai) => {
        text(svg, x + boxW / 2, y + 50 + ai * 13, addr, "#58a6ff", 10);
      });
    });

    /* route arrows below interfaces */
    const routeY = 180;
    text(svg, W / 2, routeY, "Routes", "#8b949e", 11, "bold");
    routes.forEach((r, ri) => {
      const ry = routeY + 18 + ri * 16;
      const label = `${r.dst}${r.gateway ? " via " + r.gateway : ""} dev ${r.dev}`;
      text(svg, W / 2, ry, label, "#c9d1d9", 9);
    });

    /* veth peers */
    const vethY = routeY + 18 + routes.length * 16 + 20;
    if (veths.length > 0) {
      text(svg, W / 2, vethY, "veth / Link Peers", "#8b949e", 11, "bold");
      veths.forEach((v, vi) => {
        const vy = vethY + 16 + vi * 15;
        const peerNote = v.peer_ifindex ? ` \u2194 peer@${v.peer_ifindex}` : "";
        const label = `${v.ifname} [idx:${v.ifindex}] ${v.operstate}${peerNote}`;
        const col = v.operstate === "UP" ? "#3fb950" : "#f85149";
        text(svg, W / 2, vy, label, col, 9);
      });
    }

    /* docker networks */
    if (docker.length > 0) {
      const dockY = vethY + 16 + veths.length * 15 + 14;
      text(svg, W / 2, dockY, "Docker Networks", "#8b949e", 11, "bold");
      docker.forEach((dn, di) => {
        text(svg, W / 2, dockY + 16 + di * 15,
             `${dn.Name || dn.name} (${dn.Driver || dn.driver})`, "#d29922", 9);
      });
    }

    /* namespaces */
    if (ns.length > 0) {
      const nsY = H - 30;
      text(svg, W / 2, nsY, "NETNS: " + ns.join(", "), "#79c0ff", 10);
    }

    wrap.innerHTML = "";
    wrap.appendChild(svg);
  }

  /* ---- SVG helpers ---- */
  function rect(parent, x, y, w, h, fill, r) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    el.setAttribute("x", x); el.setAttribute("y", y);
    el.setAttribute("width", w); el.setAttribute("height", h);
    el.setAttribute("fill", fill);
    if (r) el.setAttribute("rx", r);
    parent.appendChild(el);
    return el;
  }
  function roundRect(parent, x, y, w, h, fill, stroke) {
    const el = rect(parent, x, y, w, h, fill, 6);
    el.setAttribute("stroke", stroke); el.setAttribute("stroke-width", 1);
    return el;
  }
  function circle(parent, cx, cy, r, fill) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    el.setAttribute("cx", cx); el.setAttribute("cy", cy);
    el.setAttribute("r", r); el.setAttribute("fill", fill);
    parent.appendChild(el);
    return el;
  }
  function text(parent, x, y, content, fill, size, weight) {
    const el = document.createElementNS("http://www.w3.org/2000/svg", "text");
    el.setAttribute("x", x); el.setAttribute("y", y);
    el.setAttribute("fill", fill || "#c9d1d9");
    el.setAttribute("font-size", size || 12);
    el.setAttribute("text-anchor", "middle");
    if (weight) el.setAttribute("font-weight", weight);
    el.textContent = content;
    parent.appendChild(el);
    return el;
  }

  /* ---- Feedback log ---- */
  function appendLog(logId, message) {
    const el = document.getElementById(logId);
    if (!el) return;
    const ts = new Date().toLocaleTimeString();
    el.textContent += `[${ts}] ${message}\n`;
    el.scrollTop = el.scrollHeight;
  }

  /* ---- Topology data loader ---- */
  async function loadTopology() {
    try {
      const res = await fetch("data/topology.json?t=" + Date.now());
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      console.error("Failed to load topology:", e);
      return null;
    }
  }

  /* ---- Refresh cycle ---- */
  async function refreshMap(containerId, logId) {
    appendLog(logId, "Fetching topology data...");
    const topo = await loadTopology();
    if (topo) {
      renderSvgMap(containerId, topo);
      appendLog(logId, `Map updated — ${topo.interfaces?.length || 0} interfaces, ` +
                        `${topo.routes?.length || 0} routes, ` +
                        `${topo.veth_peers?.length || 0} link peers`);
    } else {
      appendLog(logId, "ERROR: Could not load topology data.");
    }
  }

  /* ---- Artifact layer viewer ---- */
  async function loadArtifactLayers() {
    const res = await fetch("data/artifact-layers.json?t=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  function formatBytes(bytes) {
    if (!Number.isFinite(bytes)) return "";
    if (bytes < 1024) return `${bytes} B`;
    const units = ["KB", "MB", "GB"];
    let value = bytes / 1024;
    for (const unit of units) {
      if (value < 1024) return `${value.toFixed(1)} ${unit}`;
      value /= 1024;
    }
    return `${value.toFixed(1)} TB`;
  }

  function renderLayerSummary(payload) {
    const wrap = document.getElementById("layer-summary");
    if (!wrap) return;
    const layers = payload.layers || {};
    wrap.innerHTML = Object.entries(layers).sort().map(([layer, data]) => `
      <article class="panel layer-card">
        <strong>${layer}</strong>
        <span>${data.count || 0} files</span>
        <small>${formatBytes(data.size_bytes || 0)}</small>
      </article>
    `).join("");
  }

  function renderLayerTable(payload) {
    const tbody = document.getElementById("layer-table-body");
    const select = document.getElementById("layer-filter");
    const search = document.getElementById("search-filter");
    if (!tbody || !select || !search) return;

    const layerValue = select.value || "all";
    const query = (search.value || "").toLowerCase();
    const rows = (payload.artifacts || []).filter(item => {
      const haystack = `${item.layer} ${item.kind} ${item.path} ${item.sha256_prefix || ""}`.toLowerCase();
      return (layerValue === "all" || item.layer === layerValue) && haystack.includes(query);
    });

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="5">No matching artifact layers.</td></tr>';
      return;
    }

    tbody.innerHTML = rows.map(item => {
      const speed = item.benchmark ? `${item.benchmark.mb_per_sec} MB/s` : "not sampled";
      return `
        <tr>
          <td><span class="badge badge-unknown">${item.layer}</span><br><small>${item.kind}</small></td>
          <td>${item.path}</td>
          <td>${formatBytes(item.size_bytes || 0)}</td>
          <td><code>${item.sha256_prefix || ""}</code></td>
          <td>${speed}</td>
        </tr>
      `;
    }).join("");
  }

  function populateLayerFilter(payload) {
    const select = document.getElementById("layer-filter");
    if (!select) return;
    const current = select.value || "all";
    const layers = Object.keys(payload.layers || {}).sort();
    select.innerHTML = '<option value="all">All layers</option>' +
      layers.map(layer => `<option value="${layer}">${layer}</option>`).join("");
    select.value = layers.includes(current) ? current : "all";
  }

  async function refreshLayers() {
    const logId = "layer-log";
    appendLog(logId, "Fetching artifact-layer JSON...");
    try {
      const payload = await loadArtifactLayers();
      window.HUM_LAYER_PAYLOAD = payload;
      populateLayerFilter(payload);
      renderLayerSummary(payload);
      renderLayerTable(payload);
      appendLog(logId, `Loaded ${payload.artifact_count || 0} artifacts from ${payload.generated_at || "unknown time"}.`);
    } catch (e) {
      appendLog(logId, `ERROR: ${e.message}`);
    }
  }

  function initLayerViewer() {
    if (!document.getElementById("layer-table-body")) return;
    document.getElementById("refresh-layers")?.addEventListener("click", refreshLayers);
    document.getElementById("layer-filter")?.addEventListener("change", () => renderLayerTable(window.HUM_LAYER_PAYLOAD || {}));
    document.getElementById("search-filter")?.addEventListener("input", () => renderLayerTable(window.HUM_LAYER_PAYLOAD || {}));
    refreshLayers();
  }

  /* ---- Navigation active state ---- */
  function highlightNav() {
    const path = window.location.pathname;
    document.querySelectorAll("nav a").forEach(a => {
      if (a.getAttribute("href") && path.endsWith(a.getAttribute("href"))) {
        a.classList.add("active");
      }
    });
  }

  /* ---- Init ---- */
  function init() {
    highlightNav();

    const mapEl = document.getElementById("svg-map");
    const logEl = document.getElementById("feedback-log");
    if (mapEl) {
      refreshMap("svg-map", "feedback-log");
      setInterval(() => refreshMap("svg-map", "feedback-log"), 15000);
    }
    initLayerViewer();
  }

  document.addEventListener("DOMContentLoaded", init);

  return { renderSvgMap, refreshMap, appendLog, loadTopology, loadArtifactLayers, refreshLayers, init };
})();
