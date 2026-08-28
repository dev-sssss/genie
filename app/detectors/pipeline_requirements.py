def build_pipeline_requirements(
    backend: dict,
    frontend: dict,
    infrastructure: dict,
    database: list,
    cloud: dict,
    ci_cd: dict,
    monitoring: dict,
    security: dict,
    project: dict,
    testing: dict = None,
) -> dict:
    """
    Build explicit pipeline requirements.
    This is the BRIDGE between analysis and generation.
    Zero guesswork for AI.
    """
    req = {
        # Build stages
        "install_dependencies": True,
        "lint": False,
        "build_backend": False,
        "build_frontend": False,

        # Test stages
        "unit_tests": False,
        "integration_tests": False,
        "e2e_tests": False,
        "coverage_check": False,

        # Security stages
        "security_scan": True,  # Always recommended
        "secret_detection": False,
        "dependency_audit": True,  # Always recommended

        # Docker stages
        "docker_build": False,
        "docker_push": False,
        "docker_scan": False,

        # Infrastructure stages
        "terraform_plan": False,
        "terraform_apply": False,
        "helm_deploy": False,
        "k8s_deploy": False,

        # Deployment stages
        "deploy_staging": False,
        "deploy_production": False,
        "approval_gate": False,
        "rollback": False,

        # Post-deploy stages
        "health_check": False,
        "smoke_tests": False,
        "notify": True,  # Always recommended

        # DB stages
        "db_migration": False,

        # Monitoring stages
        "monitoring_setup": False,

        # Deployment target
        "deployment_target": None,
        "deployment_strategy": None,
        "container_registry": None,
    }

    # ---- Backend ----
    if backend.get("code_quality"):
        req["lint"] = True

    if backend.get("language") in ["Java", "Go"]:
        req["build_backend"] = True

    # ---- Testing (from testing intelligence dict) ----
    testing = testing or {}
    if testing.get("unit"):
        req["unit_tests"] = True
    if testing.get("integration"):
        req["integration_tests"] = True
    if testing.get("e2e"):
        req["e2e_tests"] = True
    if testing.get("coverage"):
        req["coverage_check"] = True

    # ---- Frontend ----
    if frontend.get("framework") and frontend.get("framework") != "Vanilla JS":
        req["build_frontend"] = True
        if frontend.get("test_command"):
            req["unit_tests"] = True

    # ---- Docker ----
    if infrastructure.get("has_docker"):
        req["docker_build"] = True
        req["docker_push"] = True
        req["docker_scan"] = True

    # ---- Kubernetes ----
    if infrastructure.get("has_kubernetes"):
        req["k8s_deploy"] = True
        req["deploy_staging"] = True
        req["deploy_production"] = True
        req["approval_gate"] = True
        req["rollback"] = True
        req["health_check"] = True
        req["smoke_tests"] = True

    # ---- Terraform ----
    if infrastructure.get("has_terraform"):
        req["terraform_plan"] = True
        req["terraform_apply"] = True

    # ---- Helm ----
    if infrastructure.get("has_helm"):
        req["helm_deploy"] = True
        req["k8s_deploy"] = False  # Helm replaces raw k8s deploy

    # ---- Database ----
    if database:
        req["db_migration"] = True

    # ---- Cloud ----
    if cloud.get("deployment_target"):
        req["deployment_target"] = cloud.get("deployment_target")
        req["deploy_staging"] = True
        req["deploy_production"] = True
        req["approval_gate"] = True

    req["deployment_strategy"] = cloud.get("deployment_strategy", "Docker")
    req["container_registry"] = cloud.get("registry", "DockerHub")

    # ---- Health check ----
    if backend.get("health_endpoint"):
        req["health_check"] = True
        req["smoke_tests"] = True

    # ---- Monitoring ----
    if monitoring.get("tools_detected"):
        req["monitoring_setup"] = True

    # ---- Security ----
    if security.get("has_hardcoded_secrets"):
        req["secret_detection"] = True

    return req


def build_deployment_recommendation(
    infrastructure: dict,
    cloud: dict,
    project: dict,
    backend: dict
) -> dict:
    """Generate deployment recommendation with reasoning."""
    recommendation = {
        "recommended_target": None,
        "recommended_strategy": None,
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

    # If cloud provider already detected
    if existing_target:
        recommendation["recommended_target"] = existing_target
        recommendation["reason"].append(f"Cloud provider hints detected: {cloud_provider}")

    # Kubernetes-based
    elif has_k8s and has_helm:
        recommendation["recommended_target"] = "Kubernetes (EKS/GKE/AKS)"
        recommendation["recommended_strategy"] = "Helm"
        recommendation["reason"].append("Helm charts detected")
        recommendation["reason"].append("Kubernetes manifests present")

    elif has_k8s:
        recommendation["recommended_target"] = "Kubernetes (EKS/GKE/AKS)"
        recommendation["recommended_strategy"] = "Kubernetes Manifests"
        recommendation["reason"].append("Kubernetes manifests present")

    # Docker-based
    elif has_docker and is_monorepo:
        recommendation["recommended_target"] = "AWS ECS Fargate"
        recommendation["recommended_strategy"] = "Docker Compose"
        recommendation["reason"].append("Dockerized multi-service application")
        recommendation["reason"].append("No Kubernetes manifests found")
        recommendation["reason"].append("Docker Compose suitable for this scale")

    elif has_docker and not is_monorepo:
        recommendation["recommended_target"] = "AWS EC2 or ECS"
        recommendation["recommended_strategy"] = "Docker"
        recommendation["reason"].append("Dockerized single service application")
        recommendation["reason"].append("Simple deployment sufficient")

    elif has_compose:
        recommendation["recommended_target"] = "AWS EC2"
        recommendation["recommended_strategy"] = "Docker Compose"
        recommendation["reason"].append("Docker Compose present")
        recommendation["reason"].append("EC2 can run compose directly")

    else:
        recommendation["recommended_target"] = "AWS EC2"
        recommendation["recommended_strategy"] = "Direct Deploy"
        recommendation["reason"].append("No containerization detected")
        recommendation["reason"].append("Direct server deployment recommended")

    return recommendation
