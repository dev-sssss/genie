"""
PipelineGeneratorEngine v2.

What changed from v1 and why:

v1 built a *second*, weaker stage plan purely from `spec`, while the analyzer
already produces a rich, deterministic `recommended_pipeline` purely from
`analysis` (real commands, real GitHub Action names, real secret groups).
Both were dumped into one LLM call with no reconciliation, so the model had
to guess which one to trust — and sometimes trusted neither, inventing its
own schema instead.

v2 does the reconciliation in Python, deterministically, before any LLM call
happens. `analysis.recommended_pipeline` is the base (it already knows the
repo). `spec` is applied as a set of overrides/filters on top of it (it
knows what the user actually wants). The result is a single
`final_pipeline_plan` — one unambiguous list of stages with concrete
commands — that phase 2 (the LLM) only has to format, not design.

Also new: EC2/VM (non-container) SSH/SSM deploy targets are now handled
deterministically. v1's recommended_pipeline only knew how to deploy via
Helm/kubectl/ECS/Lambda; SSH-based deploys (the case that broke in your
sample output) fell through to the LLM with nothing but a vague sentence.
"""

import copy
from typing import Dict, Any, List, Optional


class PipelineGeneratorEngine:
    def __init__(self, analysis: Dict[str, Any], spec: Dict[str, Any]):
        self.analysis = analysis
        self.spec = spec
        self.validation = {
            "passed": True,
            "errors": [],
            "warnings": [],
            "skipped_features": [],
        }

    # ── validation (pre-generation capability checks) ────────────────

    def _add_error(self, feature: str, reason: str, required: List[str]):
        self.validation["passed"] = False
        self.validation["errors"].append(
            {"feature": feature, "reason": reason, "required": required}
        )

    def _add_warning(self, msg: str):
        self.validation["warnings"].append(msg)

    def _validate_capabilities(self):
        target = self.spec.get("deployment_target")
        docker_cfg = self.spec.get("docker_configurations", {}) or {}
        infra_docker = self.analysis.get("infrastructure", {}).get("docker", {})

        container_targets = ["Amazon ECS", "Amazon EKS", "Kubernetes", "Docker Host"]

        if (docker_cfg.get("build_images") or docker_cfg.get("push_images")
                or target in container_targets):
            if not infra_docker.get("has_docker") and not docker_cfg.get("generate_dockerfile"):
                self._add_error(
                    feature="Docker Deployment",
                    reason=(
                        "Target or config requires Docker, but no Dockerfile was "
                        "detected in the repository and 'generate_dockerfile' is off."
                    ),
                    required=["Dockerfile", "or enable docker_configurations.generate_dockerfile"],
                )

        if target in ("EC2 (SSH)", "EC2 (SSM)", "Azure VM", "GCP VM"):
            secrets = self.spec.get("github_secrets", []) or []
            has_host_secret = any("HOST" in s.upper() or "SSH" in s.upper() for s in secrets)
            if target == "EC2 (SSH)" and not has_host_secret:
                self._add_warning(
                    "EC2 (SSH) selected but no SSH host/key secret is present in "
                    "github_secrets. The generated pipeline will reference "
                    "${{ secrets.SSH_HOST }} / ${{ secrets.SSH_PRIVATE_KEY }} as "
                    "placeholders — add these secrets before running it."
                )

        approval = self.spec.get("approval", {}) or {}
        envs = self.spec.get("environments", {}) or {}
        if approval.get("manual_approval") and not (envs.get("staging") or envs.get("production")):
            self._add_warning(
                "Manual approval requested but no environment is enabled — "
                "approval gate will be skipped."
            )

        db_tasks = self.spec.get("database_tasks", {}) or {}
        if db_tasks.get("run_migrations") and not db_tasks.get("migration_command"):
            db = self.analysis.get("database", {})
            if not db.get("migration_command"):
                self._add_warning(
                    "Migrations requested but no migration command was found in "
                    "the repo or provided in the wizard. Migration step will be "
                    "a placeholder — fill in the real command before running."
                )

    # ── command resolution ────────────────────────────────────────────

    def _resolve_commands(self) -> Dict[str, str]:
        backend = self.analysis.get("backend", {})
        frontend = self.analysis.get("frontend", {})
        scripts = self.analysis.get("scripts", {}) or {}
        pkg_manager = backend.get("package_manager") or frontend.get("package_manager") or "npm"
        user_cmds = self.spec.get("build_commands", {}) or {}

        resolved = {
            "install": user_cmds.get("install") or "",
            "build": user_cmds.get("build") or "",
            "start": user_cmds.get("start") or "",
        }

        # Exact repo scripts win over fuzzy/empty wizard input.
        if not resolved["install"]:
            resolved["install"] = f"{pkg_manager} install"
        if not resolved["build"] and scripts.get("build"):
            resolved["build"] = scripts["build"]
        if not resolved["start"] and scripts.get("start"):
            resolved["start"] = scripts["start"]

        return resolved

    # ── the merge: recommended_pipeline (analysis) + spec overrides ──

    def _merge_recommended_with_spec(self, commands: Dict[str, str]) -> Dict[str, Any]:
        recommended = self.analysis.get("recommended_pipeline")
        if not recommended or not recommended.get("stages"):
            # Fail loudly instead of silently building a near-empty plan.
            # This happens if a caller sends a hand-built or stale `analysis`
            # payload that never went through /analyze, or an older frontend
            # build that predates the recommended_pipeline field.
            self._add_error(
                feature="Repository Analysis",
                reason=(
                    "analysis.recommended_pipeline is missing or has no stages. "
                    "The analysis payload must come from a fresh /analyze call."
                ),
                required=["analysis.recommended_pipeline.stages"],
            )
            return {}

        base = copy.deepcopy(recommended)
        stages: List[Dict[str, Any]] = base.get("stages", [])
        target = self.spec.get("deployment_target")

        quality = self.spec.get("quality_checks", {}) or {}
        security = self.spec.get("security_scans", {}) or {}
        approval = self.spec.get("approval", {}) or {}
        cache_cfg = self.spec.get("cache", {}) or {}
        health = self.spec.get("health_checks", {}) or {}
        notify_cfg = self.spec.get("notification_channels", {}) or {}
        docker_cfg = self.spec.get("docker_configurations", {}) or {}
        k8s_cfg = self.spec.get("kubernetes", {}) or {}
        db_tasks = self.spec.get("database_tasks", {}) or {}
        envs_cfg = self.spec.get("environments", {}) or {}
        custom = self.spec.get("custom_pipeline", {}) or {}
        artifacts_cfg = self.spec.get("artifacts", {}) or {}

        kept_stages = []
        for stage in stages:
            name = stage.get("name", "")

            # ── code-quality: filter to only the checks the user opted into
            if name == "code-quality":
                if quality.get("linters_enabled") is False:
                    stage["parallel_jobs"] = [
                        j for j in stage.get("parallel_jobs", []) if j["name"] != "lint"
                    ]
                if not stage.get("parallel_jobs"):
                    continue  # drop empty stage

            # ── tests: apply coverage threshold override + skip disabled tiers
            if name == "test":
                jobs = stage.get("parallel_jobs", [])
                if quality.get("unit_tests") is False:
                    jobs = [j for j in jobs if j["name"] != "unit-tests"]
                if quality.get("integration_tests") is False:
                    jobs = [j for j in jobs if j["name"] != "integration-tests"]
                for j in jobs:
                    if j["name"] == "unit-tests" and quality.get("min_coverage"):
                        j["coverage_threshold"] = quality["min_coverage"]
                stage["parallel_jobs"] = jobs
                if not jobs:
                    continue

            # ── security: filter to selected scan types
            if name == "security":
                jobs = stage.get("parallel_jobs", [])
                if security.get("dependency_scan") is False:
                    jobs = [j for j in jobs if j["name"] != "dependency-audit"]
                if security.get("secret_scan") is False:
                    jobs = [j for j in jobs if j["name"] != "secret-scan"]
                if security.get("container_scan") is False:
                    jobs = [j for j in jobs if j["name"] != "container-scan"]
                if security.get("codeql"):
                    jobs.append({"name": "codeql", "tool": "github/codeql-action",
                                 "command": "CodeQL static analysis (native GH Action, not a shell command)"})
                if security.get("license_scan"):
                    jobs.append({"name": "license-scan", "command": "license-checker --failOn GPL"})
                stage["parallel_jobs"] = jobs
                if not jobs:
                    continue

            # ── docker: honor explicit build/push toggles + naming
            if name == "docker":
                if docker_cfg.get("build_images") is False and docker_cfg.get("push_images") is False:
                    continue
                image_name = docker_cfg.get("image_name") or "$IMAGE_NAME"
                image_tag = docker_cfg.get("image_tag") or "$IMAGE_TAG"
                for job in stage.get("jobs", []):
                    if "command" in job:
                        job["command"] = (
                            job["command"]
                            .replace("$IMAGE_NAME", image_name)
                            .replace("$IMAGE_TAG", image_tag)
                        )
                if docker_cfg.get("multi_architecture"):
                    for job in stage.get("jobs", []):
                        if "buildx build" in job.get("command", ""):
                            job["command"] = job["command"].replace(
                                "--platform linux/amd64",
                                "--platform linux/amd64,linux/arm64",
                            )
                stage["cache_layers"] = bool(cache_cfg.get("docker_layers"))

            # ── kubernetes: apply namespace / replicas / service type
            if name.startswith("deploy_") or name in ("deploy_staging", "deploy_production"):
                env_name = name.replace("deploy_", "")
                if k8s_cfg.get("namespace"):
                    if "command" in stage and "--namespace" in stage["command"]:
                        stage["command"] = stage["command"].replace(
                            f"--namespace {env_name}", f"--namespace {k8s_cfg['namespace']}"
                        )
                if k8s_cfg.get("replicas"):
                    stage["replicas"] = k8s_cfg["replicas"]
                if k8s_cfg.get("service_type"):
                    stage["service_type"] = k8s_cfg["service_type"]
                if approval.get("manual_approval") or approval.get("production_only") and env_name == "production":
                    stage["requires_approval"] = True
                rollback_strategy = self.spec.get("rollback_strategy")
                if rollback_strategy:
                    stage["rollback"] = rollback_strategy != "none"
                    stage["rollback_strategy"] = rollback_strategy

            # ── smoke tests: apply health-check overrides
            if name.startswith("smoke-test-"):
                if health.get("enabled") is False:
                    continue
                url = health.get("url")
                retries = health.get("retries", 5)
                timeout = health.get("timeout", 30)
                env_name = name.replace("smoke-test-", "")
                target_url = url or f"${{{env_name.upper()}_URL}}/health"
                stage["commands"] = [
                    f"curl --retry {retries} --retry-delay {timeout // 5 or 5} --max-time {timeout} -f {target_url}"
                ]

            # ── db migrations: honor overrides / seeders
            if name == "db-migration":
                if db_tasks.get("run_migrations") is False:
                    continue
                if db_tasks.get("migration_command"):
                    stage["command"] = db_tasks["migration_command"]
                if db_tasks.get("run_seeders") and db_tasks.get("seeder_command"):
                    stage["seed_command"] = db_tasks["seeder_command"]

            # ── notify: honor explicit channel selection
            if name == "notify":
                chosen = [k for k, v in notify_cfg.items() if v and k != "none"]
                if notify_cfg.get("none"):
                    continue
                if chosen:
                    stage["channels"] = chosen

            # ── artifacts: retention override
            if name == "build" and artifacts_cfg.get("retention_days"):
                stage["artifact_retention_days"] = artifacts_cfg["retention_days"]

            # ── environments: drop deploy/smoke stages for envs the user disabled
            if (name.startswith("deploy_") or name.startswith("smoke-test-")) and envs_cfg:
                env_name = name.split("_")[-1] if name.startswith("deploy_") else name.replace("smoke-test-", "")
                if env_name in ("staging", "production", "development") and envs_cfg.get(env_name) is False:
                    continue

            kept_stages.append(stage)

        # ── EC2/VM SSH deploy target: recommended_pipeline has no concept of
        # this (it only knows Helm/kubectl/ECS/Lambda). Build it deterministically
        # here instead of leaving it to the LLM's imagination.
        if target in ("EC2 (SSH)", "EC2 (SSM)", "Azure VM", "GCP VM"):
            kept_stages = self._inject_vm_deploy_stage(kept_stages, target, commands)

        # ── custom hooks: insert user-supplied shell snippets at named points
        kept_stages = self._inject_custom_hooks(kept_stages, custom)

        base["stages"] = kept_stages
        base["total_stages"] = len(kept_stages)
        return base

    def _inject_vm_deploy_stage(self, stages: List[Dict[str, Any]], target: str,
                                 commands: Dict[str, str]) -> List[Dict[str, Any]]:
        """Deterministically build the SSH/SSM deploy + rollback + health-check
        stages that recommended_pipeline doesn't cover, instead of handing the
        LLM a one-line description and hoping it invents something reasonable.
        """
        deploy_mode = self.spec.get("deployment_mode", "git pull")
        process_manager = self.spec.get("process_manager", "PM2")
        restart_cmd = {
            "PM2": "pm2 restart app --update-env",
            "Systemd": "sudo systemctl restart app",
        }.get(process_manager, "restart command")

        sync_cmd = (
            "git fetch --all && git reset --hard origin/${{ github.ref_name }}"
            if deploy_mode == "git pull"
            else "rm -rf /opt/app_new && git clone --depth 1 $REPO_URL /opt/app_new && "
                 "rsync -a --delete /opt/app_new/ /opt/app/ && rm -rf /opt/app_new"
        )

        # Guard against empty install/build commands producing a dangling
        # "&& &&" in the assembled remote command.
        remote_steps = [sync_cmd] + [c for c in (commands.get("install"), commands.get("build")) if c] + [restart_cmd]
        remote_cmd = " && ".join(remote_steps)

        if target == "EC2 (SSH)":
            deploy_command = (
                f"ssh -o StrictHostKeyChecking=yes -i $SSH_KEY_PATH "
                f"$SSH_USER@$SSH_HOST 'cd /opt/app && {remote_cmd}'"
            )
            required_secrets = ["SSH_HOST", "SSH_USER", "SSH_PRIVATE_KEY"]
        else:  # SSM / Azure RunCommand / GCP OS Login equivalents
            deploy_command = (
                "Use cloud-native remote execution (AWS SSM Run Command / "
                f"Azure RunCommand / GCP OS Login) to run: {remote_cmd}"
            )
            required_secrets = ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_REGION"]

        deploy_stage = {
            "name": "deploy_production",
            "description": f"Deploy to {target} via {'SSH' if target == 'EC2 (SSH)' else 'remote execution'}",
            "environment": "production",
            "strategy": target,
            "command": deploy_command,
            "requires_approval": bool((self.spec.get("approval") or {}).get("manual_approval")),
            "rollback": self.spec.get("rollback_strategy", "none") != "none",
            "required_secrets": required_secrets,
            "required": True,
        }

        health = self.spec.get("health_checks", {}) or {}
        smoke_stage = {
            "name": "smoke-test-production",
            "description": "Health check after VM deploy",
            "commands": [
                f"curl --retry {health.get('retries', 5)} --retry-delay 10 "
                f"--max-time {health.get('timeout', 30)} -f "
                f"{health.get('url') or '$PRODUCTION_URL/health'}"
            ],
            "depends_on": ["deploy_production"],
            "required": health.get("enabled", True) is not False,
        }

        stages.append(deploy_stage)
        if smoke_stage["required"]:
            stages.append(smoke_stage)
        return stages

    def _inject_custom_hooks(self, stages: List[Dict[str, Any]],
                              custom: Dict[str, Any]) -> List[Dict[str, Any]]:
        if not custom:
            return stages

        def _find(name):
            for i, s in enumerate(stages):
                if s.get("name") == name:
                    return i
            return None

        if custom.get("before_build"):
            idx = _find("build")
            hook = {"name": "before-build-hook", "commands": [custom["before_build"]], "required": False}
            stages.insert(idx if idx is not None else len(stages), hook)

        if custom.get("after_build"):
            idx = _find("build")
            hook = {"name": "after-build-hook", "commands": [custom["after_build"]], "required": False}
            stages.insert((idx + 1) if idx is not None else len(stages), hook)

        for stage in stages:
            if stage.get("name", "").startswith("deploy_"):
                if custom.get("before_deploy"):
                    stage.setdefault("pre_steps", []).append(custom["before_deploy"])
                if custom.get("after_deploy"):
                    stage.setdefault("post_steps", []).append(custom["after_deploy"])

        return stages

    # ── entrypoint ──────────────────────────────────────────────────

    def run(self) -> Dict[str, Any]:
        self._validate_capabilities()

        if not self.validation["passed"]:
            return {
                "status": "INVALID_CONFIGURATION",
                "validation": self.validation,
                "final_pipeline_plan": {},
                "error_reason": "Pre-generation capabilities check failed.",
            }

        commands = self._resolve_commands()
        merged_plan = self._merge_recommended_with_spec(commands)

        # _merge_recommended_with_spec can itself add a validation error
        # (missing/empty recommended_pipeline) — re-check before claiming VALID.
        if not self.validation["passed"]:
            return {
                "status": "INVALID_CONFIGURATION",
                "validation": self.validation,
                "final_pipeline_plan": {},
                "error_reason": "Analysis payload failed post-merge validation.",
            }

        return {
            "status": "VALID",
            "validation": self.validation,
            "resolved_commands": commands,
            "final_pipeline_plan": merged_plan,
        }
