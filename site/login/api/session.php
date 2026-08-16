<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/includes/auth.php';

header('Content-Type: application/xml; charset=UTF-8');
header('Cache-Control: no-store');

$user = login_current_user();
echo '<?xml version="1.0" encoding="UTF-8"?>' . "\n";
if ($user === null) {
    echo '<session xmlns="https://hum.org/login/session" authenticated="false"/>' . "\n";
    exit;
}

echo '<session xmlns="https://hum.org/login/session" authenticated="true">';
echo '<username>' . htmlspecialchars((string) $user['username'], ENT_XML1 | ENT_QUOTES, 'UTF-8') . '</username>';
echo '<displayName>' . htmlspecialchars((string) $user['display_name'], ENT_XML1 | ENT_QUOTES, 'UTF-8') . '</displayName>';
echo '</session>' . "\n";
