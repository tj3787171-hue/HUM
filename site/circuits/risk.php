<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/blog.php';

circuits_render_start('NBD / VNC risk');
?>
  <section class="panel">
    <h1>nbd0 is a high-risk collision, not a VNC target</h1>
    <p class="lede">This page is isolation policy. It does not attach, probe, or exploit VNC or NBD.</p>
    <table>
      <tbody>
        <tr><th>Block export</th><td><code>/dev/nbd0</code> zone 300</td></tr>
        <tr><th>Display path</th><td>VNC / noVNC on <code>127.0.0.1</code> zones 100+</td></tr>
        <tr><th>Attach</th><td>denied</td></tr>
        <tr><th>Sign-in</th><td>One SQL login. APK/PKG and URL dial-in reuse that origin.</td></tr>
        <tr><th>2026 listeners</th><td>HTTPS 443 + housing DNS 53 + login 8088, loopback first</td></tr>
      </tbody>
    </table>
    <p><a class="enter-btn" href="../login/">Open login desk</a></p>
  </section>
<?php
circuits_render_end();
