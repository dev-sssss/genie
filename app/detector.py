import os
import re
import json
from app.utils.file_utils import (
    read_file_safe, read_file_raw,
    find_file_anywhere, find_files_by_extension,
    find_files_by_name_pattern, folder_exists,
    get_root_files
)


def detect_language(repo_path: str) -> str:
    extension_map = {
        ".py": "Python", ".js": "Node.js", ".ts": "Node.js",
        ".java": "Java", ".go": "Go", ".rb": "Ruby", ".php": "PHP",
    }
    counts = {}
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'dist', 'build', '__pycache__', 'venv', '.venv', 'vendor', 'coverage')]
        for file in files:
            ext = os.path.splitext(file)[1]
            if ext in extension_map:
                lang = extension_map[ext]
                counts[lang] = counts.get(lang, 0) + 1

    root_files = get_root_files(repo_path)
    if "requirements.txt" in root_files or "pyproject.toml" in root_files or "setup.py" in root_files:
        counts["Python"] = counts.get("Python", 0) + 100
    if "package.json" in root_files and "requirements.txt" not in root_files:
        counts["Node.js"] = counts.get("Node.js", 0) + 100
    if "pom.xml" in root_files or "build.gradle" in root_files:
        counts["Java"] = counts.get("Java", 0) + 100
    if "go.mod" in root_files:
        counts["Go"] = counts.get("Go", 0) + 100
    return max(counts, key=counts.get) if counts else "unknown"


def detect_framework(repo_path: str, language: str) -> str:
    if language == "Python":
        for root, dirs, files in os.walk(repo_path):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for f in files:
                if f.startswith("requirements") and f.endswith(".txt"):
                    content = read_file_safe(os.path.join(root, f))
                    if "django" in content: return "Django"
                    if "fastapi" in content: return "FastAPI"
                    if "flask" in content: return "Flask"
        path = find_file_anywhere(repo_path, "pyproject.toml")
        if path:
            content = read_file_safe(path)
            if "django" in content: return "Django"
            if "fastapi" in content: return "FastAPI"
            if "flask" in content: return "Flask"
        for fname in ["setup.py", "setup.cfg"]:
            path = find_file_anywhere(repo_path, fname)
            if path:
                content = read_file_safe(path)
                if "django" in content: return "Django"
                if "fastapi" in content: return "FastAPI"
                if "flask" in content: return "Flask"

    if language == "Node.js":
        # Find the backend package.json (prefer server/ or backend/ over root in monorepos)
        pkg = _find_backend_package_json(repo_path)
        if pkg:
            content = read_file_safe(pkg)
            # Only return actual server frameworks, NOT libraries
            if '"express"' in content: return "Express"
            if '"@nestjs' in content: return "NestJS"
            if '"fastify"' in content: return "Fastify"
            if '"koa"' in content: return "Koa"
            if '"hapi"' in content or '"@hapi' in content: return "Hapi"
            if '"next"' in content: return "Next.js"
            # Check for raw http usage (no framework)
            js_files = find_files_by_extension(repo_path, ".js") + find_files_by_extension(repo_path, ".ts")
            for jf in js_files[:30]:
                jcontent = read_file_raw(jf)
                if 'http.createServer' in jcontent or 'createServer(' in jcontent:
                    return "Node HTTP Server"
            # If we have a package.json but no framework, it's a generic Node app
            return "unknown"

    if language == "Java":
        path = find_file_anywhere(repo_path, "pom.xml")
        if path:
            content = read_file_safe(path)
            if "spring-boot" in content or "springframework" in content:
                return "Spring Boot"
        path = find_file_anywhere(repo_path, "build.gradle")
        if path:
            content = read_file_safe(path)
            if "spring" in content: return "Spring Boot"

    if language == "Go":
        path = find_file_anywhere(repo_path, "go.mod")
        if path:
            content = read_file_safe(path)
            if "gin-gonic" in content: return "Gin"
            if "echo" in content: return "Echo"
    return "unknown"


def _find_backend_package_json(repo_path: str) -> str:
    """In monorepos, prefer server/backend package.json over root."""
    backend_dirs = ["server", "backend", "api", "service"]
    for d in backend_dirs:
        candidate = os.path.join(repo_path, d, "package.json")
        if os.path.exists(candidate):
            return candidate
    # Fall back to root package.json
    root_pkg = os.path.join(repo_path, "package.json")
    if os.path.exists(root_pkg):
        return root_pkg
    return find_file_anywhere(repo_path, "package.json")


def detect_libraries(repo_path: str, language: str) -> list:
    """Detect notable libraries (not frameworks) from dependency files."""
    libraries = []
    known_libs = {
        "Node.js": {
            "socket.io": "Socket.IO", "mongoose": "Mongoose",
            "sequelize": "Sequelize", "prisma": "Prisma",
            "typeorm": "TypeORM", "redis": "Redis",
            "bull": "Bull", "passport": "Passport",
            "jsonwebtoken": "JWT", "cors": "CORS",
            "helmet": "Helmet", "morgan": "Morgan",
            "multer": "Multer", "graphql": "GraphQL",
            "apollo-server": "Apollo Server",
        },
        "Python": {
            "celery": "Celery", "redis": "Redis",
            "sqlalchemy": "SQLAlchemy", "alembic": "Alembic",
            "pydantic": "Pydantic", "jwt": "JWT",
            "graphene": "Graphene",
        }
    }
    lib_map = known_libs.get(language, {})
    if not lib_map:
        return libraries

    if language == "Node.js":
        pkg = _find_backend_package_json(repo_path)
        if pkg:
            try:
                data = json.loads(read_file_raw(pkg))
                all_deps = list(data.get("dependencies", {}).keys()) + \
                           list(data.get("devDependencies", {}).keys())
                for dep in all_deps:
                    dep_lower = dep.lower()
                    if dep_lower in lib_map:
                        libraries.append(lib_map[dep_lower])
            except Exception:
                pass

    elif language == "Python":
        req = find_file_anywhere(repo_path, "requirements.txt")
        if req:
            content = read_file_raw(req).lower()
            for key, name in lib_map.items():
                if key in content:
                    libraries.append(name)

    return libraries


def detect_tests(repo_path: str, language: str) -> tuple:
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            if language == "Python":
                if file.startswith("test_") or file.endswith("_test.py"):
                    return True, "pytest"
            if language == "Node.js":
                if file.endswith(".test.js") or file.endswith(".spec.js") or file.endswith(".test.ts"):
                    return True, "Jest"
            if language == "Java":
                if file.endswith("Test.java"):
                    return True, "JUnit"
            if language == "Go":
                if file.endswith("_test.go"):
                    return True, "Go Test"
    return False, "unknown"


def detect_package_manager(repo_path: str, language: str) -> str:
    if language == "Python":
        if find_file_anywhere(repo_path, "requirements.txt"): return "pip"
        if find_file_anywhere(repo_path, "Pipfile"): return "pipenv"
        if find_file_anywhere(repo_path, "pyproject.toml"): return "poetry"
    if language == "Node.js":
        if find_file_anywhere(repo_path, "yarn.lock"): return "yarn"
        if find_file_anywhere(repo_path, "package-lock.json"): return "npm"
        if find_file_anywhere(repo_path, "package.json"): return "npm"
    if language == "Java":
        if find_file_anywhere(repo_path, "pom.xml"): return "maven"
        if find_file_anywhere(repo_path, "build.gradle"): return "gradle"
    if language == "Go":
        return "go mod"
    return "unknown"


def detect_makefile(repo_path: str) -> bool:
    return bool(find_file_anywhere(repo_path, "Makefile"))


def detect_ci(repo_path: str) -> tuple:
    github_workflows = os.path.join(repo_path, ".github", "workflows")
    if os.path.exists(github_workflows):
        files = os.listdir(github_workflows)
        if any(f.endswith(".yml") or f.endswith(".yaml") for f in files):
            return True, "GitHub Actions"
    if find_file_anywhere(repo_path, "Jenkinsfile"):
        return True, "Jenkins"
    if find_file_anywhere(repo_path, ".gitlab-ci.yml"):
        return True, "GitLab CI"
    circleci = os.path.join(repo_path, ".circleci", "config.yml")
    if os.path.exists(circleci):
        return True, "CircleCI"
    if find_file_anywhere(repo_path, ".travis.yml"):
        return True, "Travis CI"
    if find_file_anywhere(repo_path, "azure-pipelines.yml"):
        return True, "Azure Pipelines"
    return False, "none"


def detect_port(repo_path: str, language: str, framework: str) -> str:
    dockerfile = find_file_anywhere(repo_path, "Dockerfile")
    if dockerfile:
        content = read_file_raw(dockerfile)
        match = re.search(r'EXPOSE\s+(\d+)', content, re.IGNORECASE)
        if match:
            return match.group(1)
    compose = find_file_anywhere(repo_path, "docker-compose.yml") or \
              find_file_anywhere(repo_path, "docker-compose.yaml")
    if compose:
        content = read_file_raw(compose)
        match = re.search(r'["\']?(\d{4,5}):\d+', content)
        if match:
            return match.group(1)
    return None


def detect_health_endpoint(repo_path: str, language: str) -> str:
    health_patterns = ["/health", "/api/health", "/ping", "/status", "/healthz"]
    if language == "Python":
        py_files = find_files_by_extension(repo_path, ".py")
        for pf in py_files[:20]:
            content = read_file_raw(pf)
            for pattern in health_patterns:
                if f'"{pattern}"' in content or f"'{pattern}'" in content:
                    return pattern
    if language == "Node.js":
        js_files = find_files_by_extension(repo_path, ".js") + \
                   find_files_by_extension(repo_path, ".ts")
        for jf in js_files[:20]:
            content = read_file_raw(jf)
            for pattern in health_patterns:
                if f'"{pattern}"' in content or f"'{pattern}'" in content:
                    return pattern
    return None


def detect_env_variables(repo_path: str) -> list:
    env_vars = []
    for env_file in [".env.example", ".env.sample", ".env.template"]:
        path = find_file_anywhere(repo_path, env_file)
        if path:
            content = read_file_raw(path)
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    var_name = line.split("=")[0].strip()
                    if var_name:
                        env_vars.append(var_name)
            break
    return env_vars[:20]


def detect_secret_variables(env_variables: list) -> list:
    """From env vars list, identify which ones are likely secrets."""
    secret_keywords = [
        "secret", "key", "token", "password", "passwd",
        "pwd", "api_key", "auth", "credential", "private"
    ]
    return [
        v for v in env_variables
        if any(kw in v.lower() for kw in secret_keywords)
    ]


def detect_code_quality(repo_path: str, language: str) -> list:
    tools = []
    if language == "Python":
        if find_file_anywhere(repo_path, ".flake8") or \
           find_file_anywhere(repo_path, "setup.cfg"):
            tools.append("flake8")
        if find_file_anywhere(repo_path, ".pylintrc"):
            tools.append("pylint")
        pyproject = find_file_anywhere(repo_path, "pyproject.toml")
        if pyproject:
            content = read_file_safe(pyproject)
            if "black" in content: tools.append("black")
            if "isort" in content: tools.append("isort")
            if "mypy" in content: tools.append("mypy")
    if language == "Node.js":
        if find_file_anywhere(repo_path, ".eslintrc") or \
           find_file_anywhere(repo_path, ".eslintrc.js") or \
           find_file_anywhere(repo_path, ".eslintrc.json"):
            tools.append("eslint")
        if find_file_anywhere(repo_path, ".prettierrc") or \
           find_file_anywhere(repo_path, ".prettierrc.json"):
            tools.append("prettier")
    if language == "Java":
        pom = find_file_anywhere(repo_path, "pom.xml")
        if pom:
            content = read_file_safe(pom)
            if "checkstyle" in content: tools.append("checkstyle")
            if "spotbugs" in content: tools.append("spotbugs")
    return tools


def detect_coverage_threshold(repo_path: str, language: str) -> int:
    if language == "Python":
        for f in [".coveragerc", "setup.cfg", "pyproject.toml"]:
            path = find_file_anywhere(repo_path, f)
            if path:
                content = read_file_raw(path)
                match = re.search(r'fail_under\s*=\s*(\d+)', content)
                if match:
                    return int(match.group(1))
    if language == "Node.js":
        path = find_file_anywhere(repo_path, "jest.config.js") or \
               find_file_anywhere(repo_path, "jest.config.ts")
        if path:
            content = read_file_raw(path)
            match = re.search(r'lines["\']?\s*:\s*(\d+)', content)
            if match:
                return int(match.group(1))
    return None


def detect_microservices(repo_path: str) -> dict:
    result = {"is_monorepo": False, "services_count": 1, "service_names": []}
    for folder in ["services", "apps", "packages", "microservices"]:
        folder_path = os.path.join(repo_path, folder)
        if os.path.exists(folder_path):
            services = [
                d for d in os.listdir(folder_path)
                if os.path.isdir(os.path.join(folder_path, d))
            ]
            if len(services) > 1:
                result["is_monorepo"] = True
                result["services_count"] = len(services)
                result["service_names"] = services[:10]
                return result
    dockerfiles = find_files_by_name_pattern(repo_path, "Dockerfile")
    if len(dockerfiles) > 1:
        result["is_monorepo"] = True
        result["services_count"] = len(dockerfiles)
        result["service_names"] = [
            os.path.basename(os.path.dirname(d)) for d in dockerfiles
        ]
    return result


# ============================================================
# NEW: Execution Intelligence Functions
# ============================================================

def detect_build_commands(repo_path: str, language: str, framework: str) -> dict:
    """Detect actual build, test, start commands from scripts."""
    commands = {
        "build": None,
        "test": None,
        "start": None,
        "dev": None,
        "lint": None,
        "install": None,
    }

    # Node.js — read BACKEND package.json only (not frontend)
    if language == "Node.js":
        pkg = _find_backend_package_json(repo_path)
        if pkg:
            try:
                raw = read_file_raw(pkg)
                data = json.loads(raw)
                scripts = data.get("scripts", {})
                commands["build"] = scripts.get("build")
                commands["test"] = scripts.get("test")
                commands["start"] = scripts.get("start")
                commands["dev"] = scripts.get("dev")
                commands["lint"] = scripts.get("lint")
                commands["install"] = "npm install"
                
                # If the build command is a frontend tool (vite, react-scripts, etc),
                # it belongs to frontend, not backend. Set to None.
                if commands["build"]:
                    frontend_build_tools = ["vite", "react-scripts", "webpack", "next build", "nuxt", "parcel"]
                    if any(tool in commands["build"].lower() for tool in frontend_build_tools):
                        commands["build"] = None
            except Exception:
                pass

    # Python — detect from pyproject.toml / Makefile
    if language == "Python":
        commands["install"] = "pip install -r requirements.txt"
        if find_file_anywhere(repo_path, "pyproject.toml"):
            commands["install"] = "poetry install"
        if find_file_anywhere(repo_path, "Pipfile"):
            commands["install"] = "pipenv install"

        # Detect test command
        if find_file_anywhere(repo_path, "pytest.ini") or \
           find_file_anywhere(repo_path, "setup.cfg") or \
           find_file_anywhere(repo_path, "pyproject.toml"):
            commands["test"] = "pytest"
        elif find_file_anywhere(repo_path, "tox.ini"):
            commands["test"] = "tox"

        # Detect start command based on framework
        if framework == "FastAPI":
            commands["start"] = "uvicorn main:app --host 0.0.0.0 --port 8000"
        elif framework == "Django":
            commands["start"] = "python manage.py runserver 0.0.0.0:8000"
        elif framework == "Flask":
            commands["start"] = "flask run --host=0.0.0.0 --port=5000"

        # Detect build (Django collectstatic)
        if framework == "Django":
            commands["build"] = "python manage.py collectstatic --noinput"

    # Java
    if language == "Java":
        if find_file_anywhere(repo_path, "pom.xml"):
            commands["install"] = "mvn install"
            commands["build"] = "mvn package -DskipTests"
            commands["test"] = "mvn test"
            commands["start"] = "java -jar target/*.jar"
        elif find_file_anywhere(repo_path, "build.gradle"):
            commands["install"] = "gradle dependencies"
            commands["build"] = "gradle build -x test"
            commands["test"] = "gradle test"
            commands["start"] = "java -jar build/libs/*.jar"

    # Go
    if language == "Go":
        commands["install"] = "go mod download"
        commands["build"] = "go build -o app ."
        commands["test"] = "go test ./..."
        commands["start"] = "./app"

    # Override with Makefile targets if present
    makefile = find_file_anywhere(repo_path, "Makefile")
    if makefile:
        content = read_file_raw(makefile)
        if "build:" in content and not commands["build"]:
            commands["build"] = "make build"
        if "test:" in content and not commands["test"]:
            commands["test"] = "make test"
        if "run:" in content and not commands["start"]:
            commands["start"] = "make run"

    return commands


def detect_entrypoint(repo_path: str, language: str, framework: str) -> dict:
    """Detect main entrypoint file and startup command."""
    result = {"entrypoint": None, "startup_command": None}

    if language == "Python":
        # Check common entrypoint files
        for candidate in ["main.py", "app.py", "run.py", "server.py", "wsgi.py", "asgi.py"]:
            if find_file_anywhere(repo_path, candidate):
                result["entrypoint"] = candidate
                break

        if framework == "FastAPI":
            ep = result["entrypoint"] or "main.py"
            module = ep.replace(".py", "")
            result["startup_command"] = f"uvicorn {module}:app --host 0.0.0.0 --port 8000"
        elif framework == "Django":
            result["entrypoint"] = "manage.py"
            result["startup_command"] = "python manage.py runserver 0.0.0.0:8000"
        elif framework == "Flask":
            ep = result["entrypoint"] or "app.py"
            result["startup_command"] = f"python {ep}"

    if language == "Node.js":
        pkg = find_file_anywhere(repo_path, "package.json")
        if pkg:
            try:
                data = json.loads(read_file_raw(pkg))
                main = data.get("main", "index.js")
                result["entrypoint"] = main
                scripts = data.get("scripts", {})
                result["startup_command"] = scripts.get("start", f"node {main}")
            except Exception:
                result["entrypoint"] = "index.js"
                result["startup_command"] = "node index.js"

    if language == "Java":
        result["entrypoint"] = "src/main/java"
        result["startup_command"] = "java -jar target/*.jar"

    if language == "Go":
        result["entrypoint"] = "main.go"
        result["startup_command"] = "./app"

    return result


def detect_test_reality(repo_path: str, language: str) -> dict:
    """Deep test analysis — commands, dirs, integration, e2e."""
    result = {
        "test_command": None,
        "test_directories": [],
        "has_integration_tests": False,
        "has_e2e_tests": False,
    }

    # Find test directories
    test_dir_names = ["tests", "test", "__tests__", "spec", "e2e", "integration"]
    for tdir in test_dir_names:
        path = os.path.join(repo_path, tdir)
        if os.path.exists(path):
            result["test_directories"].append(tdir)
            if "integration" in tdir:
                result["has_integration_tests"] = True
            if "e2e" in tdir:
                result["has_e2e_tests"] = True

    # Check for e2e tools
    pkg = find_file_anywhere(repo_path, "package.json")
    pkg_test_script_exists = False
    if pkg:
        content = read_file_safe(pkg)
        if "cypress" in content or "playwright" in content or "selenium" in content:
            result["has_e2e_tests"] = True
        if "supertest" in content or "jest-integration" in content:
            result["has_integration_tests"] = True
        try:
            import json
            data = json.loads(read_file_raw(pkg))
            if "test" in data.get("scripts", {}):
                pkg_test_script_exists = True
        except Exception:
            pass

    # Find test files recursively (excluding generated directories)
    has_test_files = False
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'dist', 'build', '__pycache__', 'venv', '.venv')]
        for file in files:
            file_lower = file.lower()
            if "test" in file_lower or "spec" in file_lower:
                has_test_files = True
                break
        if has_test_files:
            break

    # Stop inventing test commands if no tests of any kind exist.
    if not (result["test_directories"] or has_test_files or pkg_test_script_exists):
        return result

    # Detect test command
    if language == "Python":
        if find_file_anywhere(repo_path, "pytest.ini") or \
           find_file_anywhere(repo_path, "pyproject.toml") or \
           has_test_files:
            dirs = " ".join(result["test_directories"]) or ""
            result["test_command"] = f"pytest {dirs}".strip()
            if not result["test_command"]:
                result["test_command"] = "pytest"

    if language == "Node.js" and pkg:
        try:
            data = json.loads(read_file_raw(pkg))
            scripts = data.get("scripts", {})
            if "test" in scripts:
                result["test_command"] = scripts["test"]
        except Exception:
            pass

    if language == "Java":
        if find_file_anywhere(repo_path, "pom.xml"):
            result["test_command"] = "mvn test"
        elif find_file_anywhere(repo_path, "build.gradle"):
            result["test_command"] = "gradle test"

    if language == "Go" and (has_test_files or result["test_directories"]):
        result["test_command"] = "go test ./... -v -coverprofile=coverage.out"

    return result


def detect_makefile_targets(repo_path: str) -> list:
    """Extract all targets from Makefile."""
    targets = []
    makefile = find_file_anywhere(repo_path, "Makefile")
    if makefile:
        content = read_file_raw(makefile)
        matches = re.findall(r'^([a-zA-Z][a-zA-Z0-9_-]*):', content, re.MULTILINE)
        targets = [m for m in matches if not m.startswith('.')]
    return targets
