# SPDX-License-Identifier: MIT
# SPDX-FileCopyrightText: Netresearch DTT GmbH

"""HTTP-based Matrix API requests.

All functions use ONLY stdlib.
"""

import contextlib
import http.client
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


def _origin(url: str) -> tuple:
    parts = urllib.parse.urlsplit(url)
    scheme = parts.scheme.lower()
    return (
        scheme,
        (parts.hostname or "").lower(),
        parts.port or (443 if scheme == "https" else 80),
    )


class _SameOriginAuthRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Follow redirects, but send the Authorization header only to the same origin.

    urllib copies every request header onto the redirected request, so a
    redirect to another scheme, host or port would receive the access token.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and _origin(req.full_url) != _origin(newurl):
            new.remove_header("Authorization")
        return new


_OPENER = urllib.request.build_opener(_SameOriginAuthRedirectHandler)


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


def _do_request(req: urllib.request.Request, timeout=None) -> dict:
    """Execute a request and return parsed JSON response.

    The caller must have validated the URL scheme via
    ``_require_http_scheme`` before constructing ``req``.
    """
    _require_http_scheme(req.full_url)
    # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
    kwargs = {} if timeout is None else {"timeout": timeout}
    with _OPENER.open(req, **kwargs) as response:
        return json.loads(response.read().decode())


def _parse_http_error(e: urllib.error.HTTPError) -> dict:
    """Parse an HTTPError into a result dict."""
    try:
        error_body = e.read().decode()
    finally:
        e.close()
    try:
        error_json = json.loads(error_body)
    except json.JSONDecodeError:
        error_json = None
    if not isinstance(error_json, dict):  # not JSON, or [] / null / a string
        return {"error": error_body, "errcode": str(e.code)}
    return {
        "error": error_json.get("error", error_body),
        "errcode": error_json.get("errcode"),
    }


def _lenient_http_error(e: urllib.error.HTTPError) -> dict:
    """_parse_http_error, and an error dict too when the body is cut off."""
    try:
        return _parse_http_error(e)
    except http.client.HTTPException as broken:
        return {
            "error": f"HTTP {e.code} with a broken body ({broken!r})",
            "errcode": str(e.code),
        }


class RequestFailed(OSError):
    """An error answer that a strict caller must not read as "not set"."""


def _strict_http_error(e: urllib.error.HTTPError, endpoint: str) -> dict:
    """The error dict for a 404 M_NOT_FOUND on a state event, else raise.

    A state event that is not set answers 404 M_NOT_FOUND; that is an
    answer. Any other error status (a 502 from a proxy, a 403, a 429) says
    nothing about the room, and reading it as "no name" or "no alias" can
    pick another room.
    """
    try:
        result = _parse_http_error(e)
    except http.client.HTTPException as broken:
        raise RequestFailed(
            f"{endpoint} answered HTTP {e.code} with a broken body ({broken!r})"
        ) from e
    if (
        e.code == 404
        and result.get("errcode") == "M_NOT_FOUND"
        and "/state/" in endpoint
    ):
        return result
    raise RequestFailed(
        f"{endpoint} answered HTTP {e.code}: {result.get('error')}"
    ) from e


def matrix_request(
    config: dict,
    method: str,
    endpoint: str,
    data: dict | None = None,
    api_version: str = "v3",
) -> dict:
    """Make a Matrix API request.

    Args:
        config: Dict with homeserver and access_token
        method: HTTP method (GET, POST, PUT, DELETE)
        endpoint: API endpoint (e.g., /joined_rooms)
        data: Optional dict to send as JSON body
        api_version: Client-API version in the path; the relations endpoint
            exists only under v1

    ``config`` may carry ``timeout`` (seconds per request) and ``strict``. With
    ``strict`` every failure raises instead of coming back as an error dict:
    a transport failure (timeout, refused connection) as its OSError, a broken
    HTTP answer (http.client.HTTPException) and an error status as
    RequestFailed (except 404 M_NOT_FOUND on a state event, which means "not
    set"), and a JSON answer that is not an object as ValueError.

    Returns:
        Response dict, or dict with 'error' key on failure
    """
    timeout = config.get("timeout")
    strict = config.get("strict", False)
    url = f"{config['homeserver']}/_matrix/client/{api_version}{endpoint}"
    _require_http_scheme(url)
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json",
    }

    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        return _checked(_do_request(req, timeout), strict, endpoint)
    except urllib.error.HTTPError as e:
        if strict:
            return _strict_http_error(e, endpoint)
        return _lenient_http_error(e)
    except http.client.HTTPException as e:
        if strict:
            raise RequestFailed(f"{endpoint}: broken HTTP answer ({e!r})") from e
        if isinstance(e, OSError):  # RemoteDisconnected: an answer-less close
            return {"error": str(e)}
        raise
    except OSError as e:
        if e.errno not in (101, 113):  # ENETUNREACH, EHOSTUNREACH
            if strict:
                raise
            return {"error": str(e)}
        # IPv6 likely unreachable — retry with IPv4 preference
        try:
            with _prefer_ipv4():
                req2 = urllib.request.Request(
                    url, data=body, headers=headers, method=method
                )
                return _checked(_do_request(req2, timeout), strict, endpoint)
        except urllib.error.HTTPError as e2:
            if strict:
                return _strict_http_error(e2, endpoint)
            return _lenient_http_error(e2)
        except http.client.HTTPException as e2:
            if strict:
                raise RequestFailed(f"{endpoint}: broken HTTP answer ({e2!r})") from e2
            if isinstance(e2, OSError):
                return {"error": str(e2)}
            raise
        except OSError as e2:
            if strict:
                raise
            return {"error": str(e2)}


def _checked(result, strict: bool, endpoint: str):
    if strict and not isinstance(result, dict):
        raise ValueError(f"{endpoint} answered JSON that is not an object")
    return result


def path_segment(value: str) -> str:
    """URL-encode one path segment (room ID, user ID, event ID).

    Room and event IDs contain characters such as ``!``, ``$``, ``:`` and may
    contain ``/`` or ``?``; unencoded, they can change which endpoint a
    request reaches.
    """
    return urllib.parse.quote(str(value), safe="")
