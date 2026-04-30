<?php
/**
 * recup.php — Recup data browser for /home/troy TEMPLATES and PHOTOS.
 *
 * Displays the recup import summary, manifest of classified files,
 * and directory listings for TEMPLATES and PHOTOS workspaces.
 */

$recup_home = getenv('RECUP_HOME') ?: '/home/troy';
$summary_path  = "$recup_home/recup_summary.json";
$manifest_path = "$recup_home/recup_manifest.json";

$summary  = file_exists($summary_path)  ? json_decode(file_get_contents($summary_path), true)  : null;
$manifest = file_exists($manifest_path) ? json_decode(file_get_contents($manifest_path), true) : [];

$origin    = $summary['origin'] ?? (getenv('HUM_ORIGIN') ?: 'hum.org');
$timestamp = $summary['timestamp'] ?? '—';
$total     = $summary['total_scanned'] ?? 0;
$photos_n  = $summary['photos_imported'] ?? 0;
$templ_n   = $summary['templates_imported'] ?? 0;
$skipped   = $summary['skipped'] ?? 0;

$refresh_requested = isset($_GET['refresh']);
$refresh_output = '';
if ($refresh_requested) {
    $script = realpath(__DIR__ . '/../.devcontainer/recup-setup.sh');
    if ($script && file_exists($script)) {
        $env = "HUM_ORIGIN=" . escapeshellarg($origin) . " RECUP_HOME=" . escapeshellarg($recup_home);
        exec("$env bash " . escapeshellarg($script) . " 2>&1", $lines, $rc);
        $refresh_output = implode("\n", $lines);
        $summary  = file_exists($summary_path)  ? json_decode(file_get_contents($summary_path), true)  : $summary;
        $manifest = file_exists($manifest_path) ? json_decode(file_get_contents($manifest_path), true) : $manifest;
        $total    = $summary['total_scanned'] ?? $total;
        $photos_n = $summary['photos_imported'] ?? $photos_n;
        $templ_n  = $summary['templates_imported'] ?? $templ_n;
        $skipped  = $summary['skipped'] ?? $skipped;
    } else {
        $refresh_output = "recup-setup.sh not found at expected path.";
        $rc = 1;
    }
}

function scan_dir(string $dir): array {
    if (!is_dir($dir)) return [];
    $items = [];
    foreach (new DirectoryIterator($dir) as $fi) {
        if ($fi->isDot()) continue;
        if ($fi->isDir()) {
            $sub = [];
            foreach (new DirectoryIterator($fi->getPathname()) as $sf) {
                if ($sf->isDot() || !$sf->isFile()) continue;
                $sub[] = $sf->getFilename();
            }
            sort($sub);
            $items[] = ['name' => $fi->getFilename(), 'type' => 'dir', 'files' => $sub];
        } else {
            $items[] = ['name' => $fi->getFilename(), 'type' => 'file'];
        }
    }
    usort($items, fn($a, $b) => strcmp($a['name'], $b['name']));
    return $items;
}

$templates_tree = scan_dir("$recup_home/TEMPLATES");
$photos_tree    = scan_dir("$recup_home/PHOTOS");
?>
<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>HUM Lab — Recup Data Browser</title>
  <link rel="stylesheet" href="assets/info.css">
</head>
<body>

<header>
  <span class="logo">HUM.org</span>
  <nav>
    <a href="welcome.html">Welcome</a>
    <a href="index.php">Map</a>
    <a href="navigate.php">Navigate</a>
    <a href="recup.php" class="active">Recup</a>
    <a href="recover.php">Recover</a>
    <a href="palace.php">Palace</a>
    <a href="playbook.php">Playbook</a>
    <a href="convo.php?source=list" target="_blank">API</a>
  </nav>
  <span style="margin-left:auto; font-size:.75rem; color:var(--text-dim);">
    origin: <?= htmlspecialchars($origin) ?> &middot; <?= htmlspecialchars($timestamp) ?>
  </span>
</header>

<div class="container">

  <h1 style="font-size:1.4rem; margin-bottom:.3rem; font-family:var(--mono);">
    Recup Data Browser
  </h1>
  <p style="color:var(--text-dim); font-size:.85rem; margin-bottom:1.5rem;">
    TestDisk / PhotoRec recovered files organized into
    <code>/home/troy/TEMPLATES</code> and <code>/home/troy/PHOTOS</code>.
  </p>

  <!-- Controls -->
  <div class="panel" style="margin-bottom:1.5rem;">
    <h2>Import Controls</h2>
    <a class="enter-btn" href="recup.php?refresh=1"
       style="font-size:.85rem; padding:.5rem 1.5rem;">
      &#x21bb; Re-run Recup Import
    </a>
    <?php if ($refresh_requested): ?>
      <div style="margin-top:1rem; font-family:var(--mono); font-size:.8rem;">
        <span style="color:<?= ($rc ?? 1) === 0 ? 'var(--green)' : 'var(--red)' ?>;">
          recup-setup &rarr; <?= ($rc ?? 1) === 0 ? 'OK' : 'FAIL' ?>
        </span>
        <pre style="margin-top:.5rem; color:var(--text-dim); max-height:180px; overflow-y:auto;">
<?= htmlspecialchars($refresh_output) ?></pre>
      </div>
    <?php endif; ?>
  </div>

  <!-- Summary stats -->
  <div class="panel" style="margin-bottom:1.5rem;">
    <h2>Import Summary</h2>
    <table>
      <thead><tr><th>Metric</th><th>Value</th></tr></thead>
      <tbody>
        <tr><td>Origin Server</td><td style="color:var(--accent);"><?= htmlspecialchars($origin) ?></td></tr>
        <tr><td>Recup Home</td><td><code><?= htmlspecialchars($recup_home) ?></code></td></tr>
        <tr><td>Total Scanned</td><td><?= (int)$total ?></td></tr>
        <tr>
          <td>Photos Imported</td>
          <td><span class="badge badge-up"><?= (int)$photos_n ?></span></td>
        </tr>
        <tr>
          <td>Templates Imported</td>
          <td><span class="badge badge-up"><?= (int)$templ_n ?></span></td>
        </tr>
        <tr>
          <td>Skipped / Unclassified</td>
          <td><span class="badge badge-unknown"><?= (int)$skipped ?></span></td>
        </tr>
        <tr><td>Last Run</td><td><?= htmlspecialchars($timestamp) ?></td></tr>
      </tbody>
    </table>
  </div>

  <div class="grid-2">
    <!-- TEMPLATES tree -->
    <div class="panel">
      <h2>TEMPLATES <span style="color:var(--text-dim); font-size:.72rem;">/home/troy/TEMPLATES</span></h2>
      <?php if (empty($templates_tree)): ?>
        <p style="color:var(--text-dim); font-size:.85rem;">
          No TEMPLATES directory or it is empty.
          Place PhotoRec output in <code>/home/troy/recup_output/</code> and re-run import.
        </p>
      <?php else: ?>
        <?php foreach ($templates_tree as $item): ?>
          <?php if ($item['type'] === 'dir'): ?>
            <details style="margin-bottom:.5rem;">
              <summary style="cursor:pointer; font-family:var(--mono); font-size:.85rem; color:var(--accent);">
                &#128193; <?= htmlspecialchars($item['name']) ?>
                <span class="badge badge-up" style="margin-left:.3rem;">
                  <?= count($item['files']) ?>
                </span>
              </summary>
              <ul style="list-style:none; padding-left:1.2rem; margin-top:.3rem;">
              <?php foreach ($item['files'] as $f): ?>
                <li style="font-family:var(--mono); font-size:.78rem; color:var(--text); padding:.1rem 0;">
                  &#128196; <?= htmlspecialchars($f) ?>
                </li>
              <?php endforeach; ?>
              <?php if (empty($item['files'])): ?>
                <li style="color:var(--text-dim); font-size:.78rem;">(empty)</li>
              <?php endif; ?>
              </ul>
            </details>
          <?php else: ?>
            <p style="font-family:var(--mono); font-size:.78rem; padding:.1rem 0;">
              &#128196; <?= htmlspecialchars($item['name']) ?>
            </p>
          <?php endif; ?>
        <?php endforeach; ?>
      <?php endif; ?>
    </div>

    <!-- PHOTOS tree -->
    <div class="panel">
      <h2>PHOTOS <span style="color:var(--text-dim); font-size:.72rem;">/home/troy/PHOTOS</span></h2>
      <?php if (empty($photos_tree)): ?>
        <p style="color:var(--text-dim); font-size:.85rem;">
          No PHOTOS directory or it is empty.
          Place PhotoRec output in <code>/home/troy/recup_output/</code> and re-run import.
        </p>
      <?php else: ?>
        <?php foreach ($photos_tree as $item): ?>
          <?php if ($item['type'] === 'dir'): ?>
            <details style="margin-bottom:.5rem;">
              <summary style="cursor:pointer; font-family:var(--mono); font-size:.85rem; color:var(--accent);">
                &#128247; <?= htmlspecialchars($item['name']) ?>
                <span class="badge badge-up" style="margin-left:.3rem;">
                  <?= count($item['files']) ?>
                </span>
              </summary>
              <ul style="list-style:none; padding-left:1.2rem; margin-top:.3rem;">
              <?php foreach ($item['files'] as $f): ?>
                <li style="font-family:var(--mono); font-size:.78rem; color:var(--text); padding:.1rem 0;">
                  &#128248; <?= htmlspecialchars($f) ?>
                </li>
              <?php endforeach; ?>
              <?php if (empty($item['files'])): ?>
                <li style="color:var(--text-dim); font-size:.78rem;">(empty)</li>
              <?php endif; ?>
              </ul>
            </details>
          <?php else: ?>
            <p style="font-family:var(--mono); font-size:.78rem; padding:.1rem 0;">
              &#128196; <?= htmlspecialchars($item['name']) ?>
            </p>
          <?php endif; ?>
        <?php endforeach; ?>
      <?php endif; ?>
    </div>
  </div>

  <!-- Manifest table -->
  <?php if (!empty($manifest)): ?>
  <div class="panel" style="margin-top:1.5rem;">
    <h2>File Manifest <span style="color:var(--text-dim); font-size:.72rem;">(<?= count($manifest) ?> entries)</span></h2>
    <div style="max-height:300px; overflow-y:auto;">
      <table>
        <thead><tr><th>File</th><th>Source</th><th>Class</th></tr></thead>
        <tbody>
        <?php foreach ($manifest as $entry): ?>
          <tr>
            <td><?= htmlspecialchars($entry['file'] ?? '') ?></td>
            <td><?= htmlspecialchars($entry['source'] ?? '') ?></td>
            <td>
              <?php
                $cls = $entry['class'] ?? '';
                $badge = match($cls) {
                    'PHOTO'  => 'badge-up',
                    'CODE','CONFIG','DOC','SCRIPT','DATA' => 'badge-up',
                    'SKIP'   => 'badge-unknown',
                    default  => 'badge-down',
                };
              ?>
              <span class="badge <?= $badge ?>"><?= htmlspecialchars($cls) ?></span>
            </td>
          </tr>
        <?php endforeach; ?>
        </tbody>
      </table>
    </div>
  </div>
  <?php endif; ?>

</div>

<footer>
  HUM.org Lab &middot; TestDisk/PhotoRec Recup Import &middot; /home/troy/TEMPLATES &amp; /home/troy/PHOTOS
</footer>

<script src="assets/app.js"></script>
</body>
</html>
