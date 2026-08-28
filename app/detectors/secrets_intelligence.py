import re
import os
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere, find_files_by_extension
)


# Canonical secret variables known to be needed per cloud/tool
_CLOUD_SECRETS = {
    "AWS": [
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "AWS_REGION",
    ],
    "GCP": [
        "GCP_SERVICE_ACCOUNT_KEY",
        "GCP_PROJECT_ID",
    ],
    "Azure": [
        "AZURE_CLIENT_ID",
        "AZURE_CLIENT_SECRET",
        "AZURE_TENANT_ID",
        "AZURE_SUBSCRIPTION_ID",
    ],
}

_REGISTRY_SECRETS = {
    "DockerHub": ["DOCKERHUB_USERNAME", "DOCKERHUB_TOKEN"],
    "ECR":       [],   # uses AWS creds
    "GCR":       [],   # uses GCP creds
    "ACR":       ["ACR_LOGIN_SERVER", "ACR_USERNAME", "ACR_PASSWORD"],
    "GHCR":      ["GHCR_TOKEN"],
}

_SECRET_ENV_KEYWORDS = [
    "secret", "key", "token", "password", "passwd",
    "pwd", "api_key", "auth", "credential", "private",
    "cert", "jwt", "oauth", "client_secret", "access_token",
]


def detect_required_secrets(
    repo_path: str,
    language: str,
    cloud_provider: str | None,
    registry: str | None,
    has_docker: bool,
) -> dict:
    """
    Build the full list of secrets the pipeline will need so AI can generate
    proper `${{ secrets.XYZ }}` references without guessing.
    """
    result = {
        "required_secrets": [],
        "optional_secrets": [],
        "secret_groups": {
            "cloud": [],
            "registry": [],
            "app": [],
            "notifications": [],
        }
    }

    collected = set()

    # ── 1. Cloud provider secrets ─────────────────────────────
    if cloud_provider and cloud_provider in _CLOUD_SECRETS:
        for s in _CLOUD_SECRETS[cloud_provider]:
            result["secret_groups"]["cloud"].append(s)
            collected.add(s)

    # ── 2. Registry secrets ───────────────────────────────────
    reg = registry or ("DockerHub" if has_docker else None)
    if reg and reg in _REGISTRY_SECRETS:
        for s in _REGISTRY_SECRETS[reg]:
            result["secret_groups"]["registry"].append(s)
            collected.add(s)

    # ── 3. App secrets from source code (process.env / os.environ) ──
    app_vars = _scan_source_for_secrets(repo_path, language)
    for v in app_vars:
        if v not in collected:
            result["secret_groups"]["app"].append(v)
            collected.add(v)

    # ── 4. Env file secrets (.env.example / .env.sample) ─────
    for env_file in [".env.example", ".env.sample", ".env.template"]:
        path = find_file_anywhere(repo_path, env_file)
        if path:
            for line in read_file_raw(path).splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var = line.split("=")[0].strip()
                    if var and any(kw in var.lower() for kw in _SECRET_ENV_KEYWORDS):
                        if var not in collected:
                            result["secret_groups"]["app"].append(var)
                            collected.add(var)

    # ── 5. CI file secrets (already referenced) ───────────────
    ci_secrets = _scan_ci_for_secrets(repo_path)
    for s in ci_secrets:
        if s not in collected:
            result["optional_secrets"].append(s)
            collected.add(s)

    # ── 6. Notification secrets ───────────────────────────────
    combined = _read_all_source(repo_path)
    if "slack" in combined.lower():
        result["secret_groups"]["notifications"].append("SLACK_WEBHOOK_URL")
    if "discord" in combined.lower():
        result["secret_groups"]["notifications"].append("DISCORD_WEBHOOK_URL")
    if "teams" in combined.lower():
        result["secret_groups"]["notifications"].append("TEAMS_WEBHOOK_URL")

    # ── 7. Flatten required_secrets ──────────────────────────
    for group_secrets in result["secret_groups"].values():
        for s in group_secrets:
            if s not in result["required_secrets"]:
                result["required_secrets"].append(s)

    return result


# ── helpers ───────────────────────────────────────────────────

def _scan_source_for_secrets(repo_path: str, language: str) -> list:
    found = set()

    if language == "Node.js":
        files = (
            find_files_by_extension(repo_path, ".js") +
            find_files_by_extension(repo_path, ".ts")
        )
        for f in files[:40]:
            if "node_modules" in f:
                continue
            content = read_file_raw(f)
            for m in re.findall(r'process\.env\.([A-Z_][A-Z0-9_]+)', content):
                if any(kw in m.lower() for kw in _SECRET_ENV_KEYWORDS):
                    found.add(m)

    elif language == "Python":
        files = find_files_by_extension(repo_path, ".py")
        for f in files[:40]:
            content = read_file_raw(f)
            for m in re.findall(
                r'os\.(?:environ(?:\.get)?|getenv)\(["\']([A-Z_][A-Z0-9_]+)["\']',
                content
            ):
                if any(kw in m.lower() for kw in _SECRET_ENV_KEYWORDS):
                    found.add(m)

    elif language == "Java":
        files = find_files_by_extension(repo_path, ".java")
        for f in files[:20]:
            content = read_file_raw(f)
            for m in re.findall(r'System\.getenv\(["\']([A-Z_][A-Z0-9_]+)["\']', content):
                if any(kw in m.lower() for kw in _SECRET_ENV_KEYWORDS):
                    found.add(m)

    elif language == "Go":
        files = find_files_by_extension(repo_path, ".go")
        for f in files[:30]:
            content = read_file_raw(f)
            for m in re.findall(r'os\.Getenv\(["\']([A-Z_][A-Z0-9_]+)["\']', content):
                if any(kw in m.lower() for kw in _SECRET_ENV_KEYWORDS):
                    found.add(m)

    return sorted(found)


def _scan_ci_for_secrets(repo_path: str) -> list:
    found = set()
    ci_content = ""

    workflows_dir = os.path.join(repo_path, ".github", "workflows")
    if os.path.exists(workflows_dir):
        for f in os.listdir(workflows_dir):
            if f.endswith((".yml", ".yaml")):
                ci_content += read_file_raw(os.path.join(workflows_dir, f))

    for fname in [".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"]:
        path = find_file_anywhere(repo_path, fname)
        if path:
            ci_content += read_file_raw(path)

    for m in re.findall(r'secrets\.([A-Z_][A-Z0-9_]+)', ci_content):
        found.add(m)

    return sorted(found)


def _read_all_source(repo_path: str) -> str:
    combined = ""
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d != "node_modules"]
        for f in files:
            if f.endswith((".yml", ".yaml", ".json", ".py", ".js", ".ts")):
                try:
                    combined += read_file_raw(os.path.join(root, f))
                except Exception:
                    pass
        if len(combined) > 200_000:
            break
    return combined
