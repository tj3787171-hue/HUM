<?php
/**
 * index.php — HUM.org Lab main navigation page.
 *
 * Wraps the SVG environment map, interface/route tables, and XML topology
 * into a single navigable document.  Reads data/topology.json + data/topology.xml
 * produced by collect_netns.py.
 */

$json_path = __DIR__ . '/data/topology.json';
$xml_path  = __DIR__ . '/data/topology.xml';

$topo = file_exists($json_path) ? json_decode(file_get_contents($json_path), true) : null;
$xml_raw = file_exists($xml_path) ? file_get_contents($xml_path) : '';

$hostname  = $topo['hostname']  ?? 'hum-lab';
$timestamp = $topo['timestamp'] ?? date('c');
$ifaces    = $topo['interfaces'] ?? [];
$routes    = $topo['routes']     ?? [];
$veths     = $topo['veth_peers'] ?? [];
$ns        = $topo['namespaces'] ?? [];
$docker    = $topo['docker_networks'] ?? [];

function badge(string $state): string {
    return match (strtoupper($state)) {
        'UP'   => '<span class="badge badge-up">UP</span>',
        'DOWN' => '<span class="badge badge-down">DOWN</span>',
        default => '<span class="badge badge-unknown">' . htmlspecialchars($state) . '</span>',
    };
}
?>
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HUM Lab — Environment Map</title>
  <link rel="stylesheet" href="assets/info.css">
</head>
<body>

<header>
  <span class="logo">HUM.org</span>
  <nav>
    <a href="welcome.html">Welcome</a>
    <a href="index.php" class="active">Map</a>
    <a href="navigate.php">Navigate</a>
    <a href="recup.php">Recup</a>
    <a href="data/topology.xml" target="_blank">XML</a>
  </nav>
  <span style="margin-left:auto; font-size:.75rem; color:var(--text-dim);">
    <?= htmlspecialchars($hostname) ?> &middot; <?= htmlspecialchars($timestamp) ?>
  </span>
</header>

<div class="container">

  <!-- SVG Environment Map -->
  <section class="svg-map-wrap">
    <div id="svg-map"></div>
  </section>

  <div class="grid-2">
    <!-- Interfaces panel -->
    <div class="panel">
      <h2>Interfaces</h2>
      <table>
        <thead><tr><th>Name</th><th>State</th><th>MAC</th><th>Addresses</th></tr></thead>
        <tbody>
        <?php foreach ($ifaces as $iface): ?>
          <tr>
            <td><?= htmlspecialchars($iface['name']) ?></td>
            <td><?= badge($iface['state']) ?></td>
            <td><?= htmlspecialchars($iface['mac']) ?></td>
            <td><?= htmlspecialchars(implode(', ', $iface['addresses'] ?? [])) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>

    <!-- Routes panel -->
    <div class="panel">
      <h2>Routes</h2>
      <table>
        <thead><tr><th>Destination</th><th>Gateway</th><th>Device</th></tr></thead>
        <tbody>
        <?php foreach ($routes as $r): ?>
          <tr>
            <td><?= htmlspecialchars($r['dst']) ?></td>
            <td><?= htmlspecialchars($r['gateway'] ?: '—') ?></td>
            <td><?= htmlspecialchars($r['dev']) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>

    <!-- veth Peers panel -->
    <div class="panel">
      <h2>veth / Link Peers</h2>
      <?php if (empty($veths)): ?>
        <p style="color:var(--text-dim); font-size:.85rem;">No veth peers detected.</p>
      <?php else: ?>
        <table>
          <thead><tr><th>Interface</th><th>Index</th><th>State</th><th>Peer</th></tr></thead>
          <tbody>
          <?php foreach ($veths as $v): ?>
            <tr>
              <td><?= htmlspecialchars($v['ifname']) ?></td>
              <td><?= (int)$v['ifindex'] ?></td>
              <td><?= badge($v['operstate']) ?></td>
              <td><?= isset($v['peer_ifindex']) ? '@' . (int)$v['peer_ifindex'] : '—' ?></td>
            </tr>
          <?php endforeach; ?>
          </tbody>
        </table>
      <?php endif; ?>
    </div>

    <!-- Namespaces + Docker panel -->
    <div class="panel">
      <h2>Namespaces &amp; Docker Networks</h2>
      <p style="font-size:.85rem; margin-bottom:.5rem;">
        <strong style="color:var(--accent);">NETNS:</strong>
        <?= $ns ? htmlspecialchars(implode(', ', $ns)) : '<em style="color:var(--text-dim)">none</em>' ?>
      </p>
      <?php if ($docker): ?>
        <table>
          <thead><tr><th>Network</th><th>Driver</th><th>Scope</th></tr></thead>
          <tbody>
          <?php foreach ($docker as $dn): ?>
            <tr>
              <td><?= htmlspecialchars($dn['Name'] ?? $dn['name'] ?? '') ?></td>
              <td><?= htmlspecialchars($dn['Driver'] ?? $dn['driver'] ?? '') ?></td>
              <td><?= htmlspecialchars($dn['Scope'] ?? $dn['scope'] ?? '') ?></td>
            </tr>
          <?php endforeach; ?>
          </tbody>
        </table>
      <?php else: ?>
        <p style="color:var(--text-dim); font-size:.85rem;">No Docker networks detected.</p>
      <?php endif; ?>
    </div>
  </div>

  <!-- Feedback log -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>Feedback Log</h2>
    <div id="feedback-log" class="feedback-log"></div>
  </div>

</div>

<footer>HUM.org Lab &middot; LAN-ready devcontainer environment &middot; NETNS-veth@peer collector</footer>

<script src="assets/app.js"></script>
</body>
</html>
