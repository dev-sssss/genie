import os
import re
from app.utils.file_utils import (
    read_file_safe, read_file_raw,
    find_file_anywhere, find_files_by_extension,
    folder_exists, get_root_files
)


def detect_infrastructure(repo_path: str) -> dict:
    """Deep infrastructure detection."""
    result = {
        "has_docker": False,
        "docker_image_name": None,
        "docker_exposed_ports": [],
        "docker_multistage": False,
        "has_docker_compose": False,
        "compose_services": [],
        "has_kubernetes": False,
        "k8s_namespaces": [],
        "k8s_service_names": [],
        "k8s_has_ingress": False,
        "has_terraform": False,
        "terraform_resources": [],
        "has_helm": False,
        "has_ansible": False,
    }

    # ---- Docker ----
    dockerfile_path = find_file_anywhere(repo_path, "Dockerfile")
    if dockerfile_path:
        result["has_docker"] = True
        content = read_file_raw(dockerfile_path)
        content_lower = content.lower()

        # Multi-stage
        from_count = len(re.findall(r'^\s*FROM\s+', content, re.MULTILINE | re.IGNORECASE))
        result["docker_multistage"] = from_count > 1

        # Exposed ports
        ports = re.findall(r'EXPOSE\s+(\d+)', content, re.IGNORECASE)
        result["docker_exposed_ports"] = ports

        # Image name from existing CI or compose
        ci_files = [
            find_file_anywhere(repo_path, "docker-compose.yml"),
            find_file_anywhere(repo_path, "docker-compose.yaml"),
        ]
        for cf in ci_files:
            if cf:
                c = read_file_raw(cf)
                match = re.search(r'image:\s*([^\s\n]+)', c)
                if match:
                    result["docker_image_name"] = match.group(1).strip()
                    break

    # ---- Docker Compose ----
    compose_path = find_file_anywhere(repo_path, "docker-compose.yml") or \
                   find_file_anywhere(repo_path, "docker-compose.yaml")
    if compose_path:
        result["has_docker_compose"] = True
        content = read_file_raw(compose_path)
        # Extract service names
        services = re.findall(r'^\s{2}([a-zA-Z][a-zA-Z0-9_-]*):\s*$', content, re.MULTILINE)
        result["compose_services"] = [s for s in services if s not in ["version", "networks", "volumes"]]

    # ---- Kubernetes ----
    yaml_files = find_files_by_extension(repo_path, ".yaml") + \
                 find_files_by_extension(repo_path, ".yml")
    k8s_service_names = []
    k8s_namespaces = set()

    for yf in yaml_files[:30]:
        content = read_file_raw(yf)
        content_lower = content.lower()
        if "kind:" not in content_lower:
            continue
        if any(k in content_lower for k in ["deployment", "service", "pod", "ingress", "configmap"]):
            result["has_kubernetes"] = True
            # Extract service names
            name_match = re.search(r'name:\s*([^\s\n]+)', content)
            if name_match:
                k8s_service_names.append(name_match.group(1).strip())
            # Extract namespaces
            ns_match = re.search(r'namespace:\s*([^\s\n]+)', content)
            if ns_match:
                k8s_namespaces.add(ns_match.group(1).strip())
            # Check for ingress
            if "ingress" in content_lower:
                result["k8s_has_ingress"] = True

    result["k8s_service_names"] = list(set(k8s_service_names))[:10]
    result["k8s_namespaces"] = list(k8s_namespaces)[:5]

    # ---- Terraform ----
    tf_files = find_files_by_extension(repo_path, ".tf")
    if tf_files or folder_exists(repo_path, "terraform"):
        result["has_terraform"] = True
        resources = []
        for tf in tf_files[:10]:
            content = read_file_raw(tf)
            matches = re.findall(r'resource\s+"([^"]+)"', content)
            resources.extend(matches)
        result["terraform_resources"] = list(set(resources))[:10]

    # ---- Helm ----
    if find_file_anywhere(repo_path, "Chart.yaml") or \
       folder_exists(repo_path, "helm") or \
       folder_exists(repo_path, "charts"):
        result["has_helm"] = True

    # ---- Ansible ----
    if find_file_anywhere(repo_path, "playbook.yml") or \
       find_file_anywhere(repo_path, "playbook.yaml") or \
       folder_exists(repo_path, "ansible") or \
       find_file_anywhere(repo_path, "inventory.ini"):
        result["has_ansible"] = True

    return result
