import requests
import json

session = requests.Session()
backend_url = 'https://zeroops-backend-v2.azurewebsites.net'
login_resp = session.post(f'{backend_url}/api/auth/login', json={'email': 'vedant.kulk5@gmail.com', 'password': 'ZeroOpsDemo2026!'})
print('Login:', login_resp.status_code)

deployment_id = 'af0a37e0-833a-41c6-afd9-d6a347225376'

det_resp = session.get(f'{backend_url}/api/deployments/{deployment_id}')
print('Deploy detail status:', det_resp.status_code)
if det_resp.status_code == 200:
    det = det_resp.json()
    print('Status:', det.get('status'))
    print('Logs count:', len(det.get('logs', [])))
    for log in det.get('logs', []):
        print(f"[{log.get('level')}] {log.get('message')}")

pipe_resp = session.get(f'{backend_url}/api/deployments/{deployment_id}/pipeline')
print('\nPipeline stages status:', pipe_resp.status_code)
if pipe_resp.status_code == 200:
    pipe = pipe_resp.json()
    print(f"Deployment status: {pipe.get('status')}")
    for stage in pipe.get('stages', []):
        print(f"Stage {stage.get('stage_id')} ({stage.get('name')}): status={stage.get('status')}, error={stage.get('error')}")

