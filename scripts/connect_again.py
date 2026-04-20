#!/usr/bin/env python3
"""Small connectivity checker with reconnect retry support."""

from __future__ import annotations

import argparse
import time
import urllib.error
import urllib.request
from http.client import RemoteDisconnected
from typing import Tuple


def check(uri: str, timeout: int = 10) -> Tuple[int, str]:
    """Return HTTP status/reason for URI, or 1/error for connection failures."""
    try:
        with urllib.request.urlopen(uri, timeout=timeout) as response:
            return int(response.status), str(response.reason)
    except RemoteDisconnected as exc:
        return 1, f"RemoteDisconnected: {exc}"
    except urllib.error.HTTPError as exc:
        return int(exc.code), str(exc.reason)
    except urllib.error.URLError as exc:
        return 1, f"URLError: {exc.reason}"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return 1, f"{type(exc).__name__}: {exc}"


def _should_retry(status: int, reason: str) -> bool:
    if status == 1:
        return True
    return status >= 500 or "RemoteDisconnected" in reason


def connect_again(
    uri: str,
    retries: int = 3,
    delay_seconds: float = 1.0,
    timeout: int = 10,
) -> Tuple[int, str, int]:
    """Attempt check() repeatedly until success or retries exhausted.

    Returns (status, reason, attempts_used).
    """
    attempts_used = 0
    max_attempts = max(1, retries + 1)
    current_delay = max(0.0, delay_seconds)

    while attempts_used < max_attempts:
        attempts_used += 1
        status, reason = check(uri, timeout=timeout)
        if not _should_retry(status, reason) or attempts_used >= max_attempts:
            return status, reason, attempts_used

        time.sleep(current_delay)
        # Exponential backoff keeps reconnect storms down.
        current_delay = current_delay * 2 if current_delay > 0 else 0

    return 1, "retry loop exited unexpectedly", attempts_used


def main() -> int:
    parser = argparse.ArgumentParser(description="Check URI and reconnect again on failures.")
    parser.add_argument("uri", help="URI to query")
    parser.add_argument("--retries", type=int, default=3, help="Reconnect attempts after first try")
    parser.add_argument("--delay", type=float, default=1.0, help="Initial delay between retries")
    parser.add_argument("--timeout", type=int, default=10, help="Per-request timeout in seconds")
    args = parser.parse_args()

    status, reason, attempts = connect_again(
        args.uri,
        retries=args.retries,
        delay_seconds=args.delay,
        timeout=args.timeout,
    )
    print(f"status={status} reason={reason} attempts={attempts}")
    return 0 if 200 <= status < 400 else 1


if __name__ == "__main__":
    raise SystemExit(main())
