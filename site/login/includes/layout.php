<?php
declare(strict_types=1);

function login_h(string $value): string
{
    return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function login_render_start(string $title, ?array $user = null, string $error = '', string $notice = ''): void
{
    $nav_login = '<a href="login.php">Login</a>';
    $nav_register = '<a href="register.php">Register</a>';
    $logout = '';
    if ($user !== null) {
        $nav_login = '<a href="dashboard.php">Dashboard</a>';
        $nav_register = '<a href="account.php">' . login_h((string) $user['username']) . '</a>';
        $logout = '<form class="nav-logout" method="post" action="logout.php"><button type="submit">Logout</button></form>';
    }
    echo '<!DOCTYPE html>' . "\n";
    echo '<html lang="en" xmlns="http://www.w3.org/1999/xhtml">' . "\n";
    echo '<head><meta charset="UTF-8"/><meta name="viewport" content="width=device-width, initial-scale=1.0"/>';
    echo '<title>' . login_h($title) . '</title>';
    echo '<link rel="stylesheet" href="assets/login.css"/></head><body>';
    echo '<header><span class="logo">HUM.org</span><nav>';
    echo '<a href="index.html">Home</a><a href="../circuits/">Circuits</a><a href="../welcome.html">Lab</a>';
    echo $nav_login . $nav_register . '</nav>' . $logout . '</header>';
    echo '<div class="container auth-wrap">';
    if ($notice !== '') {
        echo '<p class="flash ok">' . login_h($notice) . '</p>';
    }
    if ($error !== '') {
        echo '<p class="flash err">' . login_h($error) . '</p>';
    }
}

function login_render_end(): void
{
    echo '</div><footer>HUM.org Lab &middot; SQLite login &middot; local accounts only</footer>';
    echo '<script src="assets/login.js"></script></body></html>';
}
