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
        requirements: Dict,
        db = None
    ) -> Dict:
        logger.info("Infrastructure provisioning was requested but is disabled for this product stage.")
        return {
            "success": False,
            "error": "Automatic infrastructure provisioning is disabled. Configure required Azure resources explicitly before deployment.",
        }

        # Retained below only for database migration compatibility; execution is
        # intentionally unreachable while automatic provisioning is disabled.
        if db is None:
            from backend.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                return await self._provision_infra_impl(project_id, requirements, session)
        else:
            return await self._provision_infra_impl(project_id, requirements, db)

    async def _provision_infra_impl(self, project_id: str, requirements: Dict, db) -> Dict:
        from sqlalchemy.future import select
        from backend import models
        from backend.services import action_gateway

        proj_uuid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        result = await db.execute(select(models.Project).filter(models.Project.id == proj_uuid))
        project = result.scalars().first()
        if not project:
            return {"success": False, "error": f"Project {project_id} not found."}

        result_conn = await db.execute(
            select(models.UserAzureConnection)
            .filter(models.UserAzureConnection.user_id == project.user_id, models.UserAzureConnection.connection_status == "connected")
        )
        conn = result_conn.scalars().first()
        if not conn:
            return {"success": False, "error": "No connected Azure connection found. Cannot provision infrastructure."}

        # Hardcoded monthly rate table in cents per node for VM sizes
        sku_rates = {
            "Standard_DS2_v2": 10000,  # $100
            "Standard_D2s_v3": 9000,   # $90
            "Standard_D4s_v3": 18000,  # $180
            "Standard_F2s_v2": 8500,   # $85
        }
        
        node_count = requirements.get("node_count", 1)
        vm_size = requirements.get("vm_size", "Standard_DS2_v2")
        rate = sku_rates.get(vm_size, 8000)
        estimated_cost_cents = node_count * rate
        
        # Query environment details for the project
        env_result = await db.execute(
            select(models.Environment).filter(models.Environment.project_id == project.id)
        )
        env = env_result.scalars().first()
        env_name = env.name if env else "production"
        
        action_params = {
            "cluster_name": requirements.get("cluster_name", f"aks-{project.name}"),
            "location": requirements.get("location", conn.region or "eastus"),
            "dns_prefix": requirements.get("dns_prefix", f"aks-{project.name}-dns"),
            "node_count": node_count,
            "vm_size": vm_size,
            "estimated_cost_cents": estimated_cost_cents,
            "resource_tags": {"environment": env_name}
        }

        res = await action_gateway.execute_azure_action(
            user_id=project.user_id,
            agent_name="scaling_agent",
            action_type="create_aks_cluster",
            parameters=action_params,
            db=db
        )
        return res


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
        max_replicas: int,
        db = None
    ) -> bool:
        logger.info("Automatic capacity changes are disabled pending real cost and telemetry controls.")
        return False

        # Retained below only for database migration compatibility; execution is
        # intentionally unreachable while automatic capacity changes are disabled.
        if db is None:
            from backend.database import AsyncSessionLocal
            async with AsyncSessionLocal() as session:
                return await self._scale_resources_impl(project_id, min_replicas, max_replicas, session)
        else:
            return await self._scale_resources_impl(project_id, min_replicas, max_replicas, db)

    async def _scale_resources_impl(self, project_id: str, min_replicas: int, max_replicas: int, db) -> bool:
        from sqlalchemy.future import select
        from backend import models
        from backend.services import action_gateway

        proj_uuid = uuid.UUID(project_id) if isinstance(project_id, str) else project_id
        result = await db.execute(select(models.Project).filter(models.Project.id == proj_uuid))
        project = result.scalars().first()
        if not project:
            logger.error(f"Project {project_id} not found.")
            return False

        # Hardcoded monthly rate table in cents per node for VM sizes
        sku_rates = {
            "Standard_DS2_v2": 10000,  # $100
            "Standard_D2s_v3": 9000,   # $90
            "Standard_D4s_v3": 18000,  # $180
            "Standard_F2s_v2": 8500,   # $85
        }
        vm_size = "Standard_DS2_v2"  # Default VM size for scaling nodepool
        rate = sku_rates.get(vm_size, 8000)
        estimated_cost_cents = max_replicas * rate
        
        # Query environment details for the project
        env_result = await db.execute(
            select(models.Environment).filter(models.Environment.project_id == project.id)
        )
        env = env_result.scalars().first()
        env_name = env.name if env else "production"

        action_params = {
            "cluster_name": project.name,
            "node_pool_name": "nodepool1",
            "node_count": max_replicas,
            "vm_size": vm_size,
            "estimated_cost_cents": estimated_cost_cents,
            "resource_tags": {"environment": env_name}
        }

        res = await action_gateway.execute_azure_action(
            user_id=project.user_id,
            agent_name="scaling_agent",
            action_type="scale_aks_nodepool",
            parameters=action_params,
            db=db
        )
        return res.get("success", False)


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
        logger.info("Automatic source-code remediation is disabled.")
        return False

        # Retained below only for database migration compatibility; execution is
        # intentionally unreachable while automatic source mutation is disabled.
        
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
            
            # Verify the package exists on the public registry before writing it
            package_exists = False
            import requests
            
            package_json_path = os.path.join(repo_path, "package.json")
            req_txt_path = os.path.join(repo_path, "requirements.txt")
            
            if os.path.exists(package_json_path):
                # Query npm registry
                try:
                    escaped_name = package_name.replace("/", "%2F")
                    url = f"https://registry.npmjs.org/{escaped_name}"
                    res = requests.get(url, timeout=5)
                    package_exists = (res.status_code == 200)
                except Exception as e:
                    logger.error(f"Failed to check npm registry for package {package_name}: {e}")
            elif os.path.exists(req_txt_path):
                # Query PyPI registry
                try:
                    url = f"https://pypi.org/pypi/{package_name}/json"
                    res = requests.get(url, timeout=5)
                    package_exists = (res.status_code == 200)
                except Exception as e:
                    logger.error(f"Failed to check PyPI registry for package {package_name}: {e}")
            
            if not package_exists:
                logger.error(f"Auto-Remediate: Package '{package_name}' does not exist on the public registry. Refusing to inject.")
                return False
                
            # Route action through action gateway (classified as high risk by default)
            from backend.services import action_gateway
            action_res = await action_gateway.execute_azure_action(
                user_id=deployment.user_id,
                agent_name="healing_agent",
                action_type="inject_dependency",
                parameters={
                    "project_id": str(project.id),
                    "package_name": package_name
                },
                db=db
            )
            
            logger.info(f"Auto-Remediate: Gated dependency injection of '{package_name}'. Gateway response: {action_res}")
            fix_applied = True

                    
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
