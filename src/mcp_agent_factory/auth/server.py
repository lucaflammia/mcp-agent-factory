"""
OAuth 2.1 Authorization Server with PKCE (S256 only).

Endpoints:
  POST /register    — client registration
  GET  /authorize   — authorization code request (PKCE S256 required)
  POST /token       — authorization code exchange

Security properties implemented:
  - PKCE S256 only (plain method rejected — RFC 7636 §4.2 recommendation)
  - One-time authorization codes (deleted after exchange)
  - audience-bound JWTs (aud='mcp-server')
  - User-bound session IDs in token claims

Scope definitions:
  tools:list  — may call tools/list
  tools:call  — may call tools/call
  tools:all   — shorthand for both (expanded at issuance)

In-memory stores (acceptable for tests; replace with Redis in production —
documented in docs/security_audit.md).
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
from contextlib import asynccontextmanager
from typing import Any

from authlib.jose import OctKey, jwt
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from mcp_agent_factory.auth.session import generate_session_id

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scope registry
# ---------------------------------------------------------------------------

VALID_SCOPES = {"tools:list", "tools:call", "tools:all"}
SCOPE_EXPANSION = {
	"tools:all": {"tools:list", "tools:call"},
}


def expand_scope(scope: str) -> set[str]:
	"""Expand shorthand scopes into their constituent parts."""
	parts: set[str] = set()
	for s in scope.split():
		parts.update(SCOPE_EXPANSION.get(s, {s}))
	return parts


# ---------------------------------------------------------------------------
# In-memory stores (replace with Redis in production)
# ---------------------------------------------------------------------------

_clients: dict[str, dict] = {}   # client_id → {client_secret, redirect_uri, scope}
_codes: dict[str, dict] = {}     # code → {code_challenge, user_id, scope, client_id}


# ---------------------------------------------------------------------------
# JWT key (shared with Resource Server via set_jwt_key / get_jwt_key)
# ---------------------------------------------------------------------------

_JWT_KEY: OctKey | None = None


def get_jwt_key() -> OctKey:
	global _JWT_KEY
	if _JWT_KEY is None:
		_JWT_KEY = OctKey.generate_key(256, is_private=True)
	return _JWT_KEY


def set_jwt_key(key: OctKey) -> None:
	"""Allow tests to inject a known key shared with the Resource Server."""
	global _JWT_KEY
	_JWT_KEY = key


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
	# Ensure JWT key is generated at startup
	key = get_jwt_key()
	logger.info(json.dumps({"event": "auth_server_start", "key_alg": "HS256"}))
	yield


auth_app = FastAPI(
	title="OAuth 2.1 Authorization Server",
	description="PKCE-based OAuth 2.1 auth server for MCP agents",
	version="0.1.0",
	lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------

class ClientRegistrationRequest(BaseModel):
	client_id: str
	client_secret: str
	redirect_uri: str
	scope: str = "tools:call"


class TokenRequest(BaseModel):
	code: str
	code_verifier: str
	client_id: str
	client_secret: str
	grant_type: str = "authorization_code"


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _compute_s256(verifier: str) -> str:
	digest = hashlib.sha256(verifier.encode("ascii")).digest()
	return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@auth_app.post("/register")
async def register_client(req: ClientRegistrationRequest) -> dict:
	"""Register an OAuth 2.1 client."""
	_clients[req.client_id] = {
		"client_secret": req.client_secret,
		"redirect_uri": req.redirect_uri,
		"scope": req.scope,
	}
	logger.info(json.dumps({
		"event": "client_registered",
		"client_id": req.client_id,
		"scope": req.scope,
	}))
	return {"client_id": req.client_id, "registered": True}


@auth_app.get("/authorize")
async def authorize(
	client_id: str = Query(...),
	code_challenge: str = Query(...),
	code_challenge_method: str = Query(...),
	scope: str = Query("tools:call"),
	user_id: str = Query("anonymous"),
) -> dict:
	"""
	Issue an authorization code.

	Rejects any code_challenge_method other than 'S256'.
	"""
	if code_challenge_method != "S256":
		raise HTTPException(
			status_code=400,
			detail="Only S256 code_challenge_method is supported (plain is not allowed)",
		)
	if client_id not in _clients:
		raise HTTPException(status_code=400, detail=f"Unknown client: {client_id!r}")

	code = secrets.token_urlsafe(32)
	_codes[code] = {
		"code_challenge": code_challenge,
		"user_id": user_id,
		"scope": scope,
		"client_id": client_id,
	}
	logger.info(json.dumps({
		"event": "code_issued",
		"client_id": client_id,
		"scope": scope,
		"user_id": user_id,
	}))
	return {"code": code}


@auth_app.post("/token")
async def token(req: TokenRequest) -> dict:
	"""
	Exchange an authorization code for a JWT access token.

	Validates PKCE S256: SHA256(code_verifier) must equal stored code_challenge.
	Codes are one-time-use — deleted immediately after successful exchange.
	"""
	if req.grant_type != "authorization_code":
		raise HTTPException(status_code=400, detail="Unsupported grant_type")

	code_data = _codes.get(req.code)
	if code_data is None:
		raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

	if code_data["client_id"] != req.client_id:
		raise HTTPException(status_code=400, detail="client_id mismatch")

	client = _clients.get(req.client_id)
	if client is None or client["client_secret"] != req.client_secret:
		raise HTTPException(status_code=401, detail="Invalid client credentials")

	# PKCE S256 verification
	expected_challenge = _compute_s256(req.code_verifier)
	if expected_challenge != code_data["code_challenge"]:
		raise HTTPException(status_code=400, detail="PKCE code_verifier verification failed")

	# One-time use: delete code immediately
	del _codes[req.code]

	# Build token claims
	now = int(time.time())
	scope = code_data["scope"]
	user_id = code_data["user_id"]
	session_id = generate_session_id(user_id)
	granted_scopes = " ".join(sorted(expand_scope(scope)))

	claims: dict[str, Any] = {
		"sub": user_id,
		"aud": "mcp-server",
		"scope": granted_scopes,
		"session_id": session_id,
		"iat": now,
		"exp": now + 3600,
	}

	key = get_jwt_key()
	access_token = jwt.encode({"alg": "HS256"}, claims, key).decode("ascii")

	logger.info(json.dumps({
		"event": "token_issued",
		"client_id": req.client_id,
		"scope": granted_scopes,
		"aud": "mcp-server",
		"session_id": session_id,
		# Never log the token value
	}))

	return {
		"access_token": access_token,
		"token_type": "bearer",
		"expires_in": 3600,
		"scope": granted_scopes,
	}
