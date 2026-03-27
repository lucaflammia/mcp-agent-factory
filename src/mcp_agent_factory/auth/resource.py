"""
Resource Server middleware for the OAuth 2.1 / MCP integration.

Provides a FastAPI dependency (verify_token) that:
  1. Extracts the Bearer token from the Authorization header.
  2. Decodes and validates the JWT using the shared OctKey.
  3. Enforces audience binding: aud claim MUST equal 'mcp-server'.
     Any other audience → HTTP 401 (confused deputy protection).
  4. Enforces scope: required_scope must appear in the token's scope claim.
     Missing scope → HTTP 403.

The JWT key must be the same key used by the Authorization Server.
Use set_jwt_key() in tests to inject the shared key before testing.
"""
from __future__ import annotations

import json
import logging
from typing import Any

from authlib.jose import OctKey, jwt
from authlib.jose.errors import JoseError
from fastapi import Header, HTTPException

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Key management — shared with auth/server.py
# ---------------------------------------------------------------------------

_JWT_KEY: OctKey | None = None

EXPECTED_AUDIENCE = "mcp-server"


def get_jwt_key() -> OctKey:
    """Return the current JWT validation key."""
    global _JWT_KEY
    if _JWT_KEY is None:
        raise RuntimeError(
            "JWT key not set. Call set_jwt_key() with the Auth Server's key before use."
        )
    return _JWT_KEY


def set_jwt_key(key: OctKey) -> None:
    """Inject the JWT key (typically the Auth Server's key — used in tests and startup)."""
    global _JWT_KEY
    _JWT_KEY = key


# ---------------------------------------------------------------------------
# Token verification dependency
# ---------------------------------------------------------------------------

def make_verify_token(required_scope: str):
    """
    Factory returning a FastAPI dependency that validates a Bearer JWT.

    Usage::

        @app.post("/mcp")
        async def endpoint(claims = Depends(make_verify_token("tools:call"))):
            ...
    """
    async def verify_token(authorization: str | None = Header(None)) -> dict[str, Any]:
        if authorization is None or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Missing or malformed Authorization header")

        raw_token = authorization.split(" ", 1)[1].strip()

        try:
            key = get_jwt_key()
            claims = jwt.decode(raw_token, key)
            claims.validate()
        except (JoseError, RuntimeError, Exception) as exc:
            logger.warning(json.dumps({"event": "token_invalid", "reason": str(exc)}))
            raise HTTPException(status_code=401, detail=f"Invalid token: {exc}")

        # Confused deputy protection: reject tokens intended for other audiences
        token_aud = claims.get("aud")
        if token_aud != EXPECTED_AUDIENCE:
            logger.warning(json.dumps({
                "event": "confused_deputy_rejected",
                "expected_aud": EXPECTED_AUDIENCE,
                "got_aud": token_aud,
            }))
            raise HTTPException(
                status_code=401,
                detail=f"Invalid audience: expected '{EXPECTED_AUDIENCE}', got '{token_aud}'",
            )

        # Scope enforcement
        token_scopes = set(claims.get("scope", "").split())
        if required_scope not in token_scopes:
            logger.warning(json.dumps({
                "event": "scope_rejected",
                "required": required_scope,
                "granted": list(token_scopes),
            }))
            raise HTTPException(
                status_code=403,
                detail=f"Insufficient scope: '{required_scope}' required",
            )

        logger.info(json.dumps({
            "event": "token_accepted",
            "sub": claims.get("sub"),
            "scope": claims.get("scope"),
            "session_id": claims.get("session_id"),
        }))
        return dict(claims)

    return verify_token
