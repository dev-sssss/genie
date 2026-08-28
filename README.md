# 🔍 Repo Analyzer Service — PipelineGenie

Analyzes any public GitHub repo and detects its tech stack.

## 📦 What it detects
- Programming Language (Python, Node.js, Java, Go)
- Framework (Django, FastAPI, Express, Spring Boot, Gin)
- Docker (Dockerfile present or not)
- Tests (pytest, Jest, JUnit, Go Test)
- Package Manager (pip, npm, maven, gradle)
- Makefile presence

## 🚀 Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start server
uvicorn app.main:app --reload
```

## 🧪 Test the API

Open browser: http://localhost:8000/docs

Or use curl:
```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/django/django"}'
```

## 🐳 Run with Docker

```bash
docker build -t repo-analyzer .
docker run -p 8000:8000 repo-analyzer
```

## ✅ Health Check (for Kubernetes)

```bash
curl http://localhost:8000/health
```
