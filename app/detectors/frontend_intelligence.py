import json
import os
import re
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere, get_root_files,
    find_files_by_name_pattern
)


def _find_frontend_package_json(repo_path: str) -> str:
    """In monorepos, prefer client/frontend package.json."""
    frontend_dirs = ["client", "frontend", "web", "ui"]
    for d in frontend_dirs:
        candidate = os.path.join(repo_path, d, "package.json")
        if os.path.exists(candidate):
            return candidate
    # Fall back to root package.json (single-app repos)
    root_pkg = os.path.join(repo_path, "package.json")
    if os.path.exists(root_pkg):
        return root_pkg
    return find_file_anywhere(repo_path, "package.json")


def detect_frontend_intelligence(repo_path: str) -> dict:
    """Deep frontend analysis with build intelligence and evidence."""
    result = {
        "framework_name": None,
        "framework_confidence": 0.0,
        "framework_evidence": [],
        "build_tool": None,
        "build_command": None,
        "test_command": None,
        "dev_command": None,
        "output_directory": None,
        "node_version": None,
        "package_manager": None,
        "code_quality": [],
        "has_env_config": False,
        "dependencies": {},
        "dev_dependencies": {},
        "next_info": None
    }

    html_files = find_files_by_name_pattern(repo_path, ".html")
    pkg_path = _find_frontend_package_json(repo_path)

    if not pkg_path:
        if html_files:
            result["framework_name"] = "Vanilla JS"
            result["framework_confidence"] = 0.5
            result["framework_evidence"].append("Found HTML files but no package.json")
        return result

    raw = read_file_raw(pkg_path)
    content = raw.lower()
    evidence = []

    # Framework detection with evidence
    if "react" in content and '"next"' not in content:
        result["framework_name"] = "React"
        result["output_directory"] = "build"
        evidence.append("'react' found in package.json dependencies")
        # Check for JSX files
        jsx_files = find_files_by_name_pattern(repo_path, ".jsx") + find_files_by_name_pattern(repo_path, ".tsx")
        if jsx_files:
            evidence.append(f"Found {len(jsx_files)} JSX/TSX files")
        # Check for createRoot
        for jf in (find_files_by_name_pattern(repo_path, ".jsx") + find_files_by_name_pattern(repo_path, ".js"))[:10]:
            jcontent = read_file_raw(jf)
            if "createRoot" in jcontent or "ReactDOM.render" in jcontent:
                evidence.append("createRoot() or ReactDOM.render() found")
                break
        result["framework_confidence"] = min(0.5 + len(evidence) * 0.17, 1.0)
    elif '"next"' in content:
        result["framework_name"] = "Next.js"
        result["output_directory"] = ".next"
        evidence.append("'next' dependency found in package.json")
        result["framework_confidence"] = 0.99
    elif '"vue"' in content:
        result["framework_name"] = "Vue.js"
        result["output_directory"] = "dist"
        evidence.append("'vue' dependency found in package.json")
        result["framework_confidence"] = 0.99
    elif '"nuxt"' in content:
        result["framework_name"] = "Nuxt.js"
        result["output_directory"] = ".nuxt"
        evidence.append("'nuxt' dependency found in package.json")
        result["framework_confidence"] = 0.99
    elif '"@angular/core"' in content:
        result["framework_name"] = "Angular"
        result["output_directory"] = "dist"
        evidence.append("'@angular/core' dependency found in package.json")
        result["framework_confidence"] = 0.99
    elif '"svelte"' in content:
        result["framework_name"] = "Svelte"
        result["output_directory"] = "public"
        evidence.append("'svelte' dependency found in package.json")
        result["framework_confidence"] = 0.99
    elif html_files:
        result["framework_name"] = "Vanilla JS"
        result["framework_confidence"] = 0.5
        evidence.append("HTML files present but no known framework dependency")

    result["framework_evidence"] = evidence

    # Build tool
    if '"vite"' in content:
        result["build_tool"] = "Vite"
        result["output_directory"] = "dist"
    elif '"webpack"' in content:
        result["build_tool"] = "Webpack"
    elif '"react-scripts"' in content:
        result["build_tool"] = "CRA"
        result["output_directory"] = "build"
    elif '"parcel"' in content:
        result["build_tool"] = "Parcel"
        result["output_directory"] = "dist"

    # Scripts and deps from package.json
    try:
        data = json.loads(raw)
        scripts = data.get("scripts", {})
        result["build_command"] = scripts.get("build")
        result["test_command"] = scripts.get("test")
        result["dev_command"] = scripts.get("dev") or scripts.get("start")
        result["dependencies"] = data.get("dependencies", {})
        result["dev_dependencies"] = data.get("devDependencies", {})

        # Node version from engines
        engines = data.get("engines", {})
        if "node" in engines:
            node_ver = re.search(r'(\d+)', engines["node"])
            if node_ver:
                result["node_version"] = node_ver.group(1)
    except Exception:
        pass

    # Node version from .nvmrc or .node-version
    for nvmfile in [".nvmrc", ".node-version"]:
        path = find_file_anywhere(repo_path, nvmfile)
        if path:
            content_raw = read_file_raw(path).strip()
            match = re.search(r'(\d+)', content_raw)
            if match and not result["node_version"]:
                result["node_version"] = match.group(1)
            break

    # Package manager
    # Check in the frontend dir first, then root
    pkg_dir = os.path.dirname(pkg_path)
    dir_files = os.listdir(pkg_dir) if os.path.exists(pkg_dir) else []
    root_files = get_root_files(repo_path)
    all_files = set(dir_files) | set(root_files)
    
    if "yarn.lock" in all_files:
        result["package_manager"] = "yarn"
    elif "pnpm-lock.yaml" in all_files:
        result["package_manager"] = "pnpm"
    elif "package-lock.json" in all_files:
        result["package_manager"] = "npm"
    else:
        result["package_manager"] = "npm"

    # Code quality
    quality = []
    if find_file_anywhere(repo_path, ".eslintrc") or \
       find_file_anywhere(repo_path, ".eslintrc.js") or \
       '"eslint"' in content:
        quality.append("eslint")
    if find_file_anywhere(repo_path, ".prettierrc") or \
       '"prettier"' in content:
        quality.append("prettier")
    result["code_quality"] = quality

    # Env config
    result["has_env_config"] = bool(
        find_file_anywhere(repo_path, ".env.example") or
        find_file_anywhere(repo_path, ".env.local")
    )
    
    # Advanced Next.js specific analysis Lookups
    if result["framework_name"] == "Next.js":
        next_info = {
            "app_router": False,
            "output": None,
            "standalone_enabled": False,
            "images_unoptimized": False
        }
        
        # Check app router
        if os.path.exists(os.path.join(repo_path, "app")) or os.path.exists(os.path.join(repo_path, "src", "app")):
            next_info["app_router"] = True
            
        next_config_files = ["next.config.js", "next.config.ts", "next.config.mjs"]
        for ncf in next_config_files:
            ncf_path = find_file_anywhere(repo_path, ncf)
            if ncf_path:
                ncf_content = read_file_raw(ncf_path)
                ncf_lower = ncf_content.lower()
                
                # Check for output standalone
                if "output" in ncf_lower and "standalone" in ncf_lower:
                    # Simple heuristic
                    output_match = re.search(r'output\s*:\s*[\'"`]standalone[\'"`]', ncf_content)
                    if output_match:
                        next_info["output"] = "standalone"
                        next_info["standalone_enabled"] = True
                
                if "unoptimized" in ncf_lower and "true" in ncf_lower:
                    unopt_match = re.search(r'unoptimized\s*:\s*true', ncf_content, re.IGNORECASE)
                    if unopt_match:
                        next_info["images_unoptimized"] = True
                break
                
        result["next_info"] = next_info

    return result
