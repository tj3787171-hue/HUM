# HUM — URI Status Checker

A lightweight command-line tool that checks the HTTP status of one or more URIs.

## Usage

```
python check.py <uri> [uri ...]
```

### Examples

```bash
# Check a single URI
python check.py https://example.com

# Check multiple URIs at once
python check.py https://example.com https://example.org/missing
```

### Output

Each URI is printed with its HTTP status:

```
https://example.com          →  200 OK
https://example.org/missing  →  404 Not Found
```

The script exits with code **0** if all URIs return a successful (< 400) status,
**1** if any URI is unreachable or returns an error status, and **2** if no
arguments are provided.

## Tests

```bash
python -m unittest test_check -v
```

