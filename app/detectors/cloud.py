import os
from app.utils.file_utils import (
    read_file_safe, find_file_anywhere,
    find_files_by_extension, get_root_files
)


def detect_cloud(repo_path: str) -> dict:
    """Detect cloud provider, deployment target, strategy and registry without guesswork."""
    result = {
        "provider": None,
        "deployment_target": None,
        "deployment_strategy": None,
        "registry": None,
        "confidence": 0.0,
        "evidence": []
    }

    # Scan dependency and config files
    files_to_scan = [
        "requirements.txt", "package.json", "pom.xml",
        "build.gradle", "go.mod", "docker-compose.yml",
        "serverless.yml", "serverless.yaml",
        ".env.example", ".env.sample"
    ]
    combined = ""
    evidence_collected = []
    
    for f in files_to_scan:
        path = find_file_anywhere(repo_path, f)
        if path:
            content = read_file_safe(path)
            combined += content
            # Add simple evidence
            evidence_collected.append(f"Scanned configured file {f}")

    # Scan CI files
    for ci in [".github/workflows", ".gitlab-ci.yml", "Jenkinsfile", "azure-pipelines.yml"]:
        path = find_file_anywhere(repo_path, ci.split("/")[-1])
        if path:
            combined += read_file_safe(path)
            evidence_collected.append(f"Scanned CI/CD configuration {ci}")

    yaml_files = find_files_by_extension(repo_path, ".yaml") + \
                 find_files_by_extension(repo_path, ".yml")
    for yf in yaml_files[:15]:
        combined += read_file_safe(yf)

    # ---- AWS ----
    aws_kws = ["boto3", "aws-sdk", "amazonaws", "aws_access", "aws_secret", "aws_region", "cloudformation", "aws-actions"]
    detected_aws_kws = [kw for kw in aws_kws if kw in combined]
    
    if detected_aws_kws:
        result["provider"] = "AWS"
        result["registry"] = "ECR"
        result["confidence"] = 0.8
        result["evidence"].append(f"Detected AWS keywords in repo assets: {', '.join(detected_aws_kws)}")

        if "eks" in combined:
            result["deployment_target"] = "EKS"
            result["confidence"] = 0.95
            result["evidence"].append("Found 'eks' reference in configuration assets")
        elif "ecs" in combined or "fargate" in combined:
            result["deployment_target"] = "ECS"
            result["confidence"] = 0.95
            result["evidence"].append("Found 'ecs' or 'fargate' reference in assets")
        elif "lambda" in combined or "serverless" in combined:
            result["deployment_target"] = "Lambda"
            result["confidence"] = 0.95
            result["evidence"].append("Found 'lambda' reference in code/configs")
        elif "ec2" in combined:
            result["deployment_target"] = "EC2"
            result["confidence"] = 0.9
            result["evidence"].append("Found explicit 'ec2' reference in assets")
        else:
            # Do NOT guess EC2 by default.
            result["deployment_target"] = None

    # ---- GCP ----
    gcp_kws = ["google-cloud", "gcloud", "gcp", "firebase", "gcr.io", "gke", "cloud-run", "bigquery"]
    detected_gcp_kws = [kw for kw in gcp_kws if kw in combined]
    
    if detected_gcp_kws:
        result["provider"] = "GCP"
        result["registry"] = "GCR"
        result["confidence"] = 0.8
        result["evidence"].append(f"Detected GCP keywords in repo assets: {', '.join(detected_gcp_kws)}")

        if "gke" in combined:
            result["deployment_target"] = "GKE"
            result["confidence"] = 0.95
            result["evidence"].append("Found references to Google Kubernetes Engine (GKE)")
        elif "cloud-run" in combined:
            result["deployment_target"] = "Cloud Run"
            result["confidence"] = 0.95
            result["evidence"].append("Found explicit references to Google Cloud Run")
        else:
            result["deployment_target"] = None

    # ---- Azure ----
    azure_kws = ["azure", "microsoft", "azurewebsites", "aks", "acr", "azure-functions"]
    detected_azure_kws = [kw for kw in azure_kws if kw in combined]
    
    if detected_azure_kws:
        result["provider"] = "Azure"
        result["registry"] = "ACR"
        result["confidence"] = 0.8
        result["evidence"].append(f"Detected Azure keywords in repo assets: {', '.join(detected_azure_kws)}")

        if "aks" in combined:
            result["deployment_target"] = "AKS"
            result["confidence"] = 0.95
            result["evidence"].append("Found Google Kubernetes Service (AKS) references")
        elif "azure-functions" in combined or "functionapp" in combined:
            result["deployment_target"] = "Azure Functions"
            result["confidence"] = 0.95
            result["evidence"].append("Found references for Azure Functions app")
        else:
            result["deployment_target"] = None

    # ---- Serverless ----
    if find_file_anywhere(repo_path, "serverless.yml") or \
       find_file_anywhere(repo_path, "serverless.yaml"):
        result["deployment_target"] = "Serverless"
        result["confidence"] = 1.0
        result["evidence"].append("Found Serverless Framework configuration file (serverless.yml)")

    # ---- Deployment Strategy ----
    has_helm = bool(find_file_anywhere(repo_path, "Chart.yaml"))
    has_compose = bool(find_file_anywhere(repo_path, "docker-compose.yml") or
                       find_file_anywhere(repo_path, "docker-compose.yaml"))
    
    # Check for direct manifest Kind declarations
    has_k8s = False
    for yf in yaml_files[:10]:
        content = read_file_safe(yf)
        if "kind: deployment" in content or "kind: service" in content or "apiversion:" in content:
            has_k8s = True
            break

    if has_helm:
        result["deployment_strategy"] = "Helm"
        result["evidence"].append("Identified Helm chart configurations")
    elif has_k8s:
        result["deployment_strategy"] = "Kubernetes Manifests"
        result["evidence"].append("Identified Kubernetes manifest specifications")
    elif has_compose:
        result["deployment_strategy"] = "Docker Compose"
        result["evidence"].append("Identified Docker Compose files")
    elif find_file_anywhere(repo_path, "Dockerfile"):
        result["deployment_strategy"] = "Docker"
        result["evidence"].append("Identified Docker context files")
    else:
        result["deployment_strategy"] = None

    # Default registry if Dockerfile exists
    if not result["registry"] and find_file_anywhere(repo_path, "Dockerfile"):
        result["registry"] = "DockerHub"

    return result
