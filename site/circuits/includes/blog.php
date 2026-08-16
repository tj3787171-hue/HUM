<?php
declare(strict_types=1);

const CIRCUITS_DATA = __DIR__ . '/../data';

function circuits_h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function circuits_posts(): array
{
    $path = CIRCUITS_DATA . '/posts.xml';
    if (!is_file($path)) {
        return [];
    }
    $xml = simplexml_load_file($path);
    if ($xml === false) {
        return [];
    }
    $posts = [];
    foreach ($xml->post as $post) {
        $posts[] = [
            'id' => (string) $post['id'],
            'slug' => (string) $post['slug'],
            'date' => (string) $post['date'],
            'title' => (string) $post->title,
            'body' => (string) $post->body,
        ];
    }
    return $posts;
}

function circuits_catalog(): array
{
    $path = CIRCUITS_DATA . '/iso-catalog.json';
    if (!is_file($path)) {
        return ['isos' => []];
    }
    $payload = json_decode((string) file_get_contents($path), true);
    return is_array($payload) ? $payload : ['isos' => []];
}

function circuits_allocate(int $guest_count): array
{
    $guests = [];
    for ($index = 0; $index < $guest_count; $index++) {
        $guests[] = [
            'index' => $index,
            'track' => sprintf('10.224.%d.0/30', $index),
            'dummy_rail' => 'hum-dummy' . $index,
            'display_zone' => 100 + $index,
            'disk_zone' => 200 + $index,
            'vnc_bind' => '127.0.0.1',
            'vnc_port' => 5901 + $index,
            'vnc_shares_nbd' => false,
        ];
    }
    return [
        'housing' => '10.224.0.0/16',
        'nbd0' => ['device' => '/dev/nbd0', 'zone' => 300, 'vnc_attach' => 'denied'],
        'virtio' => ['guest' => '/dev/vda', 'host' => '/dev/sda'],
        'guests' => $guests,
    ];
}

function circuits_render_start(string $title): void
{
    echo '<!DOCTYPE html><html lang="en" xmlns="http://www.w3.org/1999/xhtml"><head>';
    echo '<meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>';
    echo '<title>' . circuits_h($title) . '</title>';
    echo '<link rel="stylesheet" href="../login/assets/login.css"/>';
    echo '<link rel="stylesheet" href="assets/circuits.css"/></head><body>';
    echo '<header><span class="logo">HUM.org</span><nav>';
    echo '<a href="index.php">Blog</a><a href="iso.php">ISOs</a><a href="zones.php">Zones</a>';
    echo '<a href="risk.php">NBD risk</a><a href="../broadcast/pages/show-and-tell.html">Broadcast</a>';
    echo '<a href="../login/">Login</a><a href="../welcome.html">Lab</a>';
    echo '</nav></header><div class="container auth-wrap">';
}

function circuits_render_end(): void
{
    echo '</div><footer>HUM.org circuits &middot; blogspot delivery &middot; VNC stays off nbd0</footer></body></html>';
}
