import os
from typing import Any, Dict
from app.plugins.base import BaseAnalyzerPlugin
from app.plugins.registry import plugin_registry

# Import detector functions
from app.detector import (
    detect_language, detect_framework,
    detect_package_manager, detect_makefile, detect_ci,
    detect_port, detect_health_endpoint,
    detect_code_quality, detect_libraries,
    detect_microservices, detect_build_commands,
    detect_entrypoint, detect_makefile_targets
)
from app.detectors.frontend_intelligence import detect_frontend_intelligence
from app.detectors.infrastructure import detect_infrastructure
from app.detectors.docker_analyzer import detect_docker_deep
from app.detectors.database_intelligence import detect_database_intelligence
from app.detectors.cloud import detect_cloud
from app.detectors.grader import calculate_grade
from app.detectors.dependencies import detect_dependencies, detect_frontend_dependencies
from app.detectors.routes import detect_api_routes
from app.detectors.environment import detect_environment_analysis
from app.detectors.monitoring import detect_monitoring
from app.detectors.security import detect_security
from app.detectors.cicd_analyzer import analyze_existing_cicd
from app.detectors.testing_intelligence import detect_testing_intelligence
from app.detectors.deployment_intelligence import (
    detect_deployment_intelligence,
    detect_infrastructure_graph,
    detect_repo_architecture
)
from app.detectors.pipeline_requirements import build_pipeline_requirements
from app.detectors.runtime import detect_runtime_versions
from app.detectors.branch_strategy import detect_branch_strategy
from app.detectors.package_scripts import detect_package_scripts
from app.detectors.secrets_intelligence import detect_required_secrets
from app.detectors.environments import detect_environments
from app.detectors.artifact_paths import detect_artifact_paths
from app.detectors.recommended_pipeline import build_recommended_pipeline


class LanguageDetectorPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "language"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        return detect_language(repo_path)


class FrameworkDetectorPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "frameworks"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        lang = context.get("language")
        
        # 1. Backend framework + libraries — completely separate from frontend
        backend_framework = detect_framework(repo_path, lang)
        backend_libraries = detect_libraries(repo_path, lang)
        backend_evidence = []
        backend_confidence = 0.0
        
        if lang != "unknown":
            backend_confidence = 0.6
            backend_evidence.append(f"Backend language detected: {lang}")
            if backend_framework != "unknown":
                backend_confidence = 0.95
                backend_evidence.append(f"Detected backend framework: {backend_framework}")
            else:
                backend_evidence.append("No specific backend framework detected")
            if backend_libraries:
                backend_evidence.append(f"Backend libraries: {', '.join(backend_libraries)}")
        
        # 2. Frontend — completely independent scan
        frontend_data = detect_frontend_intelligence(repo_path)
        frontend_deps = detect_frontend_dependencies(repo_path)

        return {
            "backend_framework": backend_framework,
            "backend_libraries": backend_libraries,
            "backend_confidence": backend_confidence,
            "backend_evidence": backend_evidence,
            "frontend_data": frontend_data,
            "frontend_deps": frontend_deps,
        }


class PackageAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "packages"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        lang = context.get("language")
        framework = context.get("frameworks", {}).get("backend_framework", "unknown")
        
        package_manager = detect_package_manager(repo_path, lang)
        port = detect_port(repo_path, lang, framework)
        health_endpoint = detect_health_endpoint(repo_path, lang)
        code_quality = detect_code_quality(repo_path, lang)
        build_commands_data = detect_build_commands(repo_path, lang, framework)
        entrypoint_data = detect_entrypoint(repo_path, lang, framework)
        deps_data = detect_dependencies(repo_path, lang)
        
        runtime_data = detect_runtime_versions(repo_path, lang)
        scripts_data = detect_package_scripts(repo_path, lang)
        testing_data = detect_testing_intelligence(repo_path, lang)

        return {
            "package_manager": package_manager,
            "port": port,
            "health_endpoint": health_endpoint,
            "code_quality": code_quality,
            "build_commands": build_commands_data,
            "entrypoint": entrypoint_data,
            "deps_data": deps_data,
            "runtime_data": runtime_data,
            "scripts_data": scripts_data,
            "testing_data": testing_data
        }


class DockerAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "docker"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        return detect_docker_deep(repo_path, context)


class KubernetesAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "kubernetes"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        infra = detect_infrastructure(repo_path)
        return {
            "has_kubernetes": infra.get("has_kubernetes", False),
            "k8s_namespaces": infra.get("k8s_namespaces", []),
            "k8s_service_names": infra.get("k8s_service_names", []),
            "k8s_has_ingress": infra.get("k8s_has_ingress", False),
            "has_helm": infra.get("has_helm", False),
            "has_ansible": infra.get("has_ansible", False),
        }


class TerraformAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "terraform"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        infra = detect_infrastructure(repo_path)
        return {
            "has_terraform": infra.get("has_terraform", False),
            "terraform_resources": infra.get("terraform_resources", []),
        }


class GitHubActionsAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "cicd"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        has_ci, existing_ci = detect_ci(repo_path)
        cicd_analysis = analyze_existing_cicd(repo_path, existing_ci)
        branch_data = detect_branch_strategy(repo_path)
        
        return {
            "has_ci": has_ci,
            "existing_ci": existing_ci,
            "cicd_analysis": cicd_analysis,
            "branch_strategy": branch_data
        }


class SecurityAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "security"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        lang = context.get("language")
        docker_data = context.get("docker", {})
        cloud_data = detect_cloud(repo_path)
        
        security_data = detect_security(repo_path, lang)
        
        secrets_data = detect_required_secrets(
            repo_path=repo_path,
            language=lang,
            cloud_provider=cloud_data.get("provider"),
            registry=cloud_data.get("registry"),
            has_docker=docker_data.get("has_docker", False),
        )
        return {
            "security_data": security_data,
            "secrets_data": secrets_data
        }


class EnvironmentAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "environment"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        lang = context.get("language")
        env_data = detect_environment_analysis(repo_path, lang)
        environments_data = detect_environments(repo_path)
        return {
            "env_data": env_data,
            "environments_data": environments_data
        }


class ArchitectureAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "architecture"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        arch_data = detect_repo_architecture(repo_path)
        microservices = detect_microservices(repo_path)
        has_makefile = detect_makefile(repo_path)
        makefile_targets = detect_makefile_targets(repo_path)
        
        taskfile_path = ""
        for fname in ["Taskfile.yml", "Taskfile.yaml", "taskfile.yml"]:
            path = os.path.join(repo_path, fname)
            if os.path.exists(path):
                taskfile_path = path
                break
        has_taskfile = bool(taskfile_path)

        frontend_fw = context.get("frameworks", {}).get("frontend_data", {}).get("framework_name")
        artifacts_data = detect_artifact_paths(repo_path, context.get("language"), frontend_fw)

        return {
            "arch_data": arch_data,
            "project_info": {
                "is_monorepo": microservices["is_monorepo"],
                "services_count": microservices["services_count"],
                "service_names": microservices["service_names"],
                "has_makefile": has_makefile,
                "makefile_targets": makefile_targets,
                "has_taskfile": has_taskfile,
            },
            "artifacts_data": artifacts_data
        }


class DatabaseAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "database"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        lang = context.get("language")
        db_data = detect_database_intelligence(repo_path, lang)
        
        # Add database confidence and evidence
        db_data["confidence"] = 0.0
        db_data["evidence"] = []
        
        if db_data.get("detected"):
            db_data["confidence"] = 1.0
            db_data["evidence"].append(f"Detected databases: {', '.join(db_data['detected'])}")
            if db_data.get("primary"):
                db_data["evidence"].append(f"Primary database: {db_data['primary']}")
            if db_data.get("has_migrations"):
                db_data["evidence"].append(f"Migration tool: {db_data['migration_tool']}")
        else:
            db_data["evidence"].append("No database configuration found")
            
        return db_data


class DependencyGraphAnalyzerPlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "dependency_graph"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        infra_dict = {
            "has_kubernetes": context.get("kubernetes", {}).get("has_kubernetes", False),
            "k8s_namespaces": context.get("kubernetes", {}).get("k8s_namespaces", []),
            "k8s_service_names": context.get("kubernetes", {}).get("k8s_service_names", []),
            "k8s_has_ingress": context.get("kubernetes", {}).get("k8s_has_ingress", False),
            "has_helm": context.get("kubernetes", {}).get("has_helm", False),
            "has_ansible": context.get("kubernetes", {}).get("has_ansible", False),
            "has_terraform": context.get("terraform", {}).get("has_terraform", False),
            "terraform_resources": context.get("terraform", {}).get("terraform_resources", []),
            "has_docker": context.get("docker", {}).get("has_docker", False),
            "has_docker_compose": context.get("docker", {}).get("has_docker_compose", False),
        }
        cloud_data = detect_cloud(repo_path)
        project_dict = context.get("architecture", {}).get("project_info", {})
        database_detected = context.get("database", {}).get("detected", [])

        deploy_data = detect_deployment_intelligence(
            repo_path=repo_path,
            infrastructure=infra_dict,
            cloud=cloud_data,
            project=project_dict
        )

        infra_graph = detect_infrastructure_graph(
            repo_path=repo_path,
            project=project_dict,
            database=database_detected,
            infrastructure=infra_dict
        )

        lang = context.get("language")
        framework = context.get("frameworks", {}).get("backend_framework", "unknown")
        routes = detect_api_routes(repo_path, lang, framework)

        return {
            "deployment": deploy_data,
            "infra_graph": infra_graph,
            "routes": routes,
            "cloud_data": cloud_data
        }


class PipelineRecommendationEnginePlugin(BaseAnalyzerPlugin):
    @property
    def name(self) -> str:
        return "recommendation"

    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        packages = context.get("packages", {})
        frameworks = context.get("frameworks", {})
        infra_dict = {
            "has_kubernetes": context.get("kubernetes", {}).get("has_kubernetes", False),
            "k8s_namespaces": context.get("kubernetes", {}).get("k8s_namespaces", []),
            "k8s_service_names": context.get("kubernetes", {}).get("k8s_service_names", []),
            "k8s_has_ingress": context.get("kubernetes", {}).get("k8s_has_ingress", False),
            "has_helm": context.get("kubernetes", {}).get("has_helm", False),
            "has_ansible": context.get("kubernetes", {}).get("has_ansible", False),
            "has_terraform": context.get("terraform", {}).get("has_terraform", False),
            "terraform_resources": context.get("terraform", {}).get("terraform_resources", []),
            "has_docker": context.get("docker", {}).get("has_docker", False),
            "has_docker_compose": context.get("docker", {}).get("has_docker_compose", False),
        }
        db_data = context.get("database", {})
        cloud_data = context.get("dependency_graph", {}).get("cloud_data", {})
        
        ci_cd_data = context.get("cicd", {})
        cicd_analysis = ci_cd_data.get("cicd_analysis", {})
        ci_cd_dict = {
            "has_ci": ci_cd_data.get("has_ci", False),
            "existing_ci": ci_cd_data.get("existing_ci", "none"),
            "has_build": cicd_analysis.get("has_build", False),
            "has_tests": cicd_analysis.get("has_tests", False),
            "has_security_scan": cicd_analysis.get("has_security_scan", False),
            "has_docker_build": cicd_analysis.get("has_docker_build", False),
            "has_deployment": cicd_analysis.get("has_deployment", False),
            "has_notifications": cicd_analysis.get("has_notifications", False),
            "has_caching": cicd_analysis.get("has_caching", False),
            "has_approval_gate": cicd_analysis.get("has_approval_gate", False),
            "has_rollback": cicd_analysis.get("has_rollback", False),
            "quality_score": cicd_analysis.get("quality_score", 0),
            "existing_stages": cicd_analysis.get("existing_stages", []),
            "missing_stages": cicd_analysis.get("missing_stages", []),
        }

        monitoring_data = detect_monitoring(repo_path, context.get("language"))
        security_all = context.get("security", {})
        security_dict = security_all.get("security_data", {})
        
        project_dict = context.get("architecture", {}).get("project_info", {})
        testing_dict = packages.get("testing_data", {})

        # Build a backward-compatible backend dict for grading / pipeline funcs
        backend_fw_name = frameworks.get("backend_framework", "unknown")
        backend_dict = {
            "language": context.get("language"),
            "framework": backend_fw_name,
            "package_manager": packages.get("package_manager"),
            "entrypoint": packages.get("entrypoint", {}).get("entrypoint"),
            "startup_command": packages.get("entrypoint", {}).get("startup_command"),
            "port": packages.get("port"),
            "health_endpoint": packages.get("health_endpoint"),
            "code_quality": packages.get("code_quality"),
            "build_commands": packages.get("build_commands"),
            "dependencies": packages.get("deps_data", {}).get("dependencies", {}),
            "dev_dependencies": packages.get("deps_data", {}).get("dev_dependencies", {}),
        }
        
        # Frontend dict for grading (use framework name string for backward compat)
        frontend_data = frameworks.get("frontend_data", {})
        frontend_compat = {
            "framework": frontend_data.get("framework_name"),
            "build_tool": frontend_data.get("build_tool"),
            "build_command": frontend_data.get("build_command"),
            "test_command": frontend_data.get("test_command"),
            "dev_command": frontend_data.get("dev_command"),
            "output_directory": frontend_data.get("output_directory"),
            "node_version": frontend_data.get("node_version"),
            "package_manager": frontend_data.get("package_manager"),
            "code_quality": frontend_data.get("code_quality", []),
            "has_env_config": frontend_data.get("has_env_config", False),
        }

        grade_result = calculate_grade(
            backend=backend_dict,
            frontend=frontend_compat,
            infrastructure=infra_dict,
            database=db_data.get("detected", []),
            cloud=cloud_data,
            ci_cd=ci_cd_dict,
            project=project_dict
        )

        pipeline_req = build_pipeline_requirements(
            backend=backend_dict,
            frontend=frontend_compat,
            infrastructure=infra_dict,
            database=db_data.get("detected", []),
            cloud=cloud_data,
            ci_cd=ci_cd_dict,
            monitoring=monitoring_data,
            security=security_dict,
            project=project_dict,
            testing=testing_dict,
        )

        recommended_pipeline_data = build_recommended_pipeline(
            backend=backend_dict,
            frontend=frontend_compat,
            testing=testing_dict,
            infrastructure=infra_dict,
            database=db_data,
            cloud=cloud_data,
            ci_cd=ci_cd_dict,
            monitoring=monitoring_data,
            security=security_dict,
            project=project_dict,
            environments=context.get("environment", {}).get("environments_data", {}),
            scripts=packages.get("scripts_data", {}),
            runtime=packages.get("runtime_data", {}),
            branch_strategy=ci_cd_data.get("branch_strategy", {}),
            secrets=security_all.get("secrets_data", {}),
            artifacts=context.get("architecture", {}).get("artifacts_data", {}),
        )

        return {
            "grade_info": grade_result,
            "pipeline_requirements": pipeline_req,
            "recommended_pipeline": recommended_pipeline_data,
            "monitoring_data": monitoring_data
        }


# Register all 13 plugins sequentially
plugin_registry.register(LanguageDetectorPlugin())
plugin_registry.register(FrameworkDetectorPlugin())
plugin_registry.register(PackageAnalyzerPlugin())
plugin_registry.register(DockerAnalyzerPlugin())
plugin_registry.register(KubernetesAnalyzerPlugin())
plugin_registry.register(TerraformAnalyzerPlugin())
plugin_registry.register(GitHubActionsAnalyzerPlugin())
plugin_registry.register(SecurityAnalyzerPlugin())
plugin_registry.register(EnvironmentAnalyzerPlugin())
plugin_registry.register(ArchitectureAnalyzerPlugin())
plugin_registry.register(DatabaseAnalyzerPlugin())
plugin_registry.register(DependencyGraphAnalyzerPlugin())
plugin_registry.register(PipelineRecommendationEnginePlugin())
