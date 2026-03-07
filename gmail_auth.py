import httpx

TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"
REVOKE_URL    = "https://oauth2.googleapis.com/revoke"

# The scope we requested — read-only, cannot send or delete
REQUIRED_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def validate_token(access_token):
    """
    Validate a Google OAuth access token.
    Returns { success, email, scopes } or { success: False, error }
    """
    r = httpx.get(TOKENINFO_URL, params={"access_token": access_token}, timeout=10)

    if r.status_code != 200:
        return {"success": False, "error": "Invalid or expired Google token."}

    info = r.json()

    # Checking the required scope is granted
    granted = info.get("scope", "")
    if REQUIRED_SCOPE not in granted:
        return {
            "success": False,
            "error": "Gmail read permission was not granted. Please allow access and try again.",
        }

    return {
        "success": True,
        "email":   info.get("email", ""),
        "scopes":  granted,
    }


def revoke_token(access_token):
    """
    Revoke a Google OAuth token — called when user closes the dialog.
    Best-effort, errors are swallowed.
    """
    try:
        httpx.post(REVOKE_URL, params={"token": access_token}, timeout=8)
    except Exception:
        pass