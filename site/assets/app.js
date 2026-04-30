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

  async function loadJson(path) {
    const res = await fetch(path + "?t=" + Date.now());
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
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

  function formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    const units = ["KB", "MB", "GB", "TB"];
    let size = value / 1024;
    let idx = 0;
    while (size >= 1024 && idx < units.length - 1) {
      size /= 1024;
      idx += 1;
    }
    return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[idx]}`;
  }

  function renderLayerInventory(report) {
    const layerFilter = document.getElementById("layer-filter");
    const searchFilter = document.getElementById("search-filter");
    const summary = document.getElementById("layer-summary");
    const tbody = document.getElementById("layer-table-body");
    if (!layerFilter || !searchFilter || !summary || !tbody || !report) return;

    const layers = Object.keys(report.layers || {}).sort();
    if (layerFilter.options.length <= 1) {
      layers.forEach(layer => {
        const option = document.createElement("option");
        option.value = layer;
        option.textContent = `${layer} (${report.layers[layer].count})`;
        layerFilter.appendChild(option);
      });
    }

    summary.innerHTML = "";
    [
      ["Artifacts", report.summary?.artifact_count || 0],
      ["Total size", formatBytes(report.summary?.total_size_bytes || 0)],
      ["Archives", report.archives?.length || 0],
      ["Sampled", formatBytes(report.benchmark?.sampled_bytes || 0)],
    ].forEach(([label, value]) => {
      const card = document.createElement("div");
      card.className = "layer-stat";
      card.innerHTML = `<div class="value">${value}</div><div class="label">${label}</div>`;
      summary.appendChild(card);
    });

    const selected = layerFilter.value || "all";
    const query = (searchFilter.value || "").toLowerCase();
    const rows = (report.artifacts || []).filter(item => {
      const layerOk = selected === "all" || item.layer === selected;
      const haystack = `${item.path} ${item.kind} ${item.sha256_prefix}`.toLowerCase();
      return layerOk && (!query || haystack.includes(query));
    });

    tbody.innerHTML = "";
    rows.slice(0, 300).forEach(item => {
      const tr = document.createElement("tr");
      const read = item.benchmark ? `${item.benchmark.elapsed_ms}ms` : "n/a";
      tr.innerHTML = `
        <td>${item.layer}</td>
        <td><code>${item.path}</code><br><span style="color:var(--text-dim)">${item.kind}</span></td>
        <td>${formatBytes(item.size_bytes)}</td>
        <td><code>${item.sha256_prefix}</code></td>
        <td>${read}</td>
      `;
      tbody.appendChild(tr);
    });
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="5">No matching artifacts.</td></tr>';
    }
  }

  function renderCacheAssembly(report) {
    const formula = document.getElementById("cache-formula");
    const summary = document.getElementById("cache-summary");
    const tbody = document.getElementById("cache-table-body");
    if (!formula || !summary || !tbody || !report) return;

    formula.textContent = report.interval_plot?.formula || "No interval formula";
    summary.innerHTML = "";
    [
      ["Pieces", report.piece_count || 0],
      ["Roots", report.roots?.length || 0],
      ["Categories", Object.keys(report.categories || {}).length],
      ["Prefix", report.interval_plot?.prefix || "n/a"],
    ].forEach(([label, value]) => {
      const card = document.createElement("div");
      card.className = "layer-stat";
      card.innerHTML = `<div class="value">${value}</div><div class="label">${label}</div>`;
      summary.appendChild(card);
    });

    tbody.innerHTML = "";
    (report.interval_plot?.points || []).slice(0, 120).forEach(point => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code>${point.id}</code></td>
        <td>${point.path}</td>
        <td>${formatBytes(point.size_bytes)}</td>
        <td>${point.n}</td>
        <td>${point.y}</td>
      `;
      tbody.appendChild(tr);
    });
    if (!tbody.children.length) {
      tbody.innerHTML = '<tr><td colspan="5">No cache intervals found.</td></tr>';
    }
  }

  async function refreshLayers() {
    appendLog("layer-log", "Loading artifact layer JSON...");
    try {
      const report = await loadJson("data/artifact-layers.json");
      renderLayerInventory(report);
      appendLog("layer-log", `Loaded ${report.summary?.artifact_count || 0} artifacts.`);
    } catch (error) {
      appendLog("layer-log", `ERROR: ${error.message}`);
    }

    try {
      const cache = await loadJson("data/cache-assembly.json");
      renderCacheAssembly(cache);
      appendLog("layer-log", `Loaded ${cache.piece_count || 0} cache pieces.`);
    } catch (error) {
      appendLog("layer-log", `ERROR: ${error.message}`);
    }
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
    if (mapEl) {
      refreshMap("svg-map", "feedback-log");
      setInterval(() => refreshMap("svg-map", "feedback-log"), 15000);
    }

    const layerTable = document.getElementById("layer-table-body");
    if (layerTable) {
      refreshLayers();
      document.getElementById("refresh-layers")?.addEventListener("click", refreshLayers);
      document.getElementById("layer-filter")?.addEventListener("change", refreshLayers);
      document.getElementById("search-filter")?.addEventListener("input", refreshLayers);
    }
  }

  document.addEventListener("DOMContentLoaded", init);

  return { renderSvgMap, refreshMap, refreshLayers, appendLog, loadTopology, init };
})();
