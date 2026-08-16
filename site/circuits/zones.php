<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/blog.php';

$catalog = circuits_catalog();
$present = 0;
foreach (($catalog['isos'] ?? []) as $iso) {
    if (($iso['phase'] ?? '') === 'present') {
        $present++;
    }
}
$plan = circuits_allocate(max(1, $present));
circuits_render_start('Isolation zones');
?>
  <section class="panel">
    <h1>Isolation zones</h1>
    <p class="lede">
      Housing <?= circuits_h((string) $plan['housing']) ?>.
      Virtio <?= circuits_h((string) $plan['virtio']['guest']) ?>
      &harr; <?= circuits_h((string) $plan['virtio']['host']) ?>.
      nbd0 zone <?= (int) $plan['nbd0']['zone'] ?> attach <?= circuits_h((string) $plan['nbd0']['vnc_attach']) ?>.
    </p>
    <table>
      <thead><tr><th>Track</th><th>Dummy rail</th><th>Display zone</th><th>VNC</th><th>Disk zone</th></tr></thead>
      <tbody>
      <?php foreach ($plan['guests'] as $guest): ?>
        <tr>
          <td><?= circuits_h((string) $guest['track']) ?></td>
          <td><?= circuits_h((string) $guest['dummy_rail']) ?></td>
          <td><?= (int) $guest['display_zone'] ?></td>
          <td><?= circuits_h((string) $guest['vnc_bind']) ?>:<?= (int) $guest['vnc_port'] ?></td>
          <td><?= (int) $guest['disk_zone'] ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
  </section>
<?php
circuits_render_end();
