from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.sql import func
from sqlalchemy.types import JSON
from sqlalchemy.orm import relationship
from app.database import Base

# --- SQLAlchemy Database Models --- #
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    chats = relationship("Chat", back_populates="user", cascade="all, delete-orphan")

class Chat(Base):
    __tablename__ = "chats"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    reasoning_details = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    chat = relationship("Chat", back_populates="messages")

# --- Pydantic Auth Schemas --- #
class UserSignup(BaseModel):
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class OTPVerifyRequest(BaseModel):
    email: str
    code: str

class OTPResponse(BaseModel):
    success: bool
    message: str
    detail: Optional[str] = None
    email: Optional[str] = None

class Token(BaseModel):
    access_token: str
    token_type: str

class ChatCreate(BaseModel):
    title: Optional[str] = "New Conversation"

class MessageCreate(BaseModel):
    role: str
    content: str
    model: Optional[str] = "x-ai/grok-4.6"
    reasoning_details: Optional[Any] = None

class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    reasoning_details: Optional[Any] = None
    created_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        from_attributes = True

class ChatResponse(BaseModel):
    id: int
    title: Optional[str]
    messages: List[MessageResponse] = []
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        from_attributes = True

class ChatListResponse(BaseModel):
    id: int
    title: Optional[str]
    updated_at: Optional[datetime] = None
    
    class Config:
        orm_mode = True
        from_attributes = True


class AnalyzeRequest(BaseModel):
    repo_url: str
    github_token: Optional[str] = None


# ── Framework Detection ───────────────────────────────────
class FrameworkDetection(BaseModel):
    name: Optional[str] = None
    confidence: float = 0.0
    evidence: List[str] = []


# ── Backend ──────────────────────────────────────────────
class BuildCommands(BaseModel):
    build: Optional[str] = None
    test: Optional[str] = None
    start: Optional[str] = None
    dev: Optional[str] = None
    lint: Optional[str] = None
    install: Optional[str] = None


class BackendInfo(BaseModel):
    language: Optional[str] = "unknown"
    framework: FrameworkDetection = FrameworkDetection()
    libraries: List[str] = []
    package_manager: Optional[str] = "unknown"
    entrypoint: Optional[str] = None
    startup_command: Optional[str] = None
    port: Optional[str] = None
    health_endpoint: Optional[str] = None
    code_quality: List[str] = []
    build_commands: BuildCommands = BuildCommands()
    dependencies: Dict[str, str] = {}
    dev_dependencies: Dict[str, str] = {}
    confidence: float = 1.0
    evidence: List[str] = []


# ── Runtime Versions ──────────────────────────────────────
class RuntimeInfo(BaseModel):
    language_version: Optional[str] = None
    runtime_image: Optional[str] = None
    node_version: Optional[str] = None
    python_version: Optional[str] = None
    java_version: Optional[str] = None
    go_version: Optional[str] = None
    ruby_version: Optional[str] = None


# ── Package Scripts ───────────────────────────────────────
class PackageScripts(BaseModel):
    start: Optional[str] = None
    dev: Optional[str] = None
    build: Optional[str] = None
    test: Optional[str] = None
    test_coverage: Optional[str] = None
    lint: Optional[str] = None
    format: Optional[str] = None
    typecheck: Optional[str] = None
    clean: Optional[str] = None
    install: Optional[str] = None
    migrate: Optional[str] = None
    seed: Optional[str] = None
    all_scripts: Dict[str, str] = {}


# ── Testing ───────────────────────────────────────────────
class TestingInfo(BaseModel):
    unit: bool = False
    integration: bool = False
    e2e: bool = False
    framework: Optional[str] = None
    test_command: Optional[str] = None
    coverage: Optional[int] = None
    coverage_command: Optional[str] = None
    test_directories: List[str] = []
    e2e_tool: Optional[str] = None


# ── Frontend ──────────────────────────────────────────────
class NextJsInfo(BaseModel):
    app_router: bool = False
    output: Optional[str] = None
    standalone_enabled: bool = False
    images_unoptimized: bool = False

class FrontendInfo(BaseModel):
    framework: FrameworkDetection = FrameworkDetection()
    build_tool: Optional[str] = None
    build_command: Optional[str] = None
    test_command: Optional[str] = None
    dev_command: Optional[str] = None
    output_directory: Optional[str] = None
    node_version: Optional[str] = None
    package_manager: Optional[str] = None
    code_quality: List[str] = []
    has_env_config: bool = False
    dependencies: Dict[str, str] = {}
    dev_dependencies: Dict[str, str] = {}
    next_info: Optional[NextJsInfo] = None
    confidence: float = 1.0
    evidence: List[str] = []


# ── Docker ────────────────────────────────────────────────
class DockerImageInfo(BaseModel):
    name: Optional[str] = None
    context: Optional[str] = None
    dockerfile_path: str
    base_image: Optional[str] = None
    exposed_ports: List[str] = []
    multistage: bool = False
    healthcheck: bool = False
    runs_as_root: bool = True
    container_port: Optional[str] = None

class DockerValidation(BaseModel):
    can_generate: bool = False
    confidence: float = 0.0
    warnings: List[str] = []
    blocking_issues: List[str] = []
    recommended_strategy: Optional[str] = None
    recommended_package_manager: Optional[str] = None
    recommended_base_image: Optional[str] = None

class DockerGenerationHints(BaseModel):
    base_image: Optional[str] = None
    multi_stage: bool = False
    package_manager: Optional[str] = None
    copy_public: bool = False
    copy_static: bool = False
    copy_standalone: bool = False
    run_as_non_root: bool = False
    use_corepack: bool = False
    enable_telemetry: bool = False
    expose_port: Optional[int] = None
    cmd: Optional[str] = None

class CopyStrategy(BaseModel):
    copy_node_modules: bool = False
    copy_standalone: bool = False
    copy_public: bool = False

class DockerInfo(BaseModel):
    has_docker: bool = False
    base_image: Optional[str] = None
    exposed_ports: List[str] = []
    multistage: bool = False
    healthcheck: bool = False
    runs_as_root: bool = True
    has_docker_compose: bool = False
    compose_services: List[str] = []
    docker_image_name: Optional[str] = None
    docker_build_context: Optional[str] = None
    dockerfile_path: Optional[str] = None
    container_port: Optional[str] = None
    docker_images: List[DockerImageInfo] = []
    
    lock_files: Dict[str, bool] = {}
    runtime_files: List[str] = []
    native_packages: List[str] = []
    build_type: Dict[str, bool] = {}
    copy_strategy: Optional[CopyStrategy] = None
    dockerignore: List[str] = []
    use_corepack: bool = False
    framework_rules: Dict[str, Any] = {}
    default_env: Dict[str, str] = {}
    
    docker_validation: Optional[DockerValidation] = None
    docker_generation: Optional[DockerGenerationHints] = None
    
    confidence: float = 1.0
    evidence: List[str] = []


# ── Infrastructure ────────────────────────────────────────
class InfrastructureInfo(BaseModel):
    docker: DockerInfo = DockerInfo()
    has_kubernetes: bool = False
    k8s_namespaces: List[str] = []
    k8s_service_names: List[str] = []
    k8s_has_ingress: bool = False
    has_terraform: bool = False
    terraform_resources: List[str] = []
    has_helm: bool = False
    has_ansible: bool = False


# ── Database ──────────────────────────────────────────────
class DatabaseInfo(BaseModel):
    detected: List[str] = []
    primary: Optional[str] = None
    migration_tool: Optional[str] = None
    has_migrations: bool = False
    migration_command: Optional[str] = None
    cache: Optional[str] = None
    message_queue: Optional[str] = None
    confidence: float = 1.0
    evidence: List[str] = []


# ── Cloud ─────────────────────────────────────────────────
class CloudInfo(BaseModel):
    provider: Optional[str] = None
    deployment_target: Optional[str] = None
    deployment_strategy: Optional[str] = None
    registry: Optional[str] = None
    confidence: float = 1.0
    evidence: List[str] = []


# ── Deployment Intelligence ───────────────────────────────
class DeploymentIntelligence(BaseModel):
    target: Optional[str] = None
    strategy: Optional[str] = None
    registry: Optional[str] = None
    environment: str = "production"
    rollback_supported: bool = False
    reason: List[str] = []


# ── Infrastructure Graph ──────────────────────────────────
class InfrastructureGraph(BaseModel):
    graph: Dict[str, Any] = {}


# ── Repository Architecture ───────────────────────────────
class RepoArchitecture(BaseModel):
    root_files: List[str] = []
    frontend_path: Optional[str] = None
    backend_path: Optional[str] = None
    dockerfile_path: Optional[str] = None
    kubernetes_path: Optional[str] = None
    terraform_path: Optional[str] = None
    tests_path: Optional[str] = None
    ci_cd_path: Optional[str] = None
    repository_tree: Dict[str, Any] = {}


# ── Project ───────────────────────────────────────────────
class ProjectInfo(BaseModel):
    is_monorepo: bool = False
    services_count: int = 1
    service_names: List[str] = []
    has_makefile: bool = False
    makefile_targets: List[str] = []
    has_taskfile: bool = False


# ── Branch Strategy ───────────────────────────────────────
class BranchStrategy(BaseModel):
    default_branch: str = "main"
    branches: List[str] = []
    strategy: str = "github-flow"
    branch_environment_map: Dict[str, str] = {}
    trigger_branches: List[str] = ["main"]
    protected_branches: List[str] = ["main"]


# ── Environments ──────────────────────────────────────────
class EnvironmentDiscovery(BaseModel):
    environments: List[str] = ["production"]
    has_staging: bool = False
    has_production: bool = True
    has_development: bool = False
    env_config_files: List[str] = []
    deployment_environments: List[str] = ["deploy_production"]
    approval_required_for: List[str] = []


# ── Secrets Intelligence ──────────────────────────────────
class SecretsInfo(BaseModel):
    required_secrets: List[str] = []
    optional_secrets: List[str] = []
    secret_groups: Dict[str, List[str]] = {}


# ── Artifact Paths ────────────────────────────────────────
class ArtifactPaths(BaseModel):
    build_output_dirs: List[str] = []
    binary_artifacts: List[str] = []
    test_report_paths: List[str] = []
    coverage_report_paths: List[str] = []
    docker_artifact: Optional[str] = None
    upload_paths: List[str] = []
    cache_paths: List[str] = []
    cache_key_files: List[str] = []


# ── Environment ───────────────────────────────────────────
class EnvironmentInfo(BaseModel):
    required_env: List[str] = []
    secret_env: List[str] = []
    optional_env: List[str] = []
    sources_found: List[str] = []


# ── CI/CD ─────────────────────────────────────────────────
class ParsedWorkflowJob(BaseModel):
    name: str
    steps: List[str] = []
    image: Optional[str] = None

class ParsedWorkflowInfo(BaseModel):
    file_path: str
    name: Optional[str] = None
    triggers: List[str] = []
    jobs: List[ParsedWorkflowJob] = []

class CiCdInfo(BaseModel):
    has_ci: bool = False
    existing_ci: Optional[str] = "none"
    has_build: bool = False
    has_tests: bool = False
    has_security_scan: bool = False
    has_docker_build: bool = False
    has_deployment: bool = False
    has_notifications: bool = False
    has_caching: bool = False
    has_approval_gate: bool = False
    has_rollback: bool = False
    quality_score: int = 0
    existing_stages: List[str] = []
    missing_stages: List[str] = []
    existing_workflows: List[str] = []
    parsed_workflows: List[ParsedWorkflowInfo] = []
    confidence: float = 1.0
    evidence: List[str] = []


# ── Monitoring ────────────────────────────────────────────
class MonitoringInfo(BaseModel):
    tools_detected: List[str] = []
    has_prometheus: bool = False
    has_grafana: bool = False
    has_opentelemetry: bool = False
    has_datadog: bool = False
    has_sentry: bool = False
    has_elk: bool = False


# ── Security ──────────────────────────────────────────────
class SecurityInfo(BaseModel):
    has_hardcoded_secrets: bool = False
    hardcoded_secret_files: List[str] = []
    runs_as_root: bool = False
    has_privileged_container: bool = False
    missing_health_check: bool = True
    missing_resource_limits: bool = True
    exposed_debug_mode: bool = False
    security_risks: List[str] = []
    security_score: int = 100


# ── Pipeline Requirements ─────────────────────────────────
class PipelineRequirements(BaseModel):
    install_dependencies: bool = True
    lint: bool = False
    build_backend: bool = False
    build_frontend: bool = False
    unit_tests: bool = False
    integration_tests: bool = False
    e2e_tests: bool = False
    coverage_check: bool = False
    security_scan: bool = True
    secret_detection: bool = False
    dependency_audit: bool = True
    docker_build: bool = False
    docker_push: bool = False
    docker_scan: bool = False
    terraform_plan: bool = False
    terraform_apply: bool = False
    helm_deploy: bool = False
    k8s_deploy: bool = False
    deploy_staging: bool = False
    deploy_production: bool = False
    approval_gate: bool = False
    rollback: bool = False
    health_check: bool = False
    smoke_tests: bool = False
    db_migration: bool = False
    monitoring_setup: bool = False
    notify: bool = True
    deployment_target: Optional[str] = None
    deployment_strategy: Optional[str] = None
    container_registry: Optional[str] = None


# ── API Routes ────────────────────────────────────────────
class ApiRoutes(BaseModel):
    routes: List[str] = []
    health_route: Optional[str] = None


# ── Grade ─────────────────────────────────────────────────
class GradeInfo(BaseModel):
    grade: str = "beginner"
    score: int = 0
    grade_reason: List[str] = []
    missing_for_enterprise: List[str] = []


# ── Recommended Pipeline ──────────────────────────────────
class RecommendedPipeline(BaseModel):
    stages: List[Dict[str, Any]] = []
    parallel_groups: Dict[str, List[str]] = {}
    warnings: List[str] = []
    trigger_branches: List[str] = ["main"]
    default_branch: str = "main"
    branch_environment_map: Dict[str, str] = {}
    runtime: Dict[str, Any] = {}
    required_secrets: List[str] = []
    secret_groups: Dict[str, List[str]] = {}
    total_stages: int = 0


# ── Final Response ────────────────────────────────────────
class AnalyzeResponse(BaseModel):
    repo_url: str

    # Code Analysis
    backend: BackendInfo = BackendInfo()
    frontend: FrontendInfo = FrontendInfo()
    testing: TestingInfo = TestingInfo()

    # Runtime & Scripts
    runtime: RuntimeInfo = RuntimeInfo()
    scripts: PackageScripts = PackageScripts()

    # Infrastructure
    infrastructure: InfrastructureInfo = InfrastructureInfo()
    database: DatabaseInfo = DatabaseInfo()
    cloud: CloudInfo = CloudInfo()

    # Intelligence Layers
    environment: EnvironmentInfo = EnvironmentInfo()
    monitoring: MonitoringInfo = MonitoringInfo()
    security: SecurityInfo = SecurityInfo()
    api_routes: ApiRoutes = ApiRoutes()

    # Deployment Intelligence
    deployment: DeploymentIntelligence = DeploymentIntelligence()
    infrastructure_graph: Dict[str, Any] = {}
    architecture: RepoArchitecture = RepoArchitecture()

    # Project
    project: ProjectInfo = ProjectInfo()
    ci_cd: CiCdInfo = CiCdInfo()

    # NEW: Enterprise Intelligence
    branch_strategy: BranchStrategy = BranchStrategy()
    environments: EnvironmentDiscovery = EnvironmentDiscovery()
    secrets: SecretsInfo = SecretsInfo()
    artifacts: ArtifactPaths = ArtifactPaths()

    # Pipeline Bridge
    pipeline_requirements: PipelineRequirements = PipelineRequirements()

    # NEW: Recommended Pipeline (direct LLM input)
    recommended_pipeline: RecommendedPipeline = RecommendedPipeline()

    # Grade
    grade_info: GradeInfo = GradeInfo()


class HealthResponse(BaseModel):
    status: str
    service: str


class GeneratePipelineRequest(BaseModel):
    analysis: Dict[str, Any]
    spec: Dict[str, Any]
    model: Optional[str] = "x-ai/grok-4.6"


class FixPipelineRequest(BaseModel):
    error_message: str
    current_pipeline: str
    spec: Dict[str, Any]
    analysis: Dict[str, Any]
    model: Optional[str] = "x-ai/grok-4.6"


class GenerateDockerRequest(BaseModel):
    analysis: Dict[str, Any]
    model: Optional[str] = "x-ai/grok-4.6"


class ChatMessage(BaseModel):
    role: str
    content: str
    reasoning_details: Optional[Any] = None
    
class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    model: Optional[str] = "x-ai/grok-4.6"

class LLMChatResponse(BaseModel):
    message: str
    reasoning_details: Optional[Any] = None

