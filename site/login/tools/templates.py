"""HTML templates for the stdlib login server."""

from __future__ import annotations

from html import escape

from authlib import User


def page(title: str, body: str, user: User | None = None, notice: str = "", error: str = "") -> str:
    nav_login = '<a href="/login">Login</a>'
    nav_register = '<a href="/register">Register</a>'
    nav_account = ""
    if user:
        nav_login = f'<a href="/dashboard">Dashboard</a>'
        nav_register = f'<a href="/account">{escape(user.username)}</a>'
        nav_account = (
            '<form class="nav-logout" method="post" action="/logout">'
            '<button type="submit">Logout</button></form>'
        )
    flash = ""
    if notice:
        flash += f'<p class="flash ok">{escape(notice)}</p>'
    if error:
        flash += f'<p class="flash err">{escape(error)}</p>'
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{escape(title)}</title>
  <link rel="stylesheet" href="/assets/login.css"/>
</head>
<body>
<header>
  <span class="logo">HUM.org</span>
  <nav>
    <a href="/">Home</a>
    <a href="../welcome.html">Lab</a>
    {nav_login}
    {nav_register}
  </nav>
  {nav_account}
</header>
<div class="container auth-wrap">
  {flash}
  {body}
</div>
<footer>HUM.org Lab &middot; SQLite login &middot; local accounts only</footer>
<script src="/assets/login.js"></script>
</body>
</html>
"""


def landing() -> str:
    body = """
  <section class="panel">
    <h1>SQL login desk</h1>
    <p class="lede">Local SQLite accounts for the HUM.org lab. PHP pages and the Python server share one schema.</p>
    <p>
      <a class="enter-btn" href="/login">Sign in</a>
      <a class="enter-btn" href="/register">Create account</a>
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
"""
    return page("HUM.org — SQL Login", body)


def auth_form(
    action: str,
    heading: str,
    csrf: str,
    extra_fields: str = "",
    submit: str = "Continue",
    form_id: str = "auth-form",
) -> str:
    return f"""
  <section class="panel auth-card">
    <h1>{escape(heading)}</h1>
    <form id="{escape(form_id)}" class="auth-form" method="post" action="{escape(action)}" novalidate="novalidate">
      <input type="hidden" name="csrf" value="{escape(csrf)}"/>
      {extra_fields}
      <label>Username
        <input type="text" name="username" autocomplete="username" required="required" minlength="3" maxlength="32"/>
      </label>
      {"" if action == "/login" else '''<label>Email
        <input type="email" name="email" autocomplete="email" required="required"/>
      </label>'''}
      <label>Password
        <input type="password" name="password" autocomplete="{'current-password' if action == '/login' else 'new-password'}" required="required" minlength="10"/>
      </label>
      {"" if action == "/login" else '''<label>Confirm password
        <input type="password" name="confirm" autocomplete="new-password" required="required" minlength="10"/>
      </label>'''}
      <button type="submit">{escape(submit)}</button>
    </form>
  </section>
"""


def dashboard(user: User) -> str:
    last = user.last_login_at or "first session"
    return f"""
  <section class="panel">
    <h1>Signed in</h1>
    <p>Welcome, <strong>{escape(user.display_name)}</strong>.</p>
    <table>
      <tbody>
        <tr><th>Username</th><td>{escape(user.username)}</td></tr>
        <tr><th>Email</th><td>{escape(user.email)}</td></tr>
        <tr><th>Created</th><td>{escape(user.created_at)}</td></tr>
        <tr><th>Last login</th><td>{escape(last)}</td></tr>
      </tbody>
    </table>
    <p><a class="enter-btn" href="/account">Account</a> <a class="enter-btn" href="../index.php">Open lab map</a></p>
  </section>
"""


def account_form(user: User, csrf: str) -> str:
    return f"""
  <section class="panel auth-card">
    <h1>Account</h1>
    <form class="auth-form" method="post" action="/account">
      <input type="hidden" name="csrf" value="{escape(csrf)}"/>
      <label>Display name
        <input type="text" name="display_name" value="{escape(user.display_name)}" maxlength="80" required="required"/>
      </label>
      <label>Current password
        <input type="password" name="current_password" autocomplete="current-password"/>
      </label>
      <label>New password
        <input type="password" name="new_password" autocomplete="new-password" minlength="10"/>
      </label>
      <button type="submit">Save</button>
    </form>
  </section>
"""


def session_xml(user: User | None) -> str:
    if user is None:
        return (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<session xmlns="https://hum.org/login/session" authenticated="false"/>\n'
        )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<session xmlns="https://hum.org/login/session" authenticated="true">'
        f"<username>{escape(user.username)}</username>"
        f"<displayName>{escape(user.display_name)}</displayName>"
        f"</session>\n"
    )
