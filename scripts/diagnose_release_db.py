"""Read-only release diagnostics; credentials are fetched without printing them."""
import asyncio
import json
import subprocess
import ssl
import asyncpg

DEPLOYMENT = '1e918195-6a92-45bd-865e-ad1aa02f1dad'

async def main():
    result = subprocess.run(['az.cmd', 'keyvault', 'secret', 'show', '--subscription', '6f0a17f3-f270-4bf7-a2dd-5571fb503ff2', '--vault-name', 'zeroops-kv-v2', '--name', 'zeroops-database-url', '--query', 'value', '-o', 'json'], capture_output=True, text=True, check=True)
    url = json.loads(result.stdout).replace('postgresql+asyncpg://', 'postgresql://')
    conn = await asyncpg.connect(url, ssl=ssl.create_default_context(), timeout=15)
    async with conn.transaction(readonly=True):
        queries = {
            'latest_deployments': "SELECT id,status,commit_sha,live_url,failure_reason FROM deployments ORDER BY started_at DESC LIMIT 5",
            'active_jobs': "SELECT id,status,deployment_id,worker_id FROM deployment_jobs WHERE status IN ('queued','running')",
            'plans': "SELECT id,project_id,status,revision FROM infrastructure_plans ORDER BY updated_at DESC LIMIT 3",
            'job_columns': "SELECT column_name FROM information_schema.columns WHERE table_name='deployment_jobs'",
            'jobs': "SELECT id,status,deployment_id FROM deployment_jobs WHERE deployment_id=$1::uuid",
            'runs': "SELECT id,status,source_revision,created_at FROM pipeline_runs WHERE deployment_id=$1::uuid",
            'stage_duplicates': "SELECT pipeline_run_id,stage_key,attempt_number,count(*) FROM pipeline_stage_attempts WHERE deployment_id=$1::uuid GROUP BY 1,2,3 HAVING count(*)>1",
            'constraints': "SELECT conname FROM pg_constraint WHERE conrelid='pipeline_stage_attempts'::regclass",
            'stages': "SELECT stage_key,status,attempt_number,count(*) FROM pipeline_stage_attempts WHERE deployment_id=$1::uuid GROUP BY 1,2,3 ORDER BY 1",
        }
        for label, query in queries.items():
            rows = await conn.fetch(query, *([DEPLOYMENT] if '$1' in query else []))
            print(label, json.dumps([dict(row) for row in rows], default=str))
    await conn.close()

if __name__ == '__main__':
    asyncio.run(main())
