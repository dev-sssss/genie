import os
import re
import json
from app.utils.file_utils import (
    read_file_raw, read_file_safe,
    find_file_anywhere, find_files_by_extension
)


def detect_testing_intelligence(repo_path: str, language: str) -> dict:
    """Deep testing analysis."""
    result = {
        "unit": False,
        "integration": False,
        "e2e": False,
        "framework": None,
        "test_command": None,
        "coverage": None,
        "coverage_command": None,
        "test_directories": [],
        "e2e_tool": None
    }

    # Find test directories
    test_dirs = ["tests", "test", "__tests__", "spec"]
    for td in test_dirs:
        if os.path.exists(os.path.join(repo_path, td)):
            result["test_directories"].append(td)

    # Check for integration test dirs
    integ_dirs = ["integration", "e2e", "functional", "acceptance"]
    for root, dirs, _ in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for d in dirs:
            if any(kw in d.lower() for kw in integ_dirs):
                if "e2e" in d.lower():
                    result["e2e"] = True
                else:
                    result["integration"] = True

    if language == "Python":
        # Check for test files
        py_files = find_files_by_extension(repo_path, ".py")
        for pf in py_files[:50]:
            fname = os.path.basename(pf)
            if fname.startswith("test_") or fname.endswith("_test.py"):
                result["unit"] = True
                result["framework"] = "pytest"
                break

        # Coverage config
        coveragerc = find_file_anywhere(repo_path, ".coveragerc")
        pyproject = find_file_anywhere(repo_path, "pyproject.toml")
        if coveragerc or pyproject:
            for f in [coveragerc, pyproject]:
                if f:
                    content = read_file_raw(f)
                    match = re.search(r'fail_under\s*=\s*(\d+)', content)
                    if match:
                        result["coverage"] = int(match.group(1))
                        break

        if result["framework"] == "pytest":
            result["test_command"] = "pytest"
            result["coverage_command"] = "pytest --cov=. --cov-report=xml --cov-fail-under=80"

    if language == "Node.js":
        pkg = find_file_anywhere(repo_path, "package.json")
        if pkg:
            try:
                data = json.loads(read_file_raw(pkg))
                scripts = data.get("scripts", {})
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}

                # Detect framework
                if "jest" in deps:
                    result["framework"] = "Jest"
                    result["unit"] = True
                elif "mocha" in deps:
                    result["framework"] = "Mocha"
                    result["unit"] = True
                elif "vitest" in deps:
                    result["framework"] = "Vitest"
                    result["unit"] = True

                # E2E tools
                if "cypress" in deps:
                    result["e2e"] = True
                    result["e2e_tool"] = "Cypress"
                elif "playwright" in deps:
                    result["e2e"] = True
                    result["e2e_tool"] = "Playwright"

                # Integration
                if "supertest" in deps:
                    result["integration"] = True

                result["test_command"] = scripts.get("test", "npm test")
                result["coverage_command"] = scripts.get(
                    "test:coverage",
                    "jest --coverage"
                )

                # Coverage threshold from jest config
                jest_config = data.get("jest", {})
                threshold = jest_config.get("coverageThreshold", {}).get("global", {})
                if threshold:
                    result["coverage"] = threshold.get("lines", None)

            except Exception:
                pass

    if language == "Java":
        pom = find_file_anywhere(repo_path, "pom.xml")
        if pom:
            result["framework"] = "JUnit"
            result["unit"] = True
            result["test_command"] = "mvn test"
            result["coverage_command"] = "mvn test jacoco:report"

    if language == "Go":
        go_files = find_files_by_extension(repo_path, ".go")
        for gf in go_files:
            if gf.endswith("_test.go"):
                result["unit"] = True
                result["framework"] = "Go Test"
                result["test_command"] = "go test ./..."
                result["coverage_command"] = "go test ./... -coverprofile=coverage.out"
                break

    return result
