<?php
declare(strict_types=1);

require_once __DIR__ . '/includes/blog.php';

$catalog = circuits_catalog();
circuits_render_start('ISO tracks');
?>
  <section class="panel">
    <h1>ISO tracks</h1>
    <p class="lede">
      Guest <?= circuits_h((string) ($catalog['guest_disk'] ?? '/dev/vda')) ?>
      maps host <?= circuits_h((string) ($catalog['host_disk'] ?? '/dev/sda')) ?>.
      Present tracks grow first. Optional and onsite ISOs stay unbundled.
    </p>
    <table>
      <thead><tr><th>ID</th><th>Title</th><th>Phase</th><th>Family</th><th>Bundled</th></tr></thead>
      <tbody>
      <?php foreach (($catalog['isos'] ?? []) as $iso): ?>
        <tr>
          <td><?= circuits_h((string) ($iso['id'] ?? '')) ?></td>
          <td><?= circuits_h((string) ($iso['title'] ?? '')) ?></td>
          <td><?= circuits_h((string) ($iso['phase'] ?? '')) ?></td>
          <td><?= circuits_h((string) ($iso['family'] ?? '')) ?></td>
          <td><?= !empty($iso['bundle']) ? 'yes' : 'no' ?></td>
        </tr>
      <?php endforeach; ?>
      </tbody>
    </table>
  </section>
<?php
circuits_render_end();
