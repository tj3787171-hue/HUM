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
    } elseif (((string) ($_POST['password'] ?? '')) !== ((string) ($_POST['confirm'] ?? ''))) {
        $error = 'Passwords do not match.';
    } else {
        try {
            $user = login_register(
                trim((string) ($_POST['username'] ?? '')),
                trim((string) ($_POST['email'] ?? '')),
                (string) ($_POST['password'] ?? '')
            );
            $token = login_create_session((int) $user['id']);
            login_set_session_cookie($token);
            header('Location: dashboard.php');
            exit;
        } catch (InvalidArgumentException $exc) {
            $error = $exc->getMessage();
        }
    }
}

$csrf = login_issue_csrf();
login_render_start('Register', null, $error);
?>
  <section class="panel auth-card">
    <h1>Create account</h1>
    <form id="register-form" class="auth-form" method="post" action="register.php" novalidate="novalidate">
      <input type="hidden" name="csrf" value="<?= login_h($csrf) ?>"/>
      <label>Username
        <input type="text" name="username" autocomplete="username" required="required" minlength="3" maxlength="32"/>
      </label>
      <label>Email
        <input type="email" name="email" autocomplete="email" required="required"/>
      </label>
      <label>Password
        <input type="password" name="password" autocomplete="new-password" required="required" minlength="10"/>
      </label>
      <label>Confirm password
        <input type="password" name="confirm" autocomplete="new-password" required="required" minlength="10"/>
      </label>
      <button type="submit">Register</button>
    </form>
  </section>
<?php
login_render_end();
