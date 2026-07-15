import os
import subprocess
import shutil
from typing import List

class TerraformExecutor:
    def __init__(self, workspace_dir: str, logger):
        self.workspace_dir = workspace_dir
        self.logger = logger
        self.tf_path = shutil.which("terraform") or shutil.which("terraform.exe") or "terraform"

    def run_command(self, args: List[str]) -> bool:
        """Executes a terraform CLI command, streaming all outputs line-by-line to the logger."""
        cmd = [self.tf_path] + args
        self.logger.log(f"Executing: {' '.join(cmd)}", level="INFO")
        
        try:
            # Set up environment with TF_IN_BACKGROUND/TF_IN_AUTOMATION flag
            env = os.environ.copy()
            env["TF_IN_AUTOMATION"] = "true"
            
            process = subprocess.Popen(
                cmd,
                cwd=self.workspace_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=env
            )
            
            # Read stdout line by line as it is outputted
            while True:
                line = process.stdout.readline()
                if not line and process.poll() is not None:
                    break
                if line:
                    self.logger.log(line.rstrip(), level="INFO")
            
            return_code = process.poll()
            if return_code == 0:
                self.logger.log(f"Terraform command finished successfully (exit code 0).", level="INFO")
                return True
            else:
                self.logger.log(f"Terraform command failed with exit code {return_code}.", level="ERROR")
                return False
        except Exception as e:
            self.logger.log(f"Exception during Terraform execution: {e}", level="ERROR")
            return False

    def init(self) -> bool:
        return self.run_command(["init", "-no-color", "-input=false"])

    def validate(self) -> bool:
        return self.run_command(["validate", "-no-color"])

    def fmt(self) -> bool:
        return self.run_command(["fmt", "-no-color", "-check"])

    def plan(self, plan_out_file: str = "tfplan") -> bool:
        return self.run_command(["plan", "-no-color", f"-out={plan_out_file}", "-input=false"])

    def apply(self, plan_out_file: str = "tfplan") -> bool:
        return self.run_command(["apply", "-no-color", "-auto-approve", plan_out_file])

    def destroy(self) -> bool:
        return self.run_command(["destroy", "-no-color", "-auto-approve"])
