import os
import re
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere, find_files_by_extension
)


def detect_security(repo_path: str, language: str) -> dict:
    """Detect security issues and risks in the repo."""
    result = {
        "has_hardcoded_secrets": False,
        "hardcoded_secret_files": [],
        "runs_as_root": False,
        "has_privileged_container": False,
        "missing_health_check": True,
        "missing_resource_limits": True,
        "exposed_debug_mode": False,
        "security_risks": [],
        "security_score": 100
    }

    # ---- Dockerfile Security ----
    dockerfile = find_file_anywhere(repo_path, "Dockerfile")
    if dockerfile:
        content = read_file_raw(dockerfile)
        content_lower = content.lower()

        # Check if running as root
        if "user root" in content_lower or \
           ("user " not in content_lower and "from " in content_lower):
            result["runs_as_root"] = True
            result["security_risks"].append("Container runs as root user")
            result["security_score"] -= 20

        # Check for privileged
        if "privileged" in content_lower:
            result["has_privileged_container"] = True
            result["security_risks"].append("Privileged container detected")
            result["security_score"] -= 20

        # Check for HEALTHCHECK
        if "healthcheck" in content_lower:
            result["missing_health_check"] = False

        # Check for debug mode
        if "debug=true" in content_lower or "debug = true" in content_lower:
            result["exposed_debug_mode"] = True
            result["security_risks"].append("Debug mode enabled in container")
            result["security_score"] -= 10

    # ---- Hardcoded Secrets Detection ----
    secret_patterns = [
        r'(?:password|passwd|pwd)\s*=\s*["\'][^"\']{6,}["\']',
        r'(?:api_key|apikey|api-key)\s*=\s*["\'][^"\']{10,}["\']',
        r'(?:secret|token)\s*=\s*["\'][^"\']{10,}["\']',
        r'(?:aws_access_key|aws_secret)\s*=\s*["\'][^"\']{10,}["\']',
        r'-----BEGIN (?:RSA |EC )?PRIVATE KEY-----',
    ]

    # Scan source files for hardcoded secrets
    scan_extensions = [".py", ".js", ".ts", ".java", ".go", ".env"]
    for ext in scan_extensions:
        files = find_files_by_extension(repo_path, ext)
        for f in files[:20]:
            # Skip test files
            if "test" in f.lower() or "spec" in f.lower():
                continue
            content = read_file_raw(f)
            for pattern in secret_patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    result["has_hardcoded_secrets"] = True
                    rel_path = os.path.relpath(f, repo_path)
                    if rel_path not in result["hardcoded_secret_files"]:
                        result["hardcoded_secret_files"].append(rel_path)
                    result["security_score"] -= 15
                    break

    if result["has_hardcoded_secrets"]:
        result["security_risks"].append(
            f"Hardcoded secrets found in: {', '.join(result['hardcoded_secret_files'][:3])}"
        )

    # ---- K8s Security ----
    yaml_files = find_files_by_extension(repo_path, ".yaml") + \
                 find_files_by_extension(repo_path, ".yml")
    for yf in yaml_files[:20]:
        content = read_file_safe(yf)
        if "kind:" not in content:
            continue
        if "resources:" in content:
            result["missing_resource_limits"] = False
        if "privileged: true" in content:
            result["has_privileged_container"] = True
            result["security_risks"].append("Privileged K8s container detected")
            result["security_score"] -= 20

    if result["missing_resource_limits"]:
        result["security_risks"].append("No resource limits defined in K8s manifests")
        result["security_score"] -= 10

    # ---- Flask/Django debug mode ----
    if language == "Python":
        py_files = find_files_by_extension(repo_path, ".py")
        for pf in py_files[:20]:
            content = read_file_safe(pf)
            if "debug=true" in content or "debug = true" in content:
                result["exposed_debug_mode"] = True
                result["security_risks"].append("Debug mode enabled in application")
                result["security_score"] -= 10
                break

    # Cap score between 0 and 100
    result["security_score"] = max(0, min(100, result["security_score"]))

    return result
