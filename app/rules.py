from typing import Dict, Any, List, Tuple

class ConfigurationValidator:
    """
    Step 2: Configuration Validator
    Validates user selections before the AI sees them.
    Rejects completely invalid combinations and normalizes automatically where possible.
    """
    def __init__(self, analysis: Dict[str, Any], spec: Dict[str, Any]):
        self.analysis = analysis
        self.spec = spec
        self.errors = []
        self.warnings = []

    def validate(self) -> List[str]:
        # Step 1: Validate Required Fields
        required = ["pipeline_tool", "cloud_provider", "deployment_target", "tech_stack"]
        for req in required:
            if not self.spec.get(req):
                self.errors.append(f"Missing required field: {req}")

        if self.errors:
            return self.errors  # Immediately fail if basic fields are missing

        # Variables for rules
        # Safely convert to lower, ignoring missing top-level keys safely since required fields check passed
        tool = (self.spec.get("pipeline_tool") or "").lower()
        cloud = (self.spec.get("cloud_provider") or "").lower()
        deploy = (self.spec.get("deployment_target") or "").lower()
        stack = (self.spec.get("tech_stack") or "").lower()
        
        # Safely extract environment and tests
        env_dict = self.spec.get("environment_setup") or {}
        env_setup = str(env_dict).lower()
        
        tests = self.spec.get("tests") or {}
        sec = self.spec.get("security_scans") or {}
        notif = self.spec.get("notifications") or {}

        auto_normalized = False


        # Step 9: Repository Validation (Infer from actual safely handling nulls)
        backend_info = self.analysis.get("backend") or {}
        repo_pm = backend_info.get("package_manager") or ""
        repo_pm = str(repo_pm).lower()
        
        infra_info = self.analysis.get("infrastructure") or {}
        docker_info = infra_info.get("docker") or {}
        has_docker = docker_info.get("has_docker", False)
        
        # Step 11: Auto Normalization (Interwoven)
        # Normalizing mismatched linters
        if "node" in stack or "express" in stack or "react" in stack or "next" in stack:
            if "flake8" in env_setup or "black" in env_setup:
                self.warnings.append("Warning: Python linters (flake8/black) removed. ESLint selected automatically.")
                auto_normalized = True
        elif "python" in stack or "fastapi" in stack or "django" in stack:
            if "eslint" in env_setup:
                self.warnings.append("Warning: ESLint removed. Flake8/Black selected automatically.")
                auto_normalized = True

        # Rollback Validation
        if str(self.spec.get("rollback", "")).lower() == "none":
            pass # AI handles this

        return self.errors


class RulesEngine:
    """
    Step 3: Rules Engine
    Applies strict logic over the inputs so the AI doesn't have to guess.
    """
    def __init__(self, analysis: Dict[str, Any], spec: Dict[str, Any]):
        self.analysis = analysis
        self.spec = spec

    def apply_rules(self) -> Dict[str, Any]:
        """
        Returns a strongly-typed enforced ruleset for the template.
        """
        runtime = self.analysis.get("backend", {}).get("language", "").lower()
        if not runtime:
            runtime = self.analysis.get("frontend", {}).get("language", "").lower()
            
        deployment = self.spec.get("deployment_target", "")
        
        rules = {
            "allow_docker": True,
            "allow_kubernetes": True,
            "allow_ssh": True,
            "allow_pm2": True,
            "package_manager": "npm",
            "linter": "eslint"
        }
        
        if deployment in ("EC2 (SSH)", "EC2 (SSM)"):
            rules["allow_docker"] = False
            rules["allow_kubernetes"] = False
        elif deployment in ("Docker Host", "Amazon ECS"):
            rules["allow_ssh"] = False
            rules["allow_pm2"] = False
        elif deployment in ("Kubernetes", "Amazon EKS"):
            rules["allow_ssh"] = False
            rules["allow_docker_compose"] = False
            
        if runtime == "python":
            rules["package_manager"] = "pip"
            rules["linter"] = "ruff"
        elif runtime in ("node.js", "javascript", "typescript"):
            rules["package_manager"] = "npm"
            rules["linter"] = "eslint"
            
        return rules
