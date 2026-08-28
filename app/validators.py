from typing import Dict, Any, List

class YamlValidator:
    """Step 6: YAML Validator"""
    def validate(self, yaml_content: str) -> List[str]:
        errors = []
        import yaml
        try:
            parsed = yaml.safe_load(yaml_content)
            if not isinstance(parsed, dict):
                errors.append("Invalid YAML: must be a mapping/dict at top level.")
            else:
                if "jobs" not in parsed:
                    errors.append("YAML does not contain 'jobs' key.")
                if "on" not in parsed and "True" not in str(parsed): # generic github action check
                    errors.append("YAML does not contain 'on' trigger.")
        except Exception as e:
            errors.append(f"YAML parsing failed: {e}")
        return errors

class RuleValidator:
    """Step 7: Rule Validator"""
    def validate(self, yaml_content: str, rules: Dict[str, Any], runtime: str) -> List[str]:
        errors = []
        content = yaml_content.lower()
        if not rules.get("allow_docker") and ("docker " in content or "docker-compose" in content):
            errors.append("Rejected: Docker found in YAML but docker is disabled.")
            
        if runtime == "python":
            if "npm install" in content or "pnpm" in content:
                errors.append("Rejected: Node package manager found in Python project.")
        elif runtime in ("node.js", "javascript"):
            if "pip install" in content:
                errors.append("Rejected: pip found in Node.js project.")
                
        return errors

class DeploymentValidator:
    """Step 8: Deployment Validator"""
    def validate(self, yaml_content: str, deployment_target: str) -> List[str]:
        errors = []
        content = yaml_content.lower()
        if "ec2" in deployment_target.lower():
            if "ssh" not in content:
                errors.append("Rejected EC2 deploy: missing ssh commands.")
            # We skip 'git pull' check as they might use rsync/scp
        return errors

class SecretValidator:
    """Step 9: Secret Validator"""
    def validate(self, yaml_content: str, deployment_target: str) -> List[str]:
        errors = []
        if "ec2" in deployment_target.lower():
            if "ssh_host" not in yaml_content and "SSH_HOST" not in yaml_content:
                errors.append("Rejected: SSH deployment missing SSH_HOST secret.")
            if "ssh_private_key" not in yaml_content and "SSH_PRIVATE_KEY" not in yaml_content:
                errors.append("Rejected: SSH deployment missing SSH_PRIVATE_KEY secret.")
        return errors

class PipelineValidators:
    @staticmethod
    def run_all(yaml_content: str, deployment_target: str, rules: Dict, runtime: str) -> List[str]:
        errors = []
        errors.extend(YamlValidator().validate(yaml_content))
        errors.extend(RuleValidator().validate(yaml_content, rules, runtime))
        errors.extend(DeploymentValidator().validate(yaml_content, deployment_target))
        errors.extend(SecretValidator().validate(yaml_content, deployment_target))
        return errors
