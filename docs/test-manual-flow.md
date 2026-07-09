# Azure BYOS Manual Verification Flow

To verify the Bring Your Own Subscription (BYOS) credentials and execution layer, execute the following API calls against the ZeroOps backend.

## Prerequisites
- A running ZeroOps backend (e.g. at `http://localhost:8000`)
- An authenticated user session token or authorization API key.

---

## Step 1: Connect Azure Account (Onboarding)
Send a POST request to onboard a new Azure subscription. This will validate credentials and write the Client Secret to the Key Vault (or mock fallback).

```bash
curl -X POST "http://localhost:8000/api/azure/connect" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     -d '{
       "tenant_id": "mock",
       "client_id": "mock",
       "client_secret": "mock",
       "subscription_id": "mock-sub-12345",
       "resource_group": "mock-resource-group",
       "region": "eastus"
     }'
```

**Expected Response (200 OK):**
```json
{
  "connected": true,
  "connection_status": "connected",
  "subscription_id": "mock-sub-12345",
  "tenant_id": "mock",
  "client_id": "mock",
  "resource_group": "mock-resource-group",
  "region": "eastus"
}
```
*Verify: The response does NOT contain the client secret.*

---

## Step 2: Query Connection Status
Verify the dashboard can fetch the connection metadata safely.

```bash
curl -X GET "http://localhost:8000/api/azure/connection" \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Expected Response (200 OK):**
- Should return connection status of "connected" and metadata fields.

---

## Step 3: Trigger a Low-Risk Action (Immediate Execution)
Simulate a DevOps agent listing resource groups.

```bash
# Handled automatically in agent orchestration or tested by running the test suite
```

---

## Step 4: Trigger a High-Risk Action (Approval Gating)
Simulate deleting a resource, which must be blocked.

```bash
# This triggers a delete_resource action. The system classifies it as high risk and blocks it.
```

## Step 5: Check Pending Approvals
List blocked operations requiring human sign-off.

```bash
curl -X GET "http://localhost:8000/api/approvals/pending" \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Expected Response (200 OK):**
- Returns a list containing the pending approval object.

---

## Step 6: Decide on Pending Approval (Approve)
Submit approval to execute the gated action.

```bash
curl -X POST "http://localhost:8000/api/approvals/PENDING_APPROVAL_ID/decision" \
     -H "Content-Type: application/json" \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
     -d '{
       "decision": "approved"
     }'
```

---

## Step 7: Check Audit Logs
List the history of actions executed by the agent.

```bash
curl -X GET "http://localhost:8000/api/audit-log" \
     -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

**Expected Response (200 OK):**
- Lists entries for connection connect, disconnect, and all operations with redacted parameters.
