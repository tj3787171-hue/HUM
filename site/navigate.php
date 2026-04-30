<?php
/**
 * navigate.php — NETNS-veth@peer collection & feedback loop page.
 *
 * Re-runs the Python collector on demand, then renders live data
 * and provides a feedback loop for continuous monitoring.
 *
 * Implements:  Info.css × APP.js × [+.py][+.xml] = <NAVIGATE.HTML>.PHP
 */

$refresh_requested = isset($_GET['refresh']);

if ($refresh_requested) {
    $collector = __DIR__ . '/data/collect_netns.py';
    if (file_exists($collector)) {
        exec('python3 ' . escapeshellarg($collector) . ' 2>&1', $output, $rc);
        $collect_status = $rc === 0 ? 'OK' : 'FAIL';
        $collect_output = implode("\n", $output);
    } else {
        $collect_status = 'MISSING';
        $collect_output = 'Collector script not found.';
    }
}

$json_path = __DIR__ . '/data/topology.json';
$xml_path  = __DIR__ . '/data/topology.xml';

$topo = file_exists($json_path) ? json_decode(file_get_contents($json_path), true) : null;
$xml_raw = file_exists($xml_path) ? htmlspecialchars(file_get_contents($xml_path)) : 'No XML data.';

$hostname  = $topo['hostname']  ?? 'hum-lab';
$timestamp = $topo['timestamp'] ?? 'unknown';
$ifaces    = $topo['interfaces'] ?? [];
$routes    = $topo['routes']     ?? [];
$veths     = $topo['veth_peers'] ?? [];
$ns        = $topo['namespaces'] ?? [];
$docker    = $topo['docker_networks'] ?? [];

function nav_badge(string $state): string {
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
  <title>HUM Lab — Navigate NETNS</title>
  <link rel="stylesheet" href="assets/info.css">
</head>
<body>

<header>
  <span class="logo">HUM.org</span>
  <nav>
    <a href="welcome.html">Welcome</a>
    <a href="index.php">Map</a>
    <a href="navigate.php" class="active">Navigate</a>
    <a href="recup.php">Recup</a>
    <a href="recover.php">Recover</a>
    <a href="palace.php">Palace</a>
    <a href="playbook.php">Playbook</a>
    <a href="layers.html">Layers</a>
    <a href="convo.php?source=list" target="_blank">API</a>
  </nav>
  <span style="margin-left:auto; font-size:.75rem; color:var(--text-dim);">
    <?= htmlspecialchars($hostname) ?> &middot; <?= htmlspecialchars($timestamp) ?>
  </span>
</header>

<div class="container">

  <h1 style="font-size:1.4rem; margin-bottom:.5rem; font-family:var(--mono);">
    NETNS-veth@peer Navigator
  </h1>
  <p style="color:var(--text-dim); font-size:.85rem; margin-bottom:1.5rem;">
    Collect, inspect, and feedback-loop network namespace and link-peer data.
  </p>

  <!-- Refresh controls -->
  <div class="panel" style="margin-bottom:1.5rem;">
    <h2>Collector Controls</h2>
    <a class="enter-btn" href="navigate.php?refresh=1" style="font-size:.85rem; padding:.5rem 1.5rem;">
      &#x21bb; Re-collect Now
    </a>
    <?php if ($refresh_requested): ?>
      <div style="margin-top:1rem; font-family:var(--mono); font-size:.8rem;">
        <span style="color:<?= $collect_status === 'OK' ? 'var(--green)' : 'var(--red)' ?>;">
          collect_netns.py &rarr; <?= $collect_status ?>
        </span>
        <pre style="margin-top:.5rem; color:var(--text-dim);"><?= htmlspecialchars($collect_output) ?></pre>
      </div>
    <?php endif; ?>
  </div>

  <!-- Live SVG map -->
  <section class="svg-map-wrap">
    <div id="svg-map"></div>
  </section>

  <div class="grid-2">
    <!-- Combined interface+veth detail -->
    <div class="panel">
      <h2>Interface &harr; veth Detail</h2>
      <table>
        <thead><tr><th>Name</th><th>Idx</th><th>State</th><th>Addr</th><th>Peer</th></tr></thead>
        <tbody>
        <?php foreach ($ifaces as $iface):
            $peer = '—';
            foreach ($veths as $v) {
                if ($v['ifname'] === $iface['name'] && isset($v['peer_ifindex'])) {
                    $peer = '@' . $v['peer_ifindex'];
                }
            }
            $idx = '—';
            foreach ($veths as $v) {
                if ($v['ifname'] === $iface['name']) {
                    $idx = $v['ifindex'];
                }
            }
        ?>
          <tr>
            <td><?= htmlspecialchars($iface['name']) ?></td>
            <td><?= $idx ?></td>
            <td><?= nav_badge($iface['state']) ?></td>
            <td><?= htmlspecialchars(implode(', ', $iface['addresses'] ?? [])) ?></td>
            <td><?= $peer ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>

    <!-- Route + NS summary -->
    <div class="panel">
      <h2>Routing &amp; Namespace Summary</h2>
      <table>
        <thead><tr><th>Dest</th><th>Via</th><th>Dev</th></tr></thead>
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
      <p style="margin-top:1rem; font-size:.85rem;">
        <strong style="color:var(--accent);">NETNS:</strong>
        <?= $ns ? htmlspecialchars(implode(', ', $ns)) : '<em style="color:var(--text-dim)">none active</em>' ?>
      </p>
      <?php if ($docker): ?>
        <p style="margin-top:.5rem; font-size:.85rem;">
          <strong style="color:var(--orange);">Docker nets:</strong>
          <?php foreach ($docker as $dn): ?>
            <?= htmlspecialchars($dn['Name'] ?? $dn['name'] ?? '') ?>
            (<?= htmlspecialchars($dn['Driver'] ?? $dn['driver'] ?? '') ?>)
          <?php endforeach; ?>
        </p>
      <?php endif; ?>
    </div>
  </div>

  <!-- XML source view -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>topology.xml Source</h2>
    <pre style="font-family:var(--mono); font-size:.78rem; color:var(--text-dim);
                max-height:300px; overflow:auto; white-space:pre-wrap;"><?= $xml_raw ?></pre>
  </div>

  <!-- Feedback log -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>Feedback Loop</h2>
    <div id="feedback-log" class="feedback-log"></div>
  </div>

</div>

<footer>HUM.org Lab &middot; NETNS-veth@peer feedback loop &middot; Info.css &times; APP.js &times; [+.py][+.xml]</footer>

<script src="assets/app.js"></script>
</body>
</html>
