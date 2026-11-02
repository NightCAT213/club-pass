import base64
import hashlib
import hmac
import re
import secrets

# A pass contains a random opaque nonce, not a guessable guest ID.
# The HMAC prevents anyone from changing or inventing a valid pass.
PASS_PATTERN = re.compile(r"^bc1\.([A-Za-z0-9_-]{32})\.([A-Za-z0-9_-]{43})$")


def new_nonce() -> str:
    return secrets.token_urlsafe(24)


def make_pass(nonce: str, signing_key: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{32}", nonce):
        raise ValueError("Invalid nonce")
    body = f"bc1.{nonce}"
    signature = hmac.new(signing_key.encode(), body.encode(), hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(signature).decode().rstrip("=")
    return f"{body}.{encoded}"


def read_pass(code: str, signing_key: str) -> str | None:
    match = PASS_PATTERN.fullmatch(code.strip())
    if match is None:
        return None
    nonce = match.group(1)
    expected = make_pass(nonce, signing_key)
    if not hmac.compare_digest(expected, code.strip()):
        return None
    return nonce
