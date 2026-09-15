import requests
import json

session = requests.Session()
backend_url = "https://zeroops-backend-v2.azurewebsites.net"
session.post(f"{backend_url}/api/auth/login", json={"email": "vedant.kulk5@gmail.com", "password": "ZeroOpsDemo2026!"})

deploy_id = "d2b2e156-ac82-49b8-bffa-f979890c18dc"

r_pipe = session.get(f"{backend_url}/api/deployments/{deploy_id}/pipeline")
if r_pipe.status_code == 200:
    p_data = r_pipe.json()
    for s in p_data.get("stages", []):
        if s.get("name") == "Application Deployment":
            print("Stage Application Deployment:")
            print("Status:", s.get("status"))
            print("Error:", s.get("error") or s.get("error_message"))
            print("Reason:", s.get("reason"))
            print("Summary:", s.get("summary"))
            print("Evidence:", json.dumps(s.get("evidence"), indent=2))

r_fa = session.get(f"{backend_url}/api/deployments/{deploy_id}/failure-analysis")
if r_fa.status_code == 200:
    print("\nFailure analysis:", json.dumps(r_fa.json(), indent=2))
