<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/layout.php';

if (login_current_user() !== null) {
    header('Location: dashboard.php');
    exit;
}

$error = '';
if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST') {
    if (!login_consume_csrf($_POST['csrf'] ?? null)) {
        $error = 'The form token was missing or expired. Reload and try again.';
    } else {
        try {
            $user = login_authenticate(trim((string) ($_POST['username'] ?? '')), (string) ($_POST['password'] ?? ''));
            $token = login_create_session((int) $user['id']);
            login_set_session_cookie($token);
            header('Location: dashboard.php');
            exit;
        } catch (RuntimeException $exc) {
            $error = $exc->getMessage();
        }
    }
}

$csrf = login_issue_csrf();
login_render_start('Sign in', null, $error);
?>
  <section class="panel auth-card">
    <h1>Sign in</h1>
    <form id="login-form" class="auth-form" method="post" action="login.php" novalidate="novalidate">
      <input type="hidden" name="csrf" value="<?= login_h($csrf) ?>"/>
      <label>Username
        <input type="text" name="username" autocomplete="username" required="required" minlength="3" maxlength="32"/>
      </label>
      <label>Password
        <input type="password" name="password" autocomplete="current-password" required="required" minlength="10"/>
      </label>
      <button type="submit">Sign in</button>
    </form>
  </section>
<?php
login_render_end();
