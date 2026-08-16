<?php
declare(strict_types=1);

require_once __DIR__ . '/db.php';
require_once __DIR__ . '/csrf.php';

const LOGIN_PASSWORD_PREFIX = 'pbkdf2_sha256';
const LOGIN_GENERIC_ERROR = 'Invalid username or password.';
const LOGIN_THROTTLE_ERROR = 'Too many failed sign-in attempts. Try again later.';

function login_utc_now(): string
{
    return gmdate('Y-m-d\TH:i:s\Z');
}

function login_hash_password(string $password): string
{
    $config = login_config();
    $salt = random_bytes(16);
    $hash = hash_pbkdf2('sha256', $password, $salt, $config['iterations'], 32, true);
    return LOGIN_PASSWORD_PREFIX . '$' . $config['iterations'] . '$' . bin2hex($salt) . '$' . bin2hex($hash);
}

function login_verify_password(string $password, string $stored): bool
{
    $parts = explode('$', $stored);
    if (count($parts) !== 4 || $parts[0] !== LOGIN_PASSWORD_PREFIX) {
        return false;
    }
    $iterations = (int) $parts[1];
    $salt = hex2bin($parts[2]);
    $expected = hex2bin($parts[3]);
    if ($salt === false || $expected === false) {
        return false;
    }
    $actual = hash_pbkdf2('sha256', $password, $salt, $iterations, strlen($expected), true);
    return hash_equals($expected, $actual);
}

function login_validate_username(string $username): ?string
{
    if (!preg_match('/^[A-Za-z][A-Za-z0-9_]{2,31}$/', $username)) {
        return 'Username must start with a letter and be 3-32 letters, digits, or underscores.';
    }
    return null;
}

function login_validate_email(string $email): ?string
{
    if (strlen($email) > 254 || filter_var($email, FILTER_VALIDATE_EMAIL) === false) {
        return 'Enter a valid email address.';
    }
    return null;
}

function login_validate_password(string $password): ?string
{
    $min = login_config()['min_password'];
    if (strlen($password) < $min) {
        return 'Password must be at least ' . $min . ' characters.';
    }
    if (!preg_match('/[A-Za-z]/', $password) || !preg_match('/\d/', $password)) {
        return 'Password must include at least one letter and one number.';
    }
    return null;
}

function login_client_ip(): string
{
    return $_SERVER['REMOTE_ADDR'] ?? '0.0.0.0';
}

function login_read_cookie(): ?string
{
    $name = login_config()['cookie_name'];
    if (!isset($_COOKIE[$name]) || !is_string($_COOKIE[$name]) || $_COOKIE[$name] === '') {
        return null;
    }
    return $_COOKIE[$name];
}

function login_set_session_cookie(string $token): void
{
    $config = login_config();
    setcookie($config['cookie_name'], $token, [
        'expires' => time() + $config['session_ttl'],
        'path' => '/',
        'httponly' => true,
        'samesite' => 'Lax',
        'secure' => false,
    ]);
}

function login_clear_session_cookie(): void
{
    $config = login_config();
    setcookie($config['cookie_name'], '', [
        'expires' => time() - 3600,
        'path' => '/',
        'httponly' => true,
        'samesite' => 'Lax',
    ]);
}

function login_current_user(): ?array
{
    $token = login_read_cookie();
    if ($token === null) {
        return null;
    }
    $pdo = login_pdo();
    $stmt = $pdo->prepare('SELECT user_id, expires_at FROM sessions WHERE id = :id');
    $stmt->execute(['id' => $token]);
    $session = $stmt->fetch();
    if ($session === false) {
        return null;
    }
    if ((string) $session['expires_at'] < login_utc_now()) {
        $delete = $pdo->prepare('DELETE FROM sessions WHERE id = :id');
        $delete->execute(['id' => $token]);
        return null;
    }
    $user_stmt = $pdo->prepare(
        'SELECT id, username, email, display_name, created_at, last_login_at, is_active '
        . 'FROM users WHERE id = :id AND is_active = 1'
    );
    $user_stmt->execute(['id' => $session['user_id']]);
    $user = $user_stmt->fetch();
    return $user === false ? null : $user;
}

function login_require_user(): array
{
    $user = login_current_user();
    if ($user === null) {
        header('Location: login.php');
        exit;
    }
    return $user;
}

function login_count_failures(string $username, string $ip): int
{
    $config = login_config();
    $cutoff = gmdate('Y-m-d\TH:i:s\Z', time() - $config['window_seconds']);
    $stmt = login_pdo()->prepare(
        'SELECT COUNT(*) AS n FROM login_attempts '
        . 'WHERE username = :username AND ip_address = :ip AND success = 0 AND created_at >= :cutoff'
    );
    $stmt->execute(['username' => $username, 'ip' => $ip, 'cutoff' => $cutoff]);
    $row = $stmt->fetch();
    return (int) ($row['n'] ?? 0);
}

function login_record_attempt(string $username, string $ip, bool $success): void
{
    $stmt = login_pdo()->prepare(
        'INSERT INTO login_attempts (username, ip_address, success) VALUES (:username, :ip, :success)'
    );
    $stmt->execute(['username' => $username, 'ip' => $ip, 'success' => $success ? 1 : 0]);
}

function login_authenticate(string $username, string $password): array
{
    $ip = login_client_ip();
    if (login_count_failures($username, $ip) >= login_config()['max_failures']) {
        throw new RuntimeException(LOGIN_THROTTLE_ERROR);
    }

    $stmt = login_pdo()->prepare(
        'SELECT id, username, email, password_hash, display_name, created_at, last_login_at, is_active '
        . 'FROM users WHERE username = :username'
    );
    $stmt->execute(['username' => $username]);
    $row = $stmt->fetch();
    $ok = $row !== false && (int) $row['is_active'] === 1 && login_verify_password($password, (string) $row['password_hash']);
    login_record_attempt($username, $ip, $ok);
    if (!$ok) {
        throw new RuntimeException(LOGIN_GENERIC_ERROR);
    }

    $update = login_pdo()->prepare('UPDATE users SET last_login_at = :ts WHERE id = :id');
    $update->execute(['ts' => login_utc_now(), 'id' => $row['id']]);
    unset($row['password_hash']);
    return $row;
}

function login_create_session(int $user_id): string
{
    $token = bin2hex(random_bytes(32));
    $expires = gmdate('Y-m-d\TH:i:s\Z', time() + login_config()['session_ttl']);
    $stmt = login_pdo()->prepare(
        'INSERT INTO sessions (id, user_id, expires_at, ip_address, user_agent) '
        . 'VALUES (:id, :user_id, :expires, :ip, :ua)'
    );
    $stmt->execute([
        'id' => $token,
        'user_id' => $user_id,
        'expires' => $expires,
        'ip' => login_client_ip(),
        'ua' => substr((string) ($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 300),
    ]);
    return $token;
}

function login_destroy_session(): void
{
    $token = login_read_cookie();
    if ($token !== null) {
        $stmt = login_pdo()->prepare('DELETE FROM sessions WHERE id = :id');
        $stmt->execute(['id' => $token]);
    }
    login_clear_session_cookie();
}

function login_register(string $username, string $email, string $password): array
{
    $username_error = login_validate_username($username);
    if ($username_error !== null) {
        throw new InvalidArgumentException($username_error);
    }
    $email_error = login_validate_email($email);
    if ($email_error !== null) {
        throw new InvalidArgumentException($email_error);
    }
    $password_error = login_validate_password($password);
    if ($password_error !== null) {
        throw new InvalidArgumentException($password_error);
    }

    $pdo = login_pdo();
    $exists = $pdo->prepare('SELECT username FROM users WHERE username = :username OR email = :email');
    $exists->execute(['username' => $username, 'email' => $email]);
    if ($exists->fetch() !== false) {
        throw new InvalidArgumentException('That username or email is already registered.');
    }

    $insert = $pdo->prepare(
        'INSERT INTO users (username, email, password_hash, display_name) VALUES (:username, :email, :hash, :name)'
    );
    $insert->execute([
        'username' => $username,
        'email' => $email,
        'hash' => login_hash_password($password),
        'name' => $username,
    ]);

    $user = $pdo->prepare(
        'SELECT id, username, email, display_name, created_at, last_login_at, is_active FROM users WHERE username = :username'
    );
    $user->execute(['username' => $username]);
    $row = $user->fetch();
    if ($row === false) {
        throw new RuntimeException('Registration failed.');
    }
    return $row;
}
