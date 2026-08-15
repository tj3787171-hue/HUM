<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/auth.php';
require_once __DIR__ . '/includes/layout.php';

$user = login_current_user();
login_render_start('HUM.org — SQL Login', $user);
?>
  <section class="panel">
    <h1>SQL login desk</h1>
    <p class="lede">Local SQLite accounts for the HUM.org lab. PHP pages and the Python server share one schema.</p>
    <p>
      <a class="enter-btn" href="login.php">Sign in</a>
      <a class="enter-btn" href="register.php">Create account</a>
    </p>
  </section>
  <section class="panel">
    <h2>Directory map</h2>
    <table>
      <thead><tr><th>Path</th><th>Type</th><th>Role</th></tr></thead>
      <tbody>
        <tr><td><code>sql/schema.sql</code></td><td>SQL</td><td>Users, sessions, attempts, CSRF</td></tr>
        <tr><td><code>includes/*.php</code></td><td>PHP</td><td>PDO, auth, CSRF, layout</td></tr>
        <tr><td><code>login.php</code> / <code>register.php</code></td><td>PHP</td><td>Public forms</td></tr>
        <tr><td><code>dashboard.php</code> / <code>account.php</code></td><td>PHP</td><td>Session-gated pages</td></tr>
        <tr><td><code>assets/login.css</code> / <code>login.js</code></td><td>CSS / JS</td><td>Theme and client checks</td></tr>
        <tr><td><code>xml/auth-config.xml</code></td><td>XML</td><td>TTL, throttle, bind</td></tr>
        <tr><td><code>tools/login_server.py</code></td><td>PY</td><td>Stdlib server when PHP is absent</td></tr>
        <tr><td><code>docs/login-system.*</code></td><td>XHTML / RTF / DOC</td><td>Operator notes</td></tr>
      </tbody>
    </table>
  </section>
<?php
login_render_end();
