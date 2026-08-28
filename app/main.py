from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from app.models import AnalyzeRequest, AnalyzeResponse, HealthResponse, GeneratePipelineRequest, FixPipelineRequest, GenerateDockerRequest, ChatRequest, ChatResponse
from app.analyzer import analyze_repo
from app.pipeline_generator import PipelineGeneratorEngine
from app.pipeline_templates import (
    get_platform_prompt_block,
    get_manifest_prompt_block,
    PLATFORM_FILES,
    PLATFORM_REQUIRED_KEYS,
)
import json
import os
import re
import yaml
from app.template_engine import TemplateEngine

MANDATORY_PRE_GENERATION_VERIFICATION_GATES = """
=== MANDATORY PRE-GENERATION VERIFICATION GATES ===
Before finalizing any Dockerfile or CI/CD pipeline, verify EACH of the following.
Do not skip any gate. Record PASS/FAIL with a one-line justification for each in
the audit notes. If a gate fails, fix the output before returning it — do not
return a failing artifact with a note explaining the failure.

GATE 1 — FILE COMPLETENESS
Never COPY individual named source files (e.g. `COPY backend/server.js ./`)
unless repo_analysis.json has explicitly enumerated every file the entrypoint
imports and confirmed no other local modules exist. Default to copying the
entire application directory (`COPY backend/ ./`). Cherry-picking files is only
acceptable when the analyser proves the app is single-file.

GATE 2 — ONE PROCESS PER CONTAINER
Each Dockerfile packages exactly one service. If the repo has multiple
deployable tiers (backend + frontend, etc.), generate separate Dockerfiles and
note in the implementation plan that they run as separate containers. Never
write a custom multi-process entrypoint script bundling unrelated services
into one image unless the user explicitly requested a combined container.

GATE 3 — NO DEPRECATED OR INVALID FLAGS
Banned: `npm ci --only=production` (deprecated — use `--omit=dev`),
`npm install --frozen-lockfile` (this is a Yarn flag, not valid npm — use
`npm ci` instead). Before emitting any package-manager command, verify it
against current syntax for that exact package manager, not older convention.

GATE 4 — PORT CONSISTENCY
Cross-check every hardcoded PORT / EXPOSE / CONTAINER_PORT value against
repo_analysis.json's detected backend.port or .env.example default. If they
don't match, use the detected value. If no detected value exists, state the
assumed default explicitly in the audit notes rather than silently guessing.

GATE 5 — DEPLOY TRIGGER SAFETY
Any job that deploys to a live environment, pushes to a registry, or runs
infrastructure-changing commands MUST carry an explicit `if:` condition
restricting it to the intended trigger (typically
`github.event_name == 'push' && github.ref == 'refs/heads/main'`). A workflow
triggering on both push and pull_request with an unguarded deploy job is an
automatic FAIL.

GATE 6 — ARTIFACT CHAIN CONSISTENCY
Trace every built artifact from creation to consumption. If an image is
built, confirm it is actually pushed to a registry the deploy stage can reach
(`push: true` whenever a downstream job depends on registry availability;
matching tag, matching registry). If credentials are configured for one
runner (e.g. Docker Hub login on the CI runner), confirm the actual consuming
command (e.g. `docker pull` executed via SSH on a remote host) also has
access to that same authentication — logging in on the wrong machine is a FAIL.

GATE 7 — ROLLBACK MUST RESTORE SERVICE
A rollback stage must end with the service running in a known-good state —
never merely stop/remove the failing container and exit with "manual
intervention required." If restoring a previous version requires a snapshot
mechanism (previous image tag, commit SHA, etc.), generate that mechanism as
part of the deploy stage rather than assuming it already exists.

GATE 8 — HEALTHCHECK TOOL MATCHES TARGET
Match verification tooling to the actual deployment target. Do not reuse
Kubernetes-native readiness actions/kubectl wait for non-Kubernetes targets.
For plain HTTP endpoints on VMs/Docker hosts, use a simple curl/wget retry
loop unless the target genuinely runs an orchestrator that requires otherwise.

If any gate cannot be verified due to missing information in repo_analysis.json,
say so explicitly in the audit notes rather than assuming a safe default silently.
=== END VERIFICATION GATES ===
"""

app = FastAPI(
    title="PipelineGenie - Repo Analyzer Service",
    description="Analyzes a GitHub repo and detects language, framework, docker, tests, and more.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Dependency Injections --- #
from fastapi import Depends, HTTPException
from app.database import get_db
from sqlalchemy.orm import Session
from app.models import User, UserSignup, UserLogin, Token, OTPVerifyRequest, OTPResponse, Chat, Message, ChatCreate, ChatResponse, ChatListResponse, MessageCreate, MessageResponse, ChatMessage
from app.auth import get_current_user, create_access_token, get_password_hash, verify_password
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse
from authlib.integrations.starlette_client import OAuth
from starlette.config import Config
import os

app.add_middleware(SessionMiddleware, secret_key="super_secret_genie_key_override_me")

# Setup OAuth
config_data = {
    'GOOGLE_CLIENT_ID': os.getenv('GOOGLE_CLIENT_ID', ''),
    'GOOGLE_CLIENT_SECRET': os.getenv('GOOGLE_CLIENT_SECRET', '')
}
starlette_config = Config(environ=config_data)
oauth = OAuth(starlette_config)
oauth.register(
    name='google',
    server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
    client_kwargs={'scope': 'openid email profile'},
)

# --- Auth Routes --- #
import random
import time

# Global simulated Sandbox OTP storage
OTP_STORE = {}

import smtplib
from email.message import EmailMessage

import socket
import logging
import re
import ssl
import smtplib
from email.message import EmailMessage
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, List

logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(name)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("genie.smtp")

class TestEmailRequest(BaseModel):
    email: EmailStr

def validate_smtp_env() -> Dict[str, Any]:
    import os
    host = os.getenv("SMTP_HOST", "").strip()
    port_str = os.getenv("SMTP_PORT", "").strip()
    email = os.getenv("SMTP_EMAIL", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    
    errors = []
    if not host: errors.append("SMTP_HOST is missing or empty")
    if not email: errors.append("SMTP_EMAIL is missing or empty")
    if not password: errors.append("SMTP_PASSWORD is missing or empty")
    
    port = None
    if not port_str:
        errors.append("SMTP_PORT is missing or empty")
    else:
        try:
            port = int(port_str)
            if port not in [25, 465, 587, 8025, 2525]:
                logger.warning(f"Using non-standard SMTP port: {port}")
        except ValueError:
            errors.append(f"SMTP_PORT '{port_str}' is not a valid integer")
            
    email_regex = re.compile(r"^[^@]+@[^@]+\.[^@]+$")
    if email and not email_regex.match(email):
        errors.append(f"SMTP_EMAIL '{email}' is strictly invalid.")

    if errors:
        logger.error(f"Environment Verification Failed: {'; '.join(errors)}")
        raise ValueError(f"Environment Verification Failed: {'; '.join(errors)}")
        
    return {"host": host, "port": port, "email": email, "password": password}


def dispatch_otp_email(to_email: str, code: str, is_test: bool = False):
    import time
    start_time = time.time()
    try:
        config = validate_smtp_env()
    except ValueError as e:
        logger.error(f"Cannot dispatch email to {to_email}. Root Cause: {str(e)}")
        if is_test: raise e
        return

    logger.info(f"Targeting SMTP Dispatch for {to_email} via {config['host']}:{config['port']}")
    
    msg = EmailMessage()
    msg.set_content(f"This is the verification code. Copy and paste the OTP code to verify your account:\n\nOTP Code: {code}")
    msg['Subject'] = 'Sensetronix Authorization Code' if not is_test else 'Sensetronix.ai OTP Verification'
    msg['From'] = config['email']
    msg['To'] = to_email

    server = None
    try:
        server = smtplib.SMTP(config['host'], config['port'], timeout=10.0)
        server.set_debuglevel(1)
        
        server.ehlo()
        
        if server.has_extn('STARTTLS'):
            logger.info("STARTTLS enabled on remote host. Securing stream...")
            context = ssl.create_default_context()
            server.starttls(context=context)
            server.ehlo()
        else:
            logger.warning("Remote Server lacks STARTTLS support. Authenticating over raw TCP plaintext!")
            
        logger.info(f"Authenticating as {config['email']}...")
        server.login(config['email'], config['password'])
        
        server.send_message(msg)
        elapsed = time.time() - start_time
        logger.info(f"Successfully bridged dispatch to {to_email} in {elapsed:.2f}s")
        
    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"Authentication Rejected by {config['host']}. [Code {e.smtp_code}]: {e.smtp_error.decode(errors='ignore')}")
        if is_test: raise e
    except smtplib.SMTPSenderRefused as e:
        logger.error(f"Sender Identity Rejected by {config['host']}. Sender '{e.sender}' [Code {e.smtp_code}]: {e.smtp_error.decode(errors='ignore')}")
        if is_test: raise e
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"Recipient Identity Rejected by {config['host']}. Recipient '{to_email}'.")
        if is_test: raise e
    except smtplib.SMTPConnectError as e:
        logger.error(f"Host Disconnection error while bridging. Active firewall filter? {str(e)}")
        if is_test: raise e
    except smtplib.SMTPDataError as e:
        logger.error(f"SMTP Data Exception during payload transit: [Code {e.smtp_code}]: {e.smtp_error.decode(errors='ignore')}")
        if is_test: raise e
    except socket.timeout:
        logger.error("TCP Timeout hit while connecting to SMTP layer.")
        if is_test: raise
    except socket.gaierror as e:
        logger.error(f"DNS resolution failure for SMTP Host '{config['host']}': {str(e)}")
        if is_test: raise e
    except smtplib.SMTPServerDisconnected:
        logger.error("Disconnected forcibly")
        if is_test: raise e
    except Exception as e:
        logger.error(f"Massive Unhandled Exception during Mail Processing: {type(e).__name__} -> {str(e)}")
        if is_test: raise e
    finally:
        if server:
            try:
                server.quit()
            except Exception:
                pass


@app.get("/api/system/email-health")
def api_email_health():
    try:
        config = validate_smtp_env()
    except Exception as e:
        return {"status": "degraded", "error": f"Env Validation: {str(e)}"}
        
    dns_resolves = False
    tls_supported = False
    
    try:
        socket.gethostbyname(config['host'])
        dns_resolves = True
    except Exception as e:
        return {"status": "error", "error": f"DNS failure: {str(e)}"}
        
    try:
        with smtplib.SMTP(config['host'], config['port'], timeout=5.0) as server:
            server.ehlo()
            tls_supported = server.has_extn('STARTTLS')
    except Exception as e:
        return {"status": "error", "error": f"Port reachable but SMTP proxy failed. TCP Block? {str(e)}"}
        
    return {
        "status": "online",
        "host": config['host'],
        "port": config['port'],
        "sender_mapped": config['email'],
        "checks": {
            "dns": dns_resolves,
            "tls_support": tls_supported
        }
    }

@app.post("/api/system/test-email")
def api_test_email(req: TestEmailRequest):
    import random
    try:
        code = f"{random.randint(100000, 999999)}"
        dispatch_otp_email(req.email, code, is_test=True)
        return {"status": "success", "message": f"Test payload dispatched successfully. Check terminal for packet outputs."}
    except Exception as e:
        return {"status": "failed", "error": str(e), "exception": type(e).__name__}

@app.post("/api/auth/signup", response_model=OTPResponse)
def signup(user: UserSignup, db: Session = Depends(get_db)):
    email_clean = user.email.strip().lower()
    db_user = db.query(User).filter(User.email == email_clean).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered. Please log in directly.")
    
    code = f"{random.randint(100000, 999999)}"
    OTP_STORE[email_clean] = {
        "code": code,
        "password": user.password,
        "expires_at": time.time() + 600
    }
    
    try:
        dispatch_otp_email(email_clean, code, is_test=True)
    except Exception as e:
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=500, content={"success": False, "message": "Unable to send OTP email"})
    
    return OTPResponse(success=True, message="OTP sent successfully", detail="OTP verification required. Code has been physically dispatched.", email=email_clean)

@app.post("/api/auth/login")
def login(user: UserLogin, db: Session = Depends(get_db)):
    email_clean = user.email.strip().lower()
    db_user = db.query(User).filter(User.email == email_clean).first()
    if not db_user:
        # User not found -> prompt user to sign up or trigger signup OTP
        raise HTTPException(status_code=404, detail="Account not found. Please create an account first.")
    
    if not verify_password(user.password, db_user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")
    
    access_token = create_access_token(data={"sub": email_clean})
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/auth/verify-otp")
def verify_otp(req: OTPVerifyRequest, db: Session = Depends(get_db)):
    email_clean = req.email.strip().lower()
    record = OTP_STORE.get(email_clean)
    
    if not record:
        raise HTTPException(status_code=400, detail="No OTP requested or OTP has expired")
    
    if time.time() > record["expires_at"]:
        del OTP_STORE[email_clean]
        raise HTTPException(status_code=400, detail="OTP expired")
    
    if record["code"] != req.code.strip():
        raise HTTPException(status_code=401, detail="Invalid OTP code")
    
    # Check if user was already in DB, if not create now upon verified OTP
    db_user = db.query(User).filter(User.email == email_clean).first()
    if not db_user:
        raw_password = record.get("password")
        if raw_password:
            hashed_pwd = get_password_hash(raw_password)
            new_user = User(email=email_clean, hashed_password=hashed_pwd)
            db.add(new_user)
            db.commit()
            db.refresh(new_user)
    
    del OTP_STORE[email_clean]
    access_token = create_access_token(data={"sub": email_clean})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/chats", response_model=List[ChatListResponse])
def get_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chats = db.query(Chat).filter(Chat.user_id == current_user.id).order_by(Chat.updated_at.desc()).all()
    return chats

@app.post("/api/chats", response_model=ChatListResponse)
def create_chat(data: ChatCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = Chat(user_id=current_user.id, title=data.title)
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat

@app.get("/api/chats/{chat_id}", response_model=ChatResponse)
def get_chat(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = db.query(Message).filter(Message.chat_id == chat.id).order_by(Message.created_at.asc()).all()
    
    return ChatResponse(
        id=chat.id,
        title=chat.title,
        updated_at=chat.updated_at,
        messages=[MessageResponse(id=m.id, role=m.role, content=m.content, reasoning_details=m.reasoning_details, created_at=m.created_at) for m in messages]
    )

@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if chat:
        db.delete(chat)
        db.commit()
    return {"status": "success"}

@app.get("/api/auth/google/login")
async def google_login(request: Request):
    if not os.getenv('GOOGLE_CLIENT_ID'):
        raise HTTPException(status_code=501, detail="Google SSO requires external Server Configuration. Please configure your CLIENT_ID and CLIENT_SECRET in backend infrastructure.")
    redirect_uri = request.url_for('google_callback')
    return await oauth.google.authorize_redirect(request, redirect_uri)

@app.get("/api/auth/google/callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"OAuth verification failed: {str(e)}")
        
    userinfo = token.get('userinfo')
    if not userinfo:
        raise HTTPException(status_code=400, detail="Failed to fetch user info")
        
    email = userinfo.get("email")
    db_user = db.query(User).filter(User.email == email).first()
    if not db_user:
        db_user = User(email=email, hashed_password="GOOGLE_OAUTH_USER_BLOCKED")
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
    access_token = create_access_token(data={"sub": db_user.email})
    HTML = f"""
    <html>
        <body>
            <script>
                localStorage.setItem("genie_auth_token", "{access_token}");
                window.location.href = "/";
            </script>
        </body>
    </html>
    """
    return HTMLResponse(content=HTML)

# In-memory storage for heuristics cache
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/landing.html")

@app.get("/pipeline")
def read_pipeline():
    return FileResponse("static/pipeline.html")

@app.get("/docker")
def read_docker():
    return FileResponse("static/docker.html")

@app.get("/chat")
def read_chat():
    return FileResponse("static/chat.html")


@app.get("/hyperspeed.js", tags=["static"])
def read_hyperspeed():
    return FileResponse("static/hyperspeed.js", media_type="application/javascript")


@app.get("/health", response_model=HealthResponse)
def health_check():
    return HealthResponse(status="healthy", service="repo-analyzer-service")


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest, current_user: str = Depends(get_current_user)):
    if not request.repo_url.startswith("https://github.com"):
        raise HTTPException(status_code=400, detail="Only GitHub URLs are supported.")

    try:
        result = analyze_repo(request.repo_url, request.github_token)
        return result
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")


from app.rules import ConfigurationValidator, RulesEngine
from app.validators import PipelineValidators

def _validate_generated_output(platform: str, filename: str, content: str, spec: dict, analysis: dict, rules: dict) -> list:
    """Returns a list of validation error strings using the 10-stage architecture Validators."""
    runtime = analysis.get("backend", {}).get("language", "") or analysis.get("frontend", {}).get("language", "")
    deployment_target = spec.get("deployment_target", "")
    # Combine old YAML structural guard with new validators
    errors = PipelineValidators.run_all(content, deployment_target, rules, runtime)
    
    if platform != "Jenkins" and "kind" in content and "apiVersion" in content and "kubernetes" not in deployment_target.lower():
         errors.append("Output uses a Kubernetes-style scheme inappropriately.")

    # Companion Rule 16 check: Warn if OIDC / id-token: write is granted without downstream consumption
    if "id-token: write" in content or "configure-aws-credentials" in content:
        aws_actions = ["aws s3", "aws ecs", "aws ecr", "aws lambda", "aws secretsmanager", "aws ssm", "kubectl"]
        has_real_use = any(act in content.lower() for act in aws_actions)
        if not has_real_use and "sts get-caller-identity" in content:
            # Identity check only without action
            pass  # Warning handled via warnings if desired
    return errors


def _missing_requested_manifests(spec: dict, generated_files: list) -> list:
    """Returns human-readable warnings for manifest types the user requested
    in the wizard but that never showed up in generated_files. Non-fatal —
    the pipeline itself may still be correct — but this must be visible
    instead of silently dropped, which is what happened before."""
    docker_cfg = spec.get("docker_configurations", {}) or {}
    k8s_cfg = spec.get("kubernetes", {}) or {}
    infra_cfg = spec.get("infrastructure", {}) or {}
    gen_cfg = spec.get("generate_manifests", {}) or {}
    paths = [f.get("path", "").lower() for f in generated_files]

    checks = [
        (docker_cfg.get("generate_dockerfile") or gen_cfg.get("dockerfile"),
         "Dockerfile", lambda p: "dockerfile" in p),
        (docker_cfg.get("generate_compose") or gen_cfg.get("docker_compose"),
         "docker-compose.yml", lambda p: "compose" in p),
        (infra_cfg.get("terraform") or gen_cfg.get("terraform"),
         "Terraform files", lambda p: p.endswith(".tf")),
        (k8s_cfg.get("generate_manifests") or gen_cfg.get("kubernetes"),
         "Kubernetes manifests", lambda p: "k8s" in p or "kubernetes" in p),
        (k8s_cfg.get("generate_helm") or gen_cfg.get("helm_charts"),
         "Helm chart", lambda p: "chart" in p or "helm" in p),
    ]

    warnings = []
    for requested, label, matcher in checks:
        if requested and not any(matcher(p) for p in paths):
            warnings.append(
                f"{label} was requested in the wizard but not found in the "
                "generated output — check generated_files manually."
            )
    return warnings


def _call_llm(api_key: str, system_prompt: str, user_message: str, model_target: str = "x-ai/grok-4.6") -> str:
    import requests
    payload = {
        "model": model_target,
        "max_tokens": 8192,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    }
    if any(k in model_target for k in ["kimi-k3", "gemini", "grok", "deepseek"]):
        # Cap reasoning effort to prevent multi-minute timeouts while preserving quality
        payload["reasoning"] = {
            "enabled": True,
            "max_tokens": 800
        }
        payload["messages"][0]["content"] += "\n\nSPEED & QUALITY DIRECTIVE: Respond directly with the required JSON structure immediately. Keep internal reasoning concise (under 500 tokens). Do not regenerate full explanations before code."
        
    headers = {
        "Authorization": f"Bearer {api_key}", 
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:8088",
        "X-Title": "PipelineGenie"
    }
    resp = requests.post(
        "https://openrouter.ai/api/v1/chat/completions",
        headers=headers, json=payload, timeout=300,
    )
    resp.raise_for_status()
    resp_message = resp.json()["choices"][0]["message"]
    raw = (resp_message.get("content") or "").strip()

    if not raw:
        reasoning = resp_message.get("reasoning") or ""
        if not reasoning and resp_message.get("reasoning_details"):
            try:
                reasoning = resp_message["reasoning_details"][0].get("text", "")
            except Exception:
                pass
        
        if reasoning:

            json_match = re.search(r'```json\n(.*?)\n```', reasoning, re.DOTALL | re.IGNORECASE)
            if json_match:
                raw = json_match.group(1).strip()
            else:
                yaml_match = re.search(r'```(?:yaml|yml)\n(.*?)\n```', reasoning, re.DOTALL | re.IGNORECASE)
                if yaml_match:
                    raw = yaml_match.group(1).strip()
                else:
                    raw = reasoning.strip()

    if raw.startswith("```"):
        first_newline = raw.find("\n")
        if first_newline != -1:
            raw = raw[first_newline + 1:]
    if raw.endswith("```"):
        raw = raw[:-3].strip()

    return raw


@app.post("/generate-pipeline")
def generate_pipeline(request: GeneratePipelineRequest, current_user: str = Depends(get_current_user)):
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or api_key.lower() == "your_openrouter_api_key_here":
        raise HTTPException(status_code=500, detail="Missing OPENROUTER_API_KEY in environment/env file")

    # Mappings to align frontend labels with database exact keys
    pm = {
        "GitHub Actions": "github_actions",
        "GitLab CI": "gitlab_ci",
        "Azure DevOps": "azure_devops",
        "CircleCI": "circleci",
        "Jenkins": "jenkins",
        "Bitbucket Pipelines": "bitbucket"
    }

    # Extract UI spec copy
    spec = dict(request.spec)
    ci_platform_raw = spec.get("pipeline_tool") or spec.get("cicd_platform") or "GitHub Actions"
    
    # We maintain cicd_platform for internal consistency
    spec["cicd_platform"] = pm.get(ci_platform_raw, ci_platform_raw.lower().replace(" ", "_"))
    spec["pipeline_tool"] = spec["cicd_platform"]  # Keep both in sync for the LLM prompt
    
    # Pre-Generation Configuration Validation
    from app.rules import ConfigurationValidator
    validator = ConfigurationValidator(request.analysis, dict(request.spec))
    validation_errors = validator.validate()
    if validation_errors:
        raise HTTPException(status_code=422, detail="Configuration Validation Failed:\n" + "\n".join(validation_errors))

    # Values might be things like "Node.js (NPM)" -> "node_npm_build"
    # To keep it simple, we use logic depending on key names or rely on exactly identical keys if changed in pipeline.html in V2.
    expected_filename = PLATFORM_FILES.get(ci_platform_raw, "pipeline.yml")

    system_prompt = """You are DevOps Pipeline Architect AI, a Principal DevOps Engineer with 
expertise in enterprise CI/CD systems, cloud platforms, deployment automation, and 
Infrastructure as Code.

Your sole responsibility is to generate WORLD-CLASS, production-ready CI/CD pipeline code 
that is technically correct, executable, secure, heavily documented, and natively optimized. 
The generated scripts must surpass basic functionality and immediately be fit for Enterprise Production.

CRITICAL ENTERPRISE DEVOPS RULES YOU MUST ENFORCE:
- Rule 1: Zero-Trust Security. Strictly enforce `permissions: read-all` in Actions, unless specifically deploying. Leverage short-lived OIDC tokens. Require explicit dependency vulnerability auditing (e.g., SAST/DAST integrations) and hard-fail on secrets in code.
- Rule 2: Advanced Deterministic Caching. You MUST natively implement robust layer/dependency caching across parallel jobs. Hash lockfiles (e.g. `hashFiles('package-lock.json')` or `.m2` checksums) to eliminate redundant downloads and slash build times.
- Rule 3: Production-Grade Reliability. Mandate retries/fail-safes for fragile network steps, enforce strict SLA timeouts on jobs (`timeout-minutes: 15`), and implement rollback logic that automatically executes on deployment failure.
- Rule 4: Explicit Documentation. Add extensive inline YAML comments justifying *why* the pipeline is configured this way. Focus on long-term maintainability for the user.
- Rule 5: Build-Once, Deploy-Many. The pipeline must NEVER rebuild artifacts after the build stage. If a container/binary is created in 'Build', subsequent test/deployment steps must download that artifact securely instead of running `npm run build` again.
- Rule 6: Rollback accuracy. Rollbacks must correspond exactly to the deployment strategy (e.g. using `kubectl rollout undo` if K8s, or proper `docker` logic if host). Remove unused templates fully.
- Rule 7: Strict adherence to user config. If the user disabled PR triggers or certain stages, DO NOT generate them.
- Rule 8: No hardcoded conditional booleans like `[ "true" = "true" ]`.
- Rule 9: The cloud_provider context MUST be gracefully acknowledged natively (e.g. `aws sts get-caller-identity`).
- Rule 10: If a testing framework is executed (`pytest`, `jest`), add directory fallback guards so the pipeline does not critically fail with "no tests found" exit codes.
- Rule 11: Gate Enforcement. Every quality/security/test/lint gate must be traced for actual enforcement. NEVER allow `|| true`, `continue-on-error: true`, or `|| exit 0` to swallow a non-zero exit code unless the user explicitly requested a soft-fail. A gate that cannot fail is a false sense of security.
- Rule 12: Credential Consumer Verification. Every authentication step (cloud OIDC, registry login, secret fetch) MUST have a downstream consuming job/step. If no step uses it, DO NOT include the auth step.

You are NOT a generic chatbot. You MUST generate flawless automation blueprints without missing any details.
You are NOT a generic chatbot.
You are NOT allowed to guess.
You are NOT allowed to invent deployment strategies.
You are NOT allowed to assume a project's structure — a repo-analyser service has 
already inspected the repository, and you must treat its output as ground truth.
You must generate deterministic pipelines based only on the provided template database, 
the user configuration, and the ANALYSER JSON (repo_analysis.json).

────────────────────────────────────────────

PRIMARY OBJECTIVE

Your task consists of seven phases. Never skip any phase, and never skip ahead.

Phase 0 — Ingest & Cross-Validate the Analyser Output
Phase 0.5 — Cross-Reference Pass (Check server-likelihood, keyword-noise, build-output modes, existing CI/CD, gate-enforcement, and credential-usage)
Phase 1 — Determine the correct pipeline template from the Pipeline Database (Brain Context)
Phase 2 — Interpret the user's configuration JSON
Phase 3 — Pre-Generation Audit (Verify compatibility, paths, secrets, and template availability BEFORE code generation)
Phase 4 — Generate the pipeline by combining template + config + validated analyser facts
Phase 5 — Verify the generated outputs (post-generation stage-by-stage audit)

────────────────────────────────────────────

PHASE 0 — INGEST & CROSS-VALIDATE THE ANALYSER OUTPUT

A file named "repo_analysis.json" is provided by an upstream repo-analyser service. 
It contains fields such as: architecture (frontend_path, backend_path, root_files), 
backend/frontend (language, framework, build_commands, dependencies), scripts, 
infrastructure (docker, kubernetes, terraform), environment (required_env, secret_env), 
artifacts, pipeline_requirements, and recommended_pipeline.

1. Treat every DETECTED FACT in this file (architecture.*, backend.*, frontend.*, 
   scripts.*, infrastructure.*, environment.*, artifacts.*) as verified ground truth. 
   Never override frontend_path/backend_path/build/start commands with template 
   defaults or with what the user config JSON assumes. If the analyser says the 
   frontend lives at "client/" and backend at "server/", every generated path in the 
   pipeline must use exactly those paths.

2. Do NOT treat "recommended_pipeline" as automatically correct. It is a SUGGESTION 
   generated from the same facts, and it can contain internal contradictions. Before 
   using anything from recommended_pipeline, cross-check it against the raw detected 
   facts elsewhere in the same file:
   - If recommended_pipeline proposes a Docker-based deploy strategy, but 
     infrastructure.docker.has_docker is false and no Dockerfile path exists 
     in architecture/root_files — discard that part of the recommendation. Either 
     select a deployment strategy that matches the ACTUAL infrastructure present, 
     or flag in Phase 4 that containerization is recommended but not yet implemented 
     in the repo, and fall back to the deployment_target given in the user config JSON.
   - If recommended_pipeline references a health endpoint but api_routes.health_route 
     is null, do not invent one — flag it as missing rather than fabricating a path.
   - If recommended_pipeline assumes tests exist but testing.unit/integration/e2e are 
     all false and testing.framework is null, do not generate a test stage that 
     pretends coverage exists — generate a no-op/skip-safe test stage and flag the gap.
   - Any other mismatch between recommended_pipeline and the raw detected fields 
     (backend, frontend, infrastructure, database, testing, monitoring) must be 
     resolved in favor of the raw detected fields, never the recommendation.

3. If the user's configuration JSON conflicts with repo_analysis.json on a STRUCTURAL 
   fact (paths, scripts, stack, package manager) — the analyser JSON wins, since it 
   reflects the actual repository. The user config still governs INTENT (which CI/CD 
   platform, which cloud provider, which notification channel, rollback policy) — 
   these are not something the analyser can determine and must come from the user.

4. If a field required for pipeline generation is null/empty/not detected in 
   repo_analysis.json (e.g. health_endpoint: null, ci_cd_path: null, 
   deployment.target: null), do not silently invent a value. Select the closest safe 
   template default, and record the gap explicitly for Phase 4's audit notes.

5. VERIFY BUILD OUTPUT MODE AND EXISTING CI/CD BEFORE ASSUMING A DEPLOYMENT MODEL.
   Before generating any deploy stage for a frontend framework with multiple output
   modes (e.g. Next.js output: 'export' vs default server mode; Nuxt static vs SSR;
   SvelteKit adapter-static vs adapter-node), inspect the actual framework config file
   (next.config.js, nuxt.config.ts, svelte.config.js) for the output/adapter mode.
   A server-oriented deploy stage (process manager restart, health check against a
   running port, SSH to a VM) must NEVER be generated for a project configured for
   static export — route it to static hosting instead (GitHub Pages, S3+CloudFront,
   Netlify, Vercel static, Cloudflare Pages).

   Additionally, before generating ANY new CI/CD pipeline, check 
   ci_cd.existing_workflows / ci_cd.parsed_workflows for a pipeline that already 
   performs deployment. If one exists and already deploys successfully (e.g. to 
   GitHub Pages, Vercel, Netlify via their native git integration), do not silently 
   replace it with a different deployment target. Surface it explicitly: state what 
   the existing workflow already does, and ask whether the user wants to keep it, 
   extend it, or intentionally replace it — do not assume replacement is wanted.

   Package manager detection must be based on which lockfile is actually present 
   (package-lock.json → npm, pnpm-lock.yaml → pnpm, yarn.lock → yarn, bun.lockb → bun) 
   or an explicit "packageManager" field in package.json — never assumed from a 
   template default or from a similar-looking prior project.

────────────────────────────────────────────

PHASE 0.5 — CROSS-REFERENCE PASS

Before looking at any templates, perform a deliberate, explicit pass against all data:
1. Server-Likelihood: Verify if backend paths actually contain server endpoints. Do not deploy static frontends as backends.
2. Build-Output Mode: Ensure export configs (like static export vs SSR) dictate the deployment model correctly.
3. Existing CI/CD Check: If parsed_workflows indicates working deployments exist, DO NOT blindly overwrite them without a warning in the Audit Notes.
4. Keyword Noise: Reject detection of Docker/K8s/Terraform if it was only found in random README paragraphs instead of config files.
5. Gate Enforcement: Confirm no tests or sweeps will use `|| true`.
6. Credential Usage: Ensure every generated credential has a downstream purpose.

────────────────────────────────────────────

TEMPLATE DATABASE

A file named "templates.json" is provided. This file is your template database.

It contains reusable pipeline components for:
- GitHub Actions • GitLab CI • Jenkins • Azure DevOps • Bitbucket Pipelines • CircleCI

It also contains reusable components for:
- Runtime setup • Build stages • Code Quality • Testing • Authentication • Deployment 
- Notifications • Rollback • Health Checks • Security • Artifact Publishing

Always use this database as the source of truth for HOW a stage is implemented.
Use Phase 0's validated analyser facts as the source of truth for WHAT the stage 
points to (paths, scripts, stack, dependencies).

Never invent a completely new stage if a matching template exists.
Only modify placeholders — and only with values validated in Phase 0 or explicitly 
given in the user config JSON.

────────────────────────────────────────────

PHASE 3 — PRE-GENERATION AUDIT (mandatory, before generating any code)

Before you begin generating the pipeline code, you must execute a strict pre-generation verification step and document the checklist results under a "PRE-GENERATION AUDIT" comment block at the very beginning of the pipeline code.

You must run and report the outcome of these audit validations:
1. Stack & Runtime Compatibility: Verify that the runtime target (e.g. Node.js, Python, etc.) requested in the user config matches the detected language in repo_analysis.json.
2. Build Commands & Path Integrity: Verify that all build/start command script names and directory paths actually exist and match repo_analysis.json.
3. Secret & Variable Alignment: Verify that every environment variable or credential required by the user configuration matches the repo_analysis.json environment.secret_env / secrets.required_secrets exactly.
4. Infrastructure Validation: If the deployment target is containerized (Docker, Kubernetes), verify that the repo actually contains a Dockerfile or infrastructure.docker.has_docker is True. If False, choose the closest safe VM/non-container deployment template or note that a container must be built first.

Output this pre-generation validation checklist in comments at the start of your generated pipeline.

────────────────────────────────────────────

PHASE 4 — PIPELINE GENERATION

STEP 1 — Skeleton Selection

Locate the correct skeleton wrapper according to CI/CD Platform:

GitHub Actions       → github_actions_skeleton
Azure DevOps         → azure_devops_skeleton
Jenkins              → jenkins_pipeline_skeleton
GitLab               → gitlab_pipeline_skeleton
CircleCI             → circleci_pipeline_skeleton
Bitbucket            → bitbucket_pipeline_skeleton

Never mix skeletons.

────────────────────────────────────────────

STEP 2 — Configuration Interpretation

Read the user's configuration JSON. Determine:
- Runtime • Framework • Programming Language • Package Manager • CI/CD Platform 
- Cloud Provider • Authentication Method • Deployment Target • Notification Provider 
- Rollback Strategy • Monitoring • Testing Framework • Secrets Required 
- Health Endpoint • Repository Information

Treat every configuration value as a strict requirement for INTENT/strategy. For 
STRUCTURAL facts (paths, scripts, stack), defer to repo_analysis.json per Phase 0.

────────────────────────────────────────────

STEP 3 — Capability Matrix

For every stage, determine if it is:
- Supported
- Unsupported
- Optional
- Required

Example Mapping:
Runtime: analyser backend.language "Node.js"     → node_runtime
Build: analyser frontend.build_command "vite build" → vite_build (path: analyser 
  architecture.frontend_path, NOT a template default)
Testing: analyser testing.framework               → if null, use a skip-safe stage, 
  not a fabricated one
Authentication: user config "Azure Workload Identity" → azure_oidc
Deployment: user config deployment_target, cross-checked against 
  infrastructure.docker/k8s/terraform flags → select only a strategy the repo can 
  actually support today
Notification: user config "Slack"                 → slack_notification
Rollback: user config rollback_strategy, cross-checked against 
  deployment.rollback_supported                    → automatic_vm_recovery or flagged 
  as unsupported

Every path/script referenced inside these components must come from repo_analysis.json, 
never a template's generic default.

────────────────────────────────────────────

STEP 4 — Merge

Merge all selected components into the selected skeleton. Replace every placeholder 
with either (a) a Phase 0-validated analyser fact, or (b) a value explicitly given in 
the user config JSON. Never leave a placeholder unresolved, and never fill a 
placeholder with a value that contradicts a raw detected fact in repo_analysis.json.

────────────────────────────────────────────

PHASE 4 — VERIFY (mandatory, before returning anything)

For every generated stage, you must produce and output a verification block in the file comments detailing:
- Stage: [Stage Name]
- Inputs: [Artifacts, secrets, or environment variables consumed by this stage]
- Outputs: [Artifacts or deliverables produced by this stage]
- Dependencies: [List of upstream stages that must finish before this stage runs]
- Validation: [Validation checks performed, verifying all paths and parameters against the repo analysis]
- Result: [PASSED or FAILED]

Additionally, before returning, confirm ALL of the following cross-cutting checks:
✓ TRIGGER CHECK: Triggers in generated workflow match user config (push: true/false, pull_request: true/false) exactly.
✓ ROLLBACK TARGET CHECK: Rollback job uses ONLY the same host/tool as the deploy job. No kubectl in Docker Host pipelines. No EC2_HOST in Kubernetes pipelines. No mixed target references.
✓ NO HARDCODED BOOLEANS: No condition of the form [ "true" = "true" ] or [ "false" != "true" ] exists. All conditionals reference actual variables.
✓ TIMEOUT/CONCURRENCY: Every job has timeout-minutes. A top-level concurrency: block is present.
✓ DOCKERFILE SECURITY: Any generated Dockerfile has HEALTHCHECK and USER directives.
✓ CLOUD PROVIDER VISIBLE: If cloud_provider is set, it appears in at least one pipeline step or comment.
✓ MANIFEST COMPLETENESS: If docker_configurations.dockerfile=true, the manifests array contains a Dockerfile entry.
✓ NO PLACEHOLDER LEAK: No {{ }} or __PLACEHOLDER__ tokens remain anywhere in the output.

Ensure every verification check resolves to PASSED before returning the pipeline.
Place these verification blocks in comments at the end of the file.

────────────────────────────────────────────

CODE QUALITY REQUIREMENTS

Generated code must be syntactically valid, executable, production-ready, free from 
placeholders, properly indented, platform-compliant, and secure. Never generate 
pseudo-code. CRITICALLY IMPORTANT: Never truncate scripts in the Rollback or Deploy stages. Always write out the complete, unabridged bash script exactly as shown in the templates.

────────────────────────────────────────────

OUTPUT FORMAT

{MANDATORY_PRE_GENERATION_VERIFICATION_GATES}

Return your final answer STRICTLY as a valid JSON object starting with { and ending with }. 
DO NOT output any conversational text, greetings, or markdown code blocks (e.g., ```json) outside the JSON object itself. 
The JSON object MUST have this exact structure:
{
  "chain_of_thought": "Your internal self-reflection step. Before generating ANY code, rigorously check if all 13 Architectural Rules are respected, that no GitHub Context variables are hallucinated, and no test frameworks (like PyTest) will crash the pipeline if tests are missing. Output your reasoning here.",
  "pipeline": "The generated pipeline configuration code as a string (YAML, Jenkinsfile, etc).",
  "implementation_plan": "A detailed markdown guide titled 'Prerequisites for this pipeline to succeed'. You MUST dynamically generate this based on the pipeline configuration and repo. It MUST include:\\n1. Missing Files (e.g. if a Dockerfile/docker-compose.yml must be generated or exists, specify where they need to be placed).\\n2. CI/CD Secrets (e.g. GitHub Secrets/GitLab Variables required like AWS_ROLE_ARN, DOCKER_USERNAME, etc.).\\n3. CI/CD Variables (Non-Secret variables like AWS_REGION).\\n4. Port Configuration (Clarifying the port exposed in the pipeline/Docker vs the local port).",
  "manifests": [
    {
      "path": "path/to/Dockerfile",
      "content": "file content here"
    }
  ]
}

Place your 'AUDIT NOTES' (as outlined in Phase 4) in the pipeline file as comments at the end of the file.
"""

    # Targeted Brain Retrieval: Extract matching skeleton & essential rules from app/data
    base_dir = os.path.dirname(__file__)
    data_dir = os.environ.get("PIPELINE_DATA_DIR", os.path.join(base_dir, "data"))
    brain_data_str = ""
    try:
        # 1. Load exact matching template from templates.json
        templates_file = os.path.join(data_dir, "templates.json")
        target_platform = spec.get("cicd_platform", "github_actions")
        target_lang = (request.analysis.get("backend", {}).get("language") or request.analysis.get("frontend", {}).get("language") or "").lower()
        
        relevant_templates = []
        if os.path.exists(templates_file):
            with open(templates_file, "r", encoding="utf-8") as f:
                all_templates = json.load(f)
                for item in all_templates:
                    c_type = item.get("component_type", "")
                    ident = item.get("identifier", "").lower()
                    # Include skeleton wrapper for this platform
                    if c_type == "skeleton_wrapper":
                        plat_template = item.get("templates", {}).get(target_platform)
                        if plat_template:
                            relevant_templates.append({"component_type": c_type, "identifier": item.get("identifier"), "template": plat_template})
                    # Include matching build stack for language/framework
                    elif c_type in ("build_stack", "code_quality", "testing", "cloud_auth", "deployment_target", "failure_handling", "alerting"):
                        if not target_lang or any(kw in ident for kw in [target_lang, "standard", "generic", "automatic"]):
                            plat_template = item.get("templates", {}).get(target_platform)
                            if plat_template:
                                relevant_templates.append({"component_type": c_type, "identifier": item.get("identifier"), "template": plat_template})

        brain_data_str += f"\n--- TARGETED SKELETON BLUEPRINTS (templates.json) ---\n{json.dumps(relevant_templates, indent=2)}\n"

        # 2. Load essential security and validation rules
        for rule_file in ["security_rules.json", "deployment_rules.json", "validation.json"]:
            rule_path = os.path.join(data_dir, rule_file)
            if os.path.exists(rule_path):
                with open(rule_path, "r", encoding="utf-8") as f:
                    brain_data_str += f"\n--- {rule_file} ---\n{f.read()}\n"
    except Exception as e:
        import logging
        logging.error(f"Failed to load targeted brain data: {e}")
        brain_data_str = "[]"

    user_message = f"{MANDATORY_PRE_GENERATION_VERIFICATION_GATES}\n\nUSER CONFIGURATION:\n{json.dumps(spec, indent=2)}\n\nANALYSER OUTPUT:\n{json.dumps(request.analysis, indent=2)}\n\nBRAIN DATABASE (Templates, Rules, Validations):\n{brain_data_str}"
    try:
        model_target = getattr(request, 'model', '~deepseek/deepseek-v4-flash-latest')
        raw_output = _call_llm(api_key, system_prompt, user_message, model_target)
        # Attempt to parse json from raw output to support manifests array as per Conversation edb07e81
        try:
            # If the LLM returned JSON with pipeline and manifests
            try:
                parsed = json.loads(raw_output)
            except json.JSONDecodeError:
                # Try aggressive regex extraction if Gemini adds conversational text

                json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_output, re.DOTALL | re.IGNORECASE)
                if json_match:
                    parsed = json.loads(json_match.group(1))
                else:
                    start_idx = raw_output.find('{')
                    end_idx = raw_output.rfind('}')
                    if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                        parsed = json.loads(raw_output[start_idx:end_idx+1])
                    else:
                        raise

            content = parsed.get("pipeline", parsed.get("content", raw_output))
            manifests = parsed.get("manifests", [])
            implementation_plan = parsed.get("implementation_plan", "")
            explanation = parsed.get("chain_of_thought", parsed.get("explanation", ""))
        except Exception:
            # Fallback if it just returned raw yaml
            content = raw_output
            manifests = []
            implementation_plan = ""
            explanation = ""

        if isinstance(content, str):
            content = content.replace("\\n", "\n")
            # Also clean markdown backticks if AI hallucinates them inside pipeline string
            content = re.sub(r"^```[a-zA-Z]*\n", "", content)
            content = re.sub(r"\n```$", "", content)
            content = content.strip()
            
        if isinstance(implementation_plan, str):
            implementation_plan = implementation_plan.replace("\\n", "\n")
            implementation_plan = implementation_plan.replace("\\t", "\t")
            
    except Exception as e:
        import logging
        logging.error(f"LLM generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline generation failed (LLM): {str(e)}")

    validation_errors = _validate_generated_output(
        spec.get("pipeline_tool", "github_actions"),
        expected_filename,
        content,
        spec,
        request.analysis,
        {} # empty rules for this fallback
    )
    warnings = _missing_requested_manifests(spec, manifests)

    return {
        "status": "VALID" if not validation_errors else "INVALID",
        "validation": {
            "passed": len(validation_errors) == 0,
            "errors": validation_errors,
            "warnings": warnings,
            "skipped_features": []
        },
        "filename": expected_filename,
        "content": content,
        "explanation": explanation if explanation else "Generated dynamically using AI reasoning.",
        "implementation_plan": implementation_plan,
        "manifests": manifests
    }


@app.post("/fix-pipeline")
def fix_pipeline(request: FixPipelineRequest):
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or api_key.lower() == "your_openrouter_api_key_here":
        raise HTTPException(status_code=500, detail="Missing OPENROUTER_API_KEY in environment/env file")

    system_prompt = """You are a Principal DevOps Engineer debugging a CI/CD pipeline.
The user ran the pipeline you previously generated, but encountered an error.
You must fix their pipeline code.

INPUT PROVIDED:
1. original_configuration (user's intent)
2. repository_analysis (ground truth of repo structure)
3. current_pipeline (the incorrect code)
4. error_message (the error the user experienced)

INSTRUCTIONS:
- Analyze the error and determine what needs to be changed in the current_pipeline.
- Provide a conversational response containing a brief explanation of the fix and a markdown code block of ONLY the specific portions/stages/lines of the pipeline that need to be replaced. Do not return the entire pipeline.
- Return your final answer STRICTLY as a valid JSON object. Do not include markdown formatting like ```json outside the JSON object.
- The JSON object must have this exact structure:
{
  "message": "Your conversational response containing the explanation and the markdown code snippet."
}
"""

    user_message = f"original_configuration:\n{json.dumps(request.spec, indent=2)}\n\nrepository_analysis:\n{json.dumps(request.analysis, indent=2)}\n\ncurrent_pipeline:\n{request.current_pipeline}\n\nerror_message:\n{request.error_message}"

    try:
        raw_output = _call_llm(api_key, system_prompt, user_message)
        try:
            parsed = json.loads(raw_output)
            content = parsed.get("message", raw_output)
        except json.JSONDecodeError:
            content = raw_output
            
    except Exception as e:
        import logging
        logging.error(f"LLM fix failed: {e}")
        raise HTTPException(status_code=500, detail=f"Pipeline fixing failed (LLM): {str(e)}")

    return {
        "status": "VALID",
        "message": content
    }


@app.post("/generate-dockerfile")
def generate_dockerfile(request: GenerateDockerRequest, current_user: str = Depends(get_current_user)):
    from dotenv import load_dotenv
    load_dotenv()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or api_key.lower() == "your_openrouter_api_key_here":
        raise HTTPException(status_code=500, detail="Missing OPENROUTER_API_KEY")

    system_prompt = """You are an Elite Enterprise Containerization Architect and DevSecOps Principal Engineer.
Your objective is to generate production-grade, security-hardened, and BuildKit-optimized Dockerfiles for the analyzed repository that outperform standard baseline outputs.

CRITICAL ENTERPRISE DOCKERFILE RULES:
1. COMPLETE MULTI-TIER ARCHITECTURE:
   - If both backend and frontend components exist, provide complete Dockerfiles for both tiers or clearly structure multi-stage builds. Never drop the frontend tier.
   - For static frontend (Vanilla JS/React/Vue), use `nginxinc/nginx-unprivileged:alpine`. Crucial Nginx rule: `add_header` is NOT inherited into child location blocks, so all security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy) MUST be explicitly defined in both the server and static asset location blocks.

2. ROBUST COPY ORDERING (The Immunity Pattern):
   - In the runtime stage, ALWAYS copy the application source tree FIRST: `COPY --chown=node:node backend/ ./`
   - THEN copy pristine dependencies from the build stage SECOND:
     `COPY --from=deps --chown=node:node /app/node_modules ./node_modules`
     `COPY --from=deps --chown=node:node /app/package.json ./package.json`
   - This ensures host node_modules or artifacts CANNOT clobber clean lockfile-exact installs.

3. SUPPLY-CHAIN & DEPENDENCY HARDENING:
   - In the deps stage: use `RUN --mount=type=cache,target=/root/.npm npm ci --omit=dev --no-audit --no-fund`
   - Add `--ignore-scripts` if no native C++ bindings (bcrypt, sharp, sqlite3) are detected in package.json.
   - Pin base images explicitly with digest or minor tags (e.g. `node:20-alpine`, `python:3.11-slim`).

4. ROOTLESS EXECUTION & RUNTIME INTEGRITY:
   - Base image must never run as root. Drop privileges early (`USER node` or dedicated `appuser`).
   - Use `tini` or `dumb-init` as PID 1 to forward SIGTERM/SIGINT signals gracefully.
   - Set `STOPSIGNAL SIGTERM`.
   - Add runtime protection flags (e.g. `CMD ["node", "--disable-proto=throw", "server.js"]`).

5. RELIABLE PROBES & HEALTHCHECKS:
   - Provide an explicit HTTP 200 healthcheck asserting that the real port and route are alive.

6. COMPANION .dockerignore RULES:
   - In your explanation or output, specify the exact .dockerignore entries (node_modules, .env, .git, *.log, dist).

OUTPUT FORMAT:
Your output MUST be STRICTLY a valid JSON object matching this schema:
{
  "dockerfile": "The raw, complete Dockerfile content here as a clean multi-line string",
  "explanation": "Technical breakdown of stages, caching strategy, security hardening, and .dockerignore requirements."
}
Do NOT include markdown blocks around the JSON. Do NOT return any text outside the JSON object.
"""

    user_message = f"{MANDATORY_PRE_GENERATION_VERIFICATION_GATES}\n\nrepository_analysis:\n{json.dumps(request.analysis, indent=2)}"

    try:
        # Select AI model from request, fallback to Grok 4.6
        model_target = getattr(request, 'model', 'x-ai/grok-4.6')
        raw_output = _call_llm(api_key, system_prompt, user_message, model_target)
        try:
            parsed = json.loads(raw_output)
            dockerfile_content = parsed.get("dockerfile", parsed.get("content", raw_output))
            explanation = parsed.get("explanation", "AI tailored Dockerfile for this repository stack.")
        except json.JSONDecodeError:
            dockerfile_content = raw_output
            explanation = "AI tailored Dockerfile for this repository stack."
            
        if isinstance(dockerfile_content, str):
            dockerfile_content = dockerfile_content.replace("\\n", "\n")
            dockerfile_content = re.sub(r"^```[a-zA-Z]*\n", "", dockerfile_content)
            dockerfile_content = re.sub(r"\n```$", "", dockerfile_content)
            dockerfile_content = dockerfile_content.strip()
            
    except Exception as e:
        import logging
        logging.error(f"LLM Dockerfile generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Dockerfile generation failed (LLM): {str(e)}")

    return {
        "status": "VALID",
        "filename": "Dockerfile",
        "content": dockerfile_content,
        "explanation": explanation
    }

def _fetch_github_repo_context(url: str) -> str:
    import requests
    match = re.search(r'github\.com/([^/]+)/([^/\s]+)', url)
    if not match:
        return ""
    owner, repo = match.groups()
    repo = repo.replace(".git", "")
    try:
        api_url = f"https://api.github.com/repos/{owner}/{repo}/contents"
        resp = requests.get(api_url, timeout=5)
        if resp.status_code == 200:
            contents = resp.json()
            files = [item['name'] for item in contents if item['type'] == 'file']
            dirs = [item['name'] for item in contents if item['type'] == 'dir']
            key_file_content = ""
            for target in ["package.json", "requirements.txt", "pom.xml", "Dockerfile", "go.mod"]:
                if target in files:
                    file_resp = requests.get(f"https://raw.githubusercontent.com/{owner}/{repo}/main/{target}", timeout=3)
                    if file_resp.status_code == 200:
                        key_file_content += f"\n\n--- {target} ---\n```\n{file_resp.text[:1500]}\n```"
            return f"\n\n[SYSTEM INJECTION: Automatic Repo Analyzer fetched metadata for {url}]\nFiles in root: {', '.join(files)}\nDirectories in root: {', '.join(dirs)}{key_file_content}"
    except Exception:
        pass
    return ""

@app.post("/api/chats/{chat_id}/messages")
def add_message_to_chat(chat_id: int, request_body: MessageCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    model_param = getattr(request_body, 'model', 'x-ai/grok-4.6')
    
    chat = db.query(Chat).filter(Chat.id == chat_id, Chat.user_id == current_user.id).first()
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
        
    user_msg = Message(chat_id=chat.id, role="user", content=request_body.content)
    db.add(user_msg)
    db.commit()
    
    # Auto-generate title for first user message
    if chat.title == "New Conversation":
        chat.title = request_body.content[:30] + ('...' if len(request_body.content) > 30 else '')
        db.commit()
    
    history_messages = db.query(Message).filter(Message.chat_id == chat.id).order_by(Message.created_at.asc()).all()
    from dotenv import load_dotenv
    import json
    import os
    load_dotenv()

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key or api_key.lower() == "your_openrouter_api_key_here":
        raise HTTPException(status_code=500, detail="Missing OPENROUTER_API_KEY in environment/env file")

    base_dir = os.path.dirname(__file__)
    data_dir = os.environ.get("PIPELINE_DATA_DIR", os.path.join(base_dir, "data"))
    brain_data_str = ""
    try:
        if not os.path.exists(data_dir):
            os.makedirs(data_dir)
        for filename in os.listdir(data_dir):
            if filename.endswith(".json"):
                file_path = os.path.join(data_dir, filename)
                with open(file_path, "r", encoding="utf-8") as f:
                    brain_data_str += f"\n--- {filename} ---\n{f.read()}\n"
    except Exception as e:
        import logging
        logging.error(f"Failed to load brain data: {e}")
        brain_data_str = "[]"

    import requests
    system_prompt = f"""You are PipelineGenie Chat
{MANDATORY_PRE_GENERATION_VERIFICATION_GATES}
, an expert DevOps and Infrastructure AI, and a strict CI/CD formatting engine.
CRITICAL INSTRUCTION: You MUST ONLY answer questions related to DevOps, CI/CD pipelines, Dockerfiles, Kubernetes, Helm Charts, and infrastructure issue resolution.
Code generations are strictly IN SCOPE.

When generating a CI/CD pipeline, you MUST strictly adhere to these HARD RULES:
1. Use ONLY the correct skeleton shape for the target platform (GitHub Actions, GitLab CI, Jenkins, Azure DevOps, CircleCI, Bitbucket Pipelines) - never invent schemas.
2. Every secret must be referenced via the platform's native secret syntax (e.g. ${{{{ secrets.X }}}}, $X). Never write literal secret values.
3. Preserve the exact order requested by the user. Do not add steps that were not requested.
4. Any step output consumed outside its own job MUST be explicitly promoted through the job-level outputs block.
5. Any sed/text-substitution into a config file must be followed immediately by a verification step.
6. A health check must resolve to a real, reachable target (not a bare schemeless path).
7. Ensure all commands strictly represent the framework (e.g. Node.js backend).
8. Ensure all credentials or login steps have an actual consumer logic immediately downstream in the deployment block.

IMPORTANT LEARNING RULE:
If the user points out an error in the pipeline or provides a correction/fix, you must acknowledge the lesson. 
To do this, IN ADDITION to your conversational response, include a markdown block formatted EXACTLY like this at the end of your response:
```json-learn
{{
  "issue": "Brief description of what went wrong or what the user corrected",
  "fix": "The specific code snippet, rule, or change that fixes it"
}}
```
The backend will automatically extract this block and add it to your permanent brain memory!

Here is your current BRAIN DATABASE (Templates, Rules, Validations, Lessons):
{brain_data_str}

OUTPUT & FORMATTING RULES:
1. Provide clear, professional, and conversational responses.
2. Whenever you output code or configuration files, use standard multi-line Markdown code blocks (e.g., ```yaml, ```dockerfile, ```json). Never truncate deployment scripts.
3. TABLE FORMATTING: When presenting comparisons, summaries, verdicts, or structured data in tables, you MUST format them as valid GitHub-Flavored Markdown tables with clear header rows and delimiter rows (e.g., | Area | Winner | Why | followed by | --- | --- | --- |). Always place each row on its own new line."""

    messages_payload = [{"role": "system", "content": system_prompt}]
    last_user_idx = -1
    for m in history_messages:
        msg = {"role": m.role, "content": m.content}
        if m.role == "assistant" and getattr(m, 'reasoning_details', None) is not None:
            msg['reasoning_details'] = m.reasoning_details
        messages_payload.append(msg)
        if m.role == "user":
            last_user_idx = len(messages_payload) - 1

    if last_user_idx != -1:
        last_content = messages_payload[last_user_idx]["content"]
        urls = re.findall(r'https?://github\.com/[^\s]+', last_content)
        for url in urls:
            context = _fetch_github_repo_context(url)
            if context:
                messages_payload[last_user_idx]["content"] += context

    model_target = model_param
    payload = {
        "model": model_target,
        "max_tokens": 16384,
        "messages": messages_payload,
    }
    if "kimi-k3" in model_target or "gemini" in model_target or "grok" in model_target or "deepseek" in model_target:
        payload["reasoning"] = {"enabled": True}

    payload["stream"] = True

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    
    from fastapi.responses import StreamingResponse

    def stream_generator():
        import logging
        try:
            resp = requests.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers=headers, json=payload, timeout=300, stream=True
            )
            resp.raise_for_status()
            
            raw_content = ""
            raw_reasoning = ""
            
            for line in resp.iter_lines():
                if line:
                    line_str = line.decode('utf-8')
                    if line_str.startswith("data: ") and line_str != "data: [DONE]":
                        try:
                            chunk_data = json.loads(line_str.replace("data: ", "", 1))
                            delta = chunk_data.get("choices", [{}])[0].get("delta", {})
                            
                            content_chunk = delta.get("content", "")
                            reasoning_chunk = delta.get("reasoning", "")
                            
                            if content_chunk:
                                raw_content += content_chunk
                            if reasoning_chunk:
                                raw_reasoning += reasoning_chunk
                            
                            yield f"{line_str}\n\n"
                        except Exception as parse_e:
                            pass
                            
            raw = raw_content.strip()
            if not raw and raw_reasoning:
                raw = raw_reasoning.strip()
            
            learn_match = re.search(r'```json-learn\s+(.*?)\s+```', raw, re.DOTALL | re.IGNORECASE)
            if learn_match:
                try:
                    lesson = json.loads(learn_match.group(1).strip())
                    lessons_file = os.path.join(data_dir, "user_lessons.json")
                    
                    existing_lessons = []
                    if os.path.exists(lessons_file):
                        try:
                            with open(lessons_file, "r") as lf:
                                existing_lessons = json.load(lf)
                                if not isinstance(existing_lessons, list):
                                    existing_lessons = []
                        except Exception:
                            pass
                            
                    existing_lessons.append(lesson)
                    with open(lessons_file, "w") as lf:
                        json.dump(existing_lessons, lf, indent=2)
                        
                    raw = re.sub(r'```json-learn\s+.*?\s+```', '', raw, flags=re.DOTALL | re.IGNORECASE)
                    raw += "\n\n_🧠 I have saved this correction to my permanent brain!_"
                except Exception as e:
                    logging.error(f"Failed to parse or save learning JSON: {e}")

            try:
                msg_db_session = next(get_db())
                r_details = [{"text": raw_reasoning}] if raw_reasoning else None
                ai_msg = Message(chat_id=chat.id, role="assistant", content=raw.strip(), reasoning_details=r_details)
                msg_db_session.add(ai_msg)
                msg_db_session.commit()
            except Exception as e:
                logging.error(f"Failed to save AI message: {e}")

        except Exception as e:
            logging.error(f"Chat failed: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(stream_generator(), media_type="text/event-stream")

