# AGENTS.md

## Cursor Cloud specific instructions

### Repository overview

HUM is a lightweight repo with two main components:

- **DevContainer config** (`main` branch): `.devcontainer/` provides an Ubuntu 24.04 dev container with LAN networking tools. See `README.md` for usage.
- **URI status checker** (`copilot/check-status` branch): A Python 3.12+ CLI tool (`check.py`) that checks HTTP status of URIs using only the standard library. Tests in `test_check.py` use `unittest` with an embedded local HTTP server.

### Running tests

The Python app (when present on the working branch) uses only the standard library — no `pip install` needed.

```
python3 -m unittest test_check -v
```

### Known environment caveat

- `test_unreachable_host` will error in cloud/sandboxed environments because egress restrictions cause `RemoteDisconnected` instead of a `URLError` timeout. This is an environment limitation, not a code bug — 8/9 tests should pass.
- External HTTP requests may be blocked or return unexpected results due to egress restrictions. Use a local HTTP server (`python3 -m http.server`) for reliable testing.

### Network tools

The devcontainer Dockerfile installs `iproute2`, `net-tools`, `iputils-ping`, `traceroute`, and `dnsutils`. In the cloud VM, `iproute2` and `traceroute` are not pre-installed and need to be added via `apt-get` for `.devcontainer/post-create.sh` to work correctly.
