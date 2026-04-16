# AGENTS.md

## Cursor Cloud specific instructions

### Repository overview

HUM is a LAN-ready development and network lab project. The consolidated codebase includes:

| Component | Path | Description |
|---|---|---|
| DevContainer | `.devcontainer/` | Ubuntu 24.04 dev container with LAN networking tools |
| URI checker | `check.py`, `test_check.py` | Python CLI to check HTTP status of URIs (stdlib only) |
| Site / Web presence | `site/` | PHP pages + JS SVG map + CSS + data pipeline |
| Data pipeline | `site/data/name_factory.py` | Builds FINAL-PRODUCT JSON from topology + recup data |
| FINAL-PRODUCT | `site/data/FINAL-PRODUCT/` | Output: `gram.json`, `comb.json`, `palace.json`, `corps_full.json` |
| Convo API | `site/convo.php` | JSON API serving all data sources |
| SDV (Software-Defined Validation) | `websetup/sdv/` | Network validation pipeline (pool, macsec, docker wait) |
| Virtual setup | `websetup/virtual/` | Network matrix, bindings, inventory, schemas |
| Scripts | `scripts/` | Networking, recovery, telemetry, DB linking, snap handling |
| Tests | `tests/test_sdv.py`, `scripts/tests/` | SDV and connect_again test suites |
| ISO build | `iso-build/` | Reproducible Kali ISO build recipe |
| Kali defenses | `kali-iso-server/hostile-env-defense/` | Hardening scripts for Kali installation |

### Running tests

All Python code uses stdlib only — no `pip install` needed.

```bash
# URI checker tests (8/9 pass in cloud; test_unreachable_host is env-limited)
python3 -m unittest test_check -v

# Connect-again retry utility tests
python3 -m unittest scripts.tests.test_connect_again -v

# SDV validation tests (9/9 pass)
python3 -m unittest tests.test_sdv -v

# Name Factory data pipeline
cd site/data && python3 name_factory.py
```

### Serving the site locally

The `site/` directory contains PHP pages. To serve locally with PHP's built-in server:
```bash
cd site && php -S 0.0.0.0:8000
```
Or use Python for static file serving: `python3 -m http.server 8000 --directory site`

### Known environment caveats

- `test_unreachable_host` errors in cloud/sandboxed environments (egress proxy returns `RemoteDisconnected` instead of timeout). Not a code bug.
- External HTTP requests may be blocked. Use a local HTTP server for reliable URI checker testing.
- `iproute2` and `traceroute` must be installed for `post-create.sh` to display network info.
