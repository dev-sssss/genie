import json
import os
from app.utils.file_utils import read_file_raw, find_file_anywhere


def _find_backend_package_json(repo_path: str) -> str:
    """In monorepos, prefer server/backend package.json over root."""
    backend_dirs = ["server", "backend", "api", "service"]
    for d in backend_dirs:
        candidate = os.path.join(repo_path, d, "package.json")
        if os.path.exists(candidate):
            return candidate
    root_pkg = os.path.join(repo_path, "package.json")
    if os.path.exists(root_pkg):
        return root_pkg
    return find_file_anywhere(repo_path, "package.json")


def _find_frontend_package_json(repo_path: str) -> str:
    """In monorepos, prefer client/frontend package.json over root."""
    frontend_dirs = ["client", "frontend", "web", "ui"]
    for d in frontend_dirs:
        candidate = os.path.join(repo_path, d, "package.json")
        if os.path.exists(candidate):
            return candidate
    # If no dedicated frontend folder, return None (don't fall back to root
    # because that would duplicate with backend deps)
    return None


def detect_dependencies(repo_path: str, language: str) -> dict:
    """Extract backend dependency graph with versions (monorepo-aware)."""
    result = {
        "dependencies": {},
        "dev_dependencies": {}
    }

    if language == "Node.js":
        pkg = _find_backend_package_json(repo_path)
        if pkg:
            try:
                data = json.loads(read_file_raw(pkg))
                result["dependencies"] = data.get("dependencies", {})
                result["dev_dependencies"] = data.get("devDependencies", {})
            except Exception:
                pass

    elif language == "Python":
        req = find_file_anywhere(repo_path, "requirements.txt")
        if req:
            content = read_file_raw(req)
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    if "==" in line:
                        name, version = line.split("==", 1)
                        result["dependencies"][name.strip()] = version.strip()
                    elif ">=" in line:
                        name, version = line.split(">=", 1)
                        result["dependencies"][name.strip()] = f">={version.strip()}"
                    else:
                        result["dependencies"][line] = "latest"

        pyproject = find_file_anywhere(repo_path, "pyproject.toml")
        if pyproject:
            content = read_file_raw(pyproject)
            import re
            matches = re.findall(r'"([a-zA-Z][a-zA-Z0-9_-]+)\s*[>=<^~]*\s*([\d.]+)"', content)
            for name, version in matches:
                result["dependencies"][name] = version

    elif language == "Java":
        pom = find_file_anywhere(repo_path, "pom.xml")
        if pom:
            import re
            content = read_file_raw(pom)
            matches = re.findall(
                r'<artifactId>([^<]+)</artifactId>.*?<version>([^<]+)</version>',
                content, re.DOTALL
            )
            for name, version in matches[:20]:
                result["dependencies"][name.strip()] = version.strip()

    elif language == "Go":
        gomod = find_file_anywhere(repo_path, "go.mod")
        if gomod:
            import re
            content = read_file_raw(gomod)
            matches = re.findall(r'require\s+([^\s]+)\s+([^\s\n]+)', content)
            for name, version in matches:
                result["dependencies"][name] = version

    return result


def detect_frontend_dependencies(repo_path: str) -> dict:
    """Extract frontend dependencies from the frontend-specific package.json."""
    result = {
        "dependencies": {},
        "dev_dependencies": {}
    }
    pkg = _find_frontend_package_json(repo_path)
    if pkg:
        try:
            data = json.loads(read_file_raw(pkg))
            result["dependencies"] = data.get("dependencies", {})
            result["dev_dependencies"] = data.get("devDependencies", {})
        except Exception:
            pass
    return result
