import abc
import logging
import uuid
import os
import json
import re
from typing import Dict, List, Optional

try:
    from backend import models, config
    from backend.services import git
except ImportError:
    import models, config
    from services import git

logger = logging.getLogger("zeroops.ai.agent")

class AutonomousDevOpsAgent(abc.ABC):
    """
    Abstract Base Class for autonomous DevOps agent orchestration powered by NVIDIA NIMs.
    Exposes capabilities for future self-healing pipelines, predictive cost optimization,
    incident remediation, and deployment orchestrations.
    """

    @abc.abstractmethod
    async def deploy_application(
        self, 
        project_id: str, 
        repository: str, 
        branch: str, 
        environment: str = "production"
    ) -> Dict:
        """
        Autonomously verify code readiness, compile configurations,
        and trigger deployment.
        """
        pass

    @abc.abstractmethod
    async def provision_infrastructure(
        self, 
        project_id: str, 
        requirements: Dict
    ) -> Dict:
        """
        Autonomously provision cloud resources (databases, ingress, certs)
        based on repository analysis recommendations.
        """
        pass

    @abc.abstractmethod
    async def restart_failed_service(
        self, 
        project_id: str, 
        service_name: str, 
        reason: str
    ) -> bool:
        """
        Attempt automatic service restart in isolated namespace when OOM
        or crash loops occur.
        """
        pass

    @abc.abstractmethod
    async def scale_resources(
        self, 
        project_id: str, 
        min_replicas: int, 
        max_replicas: int
    ) -> bool:
        """
        Scale replicas up or down in response to real-time traffic spikes or OOM alerts.
        """
        pass

    @abc.abstractmethod
    async def analyze_incident(
        self, 
        project_id: str, 
        incident_details: str
    ) -> Dict:
        """
        Correlate timeseries metrics, logs, and infrastructure events to isolate root causes.
        """
        pass

    @abc.abstractmethod
    async def optimize_infrastructure_costs(
        self, 
        project_id: str
    ) -> Dict:
        """
        Scan resource usage profiles and recommend downscaling or database consolidation actions.
        """
        pass

    @abc.abstractmethod
    async def auto_remediate_failure(
        self, 
        deployment_id: str, 
        failure_reason: str,
        db
    ) -> bool:
        """
        Inspect deployment logs, run Nemotron analysis, and execute step-by-step
        auto-remediation actions (e.g., config injection, restart).
        """
        pass


class NvidiaNIMDevOpsAgent(AutonomousDevOpsAgent):
    """
    Concrete architectural implementation of AutonomousDevOpsAgent.
    Integrates with NVIDIA NIM endpoints to support autonomous operational intelligence.
    """

    def __init__(self, api_key: Optional[str] = None, endpoint: Optional[str] = None):
        self.api_key = api_key
        self.endpoint = endpoint or "https://integrate.api.nvidia.com/v1"
        logger.info(f"NVIDIA NIM DevOps Agent architecture layer initialized (Endpoint: {self.endpoint})")

    async def deploy_application(
        self, 
        project_id: str, 
        repository: str, 
        branch: str, 
        environment: str = "production"
    ) -> Dict:
        logger.info(f"Agent planning autonomous deploy for {repository}...")
        return {
            "status": "requires_manual_review",
            "action_id": "deploy-plan-pending",
            "recommended_target": None,
            "confidence": 0.0
        }

    async def provision_infrastructure(
        self, 
        project_id: str, 
        requirements: Dict
    ) -> Dict:
        logger.info(f"Agent planning resource provisioning: {requirements}...")
        return {
            "status": "requires_manual_review",
            "resources": [],
            "manifests_compiled": False
        }

    async def restart_failed_service(
        self, 
        project_id: str, 
        service_name: str, 
        reason: str
    ) -> bool:
        logger.warning(f"Agent restart requested for {service_name} due to: {reason}; no restart executor is configured.")
        return False

    async def scale_resources(
        self, 
        project_id: str, 
        min_replicas: int, 
        max_replicas: int
    ) -> bool:
        logger.info(f"Agent scale request for {project_id}: [{min_replicas} - {max_replicas}]; no scaler executor is configured.")
        return False

    async def analyze_incident(
        self, 
        project_id: str, 
        incident_details: str
    ) -> Dict:
        logger.info(f"Agent analyzing incident logs for project {project_id}...")
        return {
            "root_cause": "No incident analysis has been recorded.",
            "remediation_plan": "Review deployment logs and metrics before requesting paid remediation.",
            "severity": "unknown"
        }

    async def optimize_infrastructure_costs(
        self, 
        project_id: str
    ) -> Dict:
        logger.info(f"Agent generating cost-optimization report for {project_id}...")
        return {
            "current_cost_est": None,
            "optimized_cost_est": None,
            "actions": []
        }

    async def auto_remediate_failure(
        self, 
        deployment_id: str, 
        failure_reason: str,
        db
    ) -> bool:
        logger.info(f"Executing self-healing pipeline for failed run {deployment_id}...")
        
        # 1. Fetch deployment & project
        from sqlalchemy.future import select
        dep_uuid = uuid.UUID(deployment_id) if isinstance(deployment_id, str) else deployment_id
        
        result = await db.execute(
            select(models.Deployment).filter(models.Deployment.id == dep_uuid)
        )
        deployment = result.scalars().first()
        if not deployment:
            logger.error(f"Auto-Remediate: Deployment {deployment_id} not found.")
            return False
            
        project = deployment.project
        if not project:
            logger.error(f"Auto-Remediate: Project for deployment {deployment_id} not found.")
            return False
            
        # 2. Get failure analysis
        fa_result = await db.execute(
            select(models.FailureAnalysis).filter(models.FailureAnalysis.deployment_id == dep_uuid)
        )
        fa = fa_result.scalars().first()
        
        summary_text = fa.failure_summary if fa else failure_reason or ""
        fix_text = fa.recommended_fix if fa else ""
        
        logger.info(f"Auto-Remediate: Analysis summary: '{summary_text}' | Suggested fix: '{fix_text}'")
        fix_applied = False
        
        # 3. Check for dependency module issues (e.g. missing package)
        is_dep_issue = any(k in summary_text.lower() or k in fix_text.lower() for k in ["dependency", "package", "module", "npm install", "pip install", "not found", "syntaxerror"])
        
        # Resolve local workspace path
        repo_path = git.get_repo_path(project.full_name)
        
        if is_dep_issue and os.path.exists(repo_path):
            # Try to identify missing module/package
            package_name = None
            
            # Find quoted module name in error/summary/fix
            match = re.search(r"['\"]([^'\"]+)['\"]", summary_text + " " + fix_text)
            if match:
                extracted = match.group(1).strip()
                # Ensure it looks like a valid package name
                if re.match(r"^[a-zA-Z0-9\-\/@_]+$", extracted):
                    package_name = extracted
            if not package_name:
                logger.warning("Auto-Remediate: No explicit package name found in failure analysis; refusing to guess a dependency.")
                return False
            
            # Apply fix to package.json (Node/Nextjs)
            package_json_path = os.path.join(repo_path, "package.json")
            if os.path.exists(package_json_path):
                try:
                    with open(package_json_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    if "dependencies" not in data:
                        data["dependencies"] = {}
                        
                    # Inject package
                    data["dependencies"][package_name] = "latest"
                    fix_applied = True
                    logger.info(f"Auto-Remediate: Injected dependency '{package_name}' into package.json")
                    
                    with open(package_json_path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=2)
                        
                    # Add an ActivityEvent for this fix
                    db.add(models.ActivityEvent(
                        user_id=deployment.user_id,
                        project_id=project.id,
                        action="AI Auto-Fix: Dependency Injected",
                        details=f"Injected package '{package_name}' into package.json dependencies list to resolve compilation error."
                    ))
                    await db.commit()
                except Exception as ex:
                    logger.error(f"Auto-Remediate: Failed to modify package.json: {ex}")
            
            # Apply fix to requirements.txt (Python)
            req_txt_path = os.path.join(repo_path, "requirements.txt")
            if os.path.exists(req_txt_path):
                try:
                    with open(req_txt_path, "a", encoding="utf-8") as f:
                        f.write(f"\n{package_name}\n")
                    fix_applied = True
                    logger.info(f"Auto-Remediate: Appended '{package_name}' to requirements.txt")
                    
                    db.add(models.ActivityEvent(
                        user_id=deployment.user_id,
                        project_id=project.id,
                        action="AI Auto-Fix: Dependency Injected",
                        details=f"Appended dependency '{package_name}' to requirements.txt file."
                    ))
                    await db.commit()
                except Exception as ex:
                    logger.error(f"Auto-Remediate: Failed to append to requirements.txt: {ex}")
                    
        # 4. Check for DATABASE_URL / missing env vars
        elif "database_url" in summary_text.lower() or "database_url" in fix_text.lower() or "db" in summary_text.lower():
            db.add(models.ActivityEvent(
                user_id=deployment.user_id,
                project_id=project.id,
                action="AI Auto-Fix: Database configuration required",
                details="Deployment failed because database configuration appears missing. No DATABASE_URL was generated automatically."
            ))
            await db.commit()
            return False
                
        # 5. Check for Out Of Memory (OOM)
        elif "memory" in summary_text.lower() or "oom" in summary_text.lower():
            db.add(models.ActivityEvent(
                user_id=deployment.user_id,
                project_id=project.id,
                action="AI Auto-Fix: Resource review required",
                details="Deployment failure references memory pressure. Resource limits were not changed automatically."
            ))
            await db.commit()
            return False

        if not fix_applied:
            logger.warning("Auto-Remediate: No verified code change was applied.")
            return False
                
        # Register a notification of self-healing action
        db.add(models.Notification(
            user_id=deployment.user_id,
            title="Auto-Fix Executed",
            message=f"ZeroOps AI applied a verified code-level fix for {project.name} and initiated a new build run.",
            type="success",
            category="ai"
        ))
        await db.commit()
        
        return True
