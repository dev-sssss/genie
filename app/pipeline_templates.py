"""
Canonical schema skeletons for every supported CI/CD platform.

Why this file exists:
The old prompt told the LLM to "produce valid YAML for the requested platform"
without ever showing it what that platform's YAML actually looks like. Left
alone, the model can drift into inventing its own schema (we saw this happen:
`apiVersion: v1 / kind: Pipeline` is not a real thing on any of the six
platforms below). This file removes that ambiguity — each platform gets a
literal skeleton plus formatting rules, injected into the system prompt
so the model is filling in a structure, not designing one.
"""

from typing import Dict


PLATFORM_FILES = {
    "GitHub Actions": ".github/workflows/deploy.yml",
    "GitLab CI": ".gitlab-ci.yml",
    "Jenkins": "Jenkinsfile",
    "Azure DevOps": "azure-pipelines.yml",
    "CircleCI": ".circleci/config.yml",
    "Bitbucket Pipelines": "bitbucket-pipelines.yml",
}

# Required top-level keys per platform — used both to build the prompt
# skeleton and to validate the LLM's output before it's returned to the user.
PLATFORM_REQUIRED_KEYS = {
    "GitHub Actions": ["name", "on", "jobs"],
    "GitLab CI": ["stages"],
    "Jenkins": None,  # Groovy, not YAML — validated by regex, see main.py
    "Azure DevOps": ["stages", "trigger"],
    "CircleCI": ["version", "jobs"],
    "Bitbucket Pipelines": ["pipelines"],
}

PLATFORM_SKELETONS: Dict[str, str] = {

    "GitHub Actions": """
name: <pipeline name>
on:
  push:
    branches: [<trigger branches from plan>]
  pull_request:
    branches: [<trigger branches from plan>]

jobs:
  <job-id-per-stage-in-plan>:
    runs-on: ubuntu-latest
    needs: [<upstream job ids, from stage.depends_on / ordering>]
    environment: <env name, only if stage.requires_approval is true>
    steps:
      - uses: actions/checkout@v4
      - uses: <setup action from plan.runtime.setup_action, e.g. actions/setup-node@v4>
        with:
          node-version: '<version>'
      - name: <human step name>
        run: <exact command from plan — never invent a command>
      # Secrets referenced as: ${{ secrets.SECRET_NAME }}
      # Never hardcode a secret value in `run:` or `env:`.
""",

    "GitLab CI": """
stages:
  - <one entry per stage.name in plan, in plan order>

variables:
  <only if plan defines global vars>

<job-name>:
  stage: <matching stage name>
  image: <runtime image from plan.runtime>
  script:
    - <exact command from plan>
  rules:
    - if: '$CI_COMMIT_BRANCH == "<branch from branch_environment_map>"'
  environment:
    name: <env name, only if stage.requires_approval is true>
  when: manual   # only if stage.requires_approval is true, else omit
# Secrets referenced as: $SECRET_NAME (CI/CD variable), never hardcoded.
""",

    "Jenkins": """
pipeline {
    agent any
    stages {
        stage('<stage.name>') {
            steps {
                sh '<exact command from plan>'
            }
        }
        // one `stage {}` block per stage in plan, in plan order
        // wrap any stage where requires_approval is true in:
        // input message: 'Deploy to <env>?'
    }
    post {
        success { <notification step from plan.notify.channels> }
        failure { <notification step from plan.notify.channels> }
    }
}
// Secrets via credentials(): environment { VAR = credentials('jenkins-cred-id') }
// Never hardcode a secret value.
""",

    "Azure DevOps": """
trigger:
  branches:
    include: [<trigger branches from plan>]

stages:
- stage: <stage.name from plan>
  jobs:
  - job: <job id>
    pool:
      vmImage: 'ubuntu-latest'
    steps:
    - script: <exact command from plan>
      displayName: '<human step name>'
    # Approval: use an Environment with checks, not a raw script gate
# Secrets referenced as: $(SECRET_NAME) via a variable group / Key Vault link.
""",

    "CircleCI": """
version: 2.1
jobs:
  <job-name-per-stage>:
    docker:
      - image: <runtime image from plan.runtime>
    steps:
      - checkout
      - run: <exact command from plan>
workflows:
  main:
    jobs:
      - <job-name>:
          requires: [<upstream job names>]
          filters:
            branches:
              only: [<branch from plan>]
# Secrets referenced as: $SECRET_NAME (CircleCI Contexts / project env vars).
""",

    "Bitbucket Pipelines": """
pipelines:
  branches:
    '<branch from plan>':
      - step:
          name: <stage.name from plan>
          script:
            - <exact command from plan>
      # steps requiring approval:
      - step:
          name: <deploy stage name>
          deployment: <environment name>
          trigger: manual
          script:
            - <exact command from plan>
# Secrets referenced as: $SECRET_NAME (repository/deployment variables).
""",
}


FORMATTING_RULES = """
Hard rules — violating any of these makes the output invalid:
1. Use ONLY the skeleton shape shown for the target platform. Do not invent
   top-level keys, a different schema, or a "generic" pipeline format.
2. Use ONLY the commands present in the supplied plan's stages. Never
   substitute, "improve", or guess a different command than what a stage
   specifies (e.g. do not swap `yarn build` for `npm run build`).
3. Every secret must be referenced via the platform's native secret syntax
   shown in the skeleton ($`{{ secrets.X }}` for GH Actions, $X for GitLab/shell,
   credentials() for Jenkins, $(X) for Azure). Never write a literal secret value.
4. Preserve the stage order given in the plan. Respect `depends_on` /
   `requires` relationships as job dependencies.
5. Any stage with `requires_approval: true` must render as a manual
   gate/approval using the platform's native mechanism shown above — not a
   sleep, a comment, or a skipped step.
6. Do not add steps that aren't in the plan. No bonus Docker build if the
   plan has no docker stage; no bonus deploy step for an environment not
   listed in the plan; no duplicate deploy stage alongside a real one for
   the same environment.
7. Output strictly the JSON envelope requested in the system prompt — no
   markdown fences, no commentary outside the JSON.
8. Any command containing a token like __SECRET_NAME__ is a placeholder
   for a secret/variable reference, not literal text. Convert it to the
   platform's native secret syntax for NAME — never delete it, never
   replace it with a bare literal path or value. If unsure how to render
   it, keep the token as-is rather than silently dropping it.
9. Any step output consumed outside its own job MUST be wired through
   both levels explicitly:
   a) the producing step needs id: <name> and writes echo "KEY=value" >> $GITHUB_OUTPUT
   b) the producing job needs a job-level outputs: block mapping KEY: ${{ steps.<name>.outputs.KEY }}
   c) only then may a downstream job reference needs.<job>.outputs.KEY.
10. Never gate a job's if: condition on a value that was only ever set as
    a step output and not promoted per rule 9. If in doubt, use a file or
    artifact on disk as the cross-job signal instead of job outputs.
11. Any sed/text-substitution into a config file must be followed
    immediately by a verification step (e.g. grep -q "<expected>" file ||
    { echo "substitution failed"; exit 1; }). Never assume a substitution
    silently succeeded.
12. Any secret used to authenticate a remote connection (SSH key, etc.)
    must be materialized into a real file/step before it's referenced by
    path — never reference a variable like $SSH_KEY_PATH unless a prior
    step actually wrote that file.
13. A health check must resolve to a real, reachable target — a scheme-
    less bare path like "/health" with no host is not a valid check.
    Health checks must only be considered "passing" based on an actual
    response from the running service, not merely that a start command
    exited 0.
14. If the plan specifies a non-empty working_directory, EVERY step that
    installs, builds, tests, or lints must be scoped to it — via
    defaults.run.working-directory at the job or workflow level (GitHub
    Actions), a working_directory: key (GitLab CI), dir(...) (Jenkins), or
    the equivalent for the target platform. A Dockerfile's COPY/build
    context must be adjusted the same way. Never assume project files sit at
    repository root without confirmation.
15. Any claim in a pre-generation audit about the repo's current state
    must be grounded in a specific file the analyzer actually found — name
    that file. If multiple config files suggest different deploy targets,
    flag the conflict explicitly.
16. Every credential, role, or auth mechanism configured in the plan must
    be consumed by at least one subsequent step. If a cloud identity is
    assumed (OIDC, IAM role, service account) but no downstream step
    actually uses those credentials, do not include it.
"""


MANIFEST_SKELETONS = {
    "dockerfile": """
Dockerfile (path: "Dockerfile"):
- Multi-stage: a `build` stage that installs deps and builds, a slim final
  stage (e.g. `-slim`/`-alpine` base matching the detected language) that
  only copies build output + runtime deps.
- Must include: a non-root `USER` directive, an `EXPOSE <port>` matching
  the detected app port, and a `HEALTHCHECK` hitting the detected health
  endpoint if one exists.
""",
    "docker_compose": """
docker-compose.yml (path: "docker-compose.yml"):
- One service per component (app, plus database/cache only if detected in
  analysis.database). Use the image built by the pipeline via a build arg
  or `image: ${IMAGE_NAME}:${IMAGE_TAG}`, not a hardcoded tag.
- Include healthcheck: and restart: unless-stopped for every service.
""",
    "terraform": """
Terraform (path: "infra/main.tf", plus "infra/variables.tf"):
- Only emit resources for what analysis.cloud.provider / deployment_target
  actually indicate (e.g. don't emit an EKS cluster resource for an EC2 SSH
  target). Use variables for anything environment-specific (region,
  instance size, image tag) — never hardcode account IDs or ARNs.
""",
    "kubernetes": """
Kubernetes manifests (path: "k8s/deployment.yaml", "k8s/service.yaml", and
"k8s/ingress.yaml" only if kubernetes.ingress is true):
- Deployment must set resource requests/limits, a readiness and liveness
  probe against the detected health endpoint, and `replicas` from the
  plan's deploy stage if present.
- Service `type` should match kubernetes.service_type from the plan if set,
  otherwise default to ClusterIP.
""",
    "helm_charts": """
Helm chart (path: "charts/Chart.yaml", "charts/values.yaml",
"charts/templates/deployment.yaml", "charts/templates/service.yaml"):
- values.yaml must expose image.repository/image.tag, replicaCount, and
  resources as overridable values — never hardcode them in the templates.
""",
}


def get_manifest_prompt_block(spec: dict) -> str:
    """
    Builds the "also generate these supporting files" section of the prompt,
    based on which wizard checkboxes the user actually enabled. Without this,
    the LLM only ever renders the pipeline file itself and silently drops
    Dockerfile/Terraform/Helm/K8s manifest requests even when the user asked
    for them in the wizard.
    """
    docker_cfg = spec.get("docker_configurations", {}) or {}
    k8s_cfg = spec.get("kubernetes", {}) or {}
    infra_cfg = spec.get("infrastructure", {}) or {}
    gen_cfg = spec.get("generate_manifests", {}) or {}

    wanted = []
    if docker_cfg.get("generate_dockerfile") or gen_cfg.get("dockerfile"):
        wanted.append("dockerfile")
    if docker_cfg.get("generate_compose") or gen_cfg.get("docker_compose"):
        wanted.append("docker_compose")
    if infra_cfg.get("terraform") or gen_cfg.get("terraform"):
        wanted.append("terraform")
    if k8s_cfg.get("generate_manifests") or gen_cfg.get("kubernetes"):
        wanted.append("kubernetes")
    if k8s_cfg.get("generate_helm") or gen_cfg.get("helm_charts"):
        wanted.append("helm_charts")

    if not wanted:
        return ""

    skeletons = "\n".join(MANIFEST_SKELETONS[w] for w in wanted)
    return f"""
In addition to the pipeline file, the user has requested these supporting
files. Populate EACH of them as a separate entry in `generated_files`
(each entry: {{"path": "<file path>", "content": "<file content>"}}) —
do not fold them into the pipeline file's `content`.
{skeletons}
"""


def get_platform_prompt_block(platform: str) -> str:
    """Returns the skeleton + rules text to inject into the system prompt."""
    skeleton = PLATFORM_SKELETONS.get(platform)
    if not skeleton:
        # Unknown/unsupported platform — fail loudly rather than let the
        # model improvise a platform we have no skeleton for.
        raise ValueError(f"No schema template registered for platform: {platform}")
    return f"""
Target platform: {platform}
Output file: {PLATFORM_FILES.get(platform, 'pipeline.yml')}

Required structural skeleton (fill placeholders, do not restructure):
{skeleton}

{FORMATTING_RULES}

Self-check before returning:
- Does every command match the plan exactly, with nothing substituted?
- Is every __SECRET_ token converted to native secret syntax, not deleted?
- Does every needs.<job>.outputs.<key> reference correspond to a job that
  actually declares that key in its own outputs: block?
- Is there exactly one deploy stage per environment — no dead duplicates?
- Does every health check target a real host, not a bare path?
- Have you added zero steps beyond what the plan specifies?
If any answer is no, fix it before returning the JSON.
"""
