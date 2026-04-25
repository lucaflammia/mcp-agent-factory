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

State backend:
  When AUTH_REDIS_URL is set, client registrations and auth codes are stored
  in Redis (codes with a 600-second TTL, registrations with no expiry).
  When AUTH_REDIS_URL is unset, FakeRedis is used for test isolation.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
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
# Redis factory — real client when AUTH_REDIS_URL is set, FakeRedis otherwise
# ---------------------------------------------------------------------------

# Namespace prefix keeps auth keys isolated from gateway session keys.
_KEY_PREFIX_CLIENT = "auth:client:"
_KEY_PREFIX_CODE = "auth:code:"
_CODE_TTL_SECONDS = 600  # 10 minutes


def _make_auth_redis():
	url = os.getenv("AUTH_REDIS_URL") or os.getenv("REDIS_URL")
	if url:
		import redis as _sync_redis
		client = _sync_redis.from_url(url, decode_responses=True, socket_connect_timeout=2)
		try:
			client.ping()
			return client
		except Exception as exc:
			logger.warning(
				json.dumps({
					"event": "auth_redis_unavailable",
					"url": url,
					"error": str(exc),
					"fallback": "fakeredis",
				})
			)
	import fakeredis
	return fakeredis.FakeRedis(decode_responses=True)


# Module-level store — replaced in tests via _set_auth_redis()
_auth_redis = _make_auth_redis()


def _set_auth_redis(client: Any) -> None:
	"""Inject a custom Redis client for tests."""
	global _auth_redis
	_auth_redis = client


# ---------------------------------------------------------------------------
# Redis-backed store helpers
# ---------------------------------------------------------------------------

def _store_client(client_id: str, data: dict) -> None:
	_auth_redis.set(f"{_KEY_PREFIX_CLIENT}{client_id}", json.dumps(data))


def _load_client(client_id: str) -> dict | None:
	raw = _auth_redis.get(f"{_KEY_PREFIX_CLIENT}{client_id}")
	return json.loads(raw) if raw else None


def _store_code(code: str, data: dict) -> None:
	_auth_redis.setex(f"{_KEY_PREFIX_CODE}{code}", _CODE_TTL_SECONDS, json.dumps(data))


def _load_and_delete_code(code: str) -> dict | None:
	"""Atomic load-and-delete for one-time-use codes."""
	key = f"{_KEY_PREFIX_CODE}{code}"
	raw = _auth_redis.getdel(key)
	return json.loads(raw) if raw else None


# ---------------------------------------------------------------------------
# JWT key (shared with Resource Server via set_jwt_key / get_jwt_key)
# ---------------------------------------------------------------------------

_JWT_KEY: OctKey | None = None


def get_jwt_key() -> OctKey:
	global _JWT_KEY
	if _JWT_KEY is None:
		secret = os.getenv("JWT_SECRET")
		if secret:
			_JWT_KEY = OctKey.import_key(secret.encode())
		else:
			_JWT_KEY = OctKey.generate_key(256, is_private=True)
			logger.warning(json.dumps({
				"event": "jwt_key_auto_generated",
				"warning": (
					"JWT_SECRET not set — ephemeral key in use. Tokens issued by this "
					"server will be rejected by the gateway (different process, different key). "
					"Set JWT_SECRET to the same value in both servers."
				),
			}))
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
	client_id: str
	client_secret: str
	grant_type: str = "authorization_code"
	# authorization_code fields (required for that grant type)
	code: str | None = None
	code_verifier: str | None = None


# ---------------------------------------------------------------------------
# PKCE helpers
# ---------------------------------------------------------------------------

def _compute_s256(verifier: str) -> str:
	digest = hashlib.sha256(verifier.encode("ascii")).digest()
	return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

_AUTH_ISSUER = os.getenv("AUTH_ISSUER", "http://localhost:8001")


@auth_app.get("/.well-known/oauth-authorization-server")
async def oauth_discovery() -> JSONResponse:
    """RFC 8414 OAuth 2.0 Authorization Server Metadata."""
    return JSONResponse({
        "issuer": _AUTH_ISSUER,
        "authorization_endpoint": f"{_AUTH_ISSUER}/authorize",
        "token_endpoint": f"{_AUTH_ISSUER}/token",
        "registration_endpoint": f"{_AUTH_ISSUER}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "client_credentials"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "scopes_supported": sorted(VALID_SCOPES),
    })


@auth_app.post("/register")
async def register_client(req: ClientRegistrationRequest) -> dict:
	"""Register an OAuth 2.1 client."""
	_store_client(req.client_id, {
		"client_secret": req.client_secret,
		"redirect_uri": req.redirect_uri,
		"scope": req.scope,
	})
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
	if _load_client(client_id) is None:
		raise HTTPException(status_code=400, detail=f"Unknown client: {client_id!r}")

	code = secrets.token_urlsafe(32)
	_store_code(code, {
		"code_challenge": code_challenge,
		"user_id": user_id,
		"scope": scope,
		"client_id": client_id,
	})
	logger.info(json.dumps({
		"event": "code_issued",
		"client_id": client_id,
		"scope": scope,
		"user_id": user_id,
	}))
	return {"code": code}


def _issue_token(client_id: str, scope: str, sub: str) -> dict:
	"""Mint a signed JWT and return the token response dict."""
	now = int(time.time())
	session_id = generate_session_id(sub)
	granted_scopes = " ".join(sorted(expand_scope(scope)))
	claims: dict[str, Any] = {
		"sub": sub,
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
		"client_id": client_id,
		"scope": granted_scopes,
		"aud": "mcp-server",
		"session_id": session_id,
	}))
	return {
		"access_token": access_token,
		"token_type": "bearer",
		"expires_in": 3600,
		"scope": granted_scopes,
	}


@auth_app.post("/token")
async def token(req: TokenRequest) -> dict:
	"""
	Exchange a credential for a JWT access token.

	Supports two grant types:
	- ``authorization_code`` (PKCE S256): interactive browser flow for human users.
	- ``client_credentials``: machine-to-machine; no code or verifier needed.
	"""
	client = _load_client(req.client_id)
	if client is None or client["client_secret"] != req.client_secret:
		raise HTTPException(status_code=401, detail="Invalid client credentials")

	if req.grant_type == "client_credentials":
		scope = client.get("scope", "tools:call")
		return _issue_token(req.client_id, scope, sub=req.client_id)

	if req.grant_type == "authorization_code":
		if not req.code or not req.code_verifier:
			raise HTTPException(
				status_code=400,
				detail="authorization_code grant requires code and code_verifier",
			)
		# Atomic load-and-delete ensures one-time use even under concurrent requests
		code_data = _load_and_delete_code(req.code)
		if code_data is None:
			raise HTTPException(status_code=400, detail="Invalid or expired authorization code")

		if code_data["client_id"] != req.client_id:
			raise HTTPException(status_code=400, detail="client_id mismatch")

		# PKCE S256 verification
		expected_challenge = _compute_s256(req.code_verifier)
		if expected_challenge != code_data["code_challenge"]:
			raise HTTPException(status_code=400, detail="PKCE code_verifier verification failed")

		return _issue_token(req.client_id, code_data["scope"], sub=code_data["user_id"])

	raise HTTPException(status_code=400, detail="Unsupported grant_type")
