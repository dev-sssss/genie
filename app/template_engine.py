import json
import os
from typing import Dict, Any
from app.utils.string_sanitizer import sanitize_and_indent

class TemplateEngine:
    def __init__(self):
        # We need to reach data/templates.json which is inside app/data
        # __file__ is inside .../PipelineGenie-execution-intelligence/RepoGenie/repo-analyzer-service/app/template_engine.py
        base_dir = os.path.dirname(__file__)
        data_dir = os.environ.get("PIPELINE_DATA_DIR", os.path.join(base_dir, "data"))
        templates_path = os.path.join(data_dir, "templates.json")
        try:
            with open(templates_path, "r", encoding="utf-8") as f:
                self.db = json.load(f)
        except Exception as e:
            self.db = []
            print(f"Warning: Failed to load templates.json: {e}")

    def get_template(self, component_type: str, identifier: str, platform: str) -> str:
        for item in self.db:
            if item.get("component_type") == component_type and (identifier is None or item.get("identifier") == identifier):
                return item.get("templates", {}).get(platform, "")
        return ""

    def compile_pipeline(self, spec: Dict[str, Any]) -> str:
        target_platform = spec.get("cicd_platform", "github_actions")
        
        # 1. Base Wrapper
        raw_wrapper = self.get_template("skeleton_wrapper", None, target_platform)
        if not raw_wrapper:
             return f"Error: No skeleton wrapper found for platform: {target_platform}"

        # 2. Extract specific parts
        build_stack = spec.get("build_stack", "")
        test_runner = spec.get("test_runner", "")
        code_quality = spec.get("code_quality", "")
        auth = spec.get("cloud_auth", "")
        deploy = spec.get("deployment_target", "")
        alert = spec.get("alerting", "")
        rollback = spec.get("automatic_rollback", "")
        
        if str(rollback).lower() == "true":
            rollback = "automatic_rollback"
        else:
            rollback = ""

        blocks = {
            "{{BUILD_STEPS}}": self.get_template("build_stack", build_stack, target_platform) if build_stack else "",
            "{{TEST_STEPS}}": self.get_template("testing", test_runner, target_platform) if test_runner else "",
            "{{QUALITY_STEPS}}": self.get_template("code_quality", code_quality, target_platform) if code_quality else "",
            "{{AUTH_STEPS}}": self.get_template("cloud_auth", auth, target_platform) if auth else "",
            "{{DEPLOY_STEPS}}": self.get_template("deployment_target", deploy, target_platform) if deploy else "",
            "{{ALERT_STEPS}}": self.get_template("alerting", alert, target_platform) if alert else "",
            "{{ROLLBACK_STEPS}}": self.get_template("failure_handling", rollback, target_platform) if rollback else "",
        }

        # Stitch
        current_wrapper = raw_wrapper
        for placeholder, raw_injection in blocks.items():
            if not raw_injection:
                current_wrapper = current_wrapper.replace(placeholder, "")
                continue

            lines = current_wrapper.split('\n')
            new_lines = []
            for line in lines:
                if placeholder in line:
                    indent = line[:line.find(placeholder)]
                    injected = sanitize_and_indent(raw_injection, indent)
                    new_lines.append(indent + injected)
                else:
                    new_lines.append(line)
            current_wrapper = "\n".join(new_lines)
            
        return current_wrapper
