# Azure BYOS (Bring Your Own Subscription) Onboarding Guide

To configure your own Azure subscription inside ZeroOps AI, you need to create a dedicated Service Principal scoped to a specific resource group with a custom RBAC role ("ZeroOps Scoped Operator"). This ensures that ZeroOps AI can only manage resources inside that group and is strictly prohibited from altering authorization, modifying policy assignments, or accessing resources outside the group.

## Step 1: Create a Dedicated Resource Group
Run the following Azure CLI command to create the resource group where ZeroOps will manage your infrastructure:

```bash
az group create --name "zeroops-resources" --location "eastus"
```

## Step 2: Create the Existing Deployment Target

ZeroOps publishes images to an existing Azure Container Registry (ACR) and
runs them on an existing **Linux** App Service plan. Creating these resources
can incur Azure charges. Choose a globally unique, lowercase ACR name:

```bash
az acr create \
  --resource-group "zeroops-resources" \
  --name "YOUR_UNIQUE_ACR_NAME" \
  --sku "Basic"

az appservice plan create \
  --resource-group "zeroops-resources" \
  --name "zeroops-linux-plan" \
  --location "eastus" \
  --is-linux \
  --sku "B1"
```

The App Service plan must be in the dashboard's configured region. The ACR may
be in another Azure region, although keeping it near the application normally
reduces transfer latency and cost.

## Step 3: Define the Custom RBAC Role
ZeroOps AI requires a custom role that allows full contributor access *except* authorization actions (assigning permissions or role definitions).

Save the following JSON content as `zeroops-operator-role.json`. Replace `YOUR_SUBSCRIPTION_ID` with your actual Azure subscription ID:

```json
{
  "Name": "ZeroOps Scoped Operator",
  "IsCustom": true,
  "Description": "Allows ZeroOps AI to build and publish managed applications in a scoped resource group without broad subscription access.",
  "Actions": [
    "Microsoft.ContainerRegistry/*",
    "Microsoft.Web/*",
    "Microsoft.ContainerService/*",
    "Microsoft.Network/*",
    "Microsoft.Storage/*",
    "Microsoft.Resources/*"
  ],
  "NotActions": [
    "Microsoft.Authorization/*/Write",
    "Microsoft.Authorization/*/Delete"
  ],
  "DataActions": [],
  "NotDataActions": [],
  "AssignableScopes": [
    "/subscriptions/YOUR_SUBSCRIPTION_ID"
  ]
}
```

Then create the role definition:

```bash
az role definition create --role-definition zeroops-operator-role.json
```

The `Microsoft.ContainerRegistry/*` operations cover ACR Tasks builds and image
metadata reads. The `Microsoft.Web/*` operations cover App Service site,
managed-identity, container, settings, restart, and status operations. Keep the
role assignment scoped to the dedicated resource group.

## Step 4: Create the Service Principal
Now, create a Service Principal and obtain the credentials:

```bash
az ad sp create-for-rbac --name "zeroops-operator-sp" --skip-assignment
```

This command will output JSON containing:
- `appId` (Client ID)
- `password` (Client Secret)
- `tenant` (Tenant ID)

**IMPORTANT: Copy these values immediately. The secret cannot be retrieved later.**

## Step 5: Assign the Custom Role to the Service Principal
Scope the Service Principal to the resource group you created in Step 1 using the custom role:

```bash
az role assignment create \
  --assignee "CLIENT_ID_OF_SERVICE_PRINCIPAL" \
  --role "ZeroOps Scoped Operator" \
  --scope "/subscriptions/YOUR_SUBSCRIPTION_ID/resourceGroups/zeroops-resources"
```

## Step 6: Allow the App Identity to Pull from ACR

Each deployed web app uses its own system-assigned managed identity. During a
first deployment, ZeroOps assigns that identity the built-in `AcrPull` role on
the configured registry. The scoped operator role above intentionally excludes
`Microsoft.Authorization/*/Write`, so it **cannot create that role assignment**
by itself.

Choose one of these controlled options:

- Grant the ZeroOps service principal **Role Based Access Control
  Administrator** at the ACR resource scope only, if your policy permits the
  worker to create the `AcrPull` assignment.
- Keep authorization writes outside ZeroOps. After the first deployment creates
  the web app identity, have an Azure administrator assign that identity
  `AcrPull` on the ACR, then retry the deployment.

Do not grant subscription-wide Owner access. Without the `AcrPull` assignment,
the private image cannot start and endpoint verification will fail.

Example for the first option (use the registry's exact resource ID):

```bash
ACR_ID=$(az acr show \
  --resource-group "zeroops-resources" \
  --name "YOUR_UNIQUE_ACR_NAME" \
  --query id \
  --output tsv)

az role assignment create \
  --assignee "CLIENT_ID_OF_SERVICE_PRINCIPAL" \
  --role "Role Based Access Control Administrator" \
  --scope "$ACR_ID"
```

## Step 7: Input Credentials in the ZeroOps Dashboard
Go to **Settings** -> **Cloud Targets** -> **Azure Connection** and enter:
- **Tenant ID**: `tenant` from Step 4
- **Subscription ID**: `YOUR_SUBSCRIPTION_ID`
- **Client ID**: `appId` from Step 4
- **Client Secret**: `password` from Step 4
- **Resource Group**: `zeroops-resources`
- **Region**: `eastus` (or your chosen region)
- **Container Registry**: `YOUR_UNIQUE_ACR_NAME.azurecr.io`
- **Linux App Service Plan**: `zeroops-linux-plan`

Saving performs read-only Azure lookups for the exact resource group, ACR, and
App Service plan. ZeroOps verifies that the plan is Linux and is in the selected
region before marking the target ready. It does not claim that build, App
Service write, or role-assignment permissions work until an approved deployment
actually exercises them.

ZeroOps stores the Client Secret securely in Azure Key Vault. The secret is
never saved in the ZeroOps SQL database.
