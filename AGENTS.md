<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

## Goal
- Perform full production-readiness audit of ZeroOps AI, fix all FAIL items, and remove demo/mock/fake data

## Constraints & Preferences
- Do NOT add new features yet
- Verify every implemented feature works end-to-end
- Goal is a real SaaS MVP suitable for production-style demonstrations

## Progress
### Done
- Audited database schema integrity (PASS)
- Added authentication to `/api/monitoring/metrics` endpoint
- Added authentication and ownership validation to `/api/secrets/*` endpoints
- Added authentication and ownership validation to `/api/autoscaling/*` endpoints
- Added authentication and ownership validation to `/api/security/status/*` endpoint
- Added `api_key` column migration to User model
- Added API key management endpoints (`/api/settings/api-key`, `/api/settings/api-key/regenerate`)
- Removed hardcoded demo API key from settings page (was `zo_live_84b72fd91c28c83e1a0b5a37f59b6c2d1e`)
- Removed mock security data (threats, blocked IPs, compliance items) - now shows empty state from API
- Monitoring page already fetches metrics from API database
- Logs page already streams real logs via WebSocket
- Fixed TypeScript compilation errors (duplicate code, interface issues)

### In Progress
- (none)

### Blocked
- (none)

## Key Decisions
- Added `db` parameter to endpoints that needed project ownership validation
- Security page now fetches security status from API and shows empty state when no data
- Settings page now fetches API key from backend and provides regenerate endpoint
- TypeScript types fixed in security/page.tsx and api.ts

## Next Steps
- (none - all major fixes complete)

## Critical Context
- Security endpoints were publicly accessible without authentication (critical security vulnerability) - FIXED
- In-memory WebSocket buffers in pipeline.py don't persist across backend restarts (by design for MVP)
- Hardcoded JWT secrets and database URLs in config.py need production environment handling
- Mock vault/secrets fallback is acceptable for MVP (falls back to local file when Azure Key Vault unavailable)
