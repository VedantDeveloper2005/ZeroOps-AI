# Azure BYOS (Bring Your Own Subscription) Onboarding Guide

To configure your own Azure subscription inside ZeroOps AI, you need to create a dedicated Service Principal scoped to a specific resource group with a custom RBAC role ("ZeroOps Scoped Operator"). This ensures that ZeroOps AI can only manage resources inside that group and is strictly prohibited from altering authorization, modifying policy assignments, or accessing resources outside the group.

## Step 1: Create a Dedicated Resource Group
Run the following Azure CLI command to create the resource group where ZeroOps will manage your infrastructure:

```bash
az group create --name "zeroops-resources" --location "eastus"
```

## Step 2: Define the Custom RBAC Role
ZeroOps AI requires a custom role that allows full contributor access *except* authorization actions (assigning permissions or role definitions).

Save the following JSON content as `zeroops-operator-role.json`. Replace `YOUR_SUBSCRIPTION_ID` with your actual Azure subscription ID:

```json
{
  "Name": "ZeroOps Scoped Operator",
  "IsCustom": true,
  "Description": "Allows ZeroOps AI to manage AKS, networking, and storage resources in a scoped resource group, preventing authorization adjustments.",
  "Actions": [
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

## Step 3: Create the Service Principal
Now, create a Service Principal and obtain the credentials:

```bash
az ad sp create-for-rbac --name "zeroops-operator-sp" --skip-assignment
```

This command will output JSON containing:
- `appId` (Client ID)
- `password` (Client Secret)
- `tenant` (Tenant ID)

**IMPORTANT: Copy these values immediately. The secret cannot be retrieved later.**

## Step 4: Assign the Custom Role to the Service Principal
Scope the Service Principal to the resource group you created in Step 1 using the custom role:

```bash
az role assignment create \
  --assignee "CLIENT_ID_OF_SERVICE_PRINCIPAL" \
  --role "ZeroOps Scoped Operator" \
  --scope "/subscriptions/YOUR_SUBSCRIPTION_ID/resourceGroups/zeroops-resources"
```

## Step 5: Input Credentials in the ZeroOps Dashboard
Go to **Settings** -> **Cloud Targets** -> **Azure Connection** and enter:
- **Tenant ID**: `tenant` from Step 3
- **Subscription ID**: `YOUR_SUBSCRIPTION_ID`
- **Client ID**: `appId` from Step 3
- **Client Secret**: `password` from Step 3
- **Resource Group**: `zeroops-resources`
- **Region**: `eastus` (or your chosen region)

ZeroOps will validate the connection and store the Client Secret securely in Azure Key Vault. The secret is never saved in the ZeroOps SQL database.
