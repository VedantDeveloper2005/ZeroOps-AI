import requests
import json

session = requests.Session()
backend_url = "https://zeroops-backend-v2.azurewebsites.net"
login_payload = {"email": "vedant.kulk5@gmail.com", "password": "ZeroOpsDemo2026!"}
session.post(f"{backend_url}/api/auth/login", json=login_payload)

deploy_id = "f284f33a-42dd-4d10-9eb6-9a0dbeaf6fa3"
r = session.get(f"{backend_url}/api/deployments/{deploy_id}/failure-analysis")
if r.status_code == 200:
    print("Failure analysis:", json.dumps(r.json(), indent=2))

r_pipe = session.get(f"{backend_url}/api/deployments/{deploy_id}/pipeline")
if r_pipe.status_code == 200:
    p_data = r_pipe.json()
    for s in p_data.get("stages", []):
        if s.get("name") == "Container Security Scan":
            print("\nContainer Security Scan stage data:")
            print("Status:", s.get("status"))
            print("Error:", s.get("error") or s.get("error_message"))
            print("Evidence:", json.dumps(s.get("evidence"), indent=2))

r_sec = session.get(f"{backend_url}/api/security/status/1ed1b668-8968-4b2c-870b-8160dd061fe6")
if r_sec.status_code == 200:
    data = r_sec.json()
    findings = data.get("findings", [])
    print(f"\nTotal findings: {len(findings)}")
    for f in findings[:10]:
        print(f" - [{f.get('severity')}] {f.get('title')} ({f.get('rule_id')})")
