<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/layout.php';

$user = login_require_user();
$error = '';

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    if (!login_consume_csrf($_POST['csrf'] ?? null)) {
        $error = 'The form token was missing or expired. Reload and try again.';
    } else {
        try {
            $name = trim((string) ($_POST['display_name'] ?? ''));
            if ($name === '' || strlen($name) > 80) {
                throw new InvalidArgumentException('Display name must be 1-80 characters.');
            }
            $stmt = login_pdo()->prepare('UPDATE users SET display_name = :name WHERE id = :id');
            $stmt->execute(['name' => $name, 'id' => $user['id']]);

            $new_password = (string) ($_POST['new_password'] ?? '');
            if ($new_password !== '') {
                $current = (string) ($_POST['current_password'] ?? '');
                $lookup = login_pdo()->prepare('SELECT password_hash FROM users WHERE id = :id');
                $lookup->execute(['id' => $user['id']]);
                $row = $lookup->fetch();
                if ($row === false || !login_verify_password($current, (string) $row['password_hash'])) {
                    throw new RuntimeException('Current password is incorrect.');
                }
                $password_error = login_validate_password($new_password);
                if ($password_error !== null) {
                    throw new InvalidArgumentException($password_error);
                }
                $update = login_pdo()->prepare('UPDATE users SET password_hash = :hash WHERE id = :id');
                $update->execute(['hash' => login_hash_password($new_password), 'id' => $user['id']]);
            }
            header('Location: dashboard.php');
            exit;
        } catch (InvalidArgumentException | RuntimeException $exc) {
            $error = $exc->getMessage();
        }
    }
    $fresh = login_current_user();
    if ($fresh !== null) {
        $user = $fresh;
    }
}

$csrf = login_issue_csrf();
login_render_start('Account', $user, $error);
?>
  <section class="panel auth-card">
    <h1>Account</h1>
    <form class="auth-form" method="post" action="account.php">
      <input type="hidden" name="csrf" value="<?= login_h($csrf) ?>"/>
      <label>Display name
        <input type="text" name="display_name" value="<?= login_h((string) $user['display_name']) ?>" maxlength="80" required="required"/>
      </label>
      <label>Current password
        <input type="password" name="current_password" autocomplete="current-password"/>
      </label>
      <label>New password
        <input type="password" name="new_password" autocomplete="new-password" minlength="10"/>
      </label>
      <button type="submit">Save</button>
    </form>
  </section>
<?php
login_render_end();
