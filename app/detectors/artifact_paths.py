import os
import json
import re
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere, get_root_files
)


def detect_artifact_paths(repo_path: str, language: str, frontend_framework: str | None) -> dict:
    """
    Detect build output directories and binary artifacts so the pipeline
    knows exactly what to upload, cache, or deploy.
    """
    result = {
        "build_output_dirs": [],
        "binary_artifacts": [],
        "test_report_paths": [],
        "coverage_report_paths": [],
        "docker_artifact": None,
        "upload_paths": [],        # → actions/upload-artifact
        "cache_paths": [],         # → actions/cache
        "cache_key_files": [],     # lockfiles for cache keys
    }

    # ── Node.js ────────────────────────────────────────────────
    if language == "Node.js":
        pkg = find_file_anywhere(repo_path, "package.json")
        output_dir = "dist"

        if pkg:
            try:
                data = json.loads(read_file_raw(pkg))
                scripts = data.get("scripts", {})
                build_cmd = scripts.get("build", "")

                # Detect output dir from build tool config
                if "vite" in build_cmd or _has_vite_config(repo_path):
                    output_dir = _read_vite_output(repo_path) or "dist"
                elif "react-scripts" in build_cmd:
                    output_dir = "build"
                elif "next" in build_cmd:
                    output_dir = ".next"
                elif "nuxt" in build_cmd:
                    output_dir = ".nuxt"
                elif "angular" in build_cmd or "@angular" in str(data.get("dependencies", {})):
                    output_dir = "dist"

                # Check outDir in tsconfig
                tsconfig = find_file_anywhere(repo_path, "tsconfig.json")
                if tsconfig:
                    try:
                        ts = json.loads(read_file_raw(tsconfig))
                        co = ts.get("compilerOptions", {})
                        if co.get("outDir"):
                            output_dir = co["outDir"].lstrip("./")
                    except Exception:
                        pass

            except Exception:
                pass

        if frontend_framework and frontend_framework not in ["Vanilla JS", None]:
            result["build_output_dirs"].append(output_dir)
            result["upload_paths"].append(output_dir)

        # Cache paths
        result["cache_paths"].append("node_modules")
        result["cache_key_files"].append("package-lock.json")
        if os.path.exists(os.path.join(repo_path, "yarn.lock")):
            result["cache_key_files"] = ["yarn.lock"]
        if os.path.exists(os.path.join(repo_path, "pnpm-lock.yaml")):
            result["cache_key_files"] = ["pnpm-lock.yaml"]

        # Test reports
        result["test_report_paths"].append("junit.xml")
        result["coverage_report_paths"].append("coverage/lcov.info")
        result["coverage_report_paths"].append("coverage/coverage-summary.json")

    # ── Python ─────────────────────────────────────────────────
    elif language == "Python":
        # Wheel / sdist
        result["build_output_dirs"].append("dist")
        result["upload_paths"].append("dist")

        # Cache
        result["cache_paths"].append("~/.cache/pip")
        venv_dir = ".venv" if os.path.exists(os.path.join(repo_path, ".venv")) else None
        if venv_dir:
            result["cache_paths"].append(venv_dir)

        # Lock file priority
        for lockfile in ["poetry.lock", "Pipfile.lock", "requirements.txt"]:
            if find_file_anywhere(repo_path, lockfile):
                result["cache_key_files"].append(lockfile)
                break

        # Test reports
        result["test_report_paths"].append("junit.xml")
        result["coverage_report_paths"].append("coverage.xml")
        result["coverage_report_paths"].append("htmlcov/")

    # ── Java ───────────────────────────────────────────────────
    elif language == "Java":
        has_maven  = bool(find_file_anywhere(repo_path, "pom.xml"))
        has_gradle = bool(find_file_anywhere(repo_path, "build.gradle") or
                          find_file_anywhere(repo_path, "build.gradle.kts"))

        if has_maven:
            result["build_output_dirs"].append("target")
            result["binary_artifacts"].append("target/*.jar")
            result["upload_paths"].append("target/*.jar")
            result["cache_paths"].append("~/.m2/repository")
            result["cache_key_files"].append("pom.xml")
            result["test_report_paths"].append("target/surefire-reports")
            result["coverage_report_paths"].append("target/site/jacoco")

        elif has_gradle:
            result["build_output_dirs"].append("build/libs")
            result["binary_artifacts"].append("build/libs/*.jar")
            result["upload_paths"].append("build/libs/*.jar")
            result["cache_paths"].append("~/.gradle/caches")
            result["cache_key_files"].append("build.gradle")
            result["test_report_paths"].append("build/reports/tests")
            result["coverage_report_paths"].append("build/reports/jacoco")

    # ── Go ─────────────────────────────────────────────────────
    elif language == "Go":
        # Binary named after module
        gomod = find_file_anywhere(repo_path, "go.mod")
        binary_name = "app"
        if gomod:
            content = read_file_raw(gomod)
            match = re.search(r"^module\s+(\S+)", content, re.MULTILINE)
            if match:
                binary_name = match.group(1).split("/")[-1]

        result["build_output_dirs"].append("bin")
        result["binary_artifacts"].append(f"bin/{binary_name}")
        result["upload_paths"].append(f"bin/{binary_name}")
        result["cache_paths"].append("~/go/pkg/mod")
        result["cache_key_files"].append("go.sum")
        result["test_report_paths"].append("report.xml")
        result["coverage_report_paths"].append("coverage.out")

    # ── Docker image artifact ──────────────────────────────────
    if find_file_anywhere(repo_path, "Dockerfile"):
        result["docker_artifact"] = "Docker image (pushed to registry)"

    return result


# ── helpers ───────────────────────────────────────────────────

def _has_vite_config(repo_path: str) -> bool:
    for name in ["vite.config.js", "vite.config.ts", "vite.config.mjs"]:
        if find_file_anywhere(repo_path, name):
            return True
    return False


def _read_vite_output(repo_path: str) -> str | None:
    for name in ["vite.config.js", "vite.config.ts", "vite.config.mjs"]:
        path = find_file_anywhere(repo_path, name)
        if path:
            content = read_file_raw(path)
            match = re.search(r'outDir\s*:\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)
    return None
