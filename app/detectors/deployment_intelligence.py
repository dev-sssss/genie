import os
from app.utils.file_utils import (
    read_file_safe, find_file_anywhere,
    find_files_by_extension
)


def detect_deployment_intelligence(
    repo_path: str,
    infrastructure: dict,
    cloud: dict,
    project: dict
) -> dict:
    """Build complete deployment intelligence, avoiding default guesses."""
    result = {
        "target": None,
        "strategy": None,
        "registry": None,
        "environment": "production",
        "rollback_supported": False,
        "reason": []
    }

    has_k8s = infrastructure.get("has_kubernetes", False)
    has_helm = infrastructure.get("has_helm", False)
    has_docker = infrastructure.get("has_docker", False)
    has_compose = infrastructure.get("has_docker_compose", False)
    has_terraform = infrastructure.get("has_terraform", False)
    is_monorepo = project.get("is_monorepo", False)
    cloud_provider = cloud.get("provider")
    existing_target = cloud.get("deployment_target")
    existing_strategy = cloud.get("deployment_strategy")

    # Registry
    if cloud.get("registry"):
        result["registry"] = cloud.get("registry")
    elif cloud_provider == "AWS":
        result["registry"] = "ECR"
    elif cloud_provider == "GCP":
        result["registry"] = "GCR"
    elif cloud_provider == "Azure":
        result["registry"] = "ACR"
    elif has_docker:
        result["registry"] = "DockerHub"

    # Strategy / Target
    if existing_target:
        result["target"] = existing_target
        result["strategy"] = existing_strategy or "Direct Deploy"
        result["reason"].append(f"Target explicitly mapped from cloud provider properties: {existing_target}")
    elif has_k8s and has_helm:
        result["target"] = "Kubernetes"
        result["strategy"] = "Helm"
        result["rollback_supported"] = True
        result["reason"].append("Helm configurations and Kubernetes manifests detected")
    elif has_k8s:
        result["target"] = "Kubernetes"
        result["strategy"] = "kubectl apply"
        result["rollback_supported"] = True
        result["reason"].append("Kubernetes manifests detected")
    elif has_terraform:
        result["target"] = "Terraform IaC"
        result["strategy"] = "terraform apply"
        result["rollback_supported"] = True
        result["reason"].append("Terraform configurations discovered")
    else:
        # Stop guessing AWS EC2/ECS when there is no explicit target config.
        result["target"] = None
        result["strategy"] = existing_strategy
        result["reason"].append("No specific deployment cloud configurations discovered")

    # Rollback
    if has_k8s or has_helm or has_terraform:
        result["rollback_supported"] = True

    return result


def detect_infrastructure_graph(
    repo_path: str,
    project: dict,
    database: list,
    infrastructure: dict
) -> dict:
    """Build infrastructure relationship/dependency map."""
    graph = {}
    service_names = project.get("service_names", [])

    if not service_names:
        # Single service
        graph["backend"] = {"path": ".", "depends_on": []}
        if database:
            graph["backend"]["depends_on"].extend(
                [db.lower() for db in database]
            )
        return graph

    # Monorepo — map each service
    for service in service_names:
        graph[service] = {
            "path": f"{service}/",
            "depends_on": []
        }

    # Frontend depends on backend
    frontend_names = ["frontend", "web", "ui", "client"]
    backend_names = ["backend", "api", "server", "service"]

    for svc in service_names:
        if any(fn in svc.lower() for fn in frontend_names):
            # Find backend to depend on
            for dep in service_names:
                if any(bn in dep.lower() for bn in backend_names):
                    graph[svc]["depends_on"].append(dep)

    # Backend depends on databases
    for svc in service_names:
        if any(bn in svc.lower() for bn in backend_names):
            if database:
                graph[svc]["depends_on"].extend(
                    [db.lower() for db in database]
                )

    return graph


def detect_repo_architecture(repo_path: str) -> dict:
    """Map repository folder structure for LLM understanding."""
    architecture = {
        "root_files": [],
        "frontend_path": None,
        "backend_path": None,
        "dockerfile_path": None,
        "kubernetes_path": None,
        "terraform_path": None,
        "tests_path": None,
        "ci_cd_path": None,
        "repository_tree": {}
    }

    # Root files
    try:
        root_items = os.listdir(repo_path)
        architecture["root_files"] = [
            f for f in root_items
            if os.path.isfile(os.path.join(repo_path, f))
        ]
    except Exception:
        pass

    # Key folder detection
    folder_map = {
        "frontend": ["frontend", "web", "ui", "client", "public"],
        "backend": ["backend", "api", "server", "src", "app"],
        "kubernetes": ["k8s", "kubernetes", "manifests", "kube"],
        "terraform": ["terraform", "infra", "infrastructure", "iac"],
        "tests": ["tests", "test", "__tests__", "spec", "e2e"],
        "ci_cd": [".github", ".gitlab-ci.yml", "Jenkinsfile"]
    }

    for key, candidates in folder_map.items():
        for candidate in candidates:
            full_path = os.path.join(repo_path, candidate)
            if os.path.exists(full_path):
                rel_path = f"{candidate}/"
                if key == "frontend":
                    architecture["frontend_path"] = rel_path
                elif key == "backend":
                    architecture["backend_path"] = rel_path
                elif key == "kubernetes":
                    architecture["kubernetes_path"] = rel_path
                elif key == "terraform":
                    architecture["terraform_path"] = rel_path
                elif key == "tests":
                    architecture["tests_path"] = rel_path
                elif key == "ci_cd":
                    architecture["ci_cd_path"] = rel_path
                break

    # Dockerfile path
    from app.utils.file_utils import find_file_anywhere
    df = find_file_anywhere(repo_path, "Dockerfile")
    if df:
        architecture["dockerfile_path"] = os.path.relpath(df, repo_path).replace("\\", "/")

    # Build tree summary (top level only)
    tree = {}
    try:
        for item in os.listdir(repo_path):
            item_path = os.path.join(repo_path, item)
            # Skip hidden and generated folders
            if item.startswith(".") or item in ["node_modules", "dist", "build", "venv", ".venv"]:
                continue
            if os.path.isdir(item_path):
                try:
                    sub_items = [
                        f for f in os.listdir(item_path)
                        if not f.startswith(".")
                    ][:5]
                    tree[item] = sub_items
                except Exception:
                    tree[item] = []
            else:
                tree[item] = "file"
    except Exception:
        pass
    architecture["repository_tree"] = tree

    return architecture
