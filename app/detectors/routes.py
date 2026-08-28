import os
import re
from app.utils.file_utils import (
    find_files_by_extension, read_file_raw
)


def detect_api_routes(repo_path: str, language: str, framework: str) -> list:
    """Discover all API routes from source code."""
    routes = set()

    if language == "Python":
        py_files = find_files_by_extension(repo_path, ".py")
        for pf in py_files[:30]:
            content = read_file_raw(pf)
            # FastAPI / Flask route patterns
            matches = re.findall(
                r'@(?:app|router)\.\w+\(["\']([^"\']+)["\']',
                content
            )
            routes.update(matches)
            # Django URL patterns
            matches = re.findall(
                r'path\(["\']([^"\']+)["\']',
                content
            )
            routes.update(["/" + m.strip("/") for m in matches])

    if language == "Node.js":
        js_files = find_files_by_extension(repo_path, ".js") + \
                   find_files_by_extension(repo_path, ".ts")
        for jf in js_files[:30]:
            content = read_file_raw(jf)
            # Express route patterns
            matches = re.findall(
                r'(?:router|app)\.\w+\(["\']([^"\']+)["\']',
                content
            )
            routes.update(matches)

    if language == "Java":
        java_files = find_files_by_extension(repo_path, ".java")
        for jf in java_files[:30]:
            content = read_file_raw(jf)
            # Spring Boot annotations
            matches = re.findall(
                r'@(?:GetMapping|PostMapping|RequestMapping|PutMapping|DeleteMapping)\(["\']([^"\']+)["\']',
                content
            )
            routes.update(matches)

    if language == "Go":
        go_files = find_files_by_extension(repo_path, ".go")
        for gf in go_files[:30]:
            content = read_file_raw(gf)
            # Gin/Echo route patterns
            matches = re.findall(
                r'\.\w+\(["\']([/][^"\']*)["\']',
                content
            )
            routes.update(matches)

    # Clean and sort routes
    cleaned = []
    for r in routes:
        r = r.strip()
        if r and r.startswith("/") and len(r) < 100:
            cleaned.append(r)

    return sorted(set(cleaned))[:30]
