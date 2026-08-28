import os
import re
from app.utils.file_utils import (
    read_file_safe, read_file_raw,
    find_file_anywhere
)


def analyze_existing_cicd(repo_path: str, existing_ci: str) -> dict:
    """Deeply analyze existing CI/CD pipeline quality and parses workflows."""
    result = {
        "platform": existing_ci,
        "has_build": False,
        "has_tests": False,
        "has_security_scan": False,
        "has_docker_build": False,
        "has_deployment": False,
        "has_notifications": False,
        "has_caching": False,
        "has_approval_gate": False,
        "has_rollback": False,
        "quality_score": 0,
        "missing_stages": [],
        "existing_stages": [],
        "parsed_workflows": [],
        "existing_workflows": [],
        "confidence": 0.0,
        "evidence": []
    }

    ci_content = ""
    parsed_wf_list = []

    # Read and parse CI files
    if existing_ci == "GitHub Actions":
        workflows_dir = os.path.join(repo_path, ".github", "workflows")
        if os.path.exists(workflows_dir):
            result["confidence"] = 1.0
            for f in os.listdir(workflows_dir):
                if f.endswith(".yml") or f.endswith(".yaml"):
                    result["existing_workflows"].append(f)
                    path = os.path.join(workflows_dir, f)
                    raw_content = read_file_raw(path)
                    ci_content += raw_content
                    # Detailed Parse GH Actions
                    rel_path = os.path.relpath(path, repo_path).replace("\\", "/")
                    wf_data = parse_github_workflow(raw_content, rel_path)
                    parsed_wf_list.append(wf_data)
                    result["evidence"].append(f"Parsed GitHub Actions workflow at {rel_path} with {len(wf_data['jobs'])} jobs")

    elif existing_ci == "GitLab CI":
        path = find_file_anywhere(repo_path, ".gitlab-ci.yml")
        if path:
            result["confidence"] = 1.0
            raw_content = read_file_raw(path)
            ci_content = raw_content
            # Detailed Parse GitLab CI
            rel_path = os.path.relpath(path, repo_path).replace("\\", "/")
            wf_data = parse_gitlab_ci(raw_content, rel_path)
            parsed_wf_list.append(wf_data)
            result["evidence"].append(f"Parsed GitLab CI pipeline at {rel_path}")

    elif existing_ci == "Jenkins":
        path = find_file_anywhere(repo_path, "Jenkinsfile")
        if path:
            result["confidence"] = 0.95
            raw_content = read_file_raw(path)
            ci_content = raw_content
            rel_path = os.path.relpath(path, repo_path).replace("\\", "/")
            result["evidence"].append(f"Found Jenkinsfile at {rel_path}")

    elif existing_ci == "Azure Pipelines":
        path = find_file_anywhere(repo_path, "azure-pipelines.yml")
        if path:
            result["confidence"] = 1.0
            raw_content = read_file_raw(path)
            ci_content = raw_content
            rel_path = os.path.relpath(path, repo_path).replace("\\", "/")
            result["evidence"].append(f"Found Azure Pipelines configuration at {rel_path}")

    result["parsed_workflows"] = parsed_wf_list

    if not ci_content:
        return result

    content_lower = ci_content.lower()

    # Analyze stages
    if any(kw in content_lower for kw in ["npm install", "pip install", "mvn", "gradle", "go build"]):
        result["has_build"] = True
        result["existing_stages"].append("build")
        result["quality_score"] += 15

    if any(kw in content_lower for kw in ["npm test", "pytest", "mvn test", "go test", "jest"]):
        result["has_tests"] = True
        result["existing_stages"].append("test")
        result["quality_score"] += 20

    if any(kw in content_lower for kw in ["trivy", "snyk", "sonar", "owasp", "bandit", "safety"]):
        result["has_security_scan"] = True
        result["existing_stages"].append("security_scan")
        result["quality_score"] += 15

    if any(kw in content_lower for kw in ["docker build", "docker push", "buildx"]):
        result["has_docker_build"] = True
        result["existing_stages"].append("docker_build")
        result["quality_score"] += 15

    if any(kw in content_lower for kw in ["kubectl", "helm", "deploy", "ecs", "ec2", "heroku"]):
        result["has_deployment"] = True
        result["existing_stages"].append("deployment")
        result["quality_score"] += 15

    if any(kw in content_lower for kw in ["slack", "email", "notify", "teams", "discord"]):
        result["has_notifications"] = True
        result["existing_stages"].append("notifications")
        result["quality_score"] += 5

    if any(kw in content_lower for kw in ["cache", "actions/cache", "cache:"]):
        result["has_caching"] = True
        result["existing_stages"].append("caching")
        result["quality_score"] += 5

    if any(kw in content_lower for kw in ["environment:", "approval", "manual", "when: manual"]):
        result["has_approval_gate"] = True
        result["existing_stages"].append("approval_gate")
        result["quality_score"] += 5

    if any(kw in content_lower for kw in ["rollback", "undo", "revert"]):
        result["has_rollback"] = True
        result["existing_stages"].append("rollback")
        result["quality_score"] += 5

    # Calculate missing stages
    if not result["has_tests"]:
        result["missing_stages"].append("unit_tests")
    if not result["has_security_scan"]:
        result["missing_stages"].append("security_scan")
    if not result["has_notifications"]:
        result["missing_stages"].append("notifications")
    if not result["has_caching"]:
        result["missing_stages"].append("dependency_caching")
    if not result["has_approval_gate"]:
        result["missing_stages"].append("approval_gate")
    if not result["has_rollback"]:
        result["missing_stages"].append("rollback")

    result["quality_score"] = min(100, result["quality_score"])

    return result


def parse_github_workflow(content: str, file_path: str) -> dict:
    """Detailed parsing of GitHub Actions YAML blocks."""
    workflow = {
        "file_path": file_path,
        "name": None,
        "triggers": [],
        "jobs": []
    }
    
    # Extract workflow name
    name_match = re.search(r'^name:\s*(.+)$', content, re.MULTILINE)
    if name_match:
        workflow["name"] = name_match.group(1).strip().strip('"\'')
        
    # Extract simple triggers
    on_match = re.search(r'^on:\s*(.+)$', content, re.MULTILINE)
    if on_match:
        trigger_str = on_match.group(1).strip()
        if trigger_str.startswith('[') and trigger_str.endswith(']'):
            triggers = [t.strip().strip('"\'') for t in trigger_str[1:-1].split(',')]
            workflow["triggers"].extend(triggers)
        else:
            workflow["triggers"].append(trigger_str.strip('"\''))
    else:
        # Multiline trigger parse
        on_block_match = re.search(r'^on:\s*\n((?:\s+.*\n)+)', content, re.MULTILINE)
        if on_block_match:
            lines = on_block_match.group(1).splitlines()
            for line in lines:
                line = line.strip()
                if line.endswith(':'):
                    workflow["triggers"].append(line[:-1].strip())
                elif line.startswith('-'):
                    workflow["triggers"].append(line[1:].strip().strip('"\''))

    # Parse jobs
    lines = content.splitlines()
    in_jobs = False
    current_job = None
    job_indent = -1
    jobs_start_indent = -1
    
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
            
        indent = len(line) - len(line.lstrip())
        
        # Entrance to job config block
        if stripped == "jobs:":
            in_jobs = True
            job_indent = -1
            continue
            
        if in_jobs:
            # Check indentation to see if we exited jobs block
            if job_indent != -1 and indent <= job_indent - 2 and not stripped.startswith('-'):
                in_jobs = False
                continue
                
            if job_indent == -1:
                jobs_start_indent = indent
                job_indent = indent
                
            # Job keys (e.g. "build:")
            if indent == job_indent and stripped.endswith(':'):
                job_name = stripped[:-1].strip()
                current_job = {
                    "name": job_name,
                    "steps": [],
                    "image": None
                }
                workflow["jobs"].append(current_job)
                continue
                
            if current_job:
                if stripped.startswith("runs-on:"):
                    current_job["image"] = stripped.replace("runs-on:", "").strip().strip('"\'')
                # Grab step names / runs
                if stripped.startswith("- name:") or stripped.startswith("- run:") or stripped.startswith("- uses:"):
                    step_val = stripped[1:].strip()
                    clean_step = re.sub(r'^(name:|run:|uses:)\s*', '', step_val).strip().strip('"\'')
                    current_job["steps"].append(clean_step)
                    
    return workflow


def parse_gitlab_ci(content: str, file_path: str) -> dict:
    """Detailed parsing of GitLab CI directives."""
    workflow = {
        "file_path": file_path,
        "name": "GitLab CI",
        "triggers": [],
        "jobs": []
    }
    
    lines = content.splitlines()
    current_job = None
    
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith('#'):
            continue
            
        indent = len(line) - len(line.lstrip())
        
        if indent == 0 and stripped.endswith(':') and not stripped.startswith(('stages:', 'default:', 'variables:', 'cache:', 'image:')):
            current_job = {
                "name": stripped[:-1].strip(),
                "steps": [],
                "image": None
            }
            workflow["jobs"].append(current_job)
            continue
            
        if current_job and indent > 0:
            if stripped.startswith("image:"):
                current_job["image"] = stripped.replace("image:", "").strip().strip('"\'')
            elif stripped.startswith("-"):
                current_job["steps"].append(stripped[1:].strip().strip('"\''))
                
    return workflow
