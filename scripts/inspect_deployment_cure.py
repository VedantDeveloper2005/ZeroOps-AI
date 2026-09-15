import requests
import json

session = requests.Session()
backend_url = "https://zeroops-backend-v2.azurewebsites.net"
login_payload = {
    "email": "vedant.kulk5@gmail.com",
    "password": "ZeroOpsDemo2026!"
}
login_resp = session.post(f"{backend_url}/api/auth/login", json=login_payload)
print("Login status:", login_resp.status_code)

deploy_id = "9c4389b7-7e72-4fa7-9d43-f6f716bf1c17"

r = session.get(f"{backend_url}/api/deployments/{deploy_id}/pipeline")
print("Pipeline status:", r.status_code)
if r.status_code == 200:
    data = r.json()
    print("Deployment status:", data.get("status"))
    print("Error message:", data.get("error_message"))
    for s in data.get("stages", []):
        print(f"Stage {s.get('name')}: status={s.get('status')} | error={s.get('error') or s.get('error_message')}")

r2 = session.get(f"{backend_url}/api/deployments/{deploy_id}/failure-analysis")
print("\nFailure Analysis status:", r2.status_code)
if r2.status_code == 200:
    print("Failure Analysis:", json.dumps(r2.json(), indent=2))
else:
    print("Failure Analysis response:", r2.text)

r3 = session.post(f"{backend_url}/api/deployments/{deploy_id}/fix-auto")
print("\nFix-auto status:", r3.status_code)
if r3.status_code == 200:
    print("Fix-auto response:", json.dumps(r3.json(), indent=2))
else:
    print("Fix-auto error:", r3.text)
