"""HTTP-based Matrix API requests.

All functions use ONLY stdlib.
"""

import json
import urllib.request
import urllib.error


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
    headers = {
        "Authorization": f"Bearer {config['access_token']}",
        "Content-Type": "application/json"
    }

    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        try:
            error_json = json.loads(error_body)
            return {
                "error": error_json.get("error", error_body),
                "errcode": error_json.get("errcode")
            }
        except json.JSONDecodeError:
            return {"error": error_body, "errcode": str(e.code)}
