<?php
declare(strict_types=1);

require_once __DIR__ . '/config.php';

function login_pdo(): PDO
{
    static $pdo = null;
    if ($pdo instanceof PDO) {
        return $pdo;
    }

    $config = login_config();
    $db_path = $config['database'];
    $dir = dirname($db_path);
    if (!is_dir($dir) && !mkdir($dir, 0700, true) && !is_dir($dir)) {
        throw new RuntimeException('Cannot create login database directory.');
    }

    $pdo = new PDO('sqlite:' . $db_path, null, null, [
        PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
        PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]);
    $pdo->exec('PRAGMA foreign_keys = ON');

    $schema = $config['schema'];
    if (is_file($schema)) {
        $sql = file_get_contents($schema);
        if ($sql !== false) {
            $pdo->exec($sql);
        }
    }

    return $pdo;
}
