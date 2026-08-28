import os
import re
from app.utils.file_utils import read_file_raw, find_file_anywhere


def detect_docker_deep(repo_path: str, context: dict = None) -> dict:
    context = context or {}
    """Deep Docker analysis - parses all Dockerfiles found, compose configurations, and computes confidence."""
    result = {
        "has_docker": False,
        "base_image": None,
        "exposed_ports": [],
        "multistage": False,
        "healthcheck": False,
        "runs_as_root": True,
        "has_docker_compose": False,
        "compose_services": [],
        "docker_image_name": None,
        "docker_build_context": None,
        "dockerfile_path": None,
        "container_port": None,
        "docker_images": [],
        "lock_files": {},
        "runtime_files": [],
        "native_packages": [],
        "build_type": {},
        "copy_strategy": None,
        "dockerignore": [],
        "use_corepack": False,
        "framework_rules": {},
        "default_env": {},
        "docker_validation": None,
        "docker_generation": None,
        "confidence": 0.0,
        "evidence": []
    }

    # Discover all Dockerfiles in the repository
    dockerfiles = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'dist', 'build', '__pycache__', 'venv', '.venv')]
        for file in files:
            if "dockerfile" in file.lower():
                dockerfiles.append(os.path.join(root, file))

    parsed_images = []
    for df in dockerfiles:
        content = read_file_raw(df)
        content_lower = content.lower()
        rel_path = os.path.relpath(df, repo_path).replace("\\", "/")

        base_image = None
        match = re.search(r'^FROM\s+([^\s\n]+)', content, re.MULTILINE | re.IGNORECASE)
        if match:
            base_image = match.group(1).strip()

        from_count = len(re.findall(r'^\s*FROM\s+', content, re.MULTILINE | re.IGNORECASE))
        multistage = from_count > 1

        exposed_ports = re.findall(r'EXPOSE\s+(\d+)', content, re.IGNORECASE)
        container_port = exposed_ports[-1] if exposed_ports else None
        healthcheck_flag = "healthcheck" in content_lower
        runs_as_root_flag = "user " not in content_lower

        # Derive name and context from dir containing Dockerfile
        df_dir = os.path.dirname(df)
        rel_dir = os.path.relpath(df_dir, repo_path)
        image_context = "." if rel_dir == "." else f"./{rel_dir}"
        image_name = os.path.basename(df_dir) if rel_dir != "." else os.path.basename(repo_path)

        parsed_images.append({
            "name": image_name,
            "context": image_context,
            "dockerfile_path": rel_path,
            "base_image": base_image,
            "exposed_ports": exposed_ports,
            "multistage": multistage,
            "healthcheck": healthcheck_flag,
            "runs_as_root": runs_as_root_flag,
            "container_port": container_port
        })

    result["docker_images"] = parsed_images

    # If Dockerfiles exist, populate main fields using the primary / shallowest Dockerfile
    if dockerfiles:
        result["has_docker"] = True
        result["confidence"] = 1.0
        # Sort by depth so the closest to root is primary
        dockerfiles_sorted = sorted(dockerfiles, key=lambda p: len(os.path.relpath(p, repo_path).split(os.sep)))
        primary_df = dockerfiles_sorted[0]
        primary_rel = os.path.relpath(primary_df, repo_path).replace("\\", "/")
        
        # Populate compatible primary fields
        primary_info = next(img for img in parsed_images if img["dockerfile_path"] == primary_rel)
        result["base_image"] = primary_info["base_image"]
        result["exposed_ports"] = primary_info["exposed_ports"]
        result["container_port"] = primary_info["container_port"]
        result["multistage"] = primary_info["multistage"]
        result["healthcheck"] = primary_info["healthcheck"]
        result["runs_as_root"] = primary_info["runs_as_root"]
        result["dockerfile_path"] = primary_rel
        
        # Primary build context
        df_dir = os.path.dirname(primary_df)
        rel_dir = os.path.relpath(df_dir, repo_path)
        result["docker_build_context"] = "." if rel_dir == "." else f"./{rel_dir}"
        
        for img in parsed_images:
            result["evidence"].append(f"Found Dockerfile at {img['dockerfile_path']} using base image {img['base_image']}")
    else:
        result["confidence"] = 0.0

    # Docker Compose detection
    compose = find_file_anywhere(repo_path, "docker-compose.yml") or \
              find_file_anywhere(repo_path, "docker-compose.yaml")
    if compose:
        result["has_docker_compose"] = True
        c = read_file_raw(compose)
        services = re.findall(r'^\s{2}([a-zA-Z][a-zA-Z0-9_-]*):\s*$', c, re.MULTILINE)
        result["compose_services"] = [
            s for s in services
            if s not in ["version", "networks", "volumes", "services"]
        ]
        if not result["has_docker"]:
            result["confidence"] = 0.9  # high confidence, but no explicit Dockerfile found
        
        result["evidence"].append(f"Found docker-compose config at {os.path.relpath(compose, repo_path)} defining services: {', '.join(result['compose_services'])}")
        
        # Docker image name (if any service defines a static image)
        match = re.search(r'image:\s*([^\s\n]+)', c)
        if match:
            result["docker_image_name"] = match.group(1).strip()
            
    # ------ Advanced Analysis (16 Missing Fields) ------
    packages = context.get("packages", {})
    frontend_data = context.get("frameworks", {}).get("frontend_data", {})
    backend_lang = context.get("language", "unknown")
    
    # 1. Lock Files Detection
    lock_files = {
        "package-lock.json": bool(find_file_anywhere(repo_path, "package-lock.json")),
        "pnpm-lock.yaml": bool(find_file_anywhere(repo_path, "pnpm-lock.yaml")),
        "yarn.lock": bool(find_file_anywhere(repo_path, "yarn.lock")),
        "bun.lockb": bool(find_file_anywhere(repo_path, "bun.lockb"))
    }
    result["lock_files"] = lock_files
    
    # 2. Node Version Resolution
    node_version = frontend_data.get("node_version") or packages.get("runtime_data", {}).get("node_version") or "20"
    
    # 3. Native Linux Packages (sharp, canvas, bcrypt, sqlite3, puppeteer)
    frontend_deps = frontend_data.get("dependencies", {})
    native_list = ["sharp", "canvas", "bcrypt", "sqlite3", "puppeteer"]
    detected_native = [pkg for pkg in native_list if pkg in frontend_deps]
    result["native_packages"] = detected_native
    if detected_native:
        result["evidence"].append(f"Detected native dependencies requiring build tools: {', '.join(detected_native)}")
        
    # Generate hints and dynamic validation strategy
    is_nextjs = frontend_data.get("framework_name") == "Next.js"
    pkg_manager = frontend_data.get("package_manager") or packages.get("package_manager") or "npm"
    use_corepack = pkg_manager in ["yarn", "pnpm"]
    result["use_corepack"] = use_corepack
    
    # Base Image Recommendation
    recommended_base = f"node:{node_version}-alpine" if not detected_native else f"node:{node_version}-slim"
    
    # Build Type
    result["build_type"] = {"multi_stage": True, "single_stage": False}
    
    # Copy Strategy and Framework Rules
    copy_strategy = {
        "copy_node_modules": False,
        "copy_standalone": False,
        "copy_public": True,
        "copy_static": True
    }
    
    rules = {}
    runtime_files = ["public"]
    cmd = "npm start"
    
    next_info = frontend_data.get("next_info", {})
    if is_nextjs:
        rules["nextjs"] = {
            "needs_standalone": next_info.get("standalone_enabled", False),
            "needs_public": True,
            "needs_next_static": True
        }
        if next_info.get("standalone_enabled"):
            copy_strategy["copy_standalone"] = True
            runtime_files.append(".next/standalone")
            runtime_files.append(".next/static")
            cmd = "node server.js"
        else:
            copy_strategy["copy_node_modules"] = True
            runtime_files.append(".next")
            cmd = "npm run start" if pkg_manager == "npm" else f"{pkg_manager} start"
    
    result["copy_strategy"] = copy_strategy
    result["framework_rules"] = rules
    result["runtime_files"] = runtime_files
    
    # Default Env
    result["default_env"] = {"NODE_ENV": "production"}
    
    # Dockerignore
    result["dockerignore"] = [
        ".git", "node_modules", ".env", "coverage", ".next", 
        "build", "dist", "*.log", "npm-debug.log*"
    ]
    
    # Exposed Port
    port_str = packages.get("port") or "3000"
    try: port_val = int(port_str)
    except: port_val = 3000
    
    # Validation Hints
    warnings = []
    if is_nextjs and not next_info.get("standalone_enabled"):
        warnings.append("Standalone output not enabled - Docker image will be very large.")
    if not frontend_data.get("node_version") and not packages.get("runtime_data", {}).get("node_version"):
        warnings.append("No node version specified, defaulting to 20")
        
    validation = {
        "can_generate": True,
        "confidence": 0.98 if is_nextjs else 0.8,
        "warnings": warnings,
        "blocking_issues": [],
        "recommended_strategy": "multi-stage",
        "recommended_package_manager": pkg_manager,
        "recommended_base_image": recommended_base
    }
    result["docker_validation"] = validation
    
    build_cmd = f"{pkg_manager} run build"
    
    generation_hints = {
        "base_image": recommended_base,
        "multi_stage": True,
        "package_manager": pkg_manager,
        "build_cmd": build_cmd,
        "copy_public": copy_strategy["copy_public"],
        "copy_static": copy_strategy.get("copy_static", False),
        "copy_standalone": copy_strategy["copy_standalone"],
        "run_as_non_root": True,
        "use_corepack_enable": use_corepack,
        "disable_telemetry": True,
        "needs_libc6_compat": "alpine" in recommended_base,
        "set_port_env": True,
        "chown_copies": True,
        "cache_optimized_deps": True,
        "add_healthcheck": True,
        "expose_port": port_val,
        "cmd": cmd
    }
    result["docker_generation"] = generation_hints

    return result
