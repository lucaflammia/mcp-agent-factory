# M004: M004

**Vision:** 

## Slices

- [x] **S01: SSE /v1 Endpoints + Connected Event** `risk:high` `depends:[]`
  > After this: 

- [x] **S02: PKCE Hardening + 401 on Missing/Invalid Token** `risk:medium` `depends:[S01]`
  > After this: 

- [x] **S03: Client Bridge — PKCE + Token Cache + SSE Consumption** `risk:medium` `depends:[S02]`
  > After this: 

- [x] **S04: Launch Script + mcp.json External Config** `risk:low` `depends:[S03]`
  > After this:
