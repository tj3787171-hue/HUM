<?php
/**
 * palace.php — Palace of Web — the FINAL-PRODUCT display.
 *
 * Renders the House of Corps collective data after the Name Factory
 * has processed all sources through the gram & comb hierarchy.
 * This is the "sources.list/FINAL-PRODUCT/gram&comb Palace of Web".
 */

$data_dir   = __DIR__ . '/data';
$fp_dir     = "$data_dir/FINAL-PRODUCT";
$recup_home = getenv('RECUP_HOME') ?: '/home/troy';
$origin     = getenv('HUM_ORIGIN') ?: 'hum.org';

$rebuild_requested = isset($_GET['rebuild']);
$rebuild_output = '';
if ($rebuild_requested) {
    $factory = "$data_dir/name_factory.py";
    $env = "HUM_ORIGIN=" . escapeshellarg($origin) . " RECUP_HOME=" . escapeshellarg($recup_home);
    exec("$env python3 " . escapeshellarg($factory) . " 2>&1", $lines, $rc);
    $rebuild_output = implode("\n", $lines);
}

$corps   = file_exists("$data_dir/corps.json")   ? json_decode(file_get_contents("$data_dir/corps.json"), true)   : null;
$gram    = file_exists("$fp_dir/gram.json")       ? json_decode(file_get_contents("$fp_dir/gram.json"), true)     : null;
$comb    = file_exists("$fp_dir/comb.json")       ? json_decode(file_get_contents("$fp_dir/comb.json"), true)     : null;
$palace  = file_exists("$fp_dir/palace.json")     ? json_decode(file_get_contents("$fp_dir/palace.json"), true)   : null;
$sources = file_exists("$data_dir/sources.list")  ? file_get_contents("$data_dir/sources.list")                   : '';

$hoc     = $corps['house_of_corps'] ?? [];
$totals  = $corps['gram_comb_totals'] ?? [];
$wc      = $corps['wanted_comb']['entries'] ?? [];
$recup_m = $corps['recup']['manifest'] ?? [];
$topo_if = $corps['topology']['interfaces'] ?? [];

function palace_badge(string $cls): string {
    return match ($cls) {
        'alpha'  => '<span class="badge badge-up">ALPHA</span>',
        'beta'   => '<span class="badge" style="background:rgba(88,166,255,.15);color:var(--accent);">BETA</span>',
        'gamma'  => '<span class="badge badge-unknown">GAMMA</span>',
        'delta'  => '<span class="badge badge-down">DELTA</span>',
        default  => '<span class="badge badge-unknown">' . htmlspecialchars(strtoupper($cls)) . '</span>',
    };
}
?>
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HUM Lab — Palace of Web</title>
  <link rel="stylesheet" href="assets/info.css">
  <style>
    .score-bar { display:inline-block; height:8px; border-radius:4px; margin-left:.5rem; vertical-align:middle; }
    .stat-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:.75rem; margin-bottom:1rem; }
    .stat-card { background:var(--bg); border:1px solid var(--border); border-radius:var(--radius); padding:.75rem; text-align:center; }
    .stat-card .val { font-size:1.8rem; font-weight:700; font-family:var(--mono); color:var(--accent); }
    .stat-card .lbl { font-size:.72rem; color:var(--text-dim); text-transform:uppercase; letter-spacing:.05em; }
  </style>
</head>
<body>

<header>
  <span class="logo">HUM.org</span>
  <nav>
    <a href="welcome.html">Welcome</a>
    <a href="index.php">Map</a>
    <a href="navigate.php">Navigate</a>
    <a href="recup.php">Recup</a>
    <a href="palace.php" class="active">Palace</a>
    <a href="convo.php?source=list" target="_blank">API</a>
  </nav>
  <span style="margin-left:auto; font-size:.75rem; color:var(--text-dim);">
    <?= htmlspecialchars($origin) ?> &middot; <?= htmlspecialchars($hoc['timestamp'] ?? '—') ?>
  </span>
</header>

<div class="container">

  <h1 style="font-size:1.6rem; margin-bottom:.3rem; font-family:var(--mono);">
    Palace of Web
  </h1>
  <p style="color:var(--text-dim); font-size:.85rem; margin-bottom:1.5rem;">
    House of Corps &mdash; FINAL-PRODUCT after the Name Factory &middot;
    gram &amp; comb hierarchy &middot; <?= htmlspecialchars($hoc['name_factory'] ?? 'Name Factory') ?>
  </p>

  <!-- Rebuild controls -->
  <div class="panel" style="margin-bottom:1.5rem;">
    <h2>Factory Controls</h2>
    <a class="enter-btn" href="palace.php?rebuild=1"
       style="font-size:.85rem; padding:.5rem 1.5rem;">
      &#x2699; Rebuild House of Corps
    </a>
    <?php if ($rebuild_requested): ?>
      <div style="margin-top:1rem; font-family:var(--mono); font-size:.8rem;">
        <span style="color:<?= ($rc ?? 1) === 0 ? 'var(--green)' : 'var(--red)' ?>;">
          name_factory &rarr; <?= ($rc ?? 1) === 0 ? 'OK' : 'FAIL' ?>
        </span>
        <pre style="margin-top:.5rem; color:var(--text-dim); max-height:140px; overflow-y:auto;"><?= htmlspecialchars($rebuild_output) ?></pre>
      </div>
    <?php endif; ?>
  </div>

  <!-- Stats overview -->
  <div class="panel" style="margin-bottom:1.5rem;">
    <h2>Corps Totals</h2>
    <div class="stat-grid">
      <div class="stat-card">
        <div class="val"><?= (int)($totals['total_data_points'] ?? 0) ?></div>
        <div class="lbl">Data Points</div>
      </div>
      <div class="stat-card">
        <div class="val"><?= (int)($totals['topology_interfaces'] ?? 0) ?></div>
        <div class="lbl">Interfaces</div>
      </div>
      <div class="stat-card">
        <div class="val"><?= (int)($totals['topology_routes'] ?? 0) ?></div>
        <div class="lbl">Routes</div>
      </div>
      <div class="stat-card">
        <div class="val"><?= (int)($totals['recup_files'] ?? 0) ?></div>
        <div class="lbl">Recup Files</div>
      </div>
      <div class="stat-card">
        <div class="val"><?= (int)($totals['wanted_comb_entries'] ?? 0) ?></div>
        <div class="lbl">Comb Entries</div>
      </div>
      <div class="stat-card">
        <div class="val"><?= (int)($totals['templates_categories'] ?? 0) + (int)($totals['photos_categories'] ?? 0) ?></div>
        <div class="lbl">Categories</div>
      </div>
    </div>
  </div>

  <div class="grid-2">
    <!-- Wanted Comb scored entries -->
    <div class="panel">
      <h2>Wanted Comb &mdash; Scored Hierarchy</h2>
      <table>
        <thead><tr><th>Tag</th><th>Band</th><th>Type</th><th>Score</th><th>R / V / M</th></tr></thead>
        <tbody>
        <?php foreach ($wc as $e): ?>
          <tr>
            <td style="font-size:.72rem;"><?= htmlspecialchars($e['factory_tag'] ?? '') ?></td>
            <td><?= palace_badge($e['band'] ?? '') ?></td>
            <td><?= htmlspecialchars($e['type'] ?? '') ?></td>
            <td>
              <strong><?= number_format($e['comb_score'] ?? 0, 1) ?></strong>
              <span class="score-bar" style="width:<?= ($e['comb_score'] ?? 0) * 0.6 ?>px; background:var(--green);"></span>
            </td>
            <td style="font-size:.72rem; color:var(--text-dim);">
              <?= number_format($e['reachability'] ?? 0, 0) ?> /
              <?= number_format($e['velocity'] ?? 0, 0) ?> /
              <?= number_format($e['mission'] ?? 0, 0) ?>
            </td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>

    <!-- Network interfaces from Corps -->
    <div class="panel">
      <h2>Topology Interfaces (Named)</h2>
      <table>
        <thead><tr><th>Factory Tag</th><th>Name</th><th>State</th><th>Addresses</th></tr></thead>
        <tbody>
        <?php foreach ($topo_if as $iface): ?>
          <tr>
            <td style="font-size:.72rem;"><?= htmlspecialchars($iface['factory_tag'] ?? '') ?></td>
            <td><?= htmlspecialchars($iface['name'] ?? '') ?></td>
            <td>
              <?php $s = strtoupper($iface['state'] ?? ''); ?>
              <span class="badge <?= $s === 'UP' ? 'badge-up' : ($s === 'DOWN' ? 'badge-down' : 'badge-unknown') ?>">
                <?= $s ?>
              </span>
            </td>
            <td style="font-size:.78rem;"><?= htmlspecialchars(implode(', ', $iface['addresses'] ?? [])) ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Recup manifest with factory tags -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>Recup Manifest (Factory Tagged)</h2>
    <div style="max-height:250px; overflow-y:auto;">
      <table>
        <thead><tr><th>Factory Tag</th><th>File</th><th>Source</th><th>Class</th></tr></thead>
        <tbody>
        <?php foreach ($recup_m as $r): ?>
          <tr>
            <td style="font-size:.72rem;"><?= htmlspecialchars($r['factory_tag'] ?? '') ?></td>
            <td><?= htmlspecialchars($r['file'] ?? '') ?></td>
            <td><?= htmlspecialchars($r['source'] ?? '') ?></td>
            <td>
              <span class="badge badge-up"><?= htmlspecialchars(strtoupper($r['class'] ?? '')) ?></span>
            </td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Sources list -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>sources.list</h2>
    <pre style="font-family:var(--mono); font-size:.78rem; color:var(--text-dim);
                max-height:220px; overflow:auto; white-space:pre-wrap;"><?= htmlspecialchars($sources) ?></pre>
  </div>

  <!-- API links -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>JSON Convo API</h2>
    <p style="font-size:.85rem; color:var(--text-dim); margin-bottom:.75rem;">
      Talk data through JSON to all sources:
    </p>
    <div style="display:flex; flex-wrap:wrap; gap:.5rem;">
      <?php foreach (['corps','gram','comb','palace','topology','manifest','summary','sources','list'] as $s): ?>
        <a href="convo.php?source=<?= $s ?>" target="_blank"
           class="enter-btn" style="font-size:.72rem; padding:.3rem .8rem;">
          <?= $s ?>
        </a>
      <?php endforeach; ?>
      <a href="convo.php?rebuild=1" target="_blank"
         class="enter-btn" style="font-size:.72rem; padding:.3rem .8rem; border-color:var(--green); color:var(--green);">
        rebuild
      </a>
    </div>
  </div>

</div>

<footer>
  HUM.org Lab &middot; Palace of Web &middot; House of Corps &middot;
  FINAL-PRODUCT/gram &amp; comb &middot; <?= htmlspecialchars($hoc['name_factory'] ?? 'Name Factory') ?>
</footer>

<script src="assets/app.js"></script>
</body>
</html>
