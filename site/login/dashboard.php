<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/layout.php';

$user = login_require_user();
$last = (string) ($user['last_login_at'] ?? 'first session');

login_render_start('Dashboard', $user);
?>
  <section class="panel">
    <h1>Signed in</h1>
    <p>Welcome, <strong><?= login_h((string) $user['display_name']) ?></strong>.</p>
    <table>
      <tbody>
        <tr><th>Username</th><td><?= login_h((string) $user['username']) ?></td></tr>
        <tr><th>Email</th><td><?= login_h((string) $user['email']) ?></td></tr>
        <tr><th>Created</th><td><?= login_h((string) $user['created_at']) ?></td></tr>
        <tr><th>Last login</th><td><?= login_h($last) ?></td></tr>
      </tbody>
    </table>
    <p class="lede">This session covers the URL desk, a future APK/PKG on the same origin, and loopback VNC in a display zone. It does not open nbd0.</p>
    <p><a class="enter-btn" href="account.php">Account</a> <a class="enter-btn" href="../circuits/">Circuits</a> <a class="enter-btn" href="../index.php">Open lab map</a></p>
  </section>
<?php
login_render_end();
