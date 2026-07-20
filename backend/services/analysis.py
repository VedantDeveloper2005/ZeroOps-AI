"""Unified repository analysis service for ZeroOps.

Scans the repository codebase for frameworks, database dependencies, storage/caching needs,
queues, Dockerfiles, Kubernetes manifests, environment variables, and security items.
"""

import os
import re
import json
from typing import Dict, Any, List, Optional
try:
    from backend.services.ai import (
        analyze_repository as ai_analyze_repository,
        has_file,
        read_file_content,
        scan_codebase_for_env_vars
    )
except ImportError:
    from services.ai import (
        analyze_repository as ai_analyze_repository,
        has_file,
        read_file_content,
        scan_codebase_for_env_vars
    )

class RepositoryAnalysis:
    def __init__(self, raw_data: Dict[str, Any]):
        self.raw_data = raw_data

    @property
    def framework(self) -> str:
        return self.raw_data.get("framework", "Unknown")

    @property
    def language(self) -> str:
        return self.raw_data.get("language", "Unknown")

    @property
    def database_dependencies(self) -> List[str]:
        return self.raw_data.get("database_dependencies", [])

    @property
    def environment_variables(self) -> List[str]:
        return self.raw_data.get("environment_variables", [])

    @property
    def vulnerabilities(self) -> List[str]:
        return self.raw_data.get("vulnerabilities", [])

    def to_dict(self) -> Dict[str, Any]:
        return self.raw_data


def analyze_repository(repo_path: Any, project_id: str = "default") -> Dict[str, Any]:
    """Perform a deep codebase analysis, combining local heuristic scans and AI review."""
    # First get the baseline AI-enriched review from the existing AI service
    # This automatically runs analyze_repo_local() inside it.
    try:
        analysis_data = ai_analyze_repository(repo_path, project_id)
    except Exception as e:
        # Fallback to local scan if AI fails
        try:
            from backend.services.ai import analyze_repo_local
        except ImportError:
            from services.ai import analyze_repo_local
        analysis_data = analyze_repo_local(repo_path, project_id)

    # Perform supplementary architect detection
    dependencies = analysis_data.get("dependencies", [])
    scanned_vars = analysis_data.get("environment_variables", [])

    # Classify frontend, backend, or fullstack
    framework = analysis_data.get("framework", "Unknown")
    is_frontend = framework in ["Next.js", "React", "Vue", "Nuxt.js", "Angular", "Svelte"]
    is_backend = framework in ["FastAPI", "Flask", "Django", "Express.js", "NestJS"]
    
    analysis_data["frontend_detected"] = is_frontend or framework == "Unknown"
    analysis_data["backend_detected"] = is_backend or framework == "Unknown"

    # Detect Storage Account requirements
    storage_detected = False
    storage_keywords = ["azure-storage", "aws-sdk", "boto3", "multer-s3", "google-cloud-storage", "blob", "s3"]
    if any(keyword in str(dependencies).lower() for keyword in storage_keywords) or \
       any(keyword in str(scanned_vars).lower() for keyword in ["storage", "blob", "bucket", "upload", "s3"]):
        storage_detected = True
    analysis_data["storage_detected"] = storage_detected

    # Detect Queue requirements
    queues_detected = False
    queue_keywords = ["celery", "bullmq", "bull", "kue", "rabbitmq", "amqp", "kafka", "azure-service-bus", "sqs"]
    if any(keyword in str(dependencies).lower() for keyword in queue_keywords) or \
       any(keyword in str(scanned_vars).lower() for keyword in ["queue", "broker", "rabbitmq", "amqp", "celery", "sqs"]):
        queues_detected = True
    analysis_data["queues_detected"] = queues_detected

    # Detect Cache requirements
    cache_detected = "Redis" in analysis_data.get("database_dependencies", [])
    if not cache_detected:
        cache_keywords = ["redis", "memcached", "ioredis"]
        if any(keyword in str(dependencies).lower() for keyword in cache_keywords) or \
           any(keyword in str(scanned_vars).lower() for keyword in ["redis", "cache", "memcached"]):
            cache_detected = True
            if "Redis" not in analysis_data["database_dependencies"]:
                analysis_data["database_dependencies"].append("Redis")
    analysis_data["cache_detected"] = cache_detected

    # Detect Secrets/KeyVault requirement
    secrets_detected = False
    secret_keywords = ["jwt", "secret", "password", "token", "keyvault", "vault", "api_key", "apikey"]
    if any(keyword in str(scanned_vars).lower() for keyword in secret_keywords) or \
       len(scanned_vars) > 0:
        secrets_detected = True
    analysis_data["secrets_detected"] = secrets_detected

    # Detect Networking / VNet requirements
    # VNet is recommended if databases, cache or queues are present
    analysis_data["networking_detected"] = len(analysis_data.get("database_dependencies", [])) > 0 or queues_detected

    return analysis_data
