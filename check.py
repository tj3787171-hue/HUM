#!/usr/bin/env python3
"""URI status checker — reports the HTTP status of a given URI."""

import sys
import urllib.request
import urllib.error


def check(uri: str) -> tuple[int | None, str]:
    """Check the HTTP status of *uri*.

    Returns a ``(status_code, message)`` tuple.  When the request cannot be
    completed (network error, invalid URL, …) *status_code* is ``None``.
    """
    try:
        with urllib.request.urlopen(uri, timeout=10) as response:
            code = response.status
            return code, f"{code} OK"
    except urllib.error.HTTPError as exc:
        return exc.code, f"{exc.code} {exc.reason}"
    except urllib.error.URLError as exc:
        return None, f"Error: {exc.reason}"
    except OSError as exc:
        return None, f"Error: {exc}"
    except ValueError as exc:
        return None, f"Invalid URI: {exc}"


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: check.py <uri> [uri ...]", file=sys.stderr)
        return 2

    exit_code = 0
    for uri in args:
        code, message = check(uri)
        print(f"{uri}  →  {message}")
        if code is None or code >= 400:
            exit_code = 1

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
