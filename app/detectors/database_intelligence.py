import os
from app.utils.file_utils import (
    read_file_safe, find_file_anywhere,
    find_files_by_extension
)


def detect_database_intelligence(repo_path: str, language: str) -> dict:
    """Deep database analysis - type, migration tool, migrations."""
    result = {
        "detected": [],
        "primary": None,
        "migration_tool": None,
        "has_migrations": False,
        "migration_command": None,
        "cache": None,
        "message_queue": None
    }

    # Collect all dependency content
    dep_files = [
        "requirements.txt", "package.json", "pom.xml",
        "build.gradle", "go.mod", "docker-compose.yml"
    ]
    combined = ""
    for f in dep_files:
        path = find_file_anywhere(repo_path, f)
        if path:
            combined += read_file_safe(path)

    # Database detection
    db_keywords = {
        "PostgreSQL": ["psycopg2", "psycopg", "pg", "postgres", "asyncpg"],
        "MySQL": ["mysql", "pymysql", "mysqlclient", "mysql2"],
        "MongoDB": ["pymongo", "mongoose", "mongodb", "motor"],
        "SQLite": ["sqlite", "sqlite3"],
        "Redis": ["redis", "aioredis", "ioredis"],
        "Elasticsearch": ["elasticsearch", "elastic"],
        "Cassandra": ["cassandra", "datastax"],
        "DynamoDB": ["dynamodb", "boto3"],
    }

    for db, keywords in db_keywords.items():
        if any(kw in combined for kw in keywords):
            result["detected"].append(db)

    # Set primary database (first non-cache)
    cache_dbs = ["Redis", "Elasticsearch"]
    queue_dbs = ["RabbitMQ", "Kafka"]

    for db in result["detected"]:
        if db == "Redis":
            result["cache"] = "Redis"
        elif db in queue_dbs:
            result["message_queue"] = db
        elif not result["primary"] and db not in cache_dbs:
            result["primary"] = db

    # Migration tool detection
    if language == "Python":
        if find_file_anywhere(repo_path, "alembic.ini") or \
           find_file_anywhere(repo_path, "migrations"):
            result["migration_tool"] = "alembic"
            result["has_migrations"] = True
            result["migration_command"] = "alembic upgrade head"
        elif find_file_anywhere(repo_path, "manage.py"):
            # Django migrations
            result["migration_tool"] = "django"
            result["has_migrations"] = True
            result["migration_command"] = "python manage.py migrate"

    if language == "Node.js":
        pkg = find_file_anywhere(repo_path, "package.json")
        if pkg:
            content = read_file_safe(pkg)
            if "typeorm" in content:
                result["migration_tool"] = "typeorm"
                result["has_migrations"] = True
                result["migration_command"] = "typeorm migration:run"
            elif "sequelize" in content:
                result["migration_tool"] = "sequelize"
                result["has_migrations"] = True
                result["migration_command"] = "sequelize db:migrate"
            elif "prisma" in content:
                result["migration_tool"] = "prisma"
                result["has_migrations"] = True
                result["migration_command"] = "prisma migrate deploy"
            elif "knex" in content:
                result["migration_tool"] = "knex"
                result["has_migrations"] = True
                result["migration_command"] = "knex migrate:latest"

    if language == "Java":
        pom = find_file_anywhere(repo_path, "pom.xml")
        if pom:
            content = read_file_safe(pom)
            if "flyway" in content:
                result["migration_tool"] = "flyway"
                result["has_migrations"] = True
                result["migration_command"] = "mvn flyway:migrate"
            elif "liquibase" in content:
                result["migration_tool"] = "liquibase"
                result["has_migrations"] = True
                result["migration_command"] = "mvn liquibase:update"

    return result
