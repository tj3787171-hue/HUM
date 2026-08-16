# HUM.org SQL login desk

Local account login for the lab site. PHP pages and a stdlib Python server share one SQLite schema.

## Advice

Use this layout when you want a real login, not a pile of unused file types:

| Type | Keep | Why |
|---|---|---|
| `.sql` | yes | Table definitions. Source of truth. |
| `.php` | yes | Web forms and PDO access on a PHP host. |
| `.py` | yes | Init + server when PHP is missing (this Cloud VM). |
| `.xml` | yes | Config, sitemap, session status. |
| `.css` / `.js` | yes | Theme and client checks. Server still validates. |
| `.html` / `.xhtml` | yes | Landing page and a well-formed spec. |
| `.rtf` / `.doc` | optional | Operator notes only. Not used by login. |
| MySQL / `.mdb` | no | Extra server you do not have in this repo. |

Do not put passwords in git. Seed a lab user on the machine that will run the desk.

## Run (Python, no PHP)

```bash
python3 site/login/tools/init_auth_db.py init
python3 site/login/tools/init_auth_db.py seed --password 'LabOnly1234'
python3 site/login/tools/login_server.py --host 127.0.0.1 --port 8088
```

Open `http://127.0.0.1:8088/`.

## Run (PHP)

Point a PHP host at `site/login/`. The first request applies `sql/schema.sql` through PDO. Keep `var/`, `includes/`, `sql/`, and `tools/` out of public fetch (see `.htaccess`).

## Security

- Passwords are stored as `pbkdf2_sha256$iterations$salt$hash`.
- All user lookups use bound parameters.
- Failed sign-in always returns the same message.
- Five failures per username+IP in 15 minutes are rejected.
- CSRF tokens are one-time and expire.
- Session cookies are HttpOnly + SameSite=Lax.
