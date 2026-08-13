from pathlib import Path
import re
import unittest


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


class WorkerImageSecurityContractTests(unittest.TestCase):
    def test_docker_build_context_is_default_deny(self):
        rules = (REPOSITORY_ROOT / ".dockerignore").read_text(encoding="utf-8")
        active = [
            line.strip()
            for line in rules.splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        self.assertEqual(active[0], "*")
        self.assertIn("!worker/**", active)
        self.assertIn("!backend/**", active)
        self.assertIn("!ai-specs/**", active)
        self.assertIn("backend/workspace", active)
        self.assertIn("backend/tests", active)
        self.assertIn("worker/tests", active)

    def test_worker_images_keep_runtime_source_read_only(self):
        for name in ("Dockerfile", "Dockerfile.pipeline"):
            source = (REPOSITORY_ROOT / "worker" / name).read_text(encoding="utf-8")
            self.assertRegex(
                source.splitlines()[0],
                re.compile(r"^FROM --platform=linux/amd64 .+@sha256:[0-9a-f]{64}$"),
            )
            self.assertNotIn("COPY .", source)
            self.assertNotIn("ADD ", source)
            self.assertIn("COPY --chown=root:root worker /app/worker", source)
            self.assertIn("chmod -R a-w /app", source)
            self.assertIn("USER zeroops", source)

        pipeline = (REPOSITORY_ROOT / "worker" / "Dockerfile.pipeline").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            "install -d -o zeroops -g zeroops -m 0700 /app/backend/workspace",
            pipeline,
        )
        self.assertIn("python3 -m venv /opt/checkov", pipeline)
        self.assertIn("python3 -m venv /opt/semgrep", pipeline)
        self.assertIn("ln -s /opt/checkov/bin/checkov /usr/local/bin/checkov", pipeline)
        self.assertIn("ln -s /opt/semgrep/bin/semgrep /usr/local/bin/semgrep", pipeline)
        runtime_install = pipeline.split("python3 -m venv /opt/checkov", 1)[0]
        scanner_install = pipeline.split("python3 -m venv /opt/checkov", 1)[1]
        self.assertNotIn("semgrep==", runtime_install)
        self.assertNotIn("checkov==", runtime_install)
        self.assertIn("semgrep==1.164.0", scanner_install)
        self.assertIn("checkov==3.3.8", scanner_install)
        checkov_install, semgrep_install = scanner_install.split(
            "python3 -m venv /opt/semgrep", 1
        )
        self.assertNotIn("semgrep==", checkov_install)
        self.assertNotIn("checkov==", semgrep_install)
        self.assertIn('CMD ["python", "-m", "worker.main"]', pipeline)


if __name__ == "__main__":
    unittest.main()
