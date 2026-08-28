import os
import re
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere, find_files_by_extension,
    get_root_files
)


_ENV_KEYWORDS = {
    "development": ["dev", "development", "local"],
    "staging":     ["staging", "stage", "uat", "qa", "preprod", "pre-prod"],
    "production":  ["prod", "production", "live", "main", "master"],
}


def detect_environments(repo_path: str) -> dict:
    """
    Discover deployment environments so AI can generate
    multi-stage pipelines: dev → staging → approval → prod.
    """
    result = {
        "environments": [],
        "has_staging": False,
        "has_production": True,       # always assume at minimum
        "has_development": False,
        "env_config_files": [],       # .env.staging, .env.prod, etc.
        "deployment_environments": [], # ordered pipeline stages
        "approval_required_for": [],
    }

    found_envs: set[str] = set()

    # ── 1. Scan .env.* files ──────────────────────────────────
    root_files = get_root_files(repo_path)
    for f in root_files:
        if f.startswith(".env"):
            suffix = f.replace(".env", "").lstrip(".")
            if suffix:
                result["env_config_files"].append(f)
                canonical = _canonicalize(suffix)
                if canonical:
                    found_envs.add(canonical)

    # Also walk subdirs for env files
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        for f in files:
            if f.startswith(".env.") or f.endswith(".env"):
                suffix = re.sub(r"\.env\.?", "", f).strip(".")
                canonical = _canonicalize(suffix)
                if canonical:
                    found_envs.add(canonical)

    # ── 2. Scan CI files for environment: / stage: blocks ─────
    ci_content = _collect_ci_content(repo_path)

    # GitHub Actions environment:
    for m in re.findall(r'environment\s*:\s*["\']?([a-zA-Z0-9_-]+)["\']?', ci_content):
        canonical = _canonicalize(m)
        if canonical:
            found_envs.add(canonical)

    # GitLab CI stage: names
    for m in re.findall(r'^\s*stage\s*:\s*([a-zA-Z0-9_-]+)', ci_content, re.MULTILINE):
        canonical = _canonicalize(m)
        if canonical:
            found_envs.add(canonical)

    # ── 3. Scan k8s namespace / Helm values files ─────────────
    yaml_files = (
        find_files_by_extension(repo_path, ".yaml") +
        find_files_by_extension(repo_path, ".yml")
    )
    for yf in yaml_files[:30]:
        content = read_file_safe(yf)
        fname = os.path.basename(yf).lower()

        # values-staging.yaml / values.prod.yaml
        for kw_list in _ENV_KEYWORDS.values():
            for kw in kw_list:
                if kw in fname:
                    canonical = _canonicalize(kw)
                    if canonical:
                        found_envs.add(canonical)

        # k8s namespace: staging / production
        for m in re.findall(r'namespace\s*:\s*([a-zA-Z0-9_-]+)', content):
            canonical = _canonicalize(m)
            if canonical:
                found_envs.add(canonical)

    # ── 4. Scan Terraform workspace names / var files ─────────
    tf_files = find_files_by_extension(repo_path, ".tf")
    for tf in tf_files[:10]:
        content = read_file_safe(tf)
        for m in re.findall(r'workspace\s*=\s*["\']([^"\']+)["\']', content):
            canonical = _canonicalize(m)
            if canonical:
                found_envs.add(canonical)

    # ── 5. Normalise & build result ───────────────────────────
    if not found_envs:
        # Sensible default
        found_envs = {"production"}

    result["has_development"] = "development" in found_envs
    result["has_staging"]     = "staging" in found_envs
    result["has_production"]  = True   # always

    all_envs = []
    if result["has_development"]:
        all_envs.append("development")
    if result["has_staging"]:
        all_envs.append("staging")
    all_envs.append("production")

    result["environments"] = all_envs

    # ── 6. Build ordered pipeline deployment stages ───────────
    deployment_stages = []
    if result["has_development"]:
        deployment_stages.append("deploy_development")
    if result["has_staging"]:
        deployment_stages.append("deploy_staging")
        result["approval_required_for"].append("production")
    deployment_stages.append("deploy_production")

    result["deployment_environments"] = deployment_stages

    return result


# ── helpers ───────────────────────────────────────────────────

def _canonicalize(name: str) -> str | None:
    name = name.lower().strip()
    for canonical, keywords in _ENV_KEYWORDS.items():
        if any(kw == name or kw in name for kw in keywords):
            return canonical
    return None


def _collect_ci_content(repo_path: str) -> str:
    content = ""
    workflows_dir = os.path.join(repo_path, ".github", "workflows")
    if os.path.exists(workflows_dir):
        for f in os.listdir(workflows_dir):
            if f.endswith((".yml", ".yaml")):
                content += read_file_raw(os.path.join(workflows_dir, f))

    for fname in [".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"]:
        path = find_file_anywhere(repo_path, fname)
        if path:
            content += read_file_raw(path)

    return content
