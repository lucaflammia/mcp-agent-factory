"""
Session ID generation and validation.

Format: ``{user_id}:{token_part}``
- user_id:   caller-provided identifier (non-empty, no colon)
- token_part: cryptographic random via secrets.token_urlsafe(32)

This format makes sessions user-bound and non-deterministic, satisfying
the R012 requirement and the Fargin Curriculum's session integrity spec.
"""
from __future__ import annotations

import secrets


def generate_session_id(user_id: str) -> str:
	"""Return a new non-deterministic session ID bound to *user_id*."""
	if not user_id or ":" in user_id:
		raise ValueError("user_id must be non-empty and must not contain ':'")
	token_part = secrets.token_urlsafe(32)
	return f"{user_id}:{token_part}"


def parse_session_id(session_id: str) -> tuple[str, str]:
	"""
	Split *session_id* into (user_id, token_part).

	Raises ValueError if the format is invalid.
	"""
	if ":" not in session_id:
		raise ValueError(f"Invalid session_id format: {session_id!r}")
	user_id, _, token_part = session_id.partition(":")
	if not user_id or not token_part:
		raise ValueError(f"Invalid session_id format: {session_id!r}")
	return user_id, token_part


def validate_session_id(session_id: str) -> bool:
	"""Return True if *session_id* has the expected user_id:token format."""
	try:
		parse_session_id(session_id)
		return True
	except ValueError:
		return False
