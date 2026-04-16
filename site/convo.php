<?php
/**
 * convo.php — JSON Conversation API for the House of Corps.
 *
 * Talks data through JSON to all sources. Serves corps.json, gram.json,
 * comb.json, palace.json, or the full sources.list depending on the
 * ?source= parameter. Also supports ?rebuild=1 to re-run name_factory.
 *
 * Usage:
 *   GET /convo.php                     → corps overview (corps.json)
 *   GET /convo.php?source=corps        → full corps.json
 *   GET /convo.php?source=gram         → FINAL-PRODUCT/gram.json
 *   GET /convo.php?source=comb         → FINAL-PRODUCT/comb.json
 *   GET /convo.php?source=palace       → FINAL-PRODUCT/palace.json
 *   GET /convo.php?source=topology     → data/topology.json
 *   GET /convo.php?source=sources      → data/sources.list (text)
 *   GET /convo.php?source=manifest     → recup_manifest.json
 *   GET /convo.php?source=summary      → recup_summary.json
 *   GET /convo.php?source=list         → list all available sources
 *   GET /convo.php?rebuild=1           → re-run name_factory then return corps
 */

$data_dir   = __DIR__ . '/data';
$fp_dir     = "$data_dir/FINAL-PRODUCT";
$recup_home = getenv('RECUP_HOME') ?: '/home/troy';

$rebuild = isset($_GET['rebuild']);
if ($rebuild) {
    $factory = "$data_dir/name_factory.py";
    $env = "HUM_ORIGIN=" . escapeshellarg(getenv('HUM_ORIGIN') ?: 'hum.org')
         . " RECUP_HOME=" . escapeshellarg($recup_home);
    exec("$env python3 " . escapeshellarg($factory) . " 2>&1", $out, $rc);
}

$source = $_GET['source'] ?? 'corps';

$source_map = [
    'corps'     => ["$data_dir/corps.json",            'application/json'],
    'gram'      => ["$fp_dir/gram.json",               'application/json'],
    'comb'      => ["$fp_dir/comb.json",               'application/json'],
    'palace'    => ["$fp_dir/palace.json",              'application/json'],
    'topology'  => ["$data_dir/topology.json",         'application/json'],
    'sources'   => ["$data_dir/sources.list",          'text/plain'],
    'manifest'  => ["$recup_home/recup_manifest.json", 'application/json'],
    'summary'   => ["$recup_home/recup_summary.json",  'application/json'],
];

if ($source === 'list') {
    header('Content-Type: application/json');
    $available = [];
    foreach ($source_map as $key => [$path, $mime]) {
        $available[] = [
            'source'  => $key,
            'url'     => "convo.php?source=$key",
            'exists'  => file_exists($path),
            'mime'    => $mime,
        ];
    }
    echo json_encode([
        'convo'   => 'House of Corps JSON Conversation API',
        'origin'  => getenv('HUM_ORIGIN') ?: 'hum.org',
        'sources' => $available,
        'rebuild' => 'convo.php?rebuild=1',
    ], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
    exit;
}

if (!isset($source_map[$source])) {
    header('HTTP/1.1 404 Not Found');
    header('Content-Type: application/json');
    echo json_encode(['error' => "Unknown source: $source", 'available' => array_keys($source_map)]);
    exit;
}

[$file_path, $mime_type] = $source_map[$source];

if (!file_exists($file_path)) {
    header('HTTP/1.1 404 Not Found');
    header('Content-Type: application/json');
    echo json_encode(['error' => "Source '$source' data not found. Run name_factory or recup-setup first.",
                       'rebuild' => 'convo.php?rebuild=1']);
    exit;
}

header("Content-Type: $mime_type; charset=utf-8");
if ($rebuild && $source !== 'sources') {
    $data = json_decode(file_get_contents($file_path), true);
    $data['_convo_rebuild'] = true;
    $data['_convo_rebuild_rc'] = $rc ?? -1;
    echo json_encode($data, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
} else {
    readfile($file_path);
}
