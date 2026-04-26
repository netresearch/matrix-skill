"""HTTP wrappers for the Synapse Admin API and Matrix Client-Server API.

Both admin endpoints (under ``/_synapse/admin``) and standard Matrix client
endpoints (under ``/_matrix/client/v3``) are reachable through the same HTTP
helpers.  Most helpers in this module accept an admin token; a few stubs are
provided for endpoints that require client-server semantics.

Stdlib only.
"""

from __future__ import annotations

import contextlib
import json
import socket
import urllib.error
import urllib.parse
import urllib.request


_ALLOWED_SCHEMES = frozenset({"http", "https"})


def _require_http_scheme(url: str) -> None:
    scheme = urllib.parse.urlparse(url).scheme
    if scheme not in _ALLOWED_SCHEMES:
        raise ValueError(
            f"Refusing to fetch URL with scheme {scheme!r}; only http/https allowed"
        )


@contextlib.contextmanager
def _prefer_ipv4():
    """Temporarily prefer IPv4 in DNS resolution (WSL2 workaround)."""
    original = socket.getaddrinfo

    def patched(*args, **kwargs):
        results = original(*args, **kwargs)
        return sorted(results, key=lambda r: r[0] != socket.AF_INET)

    socket.getaddrinfo = patched
    try:
        yield
    finally:
        socket.getaddrinfo = original


_DEFAULT_TIMEOUT = 60


def _do_request(req: urllib.request.Request) -> dict:
    """Execute a request and return parsed JSON response.

    The caller must have validated the URL scheme via
    ``_require_http_scheme`` before constructing ``req``.  A 60-second
    timeout is applied so a hung server does not freeze the script.
    """
    _require_http_scheme(req.full_url)
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    with urllib.request.urlopen(req, timeout=_DEFAULT_TIMEOUT) as response:  # noqa: S310 — scheme validated above
        body = response.read().decode()
        if not body:
            return {}
        return json.loads(body)


def _parse_http_error(e: urllib.error.HTTPError) -> dict:
    error_body = e.read().decode()
    try:
        parsed = json.loads(error_body)
        return {
            "error": parsed.get("error", error_body),
            "errcode": parsed.get("errcode"),
            "status": e.code,
        }
    except json.JSONDecodeError:
        return {"error": error_body, "errcode": str(e.code), "status": e.code}


def _request(url: str, method: str, token: str, data: dict | None) -> dict:
    _require_http_scheme(url)
    headers = {"Authorization": f"Bearer {token}"}
    body = None
    if data is not None:
        headers["Content-Type"] = "application/json"
        body = json.dumps(data).encode()

    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        return _do_request(req)
    except urllib.error.HTTPError as e:
        return _parse_http_error(e)
    except OSError as e:
        if e.errno not in (101, 113):
            return {"error": str(e)}
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


def admin_request(
    config: dict, method: str, endpoint: str, data: dict | None = None
) -> dict:
    """Call a Synapse Admin API endpoint.

    Args:
        config: Dict with ``homeserver`` and ``admin_token`` (or ``access_token``).
        method: HTTP method.
        endpoint: Admin path beginning with ``/v1/...`` or ``/v2/...``
            (the ``/_synapse/admin`` prefix is added automatically).
        data: JSON body, if any.

    Returns:
        Parsed JSON response, or a dict with ``error``/``errcode`` on failure.
    """
    token = config.get("admin_token") or config["access_token"]
    url = f"{config['homeserver']}/_synapse/admin{endpoint}"
    return _request(url, method, token, data)


def client_request(
    config: dict, method: str, endpoint: str, data: dict | None = None
) -> dict:
    """Call a Matrix Client-Server v3 endpoint with the admin token.

    Used for state events and other Matrix-spec calls that the admin token
    can perform (the admin user must be in the room).

    Args:
        config: Dict with ``homeserver`` and ``admin_token`` (or ``access_token``).
        method: HTTP method.
        endpoint: Path beginning with ``/`` (the ``/_matrix/client/v3`` prefix
            is added automatically).
        data: JSON body, if any.
    """
    token = config.get("admin_token") or config["access_token"]
    url = f"{config['homeserver']}/_matrix/client/v3{endpoint}"
    return _request(url, method, token, data)


def quote(value: str) -> str:
    """URL-encode a path segment (room IDs, user IDs, aliases)."""
    return urllib.parse.quote(value, safe="")
