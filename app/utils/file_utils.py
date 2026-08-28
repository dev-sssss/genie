import os


def read_file_safe(path: str) -> str:
    """Safely read a file and return its content in lowercase."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read().lower()
    except Exception:
        return ""


def read_file_raw(path: str) -> str:
    """Safely read a file and return its raw content (not lowercased)."""
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def find_file_anywhere(repo_path: str, filename: str) -> str:
    """Search for a file in root and all subfolders. Returns path if found."""
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'dist', 'build', '__pycache__', 'venv', '.venv', 'vendor', 'coverage')]
        if filename in files:
            return os.path.join(root, filename)
    return ""


def find_files_by_extension(repo_path: str, extension: str) -> list:
    """Find all files with a given extension recursively."""
    matches = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'dist', 'build', '__pycache__', 'venv', '.venv', 'vendor', 'coverage')]
        for file in files:
            if file.endswith(extension):
                matches.append(os.path.join(root, file))
    return matches


def find_files_by_name_pattern(repo_path: str, pattern: str) -> list:
    """Find all files whose name contains a pattern."""
    matches = []
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'dist', 'build', '__pycache__', 'venv', '.venv', 'vendor', 'coverage')]
        for file in files:
            if pattern.lower() in file.lower():
                matches.append(os.path.join(root, file))
    return matches


def folder_exists(repo_path: str, folder_name: str) -> bool:
    """Check if a folder exists anywhere in the repo."""
    for root, dirs, _ in os.walk(repo_path):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules', 'dist', 'build', '__pycache__', 'venv', '.venv', 'vendor', 'coverage')]
        if folder_name in dirs:
            return True
    return False


def get_root_files(repo_path: str) -> list:
    """Get list of files in root directory only."""
    try:
        return os.listdir(repo_path)
    except Exception:
        return []
