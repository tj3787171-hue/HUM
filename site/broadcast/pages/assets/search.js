(function () {
  "use strict";

  var input = document.getElementById("q");
  var hits = document.getElementById("hits");
  var trends = document.getElementById("trends");
  if (!input || !hits) {
    return;
  }

  function esc(value) {
    return String(value || "").replace(/[&<>"']/g, function (ch) {
      return ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;" })[ch];
    });
  }

  function render(rows) {
    hits.innerHTML = "";
    rows.forEach(function (row) {
      var tr = document.createElement("tr");
      tr.innerHTML = "<td>" + esc(row.title) + "</td><td>" + esc(row.kind) + "</td><td><a href=\"" + esc(row.path) + "\">" + esc(row.path) + "</a></td>";
      hits.appendChild(tr);
    });
    if (!rows.length) {
      hits.innerHTML = "<tr><td colspan=\"3\">No housing hits.</td></tr>";
    }
  }

  function query(value) {
    fetch("/search.json?q=" + encodeURIComponent(value))
      .then(function (res) { return res.json(); })
      .then(function (payload) { render(payload.hits || []); });
  }

  fetch("/index.json")
    .then(function (res) { return res.json(); })
    .then(function (index) {
      if (trends && index.trends) {
        trends.textContent = "Concert: " + (index.concert || []).join(" · ") +
          " — warming: " + index.trends.filter(function (row) { return row.connotation === "warming"; })
            .map(function (row) { return row.title; }).join(", ");
      }
      render(index.entries || []);
    });

  input.addEventListener("input", function () {
    query(input.value);
  });
})();
