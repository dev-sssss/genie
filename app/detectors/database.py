import os
from app.utils.file_utils import (
    read_file_safe, find_file_anywhere,
    find_files_by_name_pattern
)


def detect_databases(repo_path: str) -> list:
    """Detect databases used in the project."""
    detected = []

    # All possible dependency files to scan
    dep_files = [
        "requirements.txt", "requirements-dev.txt",
        "Pipfile", "pyproject.toml", "setup.py",
        "package.json", "pom.xml", "build.gradle",
        "go.mod", "Gemfile"
    ]

    combined_content = ""
    for dep_file in dep_files:
        path = find_file_anywhere(repo_path, dep_file)
        if path:
            combined_content += read_file_safe(path)

    # Also scan docker-compose.yml for database services
    compose_path = find_file_anywhere(repo_path, "docker-compose.yml") or \
                   find_file_anywhere(repo_path, "docker-compose.yaml")
    if compose_path:
        combined_content += read_file_safe(compose_path)

    # PostgreSQL
    if any(kw in combined_content for kw in [
        "psycopg2", "psycopg", "pg", "postgres",
        "postgresql", "asyncpg", "pg2"
    ]):
        detected.append("PostgreSQL")

    # MySQL
    if any(kw in combined_content for kw in [
        "mysql", "pymysql", "mysqlclient", "mysql2"
    ]):
        detected.append("MySQL")

    # MongoDB
    if any(kw in combined_content for kw in [
        "pymongo", "mongoose", "mongodb", "motor"
    ]):
        detected.append("MongoDB")

    # Redis
    if any(kw in combined_content for kw in [
        "redis", "aioredis", "ioredis"
    ]):
        detected.append("Redis")

    # SQLite
    if any(kw in combined_content for kw in [
        "sqlite", "sqlite3"
    ]):
        detected.append("SQLite")

    # Elasticsearch
    if any(kw in combined_content for kw in [
        "elasticsearch", "elastic"
    ]):
        detected.append("Elasticsearch")

    # Cassandra
    if any(kw in combined_content for kw in [
        "cassandra", "datastax"
    ]):
        detected.append("Cassandra")

    return detected
