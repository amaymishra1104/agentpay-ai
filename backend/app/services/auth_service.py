"""
Authentication & Server-Authoritative Identity Service.

Issues and cryptographically verifies HMAC-signed session tokens.
Enforces that customer_id used for authorization is derived strictly from
the verified token and never from untrusted client parameters.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import Header, HTTPException, status

from app.config import get_settings


class AuthError(Exception):
    """Base exception for authentication errors."""
    pass


class InvalidTokenError(AuthError):
    """Raised when a session token is tampered, malformed, or invalid."""
    pass


class ExpiredTokenError(AuthError):
    """Raised when a session token has expired."""
    pass


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64decode(data_str: str) -> bytes:
    padding = 4 - (len(data_str) % 4)
    if padding != 4:
        data_str += "=" * padding
    return base64.urlsafe_b64decode(data_str.encode("utf-8"))


def create_session_token(
    customer_id: str,
    expires_in_seconds: int | None = None,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """
    Generate an HMAC-SHA256 signed session token for a given customer identity.
    """
    if not customer_id or not str(customer_id).strip():
        raise ValueError("customer_id is required to create a session token")

    settings = get_settings()
    expiry = expires_in_seconds if expires_in_seconds is not None else settings.session_expiry_seconds
    now = int(time.time())

    payload = {
        "customer_id": str(customer_id).strip(),
        "iat": now,
        "exp": now + expiry,
    }
    if extra_claims:
        payload.update(extra_claims)

    payload_json = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_b64 = _b64encode(payload_json)

    secret = settings.session_secret.encode("utf-8")
    signature = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    sig_b64 = _b64encode(signature)

    return f"{payload_b64}.{sig_b64}"


def verify_session_token(token: str) -> dict[str, Any]:
    """
    Cryptographically verify the session token's HMAC-SHA256 signature and expiry.
    Returns the decoded claims dictionary.
    """
    if not token or not isinstance(token, str):
        raise InvalidTokenError("Session token must be a non-empty string")

    parts = token.strip().split(".")
    if len(parts) != 2:
        raise InvalidTokenError("Malformed session token format")

    payload_b64, sig_b64 = parts[0], parts[1]

    settings = get_settings()
    secret = settings.session_secret.encode("utf-8")

    expected_sig = hmac.new(secret, payload_b64.encode("utf-8"), hashlib.sha256).digest()
    expected_sig_b64 = _b64encode(expected_sig)

    if not hmac.compare_digest(sig_b64, expected_sig_b64):
        raise InvalidTokenError("Invalid session token signature")

    try:
        payload_bytes = _b64decode(payload_b64)
        claims = json.loads(payload_bytes.decode("utf-8"))
    except Exception as exc:
        raise InvalidTokenError("Failed to decode session token payload") from exc

    if "customer_id" not in claims or not claims["customer_id"]:
        raise InvalidTokenError("Missing customer_id in session token")

    exp = claims.get("exp")
    if exp is not None and int(time.time()) > int(exp):
        raise ExpiredTokenError("Session token has expired")

    return claims


def get_authenticated_customer_id(
    authorization: str | None = Header(None, alias="Authorization"),
    x_session_token: str | None = Header(None, alias="X-Session-Token"),
) -> str:
    """
    FastAPI dependency for protected endpoints.
    Extracts and verifies the HMAC session token from Authorization: Bearer <token>
    or X-Session-Token: <token>.
    Returns the authoritative customer_id.
    """
    raw_token = None

    if authorization and authorization.startswith("Bearer "):
        raw_token = authorization.split(" ", 1)[1].strip()
    elif x_session_token:
        raw_token = x_session_token.strip()

    if not raw_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required: missing session token. Please provide Authorization: Bearer <token>.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        claims = verify_session_token(raw_token)
        return claims["customer_id"]
    except ExpiredTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired. Please re-authenticate.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or tampered session token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
