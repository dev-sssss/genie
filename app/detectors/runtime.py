import re
import os
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere, get_root_files
)


def detect_runtime_versions(repo_path: str, language: str) -> dict:
    """
    Detect exact runtime versions for pipeline runner setup.
    e.g. Node 22, Python 3.11, Java 17, Go 1.22
    """
    result = {
        "language_version": None,
        "runtime_image": None,
        "node_version": None,
        "python_version": None,
        "java_version": None,
        "go_version": None,
        "ruby_version": None,
    }

    # ── Node.js ────────────────────────────────────────────
    if language == "Node.js":
        # 1. .nvmrc
        nvmrc = find_file_anywhere(repo_path, ".nvmrc")
        if nvmrc:
            raw = read_file_raw(nvmrc).strip().lstrip("v")
            match = re.search(r"(\d+)", raw)
            if match:
                result["node_version"] = match.group(1)

        # 2. .node-version
        if not result["node_version"]:
            nv = find_file_anywhere(repo_path, ".node-version")
            if nv:
                raw = read_file_raw(nv).strip().lstrip("v")
                match = re.search(r"(\d+)", raw)
                if match:
                    result["node_version"] = match.group(1)

        # 3. package.json engines.node
        if not result["node_version"]:
            pkg = find_file_anywhere(repo_path, "package.json")
            if pkg:
                content = read_file_raw(pkg)
                match = re.search(r'"node"\s*:\s*"[>=^~]*(\d+)', content)
                if match:
                    result["node_version"] = match.group(1)

        # 4. Dockerfile FROM node:XX
        if not result["node_version"]:
            df = find_file_anywhere(repo_path, "Dockerfile")
            if df:
                content = read_file_raw(df)
                match = re.search(r"FROM\s+node:(\d+)", content, re.IGNORECASE)
                if match:
                    result["node_version"] = match.group(1)

        if result["node_version"]:
            result["language_version"] = result["node_version"]
            result["runtime_image"] = f"node:{result['node_version']}-alpine"

    # ── Python ─────────────────────────────────────────────
    elif language == "Python":
        # 1. .python-version (pyenv)
        pv = find_file_anywhere(repo_path, ".python-version")
        if pv:
            raw = read_file_raw(pv).strip()
            match = re.search(r"(\d+\.\d+)", raw)
            if match:
                result["python_version"] = match.group(1)

        # 2. pyproject.toml python requires
        if not result["python_version"]:
            pp = find_file_anywhere(repo_path, "pyproject.toml")
            if pp:
                content = read_file_raw(pp)
                match = re.search(r'python_requires\s*=\s*"[>=^~]*(\d+\.\d+)', content)
                if not match:
                    match = re.search(r'python\s*=\s*"[>=^~\^]*(\d+\.\d+)', content)
                if match:
                    result["python_version"] = match.group(1)

        # 3. Dockerfile FROM python:XX
        if not result["python_version"]:
            df = find_file_anywhere(repo_path, "Dockerfile")
            if df:
                content = read_file_raw(df)
                match = re.search(r"FROM\s+python:([\d.]+)", content, re.IGNORECASE)
                if match:
                    ver = match.group(1)
                    result["python_version"] = ".".join(ver.split(".")[:2])

        # 4. runtime.txt (Heroku / Render)
        if not result["python_version"]:
            rt = find_file_anywhere(repo_path, "runtime.txt")
            if rt:
                content = read_file_raw(rt)
                match = re.search(r"python-([\d.]+)", content, re.IGNORECASE)
                if match:
                    result["python_version"] = ".".join(match.group(1).split(".")[:2])

        if result["python_version"]:
            result["language_version"] = result["python_version"]
            result["runtime_image"] = f"python:{result['python_version']}-slim"

    # ── Java ───────────────────────────────────────────────
    elif language == "Java":
        # 1. pom.xml java.version property or maven.compiler.source
        pom = find_file_anywhere(repo_path, "pom.xml")
        if pom:
            content = read_file_raw(pom)
            match = re.search(r"<java\.version>(\d+)</java\.version>", content)
            if not match:
                match = re.search(r"<maven\.compiler\.source>(\d+)</maven\.compiler\.source>", content)
            if not match:
                match = re.search(r"<release>(\d+)</release>", content)
            if match:
                result["java_version"] = match.group(1)

        # 2. build.gradle sourceCompatibility
        if not result["java_version"]:
            bg = find_file_anywhere(repo_path, "build.gradle")
            if bg:
                content = read_file_raw(bg)
                match = re.search(r"sourceCompatibility\s*=\s*['\"]?(\d+)", content)
                if not match:
                    match = re.search(r"JavaVersion\.VERSION_(\d+)", content)
                if match:
                    result["java_version"] = match.group(1)

        # 3. Dockerfile FROM eclipse-temurin / openjdk
        if not result["java_version"]:
            df = find_file_anywhere(repo_path, "Dockerfile")
            if df:
                content = read_file_raw(df)
                match = re.search(
                    r"FROM\s+(?:eclipse-temurin|openjdk|amazoncorretto|adoptopenjdk):(\d+)",
                    content, re.IGNORECASE
                )
                if match:
                    result["java_version"] = match.group(1)

        if result["java_version"]:
            result["language_version"] = result["java_version"]
            result["runtime_image"] = f"eclipse-temurin:{result['java_version']}-jre-alpine"

    # ── Go ─────────────────────────────────────────────────
    elif language == "Go":
        gomod = find_file_anywhere(repo_path, "go.mod")
        if gomod:
            content = read_file_raw(gomod)
            match = re.search(r"^go\s+([\d.]+)", content, re.MULTILINE)
            if match:
                result["go_version"] = match.group(1)

        # Dockerfile fallback
        if not result["go_version"]:
            df = find_file_anywhere(repo_path, "Dockerfile")
            if df:
                content = read_file_raw(df)
                match = re.search(r"FROM\s+golang:([\d.]+)", content, re.IGNORECASE)
                if match:
                    result["go_version"] = match.group(1)

        if result["go_version"]:
            result["language_version"] = result["go_version"]
            result["runtime_image"] = f"golang:{result['go_version']}-alpine"

    return result
