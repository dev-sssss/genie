def calculate_grade(
    backend: dict,
    frontend: dict,
    infrastructure: dict,
    database: list,
    cloud: dict,
    ci_cd: dict,
    project: dict
) -> dict:
    """
    Calculate the project grade and reasons.
    Returns grade: beginner / mid-level / enterprise
    """
    score = 0
    reasons = []
    missing = []

    # Infrastructure scoring
    if infrastructure.get("has_docker"):
        score += 10
        reasons.append("has Docker")
    else:
        missing.append("add Dockerfile for containerization")

    if infrastructure.get("docker_multistage"):
        score += 10
        reasons.append("has multi-stage Dockerfile")
    else:
        missing.append("use multi-stage Dockerfile for smaller images")

    if infrastructure.get("has_kubernetes"):
        score += 20
        reasons.append("has Kubernetes manifests")
    else:
        missing.append("add Kubernetes manifests for orchestration")

    if infrastructure.get("has_terraform"):
        score += 15
        reasons.append("has Terraform IaC")
    else:
        missing.append("add Terraform for infrastructure as code")

    if infrastructure.get("has_helm"):
        score += 10
        reasons.append("has Helm charts")
    else:
        missing.append("add Helm charts for K8s deployments")

    if infrastructure.get("has_docker_compose"):
        score += 5
        reasons.append("has Docker Compose")

    # Testing scoring
    if backend.get("has_tests"):
        score += 10
        reasons.append("has test suite")
    else:
        missing.append("add unit tests")

    if backend.get("coverage_threshold"):
        score += 5
        reasons.append("has coverage threshold configured")
    else:
        missing.append("configure test coverage threshold (min 80%)")

    # Code quality scoring
    if backend.get("code_quality"):
        score += 5
        reasons.append(f"has code quality tools: {', '.join(backend['code_quality'])}")
    else:
        missing.append("add linting tools (flake8/eslint)")

    # CI/CD scoring
    if ci_cd.get("has_ci"):
        score += 10
        reasons.append(f"has existing CI/CD: {ci_cd.get('existing_ci')}")
    else:
        missing.append("add CI/CD pipeline")

    # Cloud scoring
    if cloud.get("provider"):
        score += 10
        reasons.append(f"targets {cloud['provider']} cloud")

    # Frontend scoring
    if frontend.get("framework"):
        score += 5
        reasons.append(f"has frontend: {frontend['framework']}")

    # Database scoring
    if database:
        score += 5
        reasons.append(f"uses databases: {', '.join(database)}")

    # Health endpoint scoring
    if backend.get("health_endpoint"):
        score += 5
        reasons.append("has health check endpoint")
    else:
        missing.append("add /health endpoint for K8s probes")

    # Calculate grade
    if score >= 70:
        grade = "enterprise"
    elif score >= 40:
        grade = "mid-level"
    else:
        grade = "beginner"

    return {
        "grade": grade,
        "score": score,
        "grade_reason": reasons,
        "missing_for_enterprise": missing if grade != "enterprise" else []
    }
