<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/blog.php';

circuits_render_start('HUM circuits');
?>
  <section class="panel">
    <h1>Circuit blog</h1>
    <p class="lede">Simple delivery. Virtio vda on /dev/sda. One login. Dummy rails. VNC never joins nbd0.</p>
  </section>
<?php foreach (circuits_posts() as $post): ?>
  <article class="panel">
    <h2><?= circuits_h($post['title']) ?></h2>
    <p class="lede"><?= circuits_h($post['date']) ?> &middot; <?= circuits_h($post['slug']) ?></p>
    <p><?= circuits_h($post['body']) ?></p>
  </article>
<?php endforeach; ?>
<?php
circuits_render_end();
