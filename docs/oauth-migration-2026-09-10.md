# OAuth migration verification — 2026-09-10

Production application: https://zeroopsai-v2.azurewebsites.net

Backend: https://zeroops-backend-v2.azurewebsites.net

## Cause

The migrated backend retained the previous Google OAuth client. Google rejected
the new frontend callback with `redirect_uri_mismatch`. The new Google Cloud
project had no Auth Platform configuration. The existing GitHub OAuth app still
used the previous frontend hostname for its homepage and callback.

## Applied configuration

Google Cloud project: `zeroops-ai-504108`, owned through the new account.

- Created Google Auth branding and the `ZeroOps AI Production` web client.
- Authorized JavaScript origin: `https://zeroopsai-v2.azurewebsites.net`.
- Authorized callback: `https://zeroopsai-v2.azurewebsites.net/api/auth/google/callback`.
- Linked the existing production homepage, `/privacy`, and `/terms` pages.
- Audience: External; publishing status: In production.
- Sign-in requests use only `openid email profile`.
- Saved new versions of `zeroops-google-client-id` and
  `zeroops-google-client-secret` in `zeroops-kv-v2` and restarted
  `zeroops-backend-v2`. No credentials are recorded in this document.

GitHub OAuth app: `ZeroOps AI`, owned by `VedantDeveloper2005`, application ID
`3629381`.

- Homepage: `https://zeroopsai-v2.azurewebsites.net`.
- Callback: `https://zeroopsai-v2.azurewebsites.net/api/auth/github/callback`.
- Disabled wildcard matching for the callback.
- Reused the existing client and secret; no permission scopes were added.

## Live verification

- GitHub login completed and redirected to
  `/dashboard/repositories?auth=success`.
- Authenticated workspace loaded and listed real repositories from the
  connected `VedantDeveloper2005` account.
- Signed out of ZeroOps before independently testing Google login.
- Google account selection and basic profile/email consent completed, returning
  to the authenticated workspace with the existing GitHub connection intact.
- Both live authorization endpoints returned HTTP 302 with their configured
  clients and exact production callback URLs.
- Both provider cancellation callbacks returned to the production login page.
- Existing `/privacy` and `/terms` routes returned HTTP 200.
- Backend health returned HTTP 200 after restart.

This repair changed provider configuration and Key Vault values. No application
code changes or new application deployment were required. The website's existing
legal pages were linked as provided; their draft content was not revised.

## Future hostname changes

Update provider callbacks together with the backend's `FRONTEND_URL` and the
frontend's backend proxy destination. Production OAuth callbacks must use the
frontend hostname so session cookies remain on the same origin as API requests.
After changing Key Vault configuration, restart the backend and verify a fresh
browser login through both providers.
