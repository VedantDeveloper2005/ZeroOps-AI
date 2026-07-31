from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "functions" / "common"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(COMMON))

from backend.contracts.ai import (
    RepositoryAnalysisRequest as BackendRepositoryAnalysisRequest,
)
from backend.contracts.ai import RepositoryAssessment as BackendRepositoryAssessment
from backend.contracts.ai import TerraformBundle as BackendTerraformBundle
from backend.contracts.ai import (
    TerraformGenerationRequest as BackendTerraformGenerationRequest,
)
from zeroops_functions.ai_contracts import (
    RepositoryAnalysisRequest as FunctionRepositoryAnalysisRequest,
)
from zeroops_functions.ai_contracts import (
    RepositoryAssessment as FunctionRepositoryAssessment,
)
from zeroops_functions.ai_contracts import TerraformBundle as FunctionTerraformBundle
from zeroops_functions.ai_contracts import (
    TerraformGenerationRequest as FunctionTerraformGenerationRequest,
)


def load_module(name: str, path: Path):
    specification = importlib.util.spec_from_file_location(name, path)
    assert specification and specification.loader
    module = importlib.util.module_from_spec(specification)
    sys.modules[name] = module
    specification.loader.exec_module(module)
    return module


class CanonicalContractTests(unittest.TestCase):
    def test_function_contract_mirror_matches_backend_source_and_schemas(self):
        backend_source = (ROOT / "backend" / "contracts" / "ai.py").read_text(
            encoding="utf-8"
        )
        function_source = (
            ROOT
            / "functions"
            / "common"
            / "zeroops_functions"
            / "ai_contracts.py"
        ).read_text(encoding="utf-8")
        self.assertEqual(
            backend_source.replace("\r\n", "\n").rstrip(),
            function_source.replace("\r\n", "\n").rstrip(),
        )

        pairs = (
            (BackendRepositoryAnalysisRequest, FunctionRepositoryAnalysisRequest),
            (BackendRepositoryAssessment, FunctionRepositoryAssessment),
            (BackendTerraformGenerationRequest, FunctionTerraformGenerationRequest),
            (BackendTerraformBundle, FunctionTerraformBundle),
        )
        for backend_contract, function_contract in pairs:
            self.assertEqual(
                backend_contract.model_json_schema(),
                function_contract.model_json_schema(),
            )

    def test_checked_in_runtime_schemas_match_function_contracts(self):
        pairs = (
            (
                ROOT / "ai-specs" / "repository-analysis" / "response.schema.json",
                FunctionRepositoryAssessment,
            ),
            (
                ROOT / "ai-specs" / "terraform-generation" / "response.schema.json",
                FunctionTerraformBundle,
            ),
        )
        for path, contract in pairs:
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                contract.model_json_schema(),
            )

    def test_function_packages_are_deterministic_and_self_contained(self):
        package_module = load_module(
            "zeroops_package_functions_for_tests",
            ROOT / "scripts" / "package_functions.py",
        )
        with tempfile.TemporaryDirectory(prefix="zeroops-functions-package-") as temporary:
            output = Path(temporary) / "functions"
            first = package_module.build(output)
            second = package_module.build(output)
            self.assertEqual(first, second)

            for workload in ("repository_analysis", "terraform_generation"):
                archive = output / "packages" / f"{workload}.zip"
                with zipfile.ZipFile(archive) as package:
                    names = set(package.namelist())
                self.assertIn("function_app.py", names)
                self.assertIn("handler.py", names)
                self.assertIn("prompts/instructions.md", names)
                self.assertIn("zeroops_functions/ai_contracts.py", names)
                self.assertIn("zeroops_functions/model_client.py", names)
                if workload == "terraform_generation":
                    self.assertIn("terraform.lock.hcl", names)


if __name__ == "__main__":
    unittest.main()
