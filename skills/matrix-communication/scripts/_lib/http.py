"""HTTP-based Matrix API requests.

All functions use ONLY stdlib.
"""

import contextlib
import json
import socket
import urllib.parse
import urllib.request
import urllib.error


_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _require_http_scheme(url: str) -> None:
    scheme = urllib.parse.urlparse(url).scheme
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Refusing to fetch URL with scheme {scheme!r}; only http/https allowed"
        )


@contextlib.contextmanager
def _prefer_ipv4():
    """Temporarily prefer IPv4 addresses in DNS resolution.

    Workaround for WSL2 environments where IPv6 routes are often
    unreachable while IPv4 works fine.
    """
    original = socket.getaddrinfo

    def patched(*args, **kwargs):
        results = original(*args, **kwargs)
        return sorted(results, key=lambda r: r[0] != socket.AF_INET)

    socket.getaddrinfo = patched
    try:
        yield
    finally:
        socket.getaddrinfo = original


def _do_request(req: urllib.request.Request) -> dict:
    """Execute a request and return parsed JSON response.

    The caller must have validated the URL scheme via
    ``_require_http_scheme`` before constructing ``req``.
    """
    _require_http_scheme(req.full_url)
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(req) as response:  # noqa: S310 — scheme validated above
        return json.loads(response.read().decode())


def _parse_http_error(e: urllib.error.HTTPError) -> dict:
    """Parse an HTTPError into a result dict."""
    error_body = e.read().decode()
    try:
        error_json = json.loads(error_body)
        return {
            "error": error_json.get("error", error_body),
            "errcode": error_json.get("errcode"),
        }
    except json.JSONDecodeError:
        return {"error": error_body, "errcode": str(e.code)}


def matrix_request(config: dict, method: str, endpoint: str, data: dict = None) -> dict:
    """Make a Matrix API request.

    Args:
        config: Dict with homeserver and access_token
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: API endpoint (e.g., /joined_rooms)
        data: Optional dict to send as JSON body

    Returns:
        Response dict, or dict with 'error' key on failure
    """
    url = f"{config['homeserver']}/_matrix/client/v3{endpoint}"
    _require_http_scheme(url)
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        return _do_request(req)
    except urllib.error.HTTPError as e:
        return _parse_http_error(e)
    except OSError as e:
        if e.errno not in (101, 113):  # ENETUNREACH, EHOSTUNREACH
            return {"error": str(e)}
        # IPv6 likely unreachable — retry with IPv4 preference
        try:
            with _prefer_ipv4():
                req2 = urllib.request.Request(
                    url, data=body, headers=headers, method=method
                )
                return _do_request(req2)
        except urllib.error.HTTPError as e2:
            return _parse_http_error(e2)
        except OSError as e2:
            return {"error": str(e2)}
