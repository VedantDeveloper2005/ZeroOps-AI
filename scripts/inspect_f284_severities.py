import requests

session = requests.Session()
backend_url = "https://zeroops-backend-v2.azurewebsites.net"
login_payload = {"email": "vedant.kulk5@gmail.com", "password": "ZeroOpsDemo2026!"}
session.post(f"{backend_url}/api/auth/login", json=login_payload)

deploy_id = "f284f33a-42dd-4d10-9eb6-9a0dbeaf6fa3"
r_pipe = session.get(f"{backend_url}/api/deployments/{deploy_id}/pipeline")
if r_pipe.status_code == 200:
    for s in r_pipe.json().get("stages", []):
        if s.get("name") == "Container Security Scan":
            scanner = s.get("result_metadata", {}).get("scanner", {})
            print("Summary:", scanner.get("summary"))
            print("Status:", scanner.get("status"))
            print("Blocking:", scanner.get("blocking"))
            print("Evidence:", scanner.get("evidence"))
            findings = scanner.get("findings", [])
            print(f"Total findings: {len(findings)}")
            severities = {}
            for f in findings:
                sev = f.get("severity")
                severities[sev] = severities.get(sev, 0) + 1
            print("Severity breakdown:", severities)
            for f in findings:
                if f.get("severity") == "critical":
                    print("Critical finding:", f.get("title"), f.get("rule_id"))
