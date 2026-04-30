<?php
/**
 * recover.php — Net Driver Recovery + Systemd Service Tree dashboard.
 *
 * Displays recovery script status, systemd unit tree from the Kali XFCE
 * service hierarchy, and provides check/recover controls.
 */

$data_dir   = __DIR__ . '/data';
$origin     = getenv('HUM_ORIGIN') ?: 'hum.org';

$run_check   = isset($_GET['check']);
$run_collect = isset($_GET['collect']);
$check_output = '';

if ($run_check) {
    $script = realpath(__DIR__ . '/../.devcontainer/net-driver-recover-auto.sh');
    if ($script && file_exists($script)) {
        exec('bash ' . escapeshellarg($script) . ' check 2>&1', $lines, $rc);
        $check_output = implode("\n", $lines);
    } else {
        $check_output = 'net-driver-recover-auto.sh not found.';
        $rc = 1;
    }
}

if ($run_collect) {
    $collector = "$data_dir/collect_systemd.py";
    if (file_exists($collector)) {
        exec('python3 ' . escapeshellarg($collector) . ' 2>&1', $clines, $crc);
        $collect_output = implode("\n", $clines);
    }
}

$systemd = file_exists("$data_dir/systemd_tree.json")
    ? json_decode(file_get_contents("$data_dir/systemd_tree.json"), true) : null;

$corps = file_exists("$data_dir/corps.json")
    ? json_decode(file_get_contents("$data_dir/corps.json"), true) : null;

$recovery_info = $corps['recovery'] ?? [];
$sd_summary = $systemd['summary'] ?? [];
$sd_units   = $systemd['units'] ?? [];
$sd_targets = $systemd['targets'] ?? [];
$sd_tree    = $systemd['tree_raw'] ?? '';
$sd_default = $systemd['default_target'] ?? 'unknown';

function unit_badge(string $state): string {
    return match ($state) {
        'active'   => '<span class="badge badge-up">active</span>',
        'inactive' => '<span class="badge badge-unknown">inactive</span>',
        'failed'   => '<span class="badge badge-down">failed</span>',
        default    => '<span class="badge badge-unknown">' . htmlspecialchars($state) . '</span>',
    };
}
?>
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HUM Lab — Recovery &amp; Systemd</title>
  <link rel="stylesheet" href="assets/info.css">
  <style>
    .tree-pre { font-family:var(--mono); font-size:.72rem; color:var(--text-dim);
                max-height:400px; overflow:auto; white-space:pre; line-height:1.4; }
    .tree-pre .active-line { color:var(--green); }
    .tree-pre .failed-line { color:var(--red); }
    .tree-pre .inactive-line { color:var(--text-dim); }
    .cap-grid { display:flex; flex-wrap:wrap; gap:.4rem; margin-top:.5rem; }
    .cap-tag { padding:.2rem .6rem; background:rgba(88,166,255,.1); border:1px solid var(--border);
               border-radius:var(--radius); font-family:var(--mono); font-size:.72rem; color:var(--accent); }
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
    <a href="recover.php" class="active">Recover</a>
    <a href="palace.php">Palace</a>
    <a href="playbook.php">Playbook</a>
    <a href="layers.html">Layers</a>
    <a href="convo.php?source=list" target="_blank">API</a>
  </nav>
  <span style="margin-left:auto; font-size:.75rem; color:var(--text-dim);">
    <?= htmlspecialchars($origin) ?> &middot; <?= htmlspecialchars($systemd['timestamp'] ?? '—') ?>
  </span>
</header>

<div class="container">

  <h1 style="font-size:1.4rem; margin-bottom:.3rem; font-family:var(--mono);">
    Net Driver Recovery &amp; Systemd Tree
  </h1>
  <p style="color:var(--text-dim); font-size:.85rem; margin-bottom:1.5rem;">
    Codex Continuity Node: <strong>auto-recover-netdriver</strong> &middot;
    RTNETLINK flush &middot; driver unbind/rebind &middot; loopback purge &middot; systemd service tree
  </p>

  <!-- Controls -->
  <div class="panel" style="margin-bottom:1.5rem;">
    <h2>Recovery Controls</h2>
    <div style="display:flex; gap:.75rem; flex-wrap:wrap;">
      <a class="enter-btn" href="recover.php?check=1" style="font-size:.85rem; padding:.5rem 1.5rem;">
        &#x1f50d; Run Check (diagnostics)
      </a>
      <a class="enter-btn" href="recover.php?collect=1" style="font-size:.85rem; padding:.5rem 1.5rem;">
        &#x21bb; Collect Systemd Tree
      </a>
    </div>
    <?php if ($run_check): ?>
      <div style="margin-top:1rem;">
        <span style="font-family:var(--mono); font-size:.8rem; color:<?= ($rc ?? 1) === 0 ? 'var(--green)' : 'var(--red)' ?>;">
          net-driver-recover-auto.sh check &rarr; <?= ($rc ?? 1) === 0 ? 'OK' : 'FAIL' ?>
        </span>
        <pre class="feedback-log" style="margin-top:.5rem; max-height:300px;"><?= htmlspecialchars($check_output) ?></pre>
      </div>
    <?php endif; ?>
    <?php if ($run_collect && isset($collect_output)): ?>
      <div style="margin-top:1rem; font-family:var(--mono); font-size:.8rem; color:var(--green);">
        collect_systemd.py &rarr; <?= ($crc ?? 1) === 0 ? 'OK' : 'FAIL' ?>
        <pre style="color:var(--text-dim); margin-top:.3rem;"><?= htmlspecialchars($collect_output) ?></pre>
      </div>
    <?php endif; ?>
  </div>

  <div class="grid-2">
    <!-- Recovery script info -->
    <div class="panel">
      <h2>Recovery Script</h2>
      <table>
        <tbody>
          <tr><td>Script</td><td style="color:var(--accent);"><?= htmlspecialchars($recovery_info['script'] ?? 'net-driver-recover-auto.sh') ?></td></tr>
          <tr><td>Codex Node</td><td><?= htmlspecialchars($recovery_info['codex_node'] ?? 'auto-recover-netdriver') ?></td></tr>
          <tr><td>Commands</td><td><?= htmlspecialchars(implode(', ', $recovery_info['commands'] ?? ['recover','check','update','install','help'])) ?></td></tr>
        </tbody>
      </table>
      <p style="font-size:.78rem; color:var(--text-dim); margin-top:.75rem;">Capabilities:</p>
      <div class="cap-grid">
        <?php foreach (($recovery_info['capabilities'] ?? [
            'interface-detect','rtnetlink-flush','driver-unbind-rebind',
            'modalias-probe','dhcp-lease','dns-reset','loopback-purge',
            'self-update','systemd-install','snapshot-state',
        ]) as $cap): ?>
          <span class="cap-tag"><?= htmlspecialchars($cap) ?></span>
        <?php endforeach; ?>
      </div>
    </div>

    <!-- Systemd summary -->
    <div class="panel">
      <h2>Systemd Summary</h2>
      <table>
        <tbody>
          <tr><td>Default Target</td><td style="color:var(--accent);"><?= htmlspecialchars($sd_default) ?></td></tr>
          <tr><td>Total Tracked</td><td><?= (int)($sd_summary['total_tracked'] ?? 0) ?></td></tr>
          <tr><td>Active</td><td><span class="badge badge-up"><?= (int)($sd_summary['active'] ?? 0) ?></span></td></tr>
          <tr><td>Inactive</td><td><span class="badge badge-unknown"><?= (int)($sd_summary['inactive'] ?? 0) ?></span></td></tr>
          <tr><td>Failed</td><td><span class="badge badge-down"><?= (int)($sd_summary['failed'] ?? 0) ?></span></td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Systemd targets -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>Systemd Targets</h2>
    <div style="display:flex; flex-wrap:wrap; gap:.5rem;">
      <?php foreach ($sd_targets as $t): ?>
        <span style="display:inline-flex; align-items:center; gap:.3rem; padding:.2rem .6rem;
                     background:var(--bg); border:1px solid var(--border); border-radius:var(--radius);
                     font-family:var(--mono); font-size:.72rem;">
          <?= unit_badge($t['active'] ?? 'unknown') ?>
          <?= htmlspecialchars($t['unit'] ?? '') ?>
        </span>
      <?php endforeach; ?>
    </div>
  </div>

  <!-- Systemd units table -->
  <div class="panel" style="margin-top:1.5rem;">
    <h2>Systemd Units <span style="color:var(--text-dim); font-size:.72rem;">(<?= count($sd_units) ?> tracked)</span></h2>
    <div style="max-height:350px; overflow-y:auto;">
      <table>
        <thead><tr><th>Unit</th><th>Active</th><th>Enabled</th></tr></thead>
        <tbody>
        <?php foreach ($sd_units as $u): ?>
          <tr>
            <td><?= htmlspecialchars($u['unit'] ?? '') ?></td>
            <td><?= unit_badge($u['active'] ?? 'unknown') ?></td>
            <td style="font-size:.78rem; color:var(--text-dim);"><?= htmlspecialchars($u['enabled'] ?? '') ?></td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  </div>

  <!-- Raw dependency tree -->
  <?php if ($sd_tree): ?>
  <div class="panel" style="margin-top:1.5rem;">
    <h2>default.target Dependency Tree</h2>
    <pre class="tree-pre"><?= htmlspecialchars($sd_tree) ?></pre>
  </div>
  <?php endif; ?>

</div>

<footer>
  HUM.org Lab &middot; Net Driver Recovery &middot; auto-recover-netdriver &middot;
  RTNETLINK flush &middot; driver unbind/rebind &middot; systemd tree
</footer>

<script src="assets/app.js"></script>
</body>
</html>
