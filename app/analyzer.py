import os
import shutil
import tempfile
import subprocess

# Import implementations to register all 13 plugins
import app.plugins.implementations
from app.plugins.registry import plugin_registry

from app.models import (
    AnalyzeResponse, BackendInfo, FrontendInfo,
    InfrastructureInfo, CloudInfo, ProjectInfo,
    CiCdInfo, BuildCommands, MonitoringInfo,
    SecurityInfo, EnvironmentInfo, ApiRoutes,
    DockerInfo, DatabaseInfo, TestingInfo,
    DeploymentIntelligence, RepoArchitecture,
    PipelineRequirements, GradeInfo,
    RuntimeInfo, PackageScripts, BranchStrategy,
    EnvironmentDiscovery, SecretsInfo, ArtifactPaths,
    RecommendedPipeline, FrameworkDetection,
    DockerImageInfo, ParsedWorkflowJob, ParsedWorkflowInfo
)


from typing import Optional

def analyze_repo(repo_url: str, github_token: Optional[str] = None) -> AnalyzeResponse:
    temp_dir = tempfile.mkdtemp()
    try:
        clone_url = repo_url
        if github_token:
            if "://" in repo_url:
                parts = repo_url.split("://", 1)
                clone_url = f"{parts[0]}://{github_token}@{parts[1]}"
            else:
                clone_url = f"https://{github_token}@{repo_url}"

        # Clone repo
        result = subprocess.run(
            ["git", "clone", "--depth", "1", "--single-branch", clone_url, temp_dir],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            raise ValueError(f"Git clone failed: {result.stderr}")

        # Execute the plugin pipeline
        context = {"repo_url": repo_url}
        context = plugin_registry.run_pipeline(temp_dir, context)

        # ── Retrieve outputs from the plugin context ──
        language = context["language"]
        frameworks = context["frameworks"]
        packages = context["packages"]
        docker = context["docker"]
        kubernetes = context["kubernetes"]
        terraform = context["terraform"]
        cicd = context["cicd"]
        security = context["security"]
        environment = context["environment"]
        architecture = context["architecture"]
        database = context["database"]
        dep_graph = context["dependency_graph"]
        recommendation = context["recommendation"]

        # ── Build FrameworkDetection for backend ──
        backend_fw = FrameworkDetection(
            name=frameworks["backend_framework"] if frameworks["backend_framework"] != "unknown" else None,
            confidence=frameworks["backend_confidence"],
            evidence=frameworks["backend_evidence"]
        )

        backend = BackendInfo(
            language=language,
            framework=backend_fw,
            libraries=frameworks.get("backend_libraries", []),
            package_manager=packages["package_manager"],
            entrypoint=packages["entrypoint"].get("entrypoint"),
            startup_command=packages["entrypoint"].get("startup_command"),
            port=packages["port"],
            health_endpoint=packages["health_endpoint"],
            code_quality=packages["code_quality"],
            build_commands=BuildCommands(**packages["build_commands"]),
            dependencies=packages["deps_data"].get("dependencies", {}),
            dev_dependencies=packages["deps_data"].get("dev_dependencies", {}),
            confidence=frameworks["backend_confidence"],
            evidence=frameworks["backend_evidence"]
        )

        testing = TestingInfo(**packages["testing_data"])

        # ── Build FrameworkDetection for frontend ──
        fd = frameworks["frontend_data"]
        frontend_fw = FrameworkDetection(
            name=fd.get("framework_name"),
            confidence=fd.get("framework_confidence", 0.0),
            evidence=fd.get("framework_evidence", [])
        )

        frontend_deps = frameworks.get("frontend_deps", {})
        frontend = FrontendInfo(
            framework=frontend_fw,
            build_tool=fd.get("build_tool"),
            build_command=fd.get("build_command"),
            test_command=fd.get("test_command"),
            dev_command=fd.get("dev_command"),
            output_directory=fd.get("output_directory"),
            node_version=fd.get("node_version"),
            package_manager=fd.get("package_manager"),
            code_quality=fd.get("code_quality", []),
            has_env_config=fd.get("has_env_config", False),
            dependencies=frontend_deps.get("dependencies", fd.get("dependencies", {})),
            dev_dependencies=frontend_deps.get("dev_dependencies", fd.get("dev_dependencies", {})),
            confidence=fd.get("framework_confidence", 0.0),
            evidence=fd.get("framework_evidence", [])
        )

        # ── Docker with named images ──
        parsed_docker_images = []
        for img in docker.get("docker_images", []):
            parsed_docker_images.append(DockerImageInfo(**img))

        docker_info = DockerInfo(
            has_docker=docker["has_docker"],
            base_image=docker["base_image"],
            exposed_ports=docker["exposed_ports"],
            multistage=docker["multistage"],
            healthcheck=docker["healthcheck"],
            runs_as_root=docker["runs_as_root"],
            has_docker_compose=docker["has_docker_compose"],
            compose_services=docker["compose_services"],
            docker_image_name=docker["docker_image_name"],
            docker_build_context=docker["docker_build_context"],
            dockerfile_path=docker["dockerfile_path"],
            container_port=docker["container_port"],
            docker_images=parsed_docker_images,
            confidence=docker["confidence"],
            evidence=docker["evidence"]
        )

        infrastructure = InfrastructureInfo(
            docker=docker_info,
            has_kubernetes=kubernetes["has_kubernetes"],
            k8s_namespaces=kubernetes["k8s_namespaces"],
            k8s_service_names=kubernetes["k8s_service_names"],
            k8s_has_ingress=kubernetes["k8s_has_ingress"],
            has_terraform=terraform["has_terraform"],
            terraform_resources=terraform["terraform_resources"],
            has_helm=kubernetes["has_helm"],
            has_ansible=kubernetes["has_ansible"],
        )

        # ── Database with confidence ──
        db_confidence = database.pop("confidence", 0.0)
        db_evidence = database.pop("evidence", [])
        database_info = DatabaseInfo(**database, confidence=db_confidence, evidence=db_evidence)

        # ── Cloud with confidence ──
        cloud_raw = dep_graph["cloud_data"]
        cloud_confidence = cloud_raw.pop("confidence", 0.0)
        cloud_evidence = cloud_raw.pop("evidence", [])
        cloud = CloudInfo(**cloud_raw, confidence=cloud_confidence, evidence=cloud_evidence)

        project = ProjectInfo(**architecture["project_info"])

        # ── CI/CD with existing_workflows ──
        cicd_analysis = cicd["cicd_analysis"]
        parsed_workflows = []
        for wf in cicd_analysis.get("parsed_workflows", []):
            jobs = [ParsedWorkflowJob(**j) for j in wf.get("jobs", [])]
            parsed_workflows.append(ParsedWorkflowInfo(
                file_path=wf["file_path"],
                name=wf["name"],
                triggers=wf["triggers"],
                jobs=jobs
            ))

        ci_cd = CiCdInfo(
            has_ci=cicd["has_ci"],
            existing_ci=cicd["existing_ci"],
            has_build=cicd_analysis.get("has_build", False),
            has_tests=cicd_analysis.get("has_tests", False),
            has_security_scan=cicd_analysis.get("has_security_scan", False),
            has_docker_build=cicd_analysis.get("has_docker_build", False),
            has_deployment=cicd_analysis.get("has_deployment", False),
            has_notifications=cicd_analysis.get("has_notifications", False),
            has_caching=cicd_analysis.get("has_caching", False),
            has_approval_gate=cicd_analysis.get("has_approval_gate", False),
            has_rollback=cicd_analysis.get("has_rollback", False),
            quality_score=cicd_analysis.get("quality_score", 0),
            existing_stages=cicd_analysis.get("existing_stages", []),
            missing_stages=cicd_analysis.get("missing_stages", []),
            existing_workflows=cicd_analysis.get("existing_workflows", []),
            parsed_workflows=parsed_workflows,
            confidence=cicd_analysis.get("confidence", 0.0),
            evidence=cicd_analysis.get("evidence", [])
        )

        env_info = EnvironmentInfo(**environment["env_data"])

        # API Routes
        health_route = next(
            (r for r in dep_graph["routes"] if "health" in r.lower()), None
        )
        api_routes = ApiRoutes(routes=dep_graph["routes"], health_route=health_route)

        # Monitoring
        mon_data = recommendation["monitoring_data"]
        monitoring = MonitoringInfo(
            tools_detected=mon_data.get("tools_detected", []),
            has_prometheus=mon_data.get("has_prometheus", False),
            has_grafana=mon_data.get("has_grafana", False),
            has_opentelemetry=mon_data.get("has_opentelemetry", False),
            has_datadog=mon_data.get("has_datadog", False),
            has_sentry=mon_data.get("has_sentry", False),
            has_elk=mon_data.get("has_elk", False),
        )

        security_info = SecurityInfo(**security["security_data"])

        deployment = DeploymentIntelligence(**dep_graph["deployment"])
        infra_graph = dep_graph["infra_graph"]
        repo_architecture = RepoArchitecture(**architecture["arch_data"])

        grade_info = GradeInfo(**recommendation["grade_info"])
        pipeline_requirements = PipelineRequirements(**recommendation["pipeline_requirements"])

        runtime = RuntimeInfo(**packages["runtime_data"])
        scripts = PackageScripts(**packages["scripts_data"])
        branch_strategy = BranchStrategy(**cicd["branch_strategy"])
        environments = EnvironmentDiscovery(**environment["environments_data"])
        secrets = SecretsInfo(**security["secrets_data"])
        artifacts = ArtifactPaths(**architecture["artifacts_data"])
        recommended_pipeline = RecommendedPipeline(**recommendation["recommended_pipeline"])

        return AnalyzeResponse(
            repo_url=repo_url,
            backend=backend,
            frontend=frontend,
            testing=testing,
            runtime=runtime,
            scripts=scripts,
            infrastructure=infrastructure,
            database=database_info,
            cloud=cloud,
            environment=env_info,
            monitoring=monitoring,
            security=security_info,
            api_routes=api_routes,
            deployment=deployment,
            infrastructure_graph=infra_graph,
            architecture=repo_architecture,
            project=project,
            ci_cd=ci_cd,
            branch_strategy=branch_strategy,
            environments=environments,
            secrets=secrets,
            artifacts=artifacts,
            pipeline_requirements=pipeline_requirements,
            recommended_pipeline=recommended_pipeline,
            grade_info=grade_info,
        )

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Analysis failed: {str(e)}")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)
