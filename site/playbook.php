<?php
/**
 * playbook.php — Playbook: Banner + Runningboard checksum flow chart.
 *
 * Systems-of-table setup that flow-charts CHECKSUMS from source through
 * the pipeline to their destination. The banner shows pipeline status
 * and the runningboard tracks each file's checksum provenance.
 */

$data_dir   = __DIR__ . '/data';
$fp_dir     = "$data_dir/FINAL-PRODUCT";
$origin     = getenv('HUM_ORIGIN') ?: 'hum.org';

$refresh = isset($_GET['refresh']);

function checksum_entry(string $label, string $path, string $stage): array {
    $exists = file_exists($path);
    return [
        'label'    => $label,
        'path'     => $path,
        'stage'    => $stage,
        'exists'   => $exists,
        'size'     => $exists ? filesize($path) : 0,
        'sha256'   => $exists ? hash_file('sha256', $path) : null,
        'modified' => $exists ? date('c', filemtime($path)) : null,
    ];
}

$rebuild_output = '';
$rebuild_rc = -1;
if ($refresh) {
    $factory = "$data_dir/name_factory.py";
    exec("python3 " . escapeshellarg($factory) . " 2>&1", $lines, $rebuild_rc);
    $rebuild_output = implode("\n", $lines);
}

$sources = [
    checksum_entry('topology.json',     "$data_dir/topology.json",     'source'),
    checksum_entry('topology.xml',      "$data_dir/topology.xml",      'source'),
    checksum_entry('collect_netns.py',   "$data_dir/collect_netns.py", 'source'),
    checksum_entry('name_factory.py',    "$data_dir/name_factory.py",  'source'),
];
$pipeline = [
    checksum_entry('corps.json',    "$data_dir/corps.json",    'pipeline'),
    checksum_entry('sources.list',  "$data_dir/sources.list",  'pipeline'),
];
$destinations = [
    checksum_entry('corps_full.json', "$fp_dir/corps_full.json", 'destination'),
    checksum_entry('gram.json',       "$fp_dir/gram.json",       'destination'),
    checksum_entry('comb.json',       "$fp_dir/comb.json",       'destination'),
    checksum_entry('palace.json',     "$fp_dir/palace.json",     'destination'),
];
$infra = [
    checksum_entry('app.js',   __DIR__ . '/assets/app.js',   'infra'),
    checksum_entry('info.css', __DIR__ . '/assets/info.css',  'infra'),
];

$all_entries = array_merge($sources, $pipeline, $destinations, $infra);
$aggregate_checksum = hash('sha256', implode('', array_column($destinations, 'sha256')));

$source_ok  = count(array_filter($sources, fn($e) => $e['exists']));
$pipe_ok    = count(array_filter($pipeline, fn($e) => $e['exists']));
$dest_ok    = count(array_filter($destinations, fn($e) => $e['exists']));

function stage_badge(string $stage): string {
    $cls = match ($stage) {
        'source'      => 'badge-src',
        'pipeline'    => 'badge-pipe',
        'destination' => 'badge-dest',
        'infra'       => 'badge-unknown',
        default       => 'badge-unknown',
    };
    return '<span class="badge ' . $cls . '">' . strtoupper($stage) . '</span>';
}
?>
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HUM Lab — Playbook</title>
  <link rel="stylesheet" href="assets/info.css">
  <style>
    .banner {
      background: linear-gradient(135deg, var(--surface) 0%, #1a2332 100%);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.5rem;
      margin-bottom: 1.5rem;
      position: relative;
      overflow: hidden;
    }
    .banner::before {
      content: '';
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), var(--orange), var(--green));
    }
    .banner h1 {
      font-size: 1.6rem;
      font-family: var(--mono);
      margin-bottom: .3rem;
    }
    .banner .subtitle {
      color: var(--text-dim);
      font-size: .85rem;
      margin-bottom: 1rem;
    }
    .banner-stats {
      display: flex;
      gap: 2rem;
      flex-wrap: wrap;
      align-items: center;
    }
    .banner-stat {
      text-align: center;
    }
    .banner-stat .val {
      font-size: 1.8rem;
      font-weight: 700;
      font-family: var(--mono);
    }
    .banner-stat .lbl {
      font-size: .7rem;
      color: var(--text-dim);
      text-transform: uppercase;
      letter-spacing: .05em;
    }
    .flow-arrow {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: .5rem;
      margin: 1rem 0;
      color: var(--text-dim);
      font-family: var(--mono);
      font-size: .8rem;
    }
    .flow-arrow .arrow {
      flex: 1;
      height: 2px;
      background: linear-gradient(90deg, var(--accent), var(--orange), var(--green));
      position: relative;
    }
    .flow-arrow .arrow::after {
      content: '▸';
      position: absolute;
      right: -6px;
      top: -8px;
      color: var(--green);
      font-size: .9rem;
    }
    .runningboard {
      border: 1px solid var(--border);
      border-radius: var(--radius);
      overflow: hidden;
      margin-bottom: 1.5rem;
    }
    .runningboard-header {
      background: var(--surface);
      padding: .75rem 1.25rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: center;
      gap: .75rem;
    }
    .runningboard-header h2 {
      font-size: .95rem;
      font-family: var(--mono);
      margin: 0;
      border: none;
      padding: 0;
    }
    .runningboard table { margin: 0; }
    .runningboard td.cksum {
      font-size: .68rem;
      word-break: break-all;
      max-width: 220px;
      color: var(--accent-hi);
    }
    .badge-src  { background: rgba(88,166,255,.15); color: var(--accent); }
    .badge-pipe { background: rgba(210,153,34,.15); color: var(--orange); }
    .badge-dest { background: rgba(63,185,80,.15); color: var(--green); }
    .aggregate {
      font-family: var(--mono);
      font-size: .75rem;
      padding: .5rem 1rem;
      background: rgba(63,185,80,.08);
      border: 1px solid rgba(63,185,80,.25);
      border-radius: var(--radius);
      word-break: break-all;
      color: var(--green);
    }
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
    <a href="recover.php">Recover</a>
    <a href="palace.php">Palace</a>
    <a href="playbook.php" class="active">Playbook</a>
    <a href="convo.php?source=list" target="_blank">API</a>
  </nav>
  <span style="margin-left:auto; font-size:.75rem; color:var(--text-dim);">
    <?= htmlspecialchars($origin) ?> &middot; <?= date('H:i:s') ?>
  </span>
</header>

<div class="container">

  <!-- BANNER -->
  <div class="banner">
    <h1>Playbook</h1>
    <p class="subtitle">
      Banner + Runningboard &mdash; checksum flow chart from source &rarr; pipeline &rarr; destination
    </p>
    <div class="banner-stats">
      <div class="banner-stat">
        <div class="val" style="color:var(--accent);"><?= $source_ok ?>/<?= count($sources) ?></div>
        <div class="lbl">Sources</div>
      </div>
      <div class="banner-stat" style="font-size:1.2rem; color:var(--text-dim);">&#x2192;</div>
      <div class="banner-stat">
        <div class="val" style="color:var(--orange);"><?= $pipe_ok ?>/<?= count($pipeline) ?></div>
        <div class="lbl">Pipeline</div>
      </div>
      <div class="banner-stat" style="font-size:1.2rem; color:var(--text-dim);">&#x2192;</div>
      <div class="banner-stat">
        <div class="val" style="color:var(--green);"><?= $dest_ok ?>/<?= count($destinations) ?></div>
        <div class="lbl">Destination</div>
      </div>
      <div style="margin-left:auto;">
        <a class="enter-btn" href="playbook.php?refresh=1" style="font-size:.8rem; padding:.4rem 1.2rem;">
          &#x21bb; Refresh Pipeline
        </a>
      </div>
    </div>
    <?php if ($refresh): ?>
      <div style="margin-top:1rem; font-family:var(--mono); font-size:.8rem;">
        <span style="color:<?= $rebuild_rc === 0 ? 'var(--green)' : 'var(--red)' ?>;">
          name_factory &rarr; <?= $rebuild_rc === 0 ? 'OK' : 'FAIL' ?>
        </span>
        <pre style="margin-top:.5rem; color:var(--text-dim); max-height:100px; overflow-y:auto;"><?= htmlspecialchars($rebuild_output) ?></pre>
      </div>
    <?php endif; ?>
  </div>

  <!-- FLOW ARROW -->
  <div class="flow-arrow">
    <span style="color:var(--accent);">SOURCE</span>
    <span class="arrow"></span>
    <span style="color:var(--orange);">PIPELINE</span>
    <span class="arrow"></span>
    <span style="color:var(--green);">FINAL-PRODUCT</span>
  </div>

  <!-- RUNNINGBOARD: Sources -->
  <div class="runningboard">
    <div class="runningboard-header">
      <?= stage_badge('source') ?>
      <h2>Source Files</h2>
      <span style="margin-left:auto; font-size:.72rem; color:var(--text-dim);"><?= $source_ok ?> ready</span>
    </div>
    <table>
      <thead><tr><th>File</th><th>SHA-256</th><th>Size</th><th>Modified</th><th>Status</th></tr></thead>
      <tbody>
      <?php foreach ($sources as $e): ?>
        <tr>
          <td><?= htmlspecialchars($e['label']) ?></td>
          <td class="cksum"><?= $e['sha256'] ? substr($e['sha256'], 0, 16) . '…' : '—' ?></td>
          <td><?= $e['exists'] ? number_format($e['size']) . 'B' : '—' ?></td>
          <td style="font-size:.72rem;"><?= $e['modified'] ? htmlspecialchars(substr($e['modified'], 0, 19)) : '—' ?></td>
          <td>
            <?php if ($e['exists']): ?>
              <span class="badge badge-up">OK</span>
            <?php else: ?>
              <span class="badge badge-down">MISSING</span>
            <?php endif; ?>
          </td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
  </div>

  <!-- RUNNINGBOARD: Pipeline -->
  <div class="runningboard">
    <div class="runningboard-header">
      <?= stage_badge('pipeline') ?>
      <h2>Pipeline Intermediate</h2>
      <span style="margin-left:auto; font-size:.72rem; color:var(--text-dim);"><?= $pipe_ok ?> ready</span>
    </div>
    <table>
      <thead><tr><th>File</th><th>SHA-256</th><th>Size</th><th>Modified</th><th>Status</th></tr></thead>
      <tbody>
      <?php foreach ($pipeline as $e): ?>
        <tr>
          <td><?= htmlspecialchars($e['label']) ?></td>
          <td class="cksum"><?= $e['sha256'] ? substr($e['sha256'], 0, 16) . '…' : '—' ?></td>
          <td><?= $e['exists'] ? number_format($e['size']) . 'B' : '—' ?></td>
          <td style="font-size:.72rem;"><?= $e['modified'] ? htmlspecialchars(substr($e['modified'], 0, 19)) : '—' ?></td>
          <td>
            <?php if ($e['exists']): ?>
              <span class="badge badge-up">OK</span>
            <?php else: ?>
              <span class="badge badge-down">MISSING</span>
            <?php endif; ?>
          </td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
  </div>

  <!-- RUNNINGBOARD: Destinations -->
  <div class="runningboard">
    <div class="runningboard-header">
      <?= stage_badge('destination') ?>
      <h2>FINAL-PRODUCT Destination</h2>
      <span style="margin-left:auto; font-size:.72rem; color:var(--text-dim);"><?= $dest_ok ?> ready</span>
    </div>
    <table>
      <thead><tr><th>File</th><th>SHA-256</th><th>Size</th><th>Modified</th><th>Status</th></tr></thead>
      <tbody>
      <?php foreach ($destinations as $e): ?>
        <tr>
          <td><?= htmlspecialchars($e['label']) ?></td>
          <td class="cksum"><?= $e['sha256'] ? substr($e['sha256'], 0, 16) . '…' : '—' ?></td>
          <td><?= $e['exists'] ? number_format($e['size']) . 'B' : '—' ?></td>
          <td style="font-size:.72rem;"><?= $e['modified'] ? htmlspecialchars(substr($e['modified'], 0, 19)) : '—' ?></td>
          <td>
            <?php if ($e['exists']): ?>
              <span class="badge badge-up">OK</span>
            <?php else: ?>
              <span class="badge badge-down">MISSING</span>
            <?php endif; ?>
          </td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
  </div>

  <!-- Aggregate checksum -->
  <div class="panel" style="margin-bottom:1.5rem;">
    <h2>Aggregate FINAL-PRODUCT Checksum</h2>
    <div class="aggregate">
      SHA-256: <?= htmlspecialchars($aggregate_checksum) ?>
    </div>
    <p style="font-size:.75rem; color:var(--text-dim); margin-top:.5rem;">
      Combined hash of all destination file checksums. Changes when any FINAL-PRODUCT file is modified.
    </p>
  </div>

  <!-- Infrastructure -->
  <div class="panel">
    <h2>Infrastructure Checksums</h2>
    <table>
      <thead><tr><th>Asset</th><th>SHA-256</th><th>Size</th></tr></thead>
      <tbody>
      <?php foreach ($infra as $e): ?>
        <tr>
          <td><?= htmlspecialchars($e['label']) ?></td>
          <td class="cksum" style="color:var(--text-dim);"><?= $e['sha256'] ? substr($e['sha256'], 0, 32) . '…' : '—' ?></td>
          <td><?= $e['exists'] ? number_format($e['size']) . 'B' : '—' ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
  </div>

  <!-- Full checksum manifest (expandable) -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>Full Checksum Manifest</h2>
    <pre style="font-family:var(--mono); font-size:.72rem; color:var(--text-dim);
                max-height:280px; overflow:auto; white-space:pre-wrap;"><?php
foreach ($all_entries as $e) {
    $ck = $e['sha256'] ?? str_repeat('0', 64);
    $st = $e['exists'] ? 'OK' : 'MISSING';
    printf("%-8s  %-20s  %s  %s\n", strtoupper($e['stage']), $e['label'], $ck, $st);
}
?></pre>
  </div>

</div>

<footer>
  HUM.org Lab &middot; Playbook &middot; Banner + Runningboard &middot;
  Checksum flow: source &rarr; pipeline &rarr; FINAL-PRODUCT
</footer>

<script src="assets/app.js"></script>
</body>
</html>
