# Azure Hosting Manual Verification

Use a real non-production Azure subscription. Do not use placeholder credentials or a local secret store.

1. Sign in to ZeroOps and open **Hosting** in settings.
2. Enter the tenant, subscription, application client, resource group, registry login server, and application environment. Supply the client secret only when connecting or rotating it.
3. Confirm the connection succeeds. The response must never contain the client secret.
4. Launch a small repository or ZIP with a health endpoint.
5. Confirm the deployment log reports an Azure build, Azure ready revision, and a verified public address.
6. Open the returned address. It must be an Azure-issued URL and respond over HTTPS.
7. Check the deployment record: status is `running`, the URL is present, and the recorded revision was returned by Azure.
8. Disconnect the Azure account and confirm its Key Vault credential is deleted; a new launch must be blocked until a connection is re-established.
