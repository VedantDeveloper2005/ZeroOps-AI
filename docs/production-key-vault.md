# Production Key Vault Configuration

ZeroOps reads its application configuration directly from Azure Key Vault at
startup. It does not load `.env` files, app-setting secret references, or
plaintext process variables. The only bootstrap settings are:

| App setting | Purpose |
|---|---|
| `APP_ENV=production` | Required exact runtime mode. Missing or unrecognized values stop startup. |
| `AZURE_KEYVAULT_URL` | Key Vault endpoint, for example `https://<vault>.vault.azure.net/`. |
| `AZURE_CLIENT_ID` | Optional selector for a user-assigned managed identity. It is not a secret. |

Enable a managed identity on both the API app and the deployment worker. Do
not configure `AZURE_CLIENT_SECRET`, a database connection string, JWT key, or
provider credential as an application setting.

## Naming convention

Store each setting under `zeroops-<setting-name-in-kebab-case>`. For example:

| Application setting | Key Vault secret name | Required in production |
|---|---|---:|
| `DATABASE_URL` | `zeroops-database-url` | Yes |
| `JWT_SECRET` | `zeroops-jwt-secret` | Yes |
| `FRONTEND_URL` | `zeroops-frontend-url` | Yes |
| `ALLOWED_HOSTS` | `zeroops-allowed-hosts` | Yes |
| `SMTP_USERNAME` | `zeroops-smtp-username` | Yes |
| `SMTP_PASSWORD` | `zeroops-smtp-password` | Yes |
| `SMTP_FROM_EMAIL` | `zeroops-smtp-from-email` | Yes |
| `TWILIO_ACCOUNT_SID` | `zeroops-twilio-account-sid` | When phone verification is enabled |
| `TWILIO_AUTH_TOKEN` | `zeroops-twilio-auth-token` | When phone verification is enabled |
| `TWILIO_FROM_NUMBER` | `zeroops-twilio-from-number` | When phone verification is enabled |
| `WORKER_EVENT_TOKEN` | `zeroops-worker-event-token` | Only for an external worker event relay |
| `DB_SSL_ENABLED` | `zeroops-db-ssl-enabled` | Must remain `true` |
| `DB_SSL_VERIFY` | `zeroops-db-ssl-verify` | Must remain `true` |
| `DB_SSL_ROOT_CERT` | `zeroops-db-ssl-root-cert` | Optional CA bundle path when the image system bundle is not used |
| `WORKER_LEASE_SECONDS` | `zeroops-worker-lease-seconds` | Optional; defaults to `180` |
| `WORKER_HEARTBEAT_SECONDS` | `zeroops-worker-heartbeat-seconds` | Optional; defaults to `30` and must be shorter than the lease |
| `WORKER_MAX_ATTEMPTS` | `zeroops-worker-max-attempts` | Optional; defaults to `3` |
| `GITHUB_CLIENT_ID` | `zeroops-github-client-id` | When GitHub OAuth is enabled |
| `GITHUB_CLIENT_SECRET` | `zeroops-github-client-secret` | When GitHub OAuth is enabled |
| `GOOGLE_CLIENT_ID` | `zeroops-google-client-id` | When Google OAuth is enabled |
| `GOOGLE_CLIENT_SECRET` | `zeroops-google-client-secret` | When Google OAuth is enabled |
| `OPENAI_API_KEY` | `zeroops-ai-api-key` | When OpenAI review is enabled |
| `STRIPE_SECRET_KEY` | `zeroops-stripe-secret-key` | When Stripe billing is enabled |
| `STRIPE_WEBHOOK_SECRET` | `zeroops-stripe-webhook-secret` | When Stripe billing is enabled |

All remaining values use the same convention: `MAX_CODE_UPLOAD_MB` becomes
`zeroops-max-code-upload-mb`, `CORS_ORIGINS` becomes
`zeroops-cors-origins`, and so on. This includes operational values such as
`PORT`, `AZURE_DEFAULT_REGION`, `DB_SSL_ENABLED`, `DB_SSL_VERIFY`, model
names, rate limits, and worker polling. Missing optional values use only their
documented development-safe defaults; missing required production values stop
the application from starting.

Key Vault values are cached per process. Restart the API and worker after a
secret rotation so they fetch the new version.

The frontend build reads the public API origin from
`zeroops-next-public-api-base-url`. GitHub Actions retrieves that value through
Azure OIDC before `next build`; it is intentionally a public URL, not a browser
secret. `NEXT_PUBLIC_*` values cannot be fetched by browser code from Key Vault
because Next.js embeds them into the client bundle at build time.
Set the GitHub repository variable `ZEROOPS_KEYVAULT_NAME` to the vault name
(not its URL), and grant the workflow identity `Key Vault Secrets User`.

## Worker callbacks and deployment data

When using an external worker event relay, generate a long random
`WORKER_EVENT_TOKEN` and store it as `zeroops-worker-event-token`. The API
rejects callbacks without its `X-ZeroOps-Worker-Token` header. The included
worker writes the verified pipeline result directly and does not require the
relay.

The worker no longer stores a decrypted GitHub OAuth token in the deployment
queue. It decrypts the already encrypted user token only for the active
release. Before queueing, the API resolves the project's saved branch to a
complete GitHub commit SHA; the worker checks out that immutable revision.
The startup migration removes the legacy `github_token` column from
`deployment_jobs`.

Queue claims use renewable database leases. A stale claim is automatically
requeued only while its deployment is still `queued` and below the retry cap.
Once a release enters `building`, an expired lease is recorded as a failure
and requires an explicit retry so potentially billable Azure changes are not
silently replayed.

Customer application secrets remain separate from control-plane settings:

- Customer deployment credentials: `zo-byos-sp-<user-id>`
- Project variables: `zo-<project-id>-<variable-name>`

Their values are never stored in the application database or returned by the
API.

## Minimum permissions

- API and worker managed identities: `Key Vault Secrets Officer` on the
  ZeroOps vault. This permits reading control-plane values and creating,
  reading, and deleting customer/project secrets.
- GitHub Actions deployment identity: `Key Vault Secrets User` if it builds
  the frontend using the public API URL stored in Key Vault.
- Customer deployment application: `Contributor` on its dedicated resource
  group, `AcrPush` on its registry, and `User Access Administrator` on that
  registry scope so ZeroOps can grant the deployed application `AcrPull`.

Keep each customer deployment resource group dedicated to ZeroOps workloads.
