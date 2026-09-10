"""Exercise real HTTP, cookies, CSRF and PostgreSQL through the local audit API.

Run audit_local_runtime.py first. Optional --base-url http://localhost:3000
exercises the built frontend's reverse proxy as well. External cloud, SMTP,
SMS and payment providers are deliberately not contacted by this test.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import secrets
from urllib.parse import parse_qs, urlparse
import uuid

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:18000")
    args = parser.parse_args()
    if args.base_url not in {"http://127.0.0.1:18000", "http://localhost:3000"}:
        parser.error("Smoke tests only target the local audit runtime.")
    directory = args.directory.resolve(strict=True)
    if not directory.is_relative_to(Path(__file__).resolve().parents[1] / "tmp"):
        parser.error("Use the dedicated audit directory under tmp/.")
    results: list[dict] = []

    def check(label, condition, detail=""):
        results.append({"check": label, "passed": bool(condition), "detail": detail})
        print(f"{'PASS' if condition else 'FAIL'} {label}" + (f": {detail}" if detail else ""))

    def call(client, method, path, expected=200, **kwargs):
        response = client.request(method, path, **kwargs)
        check(f"{method} {path} -> {expected}", response.status_code == expected,
              "" if response.status_code == expected else f"HTTP {response.status_code}: {response.text[:300]}")
        csrf = response.headers.get("x-csrf-token")
        if csrf:
            client.headers["X-CSRF-Token"] = csrf
        try:
            return response.json()
        except ValueError:
            return {}

    def register(client, label):
        email = f"audit-{label}-{uuid.uuid4().hex[:10]}@example.com"
        password = secrets.token_urlsafe(24) + "1!aA"
        result = call(client, "POST", "/api/auth/signup", json={
            "email": email, "password": password, "firstName": "Audit", "lastName": label,
        })
        if not result.get("email_verification_required"):
            raise RuntimeError("Signup did not start verification; cannot continue authenticated checks.")
        messages = json.loads((directory / "mailbox.json").read_text(encoding="utf-8"))
        text = next(item["text"] for item in reversed(messages) if item["to"] == email)
        url = re.search(r"http://localhost:3000/verify-email\?\S+", text).group()
        query = parse_qs(urlparse(url).query)
        call(client, "POST", "/api/auth/verify-email", json={"email": email, "token": query["token"][0]})
        call(client, "POST", "/api/auth/verify-email", expected=400,
             json={"email": email, "token": query["token"][0]})
        call(client, "POST", "/api/auth/login", json={"email": email, "password": password})
        check("Login issued a session cookie", bool(client.cookies.get("session_token")))
        call(client, "GET", "/api/auth/me")
        return {"email": email, "password": password}

    with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as owner, \
         httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as other:
        call(owner, "GET", "/api/health")
        for path in ("/api/auth/me", "/api/projects", "/api/dashboard/stats", "/api/user/settings",
                     "/api/monitoring/metrics", "/api/deployments", "/api/history"):
            call(owner, "GET", path, expected=401)
        owner_login = register(owner, "owner")
        other_login = register(other, "other")
        (directory / "browser-accounts.json").write_text(
            json.dumps({"owner": owner_login, "other": other_login}), encoding="utf-8")

        project = call(owner, "POST", "/api/projects", json={
            "name": "Audit Project", "full_name": "audit/isolated-project", "branch": "main",
        })
        project_id = project.get("id")
        if not project_id:
            raise RuntimeError("Project creation failed; cannot continue project checks.")
        root = f"/api/projects/{project_id}"
        check("Project listing includes the persisted project",
              any(p["id"] == project_id for p in call(owner, "GET", "/api/projects")))
        check("Other account project list is empty", call(other, "GET", "/api/projects") == [])
        call(owner, "GET", root)
        for suffix in ("", "/variables", "/metrics", "/monitoring", "/incidents",
                       "/security-scans", "/pipeline-config", "/terraform-review", "/activity"):
            call(other, "GET", root + suffix, expected=404)
        call(other, "GET", f"/api/security/status/{project_id}", expected=404)
        call(other, "DELETE", root, expected=404)
        call(owner, "GET", "/api/projects/not-a-uuid", expected=422)
        call(owner, "GET", "/api/health/database")

        for path in ("/api/user/profile", "/api/user/settings", "/api/deployment-targets",
                     "/api/azure/connection", "/api/github/status", "/api/billing/operations",
                     "/api/activity", "/api/history", "/api/monitoring/metrics", "/api/deployments"):
            call(owner, "GET", path)
        response = owner.put("/api/user/profile", headers={"X-CSRF-Token": "incorrect"},
                             json={"first_name": "Must not save"})
        check("Authenticated mutation rejects an invalid CSRF token", response.status_code == 403)
        call(owner, "PUT", "/api/user/profile", json={"first_name": "Verified Audit"})
        check("Profile update persisted", call(owner, "GET", "/api/user/profile")["first_name"] == "Verified Audit")
        call(owner, "PUT", "/api/user/settings", json={"theme": "light", "email_alerts": False})
        check("Settings update persisted", call(owner, "GET", "/api/user/settings")["theme"] == "light")
        stats = call(owner, "GET", "/api/dashboard/stats")
        check("Dashboard reports actual project count", stats.get("total_projects") == 1)
        notifications = call(owner, "GET", "/api/notifications")
        if notifications:
            call(owner, "POST", f"/api/notifications/{notifications[0]['id']}/read")
        call(owner, "POST", "/api/notifications/read-all")
        check("Read-all notification state persisted", all(n["read"] for n in call(owner, "GET", "/api/notifications")))

        variable = call(owner, "POST", root + "/variables", json={"key": "AUDIT_MODE", "value": "enabled", "is_secret": False})
        call(owner, "POST", root + "/variables", expected=400,
             json={"key": "AUDIT_MODE", "value": "duplicate", "is_secret": False})
        check("Non-secret variable persisted", any(v["key"] == "AUDIT_MODE" and v["value"] == "enabled"
              for v in call(owner, "GET", root + "/variables")))
        call(owner, "POST", root + "/variables", expected=503,
             json={"key": "AUDIT_SECRET", "value": "audit-only-test-value", "is_secret": True})
        check("Unavailable vault leaves no secret metadata", all(v["key"] != "AUDIT_SECRET"
              for v in call(owner, "GET", root + "/variables")))
        if variable.get("id"):
            call(owner, "DELETE", root + f"/variables/{variable['id']}")
        for suffix in ("/metrics", "/monitoring", "/security-scans", "/incidents", "/change-analysis", "/activity"):
            call(owner, "GET", root + suffix)
        call(owner, "GET", f"/api/security/status/{project_id}")
        call(owner, "GET", root + "/pipeline-config", expected=503)
        call(owner, "GET", root + "/terraform-review")
        for path in ("/api/settings/api-key", root + "/health-score", root + "/cost-optimization", root + "/domains", root + "/members"):
            call(owner, "GET", path, expected=501)
        call(owner, "POST", "/api/deployments/deploy", expected=409, json={"project_id": project_id, "branch": "main"})
        check("Blocked deployment created no release record", call(owner, "GET", "/api/deployments") == [])
        call(owner, "POST", "/api/auth/logout")
        call(owner, "GET", "/api/auth/me", expected=401)
        call(owner, "GET", root, expected=401)

    report = {"base_url": args.base_url, "passed": sum(r["passed"] for r in results),
              "failed": sum(not r["passed"] for r in results), "checks": results}
    (directory / "http-smoke-results.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\n{report['passed']} passed, {report['failed']} failed")
    raise SystemExit(bool(report["failed"]))


if __name__ == "__main__":
    main()
