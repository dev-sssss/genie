from typing import Optional


def build_recommended_pipeline(
    backend: dict,
    frontend: dict,
    testing: dict,
    infrastructure: dict,
    database: dict,
    cloud: dict,
    ci_cd: dict,
    monitoring: dict,
    security: dict,
    project: dict,
    environments: dict,
    scripts: dict,
    runtime: dict,
    branch_strategy: dict,
    secrets: dict,
    artifacts: dict,
) -> dict:
    """
    Build a fully opinionated recommended pipeline spec.
    This is the primary input the LLM uses to generate the YAML.
    Zero ambiguity — every field is explicit.
    """

    stages = []
    parallel_groups = {}   # stages that can run in parallel
    warnings = []

    has_docker   = infrastructure.get("has_docker", False)
    has_k8s      = infrastructure.get("has_kubernetes", False)
    has_helm     = infrastructure.get("has_helm", False)
    has_terraform = infrastructure.get("has_terraform", False)
    has_frontend = bool(frontend.get("framework") and frontend.get("framework") != "Vanilla JS")
    has_db       = bool(database.get("detected"))
    is_monorepo  = project.get("is_monorepo", False)
    language     = backend.get("language", "unknown")

    # ── STAGE 1: Setup ────────────────────────────────────────
    stages.append({
        "name": "setup",
        "description": "Checkout code and install dependencies",
        "commands": _setup_commands(language, runtime, scripts),
        "cache": {
            "paths": artifacts.get("cache_paths", []),
            "key_files": artifacts.get("cache_key_files", []),
        },
        "required": True,
    })

    # ── STAGE 2: Code Quality (parallel group A) ──────────────
    quality_jobs = []

    lint_cmd = scripts.get("lint")
    if lint_cmd:
        quality_jobs.append({
            "name": "lint",
            "command": lint_cmd,
        })
    else:
        warnings.append("No lint command detected — add a linter for code quality")

    typecheck_cmd = scripts.get("typecheck")
    if typecheck_cmd:
        quality_jobs.append({
            "name": "typecheck",
            "command": typecheck_cmd,
        })

    format_cmd = scripts.get("format")
    if format_cmd:
        quality_jobs.append({
            "name": "format-check",
            "command": format_cmd,
        })

    if quality_jobs:
        stages.append({
            "name": "code-quality",
            "description": "Linting, type checking, formatting",
            "parallel_jobs": quality_jobs,
            "required": True,
        })
        parallel_groups["code-quality"] = [j["name"] for j in quality_jobs]

    # ── STAGE 3: Tests (parallel group B) ────────────────────
    test_jobs = []

    if testing.get("unit"):
        test_jobs.append({
            "name": "unit-tests",
            "command": testing.get("test_command") or scripts.get("test"),
            "coverage_command": testing.get("coverage_command") or scripts.get("test_coverage"),
            "coverage_threshold": testing.get("coverage"),
            "reports": artifacts.get("test_report_paths", []),
            "coverage_reports": artifacts.get("coverage_report_paths", []),
        })
    else:
        warnings.append("No unit tests detected — add tests to improve pipeline confidence")

    if testing.get("integration"):
        test_jobs.append({
            "name": "integration-tests",
            "command": "pytest tests/integration -v" if language == "Python" else scripts.get("test"),
            "requires": ["unit-tests"],
        })

    if test_jobs:
        stages.append({
            "name": "test",
            "description": "Run test suite with coverage",
            "parallel_jobs": test_jobs,
            "required": True,
        })

    # ── STAGE 4: Security Scan (always) ──────────────────────
    security_jobs = []

    # Dependency audit
    dep_audit_cmd = _dep_audit_cmd(language, scripts)
    security_jobs.append({
        "name": "dependency-audit",
        "command": dep_audit_cmd,
    })

    # SAST / secret scan
    security_jobs.append({
        "name": "secret-scan",
        "tool": "trufflehog",
        "command": "trufflehog git file://. --only-verified",
    })

    if has_docker:
        security_jobs.append({
            "name": "container-scan",
            "tool": "trivy",
            "command": "trivy image --exit-code 1 --severity HIGH,CRITICAL $IMAGE_NAME",
        })

    stages.append({
        "name": "security",
        "description": "Dependency audit, secret detection, container scanning",
        "parallel_jobs": security_jobs,
        "required": True,
    })

    # ── STAGE 5: Build ────────────────────────────────────────
    build_jobs = []

    backend_build_cmd = scripts.get("build") or _backend_build_cmd(language, scripts)
    if backend_build_cmd and language in ["Java", "Go"]:
        build_jobs.append({
            "name": "build-backend",
            "command": backend_build_cmd,
            "artifacts": artifacts.get("binary_artifacts", []),
        })

    if has_frontend:
        fe_build = frontend.get("build_command") or scripts.get("build")
        if fe_build:
            build_jobs.append({
                "name": "build-frontend",
                "command": fe_build,
                "artifacts": artifacts.get("build_output_dirs", []),
            })

    if build_jobs:
        stages.append({
            "name": "build",
            "description": "Compile / bundle application",
            "parallel_jobs": build_jobs,
            "upload_artifacts": artifacts.get("upload_paths", []),
            "required": True,
        })

    # ── STAGE 6: Docker Build & Push ─────────────────────────
    if has_docker:
        docker_cmds = _docker_commands(infrastructure, cloud, project, is_monorepo)
        stages.append({
            "name": "docker",
            "description": "Build, scan, and push container image(s)",
            "jobs": docker_cmds,
            "registry": cloud.get("registry", "DockerHub"),
            "required_secrets": secrets.get("secret_groups", {}).get("registry", []),
            "required": True,
        })

    # ── STAGE 7: Infrastructure (Terraform) ──────────────────
    if has_terraform:
        stages.append({
            "name": "infrastructure",
            "description": "Terraform plan (auto) and apply (manual approval)",
            "jobs": [
                {"name": "tf-plan",  "command": "terraform plan -out=tfplan"},
                {"name": "tf-apply", "command": "terraform apply tfplan",
                 "requires_approval": True},
            ],
            "required": False,
        })

    # ── STAGE 8: Database Migration ───────────────────────────
    if has_db and database.get("has_migrations"):
        stages.append({
            "name": "db-migration",
            "description": "Run database migrations before deploy",
            "command": database.get("migration_command"),
            "migration_tool": database.get("migration_tool"),
            "required": True,
        })

    # ── STAGES 9+: Deployment per environment ─────────────────
    envs = environments.get("deployment_environments", ["deploy_production"])
    approval_required_for = environments.get("approval_required_for", ["production"])

    for env_stage in envs:
        env_name = env_stage.replace("deploy_", "")
        needs_approval = env_name in approval_required_for

        deploy_job = {
            "name": env_stage,
            "description": f"Deploy to {env_name}",
            "environment": env_name,
            "strategy": _deploy_strategy(has_helm, has_k8s, cloud),
            "requires_approval": needs_approval,
            "rollback": has_k8s or has_helm or has_terraform,
            "required": True,
        }

        if has_helm:
            deploy_job["command"] = (
                f"helm upgrade --install $APP_NAME ./charts "
                f"--namespace {env_name} "
                f"--set image.tag=$IMAGE_TAG "
                f"--values ./charts/values-{env_name}.yaml"
            )
        elif has_k8s:
            deploy_job["command"] = f"kubectl apply -f k8s/ -n {env_name}"
        elif cloud.get("deployment_target") == "ECS":
            deploy_job["command"] = (
                "aws ecs update-service --cluster $ECS_CLUSTER "
                "--service $ECS_SERVICE --force-new-deployment"
            )
        elif cloud.get("deployment_target") == "Lambda":
            deploy_job["command"] = "aws lambda update-function-code --function-name $FUNCTION_NAME --image-uri $IMAGE_URI"

        stages.append(deploy_job)

        # Post-deploy health check per env
        stages.append({
            "name": f"smoke-test-{env_name}",
            "description": f"Health check and smoke tests on {env_name}",
            "commands": [
                f"curl --retry 5 --retry-delay 10 -f ${'{'}{env_name.upper()}_URL{'}'}/health",
            ],
            "depends_on": [env_stage],
            "required": True,
        })

    # ── STAGE: Notify ─────────────────────────────────────────
    notify_secrets = secrets.get("secret_groups", {}).get("notifications", [])
    stages.append({
        "name": "notify",
        "description": "Send deployment notification",
        "on": ["success", "failure"],
        "channels": _notify_channels(notify_secrets),
        "required": False,
    })

    # ── E2E tests (post-staging deploy) ──────────────────────
    if testing.get("e2e") and environments.get("has_staging"):
        e2e_tool = testing.get("e2e_tool", "Playwright")
        stages.insert(
            _stage_index(stages, "smoke-test-staging") + 1,
            {
                "name": "e2e-tests",
                "description": f"End-to-end tests with {e2e_tool} against staging",
                "command": _e2e_cmd(e2e_tool, scripts),
                "environment": "staging",
                "required": True,
            }
        )

    # ── Monitoring setup ──────────────────────────────────────
    if monitoring.get("tools_detected"):
        stages.append({
            "name": "monitoring",
            "description": "Update monitoring dashboards and alerts",
            "tools": monitoring.get("tools_detected", []),
            "required": False,
        })

    # ── Build final pipeline spec ─────────────────────────────
    return {
        "stages": stages,
        "parallel_groups": parallel_groups,
        "warnings": warnings,
        "trigger_branches": branch_strategy.get("trigger_branches", ["main"]),
        "default_branch": branch_strategy.get("default_branch", "main"),
        "branch_environment_map": branch_strategy.get("branch_environment_map", {}),
        "runtime": {
            "language": language,
            "version": runtime.get("language_version"),
            "setup_action": _setup_action(language, runtime),
        },
        "required_secrets": secrets.get("required_secrets", []),
        "secret_groups": secrets.get("secret_groups", {}),
        "total_stages": len(stages),
    }


# ── helpers ───────────────────────────────────────────────────

def _setup_commands(language: str, runtime: dict, scripts: dict) -> list:
    cmds = []
    install = scripts.get("install")
    if install:
        cmds.append(install)
    return cmds


def _setup_action(language: str, runtime: dict) -> str:
    version = runtime.get("language_version", "")
    if language == "Node.js":
        return f"actions/setup-node@v4 with node-version: {version or '20'}"
    if language == "Python":
        return f"actions/setup-python@v5 with python-version: {version or '3.11'}"
    if language == "Java":
        return f"actions/setup-java@v4 with java-version: {version or '21'}"
    if language == "Go":
        return f"actions/setup-go@v5 with go-version: {version or 'stable'}"
    return "actions/checkout@v4"


def _dep_audit_cmd(language: str, scripts: dict) -> str:
    if language == "Node.js":
        return "npm audit --audit-level=high"
    if language == "Python":
        return "pip-audit"
    if language == "Java":
        return "mvn dependency-check:check"
    if language == "Go":
        return "govulncheck ./..."
    return "echo 'No audit command configured'"


def _backend_build_cmd(language: str, scripts: dict) -> Optional[str]:
    build = scripts.get("build")
    if build:
        return build
    if language == "Java":
        return "mvn package -DskipTests"
    if language == "Go":
        return "go build -o bin/app ./cmd/..."
    return None


def _docker_commands(
    infrastructure: dict,
    cloud: dict,
    project: dict,
    is_monorepo: bool,
) -> list:
    registry = cloud.get("registry", "DockerHub")
    jobs = []

    services = project.get("service_names", []) if is_monorepo else ["app"]
    for svc in services or ["app"]:
        jobs.append({
            "name": f"docker-build-{svc}",
            "command": f"docker buildx build --platform linux/amd64 -t $IMAGE_NAME:{svc}-$IMAGE_TAG .",
        })
        jobs.append({
            "name": f"docker-push-{svc}",
            "command": f"docker push $IMAGE_NAME:{svc}-$IMAGE_TAG",
            "registry": registry,
        })

    return jobs


def _deploy_strategy(has_helm: bool, has_k8s: bool, cloud: dict) -> str:
    if has_helm:
        return "Helm"
    if has_k8s:
        return "kubectl"
    target = cloud.get("deployment_target", "")
    if target == "ECS":
        return "AWS ECS"
    if target == "Lambda":
        return "AWS Lambda"
    if target == "Cloud Run":
        return "GCP Cloud Run"
    return "Docker"


def _notify_channels(notify_secrets: list) -> list:
    channels = []
    for s in notify_secrets:
        if "SLACK" in s:
            channels.append("slack")
        elif "DISCORD" in s:
            channels.append("discord")
        elif "TEAMS" in s:
            channels.append("teams")
    return channels or ["email"]


def _e2e_cmd(tool: str, scripts: dict) -> str:
    if tool == "Cypress":
        return scripts.get("e2e") or "npx cypress run"
    if tool == "Playwright":
        return scripts.get("e2e") or "npx playwright test"
    return scripts.get("e2e") or "npm run e2e"


def _stage_index(stages: list, name: str) -> int:
    for i, s in enumerate(stages):
        if s.get("name") == name:
            return i
    return len(stages) - 1
