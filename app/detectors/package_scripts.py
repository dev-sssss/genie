import json
import re
import os
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere
)


def detect_package_scripts(repo_path: str, language: str) -> dict:
    """
    Extract all runnable scripts so the pipeline uses real commands
    instead of AI-guessed ones.
    """
    result = {
        "start": None,
        "dev": None,
        "build": None,
        "test": None,
        "test_coverage": None,
        "lint": None,
        "format": None,
        "typecheck": None,
        "clean": None,
        "install": None,
        "migrate": None,
        "seed": None,
        "all_scripts": {}
    }

    # ── Node.js: package.json scripts ────────────────────────
    if language == "Node.js":
        pkg = find_file_anywhere(repo_path, "package.json")
        if pkg:
            try:
                data = json.loads(read_file_raw(pkg))
                scripts = data.get("scripts", {})
                result["all_scripts"] = scripts

                result["start"]   = scripts.get("start")
                result["dev"]     = scripts.get("dev") or scripts.get("develop")
                result["build"]   = scripts.get("build")
                result["test"]    = scripts.get("test")
                result["lint"]    = scripts.get("lint") or scripts.get("lint:check")
                result["format"]  = scripts.get("format") or scripts.get("fmt")
                result["clean"]   = scripts.get("clean")
                result["migrate"] = scripts.get("migrate") or scripts.get("db:migrate")
                result["seed"]    = scripts.get("seed") or scripts.get("db:seed")

                # Coverage — look for test:coverage, test:cov, coverage
                for key in ["test:coverage", "test:cov", "coverage", "cov"]:
                    if key in scripts:
                        result["test_coverage"] = scripts[key]
                        break

                # Typecheck
                for key in ["typecheck", "type-check", "tsc", "ts:check"]:
                    if key in scripts:
                        result["typecheck"] = scripts[key]
                        break

                # Install command
                manager = _detect_pm(repo_path)
                result["install"] = f"{manager} install"

            except Exception:
                pass

    # ── Python: Makefile / pyproject.toml / tox ──────────────
    elif language == "Python":
        result["install"] = _python_install_cmd(repo_path)
        result["test"]    = _python_test_cmd(repo_path)
        result["lint"]    = _python_lint_cmd(repo_path)
        result["format"]  = _python_format_cmd(repo_path)
        result["test_coverage"] = "pytest --cov=. --cov-report=xml --cov-fail-under=80"

        # pyproject.toml scripts section (PDM / Hatch)
        pp = find_file_anywhere(repo_path, "pyproject.toml")
        if pp:
            content = read_file_raw(pp)
            # Hatch scripts
            matches = re.findall(r'\[tool\.hatch\.envs\.\w+\.scripts\](.*?)(?=\[)', content, re.DOTALL)
            for block in matches:
                for k, v in re.findall(r'(\w+)\s*=\s*"([^"]+)"', block):
                    result["all_scripts"][k] = v

        # Makefile targets as scripts
        makefile = find_file_anywhere(repo_path, "Makefile")
        if makefile:
            content = read_file_raw(makefile)
            targets = re.findall(r'^([a-zA-Z][a-zA-Z0-9_-]+)\s*:', content, re.MULTILINE)
            for t in targets:
                result["all_scripts"][t] = f"make {t}"

    # ── Java: Maven / Gradle ──────────────────────────────────
    elif language == "Java":
        has_maven  = bool(find_file_anywhere(repo_path, "pom.xml"))
        has_gradle = bool(find_file_anywhere(repo_path, "build.gradle") or
                          find_file_anywhere(repo_path, "build.gradle.kts"))

        if has_maven:
            result["install"]       = "mvn dependency:resolve"
            result["build"]         = "mvn package -DskipTests"
            result["test"]          = "mvn test"
            result["test_coverage"] = "mvn test jacoco:report"
            result["lint"]          = "mvn checkstyle:check"
            result["all_scripts"]   = {
                "install": result["install"],
                "build":   result["build"],
                "test":    result["test"],
                "coverage": result["test_coverage"],
            }
        elif has_gradle:
            wrapper = "./gradlew" if _has_wrapper(repo_path, "gradlew") else "gradle"
            result["install"]       = f"{wrapper} dependencies"
            result["build"]         = f"{wrapper} build -x test"
            result["test"]          = f"{wrapper} test"
            result["test_coverage"] = f"{wrapper} test jacocoTestReport"
            result["lint"]          = f"{wrapper} checkstyleMain"
            result["all_scripts"]   = {
                "install": result["install"],
                "build":   result["build"],
                "test":    result["test"],
                "coverage": result["test_coverage"],
            }

    # ── Go ────────────────────────────────────────────────────
    elif language == "Go":
        result["install"]       = "go mod download"
        result["build"]         = "go build ./..."
        result["test"]          = "go test ./..."
        result["test_coverage"] = "go test ./... -coverprofile=coverage.out -covermode=atomic"
        result["lint"]          = "golangci-lint run"
        result["format"]        = "gofmt -w ."
        result["all_scripts"]   = {
            "install": result["install"],
            "build":   result["build"],
            "test":    result["test"],
            "coverage": result["test_coverage"],
            "lint":    result["lint"],
        }

    return result


# ── helpers ───────────────────────────────────────────────────

def _detect_pm(repo_path: str) -> str:
    from app.utils.file_utils import get_root_files
    root = get_root_files(repo_path)
    if "yarn.lock" in root:
        return "yarn"
    if "pnpm-lock.yaml" in root:
        return "pnpm"
    return "npm"


def _python_install_cmd(repo_path: str) -> str:
    if find_file_anywhere(repo_path, "Pipfile"):
        return "pipenv install"
    if find_file_anywhere(repo_path, "pyproject.toml"):
        content = read_file_raw(find_file_anywhere(repo_path, "pyproject.toml"))
        if "poetry" in content:
            return "poetry install"
    return "pip install -r requirements.txt"


def _python_test_cmd(repo_path: str) -> str:
    if find_file_anywhere(repo_path, "pytest.ini") or \
       find_file_anywhere(repo_path, "setup.cfg") or \
       find_file_anywhere(repo_path, "pyproject.toml"):
        return "pytest"
    return "python -m pytest"


def _python_lint_cmd(repo_path: str) -> str:
    if find_file_anywhere(repo_path, ".flake8") or \
       find_file_anywhere(repo_path, "setup.cfg"):
        return "flake8 ."
    if find_file_anywhere(repo_path, ".ruff.toml") or \
       find_file_anywhere(repo_path, "ruff.toml"):
        return "ruff check ."
    if find_file_anywhere(repo_path, "pyproject.toml"):
        content = read_file_raw(find_file_anywhere(repo_path, "pyproject.toml"))
        if "ruff" in content:
            return "ruff check ."
        if "flake8" in content:
            return "flake8 ."
    return "flake8 ."


def _python_format_cmd(repo_path: str) -> str:
    if find_file_anywhere(repo_path, ".black") or \
       find_file_anywhere(repo_path, "pyproject.toml"):
        pp = find_file_anywhere(repo_path, "pyproject.toml")
        if pp and "black" in read_file_raw(pp):
            return "black --check ."
    return None


def _has_wrapper(repo_path: str, name: str) -> bool:
    return os.path.exists(os.path.join(repo_path, name))
