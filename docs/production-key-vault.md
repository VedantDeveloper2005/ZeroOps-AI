# Production Key Vault Checklist

Store the following values as Azure Key Vault secrets, then inject them into the ZeroOps API as Key Vault references using the matching environment-variable names.

| Environment variable | Key Vault secret name | Required | Purpose |
|---|---|---:|---|
| `DATABASE_URL` | `zeroops-database-url` | Yes | PostgreSQL connection string for ZeroOps data |
| `JWT_SECRET` | `zeroops-jwt-secret` | Yes | Long random signing secret for login tokens |
| `GITHUB_CLIENT_ID` | `zeroops-github-client-id` | Yes for GitHub source | GitHub OAuth application ID |
| `GITHUB_CLIENT_SECRET` | `zeroops-github-client-secret` | Yes for GitHub source | GitHub OAuth application secret |
| `OPENAI_API_KEY` | `zeroops-ai-api-key` | Only if AI review is enabled | Server-side repository-review access key |
| `GITHUB_TOKEN` | `zeroops-github-server-token` | Optional | Server-side fallback for repository access |
| `STRIPE_SECRET_KEY` | `zeroops-stripe-secret-key` | Only if billing is enabled | Stripe server secret |
| `STRIPE_WEBHOOK_SECRET` | `zeroops-stripe-webhook-secret` | Only if billing is enabled | Stripe webhook verification secret |

These are configuration values, not Key Vault secrets: `APP_ENV=production`, `FRONTEND_URL`, `CORS_ORIGINS`, `ALLOWED_HOSTS`, `ZEROOPS_BACKEND_URL`, `AZURE_KEYVAULT_URL`, `AZURE_DEFAULT_REGION`, `MAX_CODE_UPLOAD_MB`, `DB_SSL_VERIFY=true`, `OPENAI_MODEL=gpt-5.4-mini`, and `AI_MODEL_TIMEOUT_SECONDS=30`.

## AI review boundaries

Repository scanning derives launch-critical facts locally: framework, commands, port, detected environment-variable names, dependencies, and resource heuristics. The optional AI review receives only a bounded allowlist of repository manifests and readme files; `.env`, private keys, credentials, and secret-named files are excluded. Its structured output is limited to an explanation, launch risks, recommendations, and unresolved questions. It cannot alter launch configuration, generate costs, create credentials, or mark a deployment live.

Failure review follows the same boundary: deployment diagnostics are redacted before review and the returned incident summary is schema-validated. Model and provider identifiers remain server-side operational metadata and are never returned in the customer interface.

## Customer hosting connection

Customers enter these non-secret Azure values in **Settings → Hosting**:

- Tenant ID
- Subscription ID
- Application (client) ID
- Resource group
- Region
- Container Registry login server
- Linux App Service plan name
- Optional application-name prefix

The customer’s application secret is written to Key Vault as `zo-byos-sp-<user-id>`. Project secrets use `zo-<project-id>-<variable-name>`. Neither is returned by the API.

Project-secret values are retained only in Key Vault. The application database stores their names and secret flag, never the value; existing database secret values are migrated to Key Vault and cleared during startup once vault access is available.

## Minimum permissions

- ZeroOps API managed identity: `Key Vault Secrets Officer` on the ZeroOps vault to create, read, and revoke customer deployment credentials.
- Customer deployment application: `Contributor` on its resource group, `AcrPush` on its registry, and `User Access Administrator` on that registry scope so ZeroOps can grant the deployed application its `AcrPull` identity permission.
- The customer application’s managed identity receives `AcrPull` automatically during deployment.

Keep the customer deployment resource group dedicated to ZeroOps applications. This gives customers clear cost boundaries and prevents the launch path from modifying unrelated Azure resources.
