import os
import json
from app.utils.file_utils import (
    read_file_safe, read_file_raw, find_file_anywhere,
    find_files_by_name_pattern, get_root_files
)


def detect_frontend(repo_path: str) -> dict:
    """Detect frontend framework, build tool, commands and code quality tools."""
    result = {
        "framework": None,
        "build_tool": None,
        "build_command": None,
        "test_command": None,
        "dev_command": None,
        "package_manager": None,
        "code_quality": []
    }

    # Check for plain HTML files
    html_files = find_files_by_name_pattern(repo_path, ".html")
    pkg_path = find_file_anywhere(repo_path, "package.json")

    if not pkg_path:
        if html_files:
            result["framework"] = "Vanilla JS"
        return result

    raw_content = read_file_raw(pkg_path)
    content = raw_content.lower()

    # Detect frontend framework
    if "react" in content and '"next"' not in content:
        result["framework"] = "React"
    elif '"next"' in content or "'next'" in content:
        result["framework"] = "Next.js"
    elif '"vue"' in content:
        result["framework"] = "Vue.js"
    elif '"nuxt"' in content:
        result["framework"] = "Nuxt.js"
    elif '"@angular/core"' in content:
        result["framework"] = "Angular"
    elif '"svelte"' in content:
        result["framework"] = "Svelte"
    elif html_files:
        result["framework"] = "Vanilla JS"

    # Detect build tool
    if '"vite"' in content:
        result["build_tool"] = "Vite"
    elif '"webpack"' in content:
        result["build_tool"] = "Webpack"
    elif '"react-scripts"' in content:
        result["build_tool"] = "CRA"
    elif '"parcel"' in content:
        result["build_tool"] = "Parcel"
    elif '"esbuild"' in content:
        result["build_tool"] = "ESBuild"

    # Extract actual scripts from package.json
    try:
        data = json.loads(raw_content)
        scripts = data.get("scripts", {})
        result["build_command"] = scripts.get("build")
        result["test_command"] = scripts.get("test")
        result["dev_command"] = scripts.get("dev") or scripts.get("start")
    except Exception:
        pass

    # Detect package manager
    root_files = get_root_files(repo_path)
    if "yarn.lock" in root_files:
        result["package_manager"] = "yarn"
    elif "pnpm-lock.yaml" in root_files:
        result["package_manager"] = "pnpm"
    elif "package-lock.json" in root_files:
        result["package_manager"] = "npm"
    else:
        result["package_manager"] = "npm"

    # Detect code quality tools
    quality_tools = []
    if find_file_anywhere(repo_path, ".eslintrc") or \
       find_file_anywhere(repo_path, ".eslintrc.js") or \
       find_file_anywhere(repo_path, ".eslintrc.json") or \
       '"eslint"' in content:
        quality_tools.append("eslint")
    if find_file_anywhere(repo_path, ".prettierrc") or \
       find_file_anywhere(repo_path, ".prettierrc.json") or \
       '"prettier"' in content:
        quality_tools.append("prettier")
    result["code_quality"] = quality_tools

    return result
