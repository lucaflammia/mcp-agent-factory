"""
Auth server entry point and token-generation utility.

Usage
-----
Start the auth server::

    JWT_SECRET=mysecret python -m mcp_agent_factory.auth serve

Generate a GATEWAY_TOKEN for the bridge (without running the auth server)::

    JWT_SECRET=mysecret python -m mcp_agent_factory.auth token [--sub bridge] [--scope tools:call]

Environment variables
---------------------
JWT_SECRET   Shared HMAC secret (required for both serve and token sub-commands).
HOST         Bind address for serve (default: 0.0.0.0).
PORT         Port for serve (default: 8001).
LOG_LEVEL    Uvicorn log level for serve (default: info).
"""
from __future__ import annotations

import argparse
import os
import sys
import time


def _cmd_serve(args: argparse.Namespace) -> None:
    import uvicorn
    from mcp_agent_factory.auth.server import auth_app

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8001"))
    log_level = os.getenv("LOG_LEVEL", "info")
    print(f"Auth server running on http://{host}:{port}", flush=True)
    uvicorn.run(auth_app, host=host, port=port, log_level=log_level)


def _cmd_token(args: argparse.Namespace) -> None:
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        print("ERROR: JWT_SECRET env var is required", file=sys.stderr)
        sys.exit(1)

    from authlib.jose import OctKey, jwt
    from mcp_agent_factory.auth.session import generate_session_id

    key = OctKey.import_key(jwt_secret.encode())
    now = int(time.time())
    claims = {
        "sub": args.sub,
        "aud": "mcp-server",
        "scope": args.scope,
        "session_id": generate_session_id(args.sub),
        "iat": now,
        "exp": now + args.ttl,
    }
    token = jwt.encode({"alg": "HS256"}, claims, key).decode("ascii")
    print(token)


def main() -> None:
    from dotenv import load_dotenv
    load_dotenv()

    parser = argparse.ArgumentParser(prog="python -m mcp_agent_factory.auth")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("serve", help="Start the OAuth 2.1 authorization server")

    token_p = sub.add_parser("token", help="Print a signed GATEWAY_TOKEN to stdout")
    token_p.add_argument("--sub", default="bridge", help="Token subject (default: bridge)")
    token_p.add_argument("--scope", default="tools:call", help="Space-separated scopes")
    token_p.add_argument("--ttl", type=int, default=3600, help="Token TTL in seconds")

    args = parser.parse_args()
    if args.command == "serve":
        _cmd_serve(args)
    elif args.command == "token":
        _cmd_token(args)


if __name__ == "__main__":
    main()
