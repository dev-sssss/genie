import os
import re
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere, find_files_by_extension
)


def detect_environment_analysis(repo_path: str, language: str) -> dict:
    """Deep environment variable analysis."""
    result = {
        "required_env": [],
        "secret_env": [],
        "optional_env": [],
        "sources_found": []
    }

    all_vars = set()
    secret_keywords = [
        "secret", "key", "token", "password", "passwd",
        "pwd", "api_key", "auth", "credential", "private",
        "cert", "jwt", "oauth"
    ]

    # 1. Scan .env.example / .env.sample
    for env_file in [".env.example", ".env.sample", ".env.template", ".env"]:
        path = find_file_anywhere(repo_path, env_file)
        if path:
            result["sources_found"].append(env_file)
            content = read_file_raw(path)
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var_name = line.split("=")[0].strip()
                    if var_name:
                        all_vars.add(var_name)

    # 2. Scan source code for os.environ / process.env
    if language == "Python":
        py_files = find_files_by_extension(repo_path, ".py")
        for pf in py_files[:30]:
            content = read_file_raw(pf)
            matches = re.findall(
                r'os\.environ(?:\.get)?\(["\']([A-Z_][A-Z0-9_]+)["\']',
                content
            )
            all_vars.update(matches)
            matches = re.findall(
                r'os\.getenv\(["\']([A-Z_][A-Z0-9_]+)["\']',
                content
            )
            all_vars.update(matches)

    if language == "Node.js":
        js_files = find_files_by_extension(repo_path, ".js") + \
                   find_files_by_extension(repo_path, ".ts")
        for jf in js_files[:30]:
            content = read_file_raw(jf)
            matches = re.findall(
                r'process\.env\.([A-Z_][A-Z0-9_]+)',
                content
            )
            all_vars.update(matches)

    if language == "Java":
        java_files = find_files_by_extension(repo_path, ".java")
        for jf in java_files[:20]:
            content = read_file_raw(jf)
            matches = re.findall(
                r'System\.getenv\(["\']([A-Z_][A-Z0-9_]+)["\']',
                content
            )
            all_vars.update(matches)

    # 3. Scan docker-compose for environment section
    compose = find_file_anywhere(repo_path, "docker-compose.yml") or \
              find_file_anywhere(repo_path, "docker-compose.yaml")
    if compose:
        result["sources_found"].append("docker-compose.yml")
        content = read_file_raw(compose)
        matches = re.findall(r'^\s+([A-Z_][A-Z0-9_]+)(?:=|:)', content, re.MULTILINE)
        all_vars.update(matches)

    # 4. Categorize vars
    for var in sorted(all_vars):
        if any(kw in var.lower() for kw in secret_keywords):
            result["secret_env"].append(var)
        else:
            result["required_env"].append(var)

    return result
