import os
import subprocess
import re
from app.utils.file_utils import (
    read_file_safe, read_file_raw,
    find_file_anywhere, find_files_by_extension
)


def detect_branch_strategy(repo_path: str) -> dict:
    """
    Detect branch strategy from CI config and git refs.
    Maps branches to deployment environments so AI can generate
    correct pipeline triggers.
    """
    result = {
        "default_branch": "main",
        "branches": [],
        "strategy": "unknown",
        "branch_environment_map": {},
        "trigger_branches": [],
        "protected_branches": [],
    }

    # ── 1. Read branch triggers from existing CI files ──────
    ci_content = ""

    # GitHub Actions
    workflows_dir = os.path.join(repo_path, ".github", "workflows")
    if os.path.exists(workflows_dir):
        for f in os.listdir(workflows_dir):
            if f.endswith(".yml") or f.endswith(".yaml"):
                ci_content += read_file_raw(os.path.join(workflows_dir, f))

    # GitLab CI
    gitlab = find_file_anywhere(repo_path, ".gitlab-ci.yml")
    if gitlab:
        ci_content += read_file_raw(gitlab)

    # Jenkins
    jenkinsfile = find_file_anywhere(repo_path, "Jenkinsfile")
    if jenkinsfile:
        ci_content += read_file_raw(jenkinsfile)

    # ── 2. Extract branch names from CI triggers ─────────────
    branches_found = set()

    # GitHub Actions: on: push: branches: / pull_request: branches:
    ga_branches = re.findall(
        r"branches\s*:\s*\n((?:\s+-\s+[^\n]+\n?)+)", ci_content
    )
    for block in ga_branches:
        for b in re.findall(r"-\s+['\"]?([^'\"\n]+)['\"]?", block):
            branches_found.add(b.strip())

    # GitLab: only: / rules: refs:
    gl_branches = re.findall(r"refs?:\s*\n((?:\s+-\s+[^\n]+\n?)+)", ci_content)
    for block in gl_branches:
        for b in re.findall(r"-\s+['\"]?([^'\"\n]+)['\"]?", block):
            branches_found.add(b.strip())

    # Jenkins: when { branch '...' } or branch pattern
    for b in re.findall(r"branch\s+['\"]([^'\"]+)['\"]", ci_content):
        branches_found.add(b.strip())

    # ── 3. Try git to get actual remote branches ─────────────
    try:
        result_git = subprocess.run(
            ["git", "-C", repo_path, "branch", "-r"],
            capture_output=True, text=True, timeout=10
        )
        if result_git.returncode == 0:
            for line in result_git.stdout.splitlines():
                line = line.strip().replace("origin/", "")
                if line and "->" not in line:
                    branches_found.add(line)
    except Exception:
        pass

    # ── 4. Determine default branch ───────────────────────────
    try:
        head = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=10
        )
        if head.returncode == 0:
            result["default_branch"] = head.stdout.strip() or "main"
    except Exception:
        pass

    # Common defaults if nothing detected
    if not branches_found:
        branches_found = {"main", "develop", "feature/*"}

    result["branches"] = sorted(branches_found)

    # ── 5. Detect branching strategy ─────────────────────────
    has_main = any(b in ["main", "master"] for b in branches_found)
    has_develop = "develop" in branches_found
    has_release = any("release" in b for b in branches_found)
    has_feature = any("feature" in b for b in branches_found)
    has_staging = any("staging" in b for b in branches_found)

    if has_main and has_develop and has_feature:
        result["strategy"] = "gitflow"
        result["protected_branches"] = ["main", "develop"]
    elif has_main and has_staging:
        result["strategy"] = "environment-branches"
        result["protected_branches"] = ["main", "staging"]
    elif has_main and has_feature:
        result["strategy"] = "github-flow"
        result["protected_branches"] = ["main"]
    elif has_main:
        result["strategy"] = "trunk-based"
        result["protected_branches"] = ["main"]
    else:
        result["strategy"] = "github-flow"
        result["protected_branches"] = ["main"]

    # ── 6. Map branches to environments ──────────────────────
    env_map = {}
    for b in branches_found:
        if b in ["main", "master"]:
            env_map[b] = "production"
        elif b == "develop":
            env_map[b] = "staging"
        elif b == "staging":
            env_map[b] = "staging"
        elif "release" in b:
            env_map[b] = "staging"
        elif "feature" in b or b.startswith("feat"):
            env_map[b] = "development"
        elif "hotfix" in b:
            env_map[b] = "production"
        else:
            env_map[b] = "development"

    result["branch_environment_map"] = env_map

    # ── 7. Trigger branches for pipeline ─────────────────────
    result["trigger_branches"] = [
        b for b in branches_found
        if b in ["main", "master", "develop", "staging"]
        or "release" in b
    ] or ["main"]

    return result
