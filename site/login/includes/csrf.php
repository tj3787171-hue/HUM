<?php
declare(strict_types=1);

require_once __DIR__ . '/db.php';

function login_issue_csrf(): string
{
    $token = bin2hex(random_bytes(32));
    $expires = gmdate('Y-m-d\TH:i:s\Z', time() + 7200);
    $stmt = login_pdo()->prepare('INSERT INTO csrf_tokens (token, expires_at) VALUES (:token, :expires)');
    $stmt->execute(['token' => $token, 'expires' => $expires]);
    return $token;
}

function login_consume_csrf(?string $token): bool
{
    if ($token === null || $token === '') {
        return false;
    }
    $pdo = login_pdo();
    $stmt = $pdo->prepare('SELECT expires_at FROM csrf_tokens WHERE token = :token');
    $stmt->execute(['token' => $token]);
    $row = $stmt->fetch();
    $delete = $pdo->prepare('DELETE FROM csrf_tokens WHERE token = :token');
    $delete->execute(['token' => $token]);
    if ($row === false) {
        return false;
    }
    return (string) $row['expires_at'] >= gmdate('Y-m-d\TH:i:s\Z');
}
