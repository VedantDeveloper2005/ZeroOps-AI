import requests
import json

session = requests.Session()
backend_url = "https://zeroops-backend-v2.azurewebsites.net"
login_payload = {
    "email": "vedant.kulk5@gmail.com",
    "password": "ZeroOpsDemo2026!"
}
login_resp = session.post(f"{backend_url}/api/auth/login", json=login_payload, timeout=10)
print("Login status:", login_resp.status_code)

deploy_list_resp = session.get(f"{backend_url}/api/deployments?limit=5", timeout=10)
if deploy_list_resp.status_code == 200:
    for d in deploy_list_resp.json():
        print(f"\nDeployment {d.get('id')}: status={d.get('status')} | commit={d.get('commit_sha') or d.get('commit_hash')}")
        pipe_resp = session.get(f"{backend_url}/api/deployments/{d.get('id')}/pipeline", timeout=10)
        if pipe_resp.status_code == 200:
            p_data = pipe_resp.json()
            for s in p_data.get("stages", []):
                st = s.get("status")
                if st not in ("pending", "skipped"):
                    print(f"  Stage {s.get('name')}: {st} | error={s.get('error') or s.get('error_message')}")
        fa_resp = session.get(f"{backend_url}/api/deployments/{d.get('id')}/failure-analysis", timeout=10)
        if fa_resp.status_code == 200:
            print("  Failure Analysis:", fa_resp.json().get("failure_summary"))
            print("  Root cause:", fa_resp.json().get("root_cause"))
            print("  Recommended fix:", fa_resp.json().get("recommended_fix"))
